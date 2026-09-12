# R9 — per-stage latency and per-stage memory

*Measured 2026-09-11 overnight, on `main` at `9b40ff2`. Pure measurement — no
code was modified to produce any number here.*

Machine: Intel64 Family 6 Model 186 (16 logical CPUs, 10 torch threads),
RTX 4060 Laptop GPU **present but unused**, numpy 2.4.4, Python 3.13.9, Windows.
RAM 16.9 GB, ~2.5 GB free throughout (this machine's normal state all week).

---

## ⚑ Read this before quoting anything below

**1. "VRAM" is not measurable on this pipeline and the number does not exist.**
`cupy` is not installed (`ModuleNotFoundError`), and `torch` is `2.13.0+cpu`
with `torch.cuda.is_available() == False`. `src/gpu/allocators.py` has an
optional cupy path, but nothing on the measured path uses it — the grid is
numpy on the host. The GPU in the machine banner is detected hardware, **not a
device the pipeline allocates on.** What is reported below is **host** memory
per frame. Any table headed "VRAM" would be fabricated.

**2. The script's own warning, reproduced because it is the point:**

> MEASURED is a LOWER BOUND on frame latency, not the frame total. Six stages
> above are unmeasured; the front end is the whole of perception. The honest
> sentence is "the mapping back end costs 52.5 ms at p99", never "we run at
> 19 FPS".

**3. `--alloc` is silently ignored when `--seq` is given.** `--seq` routes to
`print_real_table(t)` (line 386), which takes no `alloc` argument; `--alloc`
only reaches `print_table(t, alloc, frame)` (line 421) on the synthetic path.
So latency-on-real-data and memory-per-stage **cannot come from one run**, and
this report is two runs. No warning is printed.

---

## A. Per-stage latency — REAL DATA, sequence 08, 200 frames

`python scripts/timing_table.py --seq 08 --frames 200`, schedule 5/10/20/40,
910,000 slots.

| stage | owner | p50 ms | p99 ms | max ms | share | ×10 Hz |
|---|---|---|---|---|---|---|
| load | JP | 1.29 | 1.78 | 1.91 | 1% | 56.2× |
| transform | JP | 2.92 | 22.81 | 24.76 | 3% | 4.4× |
| **range_image** | JP | **25.03** | **33.17** | 33.92 | **23%** | 3.0× |
| semantics | JP | 0.49 | 1.38 | 2.34 | 0% | 72.3× |
| motion | JP | 0.08 | 0.19 | 0.20 | 0% | 518.4× |
| **ground** | JP | **21.09** | **26.31** | 31.59 | **20%** | 3.8× |
| reflectivity | JP | 4.15 | 5.23 | 6.01 | 4% | 19.1× |
| bin | Aakash | 7.58 | 10.31 | 11.88 | 7% | 9.7× |
| scatter | Shrestha | 7.63 | 9.39 | 9.63 | 7% | 10.6× |
| fuse | Aakash | 4.04 | 5.86 | 5.95 | 4% | 17.1× |
| **cleanup** | Shrestha | **28.77** | **38.26** | 46.20 | **27%** | 2.6× |
| shift | Shrestha | 1.60 | 4.91 | 5.03 | 2% | 20.4× |
| **FRAME** | | **106.74** | **132.22** | 135.02 | 100% | **0.8×** |

**9.4 FPS p50, 7.6 FPS p99 — the script prints `MISSES 10 Hz at p99`.**

### Three stages are 70% of the frame

`cleanup` (27%), `range_image` (23%) and `ground` (20%). Everything else
together is 30%. Any latency work that is not aimed at those three is aimed at
the wrong place.

### `split_merge` and `pyramid` do not appear, for two different reasons

- **`split_merge`** has no per-frame batch entry point at all — the script says
  so explicitly: *"driven per cell by the refinement pool"*. It cannot be timed
  as a stage without an API that does not exist. **Not a measurement gap I can
  close; it is a design fact.**
- **`pyramid`** is in `timing.STAGES` and is timed on the **synthetic** path
  (§C, 3.06 ms p50) but is **absent from the real-data table**. Worth a look —
  either `run_real` does not drive it, or it is not instrumented there.

---

## B. ⚑ The 10 Hz claim does not reproduce, under any configuration I can run

`docs/handover-2026-09-02.md:23` lists, under **"Measured on real data and
holding"**:

> | latency | frame p50 **80.78 ms**, p99 **97.72** — meets 10 Hz | `timing_table.py --seq 08` |

Same script, same sequence, tonight:

| configuration | p50 ms | p99 ms | verdict |
|---|---|---|---|
| cold page cache, Patchwork++ | 152.27 | 187.68 | MISSES 10 Hz |
| warm page cache, Patchwork++ | **106.74** | **132.22** | MISSES 10 Hz |
| warm cache, `--no-patchworkpp` | **87.95** | **106.20** | MISSES 10 Hz |
| *handover claim* | *80.78* | *97.72* | *"meets"* |

**Two things are established, and one is not.**

*Established.* The cold/warm gap is entirely `load` (25.23 → 1.29 ms p50) — the
OS page cache, not the pipeline. And the Patchwork++ gap is entirely `ground`
(21.09 → 0.42 ms p50).

> **[!] WITHDRAWN 2026-09-12 — the inference that followed from this was wrong.**
> This paragraph originally continued: *"the logged figure is consistent with
> having been measured with `--no-patchworkpp`"*, on the arithmetic that
> 87.95/106.20 is close to 80.78/97.72. **That is not what happened.**
>
> - Shrestha's own run has `ground` at **12.41 ms** (`docs/research-log.md`,
>   4 Sep), which is the geometric segmenter, not the 0.42 ms fallback.
>   **Patchwork++ was active.**
> - The handover figure reproduces to **1.1%** as
>   `timing_table.py --cells 910000` — the *synthetic* path at full candidate
>   occupancy — with no fallback involved at all.
>
> Numeric proximity between two figures was treated as evidence they were the
> same measurement. It was not; they are different quantities that happen to
> land near each other. Full reconstruction in
> `reports/latency-gap-investigation.md`.

*Not established (at the time).* I cannot reproduce 80.78/97.72 exactly under
any flag combination, and I cannot rule out that the original run was on a
quieter machine or an earlier code state — `main` has taken PRs #31–#37 since, and this
machine has ~2.5 GB free RAM. **What I can say is narrower and still material:
in every configuration measurable tonight, p99 exceeds the 100 ms budget.**

> **Update 2026-09-12.** The figure *does* reproduce, to 1.1%, as
> `timing_table.py --cells 910000` — the synthetic path at full candidate
> occupancy, not a real seq-08 frame. Neither a quieter machine nor an earlier
> code state was needed to explain it: `timing_table.py` is unchanged since the
> handover commit apart from a 2-character unicode fix, and
> `max_candidate_cells` was already `null` then. The p99 sentence above still
> stands and has since been reproduced across every window of a 221-frame run
> (115–147 ms). See `reports/latency-gap-investigation.md`.

**Not edited.** Per tonight's rules this is logged, not fixed. It contradicts a
claim in the handover's *proven* table and belongs in a conversation.

---

## C. Per-stage memory — SYNTHETIC path (the only one that reports it)

`python scripts/timing_table.py --frames 200 --alloc`. Back end only; the five
JP front-end stages need SemanticKITTI and are excluded by this path.

| stage | owner | p50 ms | p99 ms | max ms | ×10 Hz | **MB/frame** |
|---|---|---|---|---|---|---|
| bin | Aakash | 12.23 | 14.31 | 18.65 | 7.0× | **~0** |
| scatter | Shrestha | 6.02 | 7.83 | 10.95 | 12.8× | **0.55** |
| fuse | Aakash | 7.60 | 9.60 | 10.82 | 10.4× | **~0** |
| cleanup | Shrestha | 10.52 | 12.48 | 15.02 | 8.0× | **0.07** |
| pyramid | Shrestha | 3.06 | 4.17 | 17.40 | 24.0× | **0.05** |
| shift | Shrestha | 2.31 | 5.93 | 6.26 | 16.9× | **0.29** |
| **MEASURED (back end)** | | **42.15** | **52.46** | 60.93 | 1.9× | **0.96** |

**0.96 MB/frame total**, against CLAUDE.md's hard invariant *"No allocation
inside the frame loop"*. The invariant is not literally satisfied — it is
satisfied to within ~1 MB of per-call bookkeeping, which matches what
`research-log` recorded when `bin_points` landed (8.15 → 1.31 MB/frame). The
largest single contributor is `scatter` at 0.55 MB.

Cross-check: the synthetic back end (42.15 ms p50) and the real back end
(`bin+scatter+fuse+cleanup+shift` = 7.58+7.63+4.04+28.77+1.60 ≈ **49.6 ms p50**)
are in the same range. The gap is mostly `cleanup`, which does more work on real
geometry than on the synthetic sweep.

---

## D. Bug found while running this — NOT fixed

`scripts/timing_table.py --alloc` **prints its table and then crashes**:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2691'
  timing_table.py:459 -> cp1252
```

The `⚑` in the closing warning cannot be encoded by the Windows console
codepage. The table is printed first, so the data is usable interactively, but
the script exits non-zero and **cannot be used in a pipeline or a Makefile
target on Windows**. Same class of defect I hit in my own code earlier and
resolved by using an ASCII marker.

A one-character fix exists but this modifies a tracked file, so per tonight's
rules it is **not applied** — see `pending-review/timing-table-unicode-crash.diff`.

---

## Reproduce

```bash
# A — real per-stage latency (run twice; the first is cold-cache)
VRGRID_DATA_ROOT=C:/KITTI/dataset python scripts/timing_table.py --seq 08 --frames 200

# B — the no-Patchwork++ comparison
VRGRID_DATA_ROOT=C:/KITTI/dataset python scripts/timing_table.py --seq 08 --frames 200 --no-patchworkpp

# C — per-stage memory (synthetic; --alloc is ignored with --seq)
python scripts/timing_table.py --frames 200 --alloc      # exits 1 on Windows, see D
```
