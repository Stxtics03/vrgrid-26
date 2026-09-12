# The port plan — getting vrgrid onto the device

*Shrestha, Days 3–8. The technical decision record for how the mapping pipeline
moves to GPU, and what must not break when it does.*

---

## 1. The three routes

| | What it is | Cost | Determinism | Verdict |
|---|---|---|---|---|
| **cupy** | swap arrays through `array_module()`, keep the numpy code | 1–2 days | free for int32 | **start here** |
| **`cupy.RawKernel`** | hand-written `.cu` invoked from Python | 1–2 weeks | ours to preserve | **only where cupy loses** |
| **numba.cuda** | JIT'd Python kernels | ~1 week | ours to preserve | **no** — third dependency, JIT warmup pollutes p99 |

**The plan is cupy first, measured, then RawKernel for the one or two kernels
where cupy's generic implementation is the bottleneck.**

The argument is not laziness. Writing `.cu` first means choosing an
implementation before knowing which kernel needs it, and the whole reason
`array_module()` exists is so that this decision could be made on evidence. Take
the seam, measure, then spend the week where the measurement points.

⚠️ **cupy is not automatically faster.** For small arrays, kernel launch overhead
(~5–10 µs) dominates. Our grid is 745,000 cells and a frame is ~120,000 returns —
comfortably large enough for the scatter and the cleanup, marginal for the
toroidal shift at ~1,000 cells. **Expect some stages to get slower.** That is a
result to publish, not a failure to hide.

---

## 2. The determinism argument — the core of this cycle

**This is the most valuable original systems claim our pair will have. Get it
right and write it up properly.**

### Why float on GPU destroys reproducibility

A GPU scatter runs thousands of threads concurrently. When several land on the
same output cell, the hardware serialises them through `atomicAdd` — but **in
whatever order the scheduler happens to produce**, which varies run to run with
occupancy, clock, and other work on the card.

IEEE-754 addition is not associative:

```
(a + b) + c  ≠  a + (b + c)      in general, for float32
```

So a float accumulator gives a different map every run. Bit-level diffs against a
reference become impossible, `make test-determinism` cannot exist, and **you
cannot bisect a bug whose location moves between runs.** That is the real cost —
not accuracy, debuggability.

### Why our design escapes it

Heights are quantised to 1 cm and accumulate as **int32 fixed-point**.

**Integer addition is exact, associative and commutative.** There is no rounding,
so order genuinely does not matter:

```
(a + b) + c  ==  a + (b + c)      always, for int32, absent overflow
```

`atomicAdd(int*, int)` on CUDA is a hardware instruction with the same
guarantee. So `cupyx.scatter_add` on an int32 target is **bit-identical
regardless of how the scheduler interleaves blocks**, and the determinism test
should pass on device with no change to the reduction logic.

**The Day-0 decision to use fixed-point — made for CPU reasons — is exactly what
makes a deterministic GPU port possible.** Most projects trade reproducibility
for device speed. We do not, and we can show why.

### The one thing to watch: overflow

int32 saturating is a real failure and it is silent. Bound it:

```
max_height_cm × max_returns_per_cell  <  2³¹
```

At ±800 cm (the 8 m band) and int32, a cell would need >2.6 million returns to
overflow. A frame is ~120,000 returns *total*. **Safe by four orders of
magnitude**, but assert it in the port rather than reasoning about it once.

---

## 3. ⚠️ The float audit — do this before writing any port code

The determinism guarantee holds **only where the accumulator is integer**.
Anywhere float reduction survives, the GPU reintroduces nondeterminism.

**Grep and classify every reduction in `src/gpu/` and `src/grid/fusion.py`:**

| Site | Accumulator | Safe on device? |
|---|---|---|
| height scatter | int32 | ✅ order-independent |
| weight / count accumulation | int32 | ✅ |
| Kalman variance update | **float** | ⚠️ audit — is it a reduction or elementwise? |
| law-of-total-variance merge | **float** | ⚠️ audit |
| `occupancy_state` | int/bool | ✅ |
| ceiling / ground layers | int16 cm | ✅ |

**The rule:** an *elementwise* float op is deterministic (each output depends on
one input, no ordering). A float *reduction* over a variable number of
contributors is not.

So the question for each float site is: **does this sum over a set whose order
the GPU controls?** If yes, one of:

- **(a)** Move it to fixed-point too. Variance in cm² fits int32 comfortably.
- **(b)** Keep it CPU-side if it is cheap and off the hot path.
- **(c)** Sort first, reduce in a fixed order — the `scatter_sorted` trick,
  already the default path on CPU for exactly this reason.

**Option (c) is likely the answer for most of them**, because we already have a
sorted path and it already exists to make order deterministic.

⚠️ This audit is a half-day and it is the difference between "the determinism
test passes on device" and "the determinism test passes on device except
intermittently, on Tuesdays." Do it before Day 3, not after.

---

## 4. Port order

Ordered by (win × ease). Stage timings from `timing_table.py`, 200 frames seq 08.

| # | Stage | p50 | Why / risk |
|---|---|---|---|
| **1** | `bin_points` | 6.84 ms | **Start here.** Pure elementwise integer division and clipping. No atomics, no reductions, no ordering. If cupy cannot win this one, stop and reconsider the whole port. |
| **2** | `scatter_sorted` | 7.06 ms | The heart. `cupy.argsort` + `cupyx.scatter_add` on int32. Determinism test gates it. Compare against `scatter_atomic` — on device the ranking may **invert** vs CPU, since GPUs handle contention far better than a CPU cache does. That inversion is a publishable finding. |
| **3** | `visibility_cleanup` | **26.22 ms** | **The prize.** 29% of the frame, and embarrassingly parallel — every cell is an independent range-image gather with no cross-cell dependency. If anything justifies the port, this is it. |
| **4** | `fuse` | 4.13 ms | Kalman update. Mostly elementwise → easy, **but it is the main float site.** Gated on §3. |
| **5** | `occupancy_state` | — | Elementwise, already zero-allocation. Trivial. |
| **6** | `shift` | 2.07 ms | Toroidal, O(perimeter), ~1,000 cells. **Likely slower on device** — launch overhead exceeds the work. Expect to leave it on CPU and say so. |

**Not ours, but note it:** `range_image` at 24.45 ms is the second-largest stage
and lives in `src/perception/` (JP's). Cleanup + range_image are **50 of the
89 ms**. Flag it to JP — porting only our half leaves the bigger half of the p99
untouched.

### Realistic expectation

If cleanup goes 26 → 5 ms and scatter 7 → 2, that is **26 ms off an 89 ms frame**,
putting p50 near 63 ms and p99 comfortably inside budget. That would close the
0.43 ms miss with room to spare — the honest headline of the cycle.

**Do not promise this before measuring it.** Publish the delta you get.

---

## 5. VRAM attribution — R9b

The review asks for allocation shown *isolated from everything else on the card*.
Their runtime reports 69 MB against a 900 MB cap. Ours must do better, because
our headline is a **hard bound**, not an observed figure.

```python
mempool = cupy.get_default_memory_pool()
mempool.used_bytes()      # what our arrays actually hold
mempool.total_bytes()     # what cupy reserved from the driver

torch.cuda.max_memory_allocated()    # FRNet's peak, separately
```

Plus `nvidia-smi --query-gpu=memory.used --format=csv` for the whole-card total,
so the difference between our pool and the card is visible and attributed.

⚠️ **cupy's pool caches.** `used_bytes()` is what we hold; `total_bytes()` is what
cupy has taken from the driver and not returned. For an honest bound claim,
report both, or call `mempool.free_all_blocks()` before measuring.

**The table R9b produces:**

| Component | Claimed | Device-resident | Measured how |
|---|---|---|---|
| Map arrays | 8.94 MB | | `mempool.used_bytes()` after allocate |
| Working buffers | 20.12 MB | | delta |
| **Our total** | **29.06 MB** | | |
| FRNet (if in loop) | — | | `torch.cuda.max_memory_allocated()` |
| Whole card | — | | `nvidia-smi` |

**Same page-touch discipline as CPU.** A baseline that never faults its pages is
not a baseline — `np.zeros(2.56e9)` moves RSS by 0.0 MB because the pages are
copy-on-write zeros. On device, `cupy.zeros` *does* commit, so the numbers are
more honest by default. Say so; it is a point in our favour.

---

## 6. The contention question — Day 6

**The only genuinely open technical question in this lane**, and the roadmap is
right to call it "measured, not assumed."

If R2 lands and FRNet runs in-loop, one T4 carries: our ~29 MB of arrays, FRNet's
weights and activations, and both sets of kernels competing for SMs.

Three things to measure, not reason about:

1. **Does it fit?** 16 GB against ~29 MB + FRNet at batch 1. Almost certainly
   yes. Confirm anyway.
2. **What does contention cost?** Run grid alone, FRNet alone, both — three
   timing tables. The interesting number is whether combined > sum of parts.
3. **Does the p99 survive?** Contention hits tail latency hardest, which is
   exactly the metric we already miss by 0.43 ms.

⚠️ If the answer is "it doesn't fit the budget," **that is a legitimate result**
and it directly supports the existing design decision to keep FRNet out of the
pipeline. Do not treat a bad number here as a failure — it is evidence for a
choice already made.

---

## 7. Benchmarking discipline

Numbers taken sloppily on a shared cloud GPU are worse than no numbers.

- **Warm up.** First kernel launch includes JIT and context setup. Discard the
  first 10 iterations, always.
- **Synchronise.** `cupy.cuda.Stream.null.synchronize()` before stopping the
  timer. CUDA calls are async; without this you are timing the launch, not the
  kernel.
- **Report p50 and p99, never the mean.** Existing house convention, and the
  reason is in `src/gpu/timing.py`.
- **Same frames, same order, both machines.** 200 frames of seq 08.
- **Log the GPU clock.** T4s throttle. `nvidia-smi --query-gpu=clocks.sm`
  alongside the timing, or an afternoon run will silently disagree with a
  morning one.
- **Never compare a device number to a laptop number as if it were the same
  experiment.** Publish two columns.

---

## 8. What would make this cycle a failure

Worth naming so we can steer away from it:

- **Writing `.cu` on Day 3 without measuring cupy first.** A week spent on a
  kernel that cupy already handles well.
- **Skipping the float audit** and shipping a determinism test that passes
  intermittently. Worse than no test — it makes the CI gate a liar.
- **Porting `shift` because it is easy**, discovering it is slower, and not
  publishing that.
- **Letting the deck's CUDA claim stay up while the port is half-done.** Either
  the code matches the claim or the claim comes down. There is no third option
  before a panel.
- **Measuring VRAM before there is anything on the device to measure.** R9b is
  Day 6, not Day 1.

---

## 9. Definition of done

- [ ] Float audit complete, every reduction classified
- [ ] `bin_points`, `scatter`, `visibility_cleanup` on device
- [ ] `make test-determinism` green **on device**
- [ ] int32 overflow bound asserted in code, not just reasoned
- [ ] Per-stage table, two columns: CPU laptop / T4
- [ ] VRAM attribution table, four rows, pool and card both shown
- [ ] Contention measured three ways: grid alone, FRNet alone, both
- [ ] Every number in the research log with GPU, driver, CUDA and clock recorded
- [ ] Any stage that got *slower* published alongside the ones that got faster
