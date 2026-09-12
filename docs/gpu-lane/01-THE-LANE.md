# The lane — Shrestha + Pratyushi, 10 days

*Read `00-WHERE-WE-ARE.md` first. This file is what our pair owns, how we split
it, and six things in the roadmap that need resolving **before Day 1 starts.***

---

## 1. The split

**Shrestha — everything that is built.** Kernels, the cupy port, the AWS
instance, the measurement harness, the CI test, all profiling.

**Pratyushi — everything that is written or read.** The research shelf
(`04-RESEARCH-SHELF.md`), research-log entries for every measurement, the README
and report sections that quote our numbers, prior-art for the port, and the
reconciliation table in §3 below.

**The one hard rule:** every number Shrestha measures gets a research-log entry
from Pratyushi the same day, in the existing append-only format. The competitor
review's §2 closing note is the reason — *their grid engine and their detector
were evaluated by two different people to two different standards, and the
results disagree sharply. That is a team process failure, not a technical one.*
The log is what protects us from the same outcome, and it only works if it is
current.

---

## 2. ⚠️ Six things to resolve before Day 1

### ① "CUDA kernels" — cupy, or actual `.cu` files?

The roadmap says *"Implement R3's fix at the CUDA/kernel level."* There is no
CUDA. So this reads two ways:

- **(a) cupy port** — swap the arrays through `array_module()`, keep the numpy
  code. Days, not weeks. Deterministic for free (int32). Risk: cupy's generic
  ops may not beat CPU on some kernels.
- **(b) real `.cu` via `cupy.RawKernel`** — full control, matches the deck's
  current claim, but a much longer tail.

**Recommendation: (a) first, then (b) only where measurement says cupy is the
bottleneck.** The seam already exists; taking it is one to two days and gives us
a real number to decide (b) against. Writing `.cu` first is choosing an
implementation before we know which kernel needs it.

Either way, **the deck's current CUDA claim has to come down until the code
matches it.** See `09-GPU-WHAT-TO-SAY.md` in `docs/presentation/`.

### ② R3/R4 are in Aakash's directory, not ours

The anisotropy lives in `src/grid/` — `schedule.py`, `lattice.py`, `gate.py`,
`splitmerge.py`. Not one line of it is in `src/gpu/`.

The roadmap half-flags this (*"R3 and R4 span two pairs… agree the interface
before Day 3 starts"*) but assigns the implementation to us anyway. Under the
directory-ownership model, that is a collision.

**Resolve on Day 0:** either JP/Hriday write the fix in `src/grid/` and we write
the CI test and profile the cost, or we get explicit sign-off to touch
`src/grid/`. The roadmap's own warning names the precedent — *the range_image.py
/ visibility.py azimuth mismatch* cost days of silent divergence, and that was
exactly two people editing across a boundary without agreeing the contract.

**My read: we should own R4 (the test) outright and hand R3 (the fix) to the
grid pair.** A test is a contract; writing it first is the cleanest handoff.

### ③ R9's "attributed VRAM" is currently unmeasurable

Nothing in the mapping pipeline uses VRAM. There is nothing to attribute until
the port lands.

**So R9 is two deliverables, not one:**
- **R9a, Day 1, no GPU needed:** the per-stage latency table and the memory
  reconciliation (§3). This is publishable immediately.
- **R9b, after the port:** VRAM attribution, which only becomes real once our
  arrays are on the device.

Do not block R9a on the instance.

### ④ R9's latency table is already half-done

`scripts/timing_table.py` exists and the end-to-end run is in the research log at
line 454: **p50 89.18 / p99 100.43 ms**, twelve stages, flat and disjoint. The
competitor review says *"we have the timing infrastructure in src/gpu and no
published table"* — that was true when it was written and is not true now.

**So Day 1 is not "build the table," it is "publish it, and add the VRAM/memory
column."** That frees most of Day 1.

⚠️ `scripts/timing_table.py:13`'s docstring still claims there is no end-to-end
loop to time. Stale. Two-minute fix, and it is the script a judge would ask us to
run.

### ⑤ Four memory numbers, no published reconciliation

8.94 / 10.3 / 29.06 / 32.17. See `00-WHERE-WE-ARE.md` §3. R8 says *"lead the
README with 21.5×"*; R9 says *"attributed VRAM."* Neither works until the four
numbers are one table.

**This is Pratyushi's Day 1**, off the back of Shrestha's `memory_table.py` and
`memory_bound.py` runs. See §3.

### ⑥ The review's R(S) figures are stale

Rule 5 says to print *"5.803 against 0.146 … 1.793 after"* under the money plot.
Those are pre-2-September, before the three metric defects were fixed. The
current numbers are in `00-WHERE-WE-ARE.md` §4. Anyone quoting the PDF verbatim
will publish superseded figures.

---

## 3. The memory reconciliation table — Day 1, Pratyushi

The deliverable. One table, four rows, published in the README and the report,
so that no two of our own numbers can ever look like a contradiction again.

| Row | Value | What it counts | Where it is measured |
|---|---|---|---|
| Map | **8.94 MB** | 745,000 logical cells × 12 B | `memory_table.py` |
| Representation bound | **10.3 MB** | map + refinement pool + transient + tracks | `sih-math.md` §derivation |
| Committed at startup | **29.06 MB** | the above + every frame-path working buffer | `allocate()`, dashboard |
| With pyramid | **32.17 MB** | + conservative max/min pyramid | non-default |

**Ratios are computed on row 1** and that must be stated on the same page.
The competitor review's R8 point is that 21.5× (vs uniform 2.5D) is the honest
headline, not 286× (vs dense 3D) — and it adds the stronger move we are not
making:

> **Our ratio contains no sparsity.** We allocate all 745,000 ring slots at
> startup whether occupied or not, so 21.5× is *foveation alone* — against their
> 257× decomposing into 188× sparsity and **1.37× foveation.** Ours is roughly
> fifteen times their foveation-only figure and immune to the objection that
> killed their headline.

That sentence belongs in the README and on the slide. It is the single
highest-value sentence in the competitor document.

---

## 4. Day by day

*Rewritten from the roadmap with ①–⑥ applied. Gates unchanged where they still
make sense.*

| Day | Shrestha (build) | Pratyushi (write / read) | Gate |
|---|---|---|---|
| **0** | Resolve ①②③ with the team. 30 min, not a day. | Read `00-WHERE-WE-ARE.md`, `04-RESEARCH-SHELF.md` §1–2 | Ownership of R3 vs R4 agreed in writing |
| **1** | Provision AWS (`02-AWS-RUNBOOK.md`). Run `frnet_fast_scatter.py` verify locally. Publish R9a: per-stage table + memory rows. Fix `timing_table.py:13`. | The §3 reconciliation table. R8 README wording incl. the no-sparsity sentence. | R9a published; instance reachable; README corrected |
| **2** | Sync seq 08 to the instance. Run `frnet_eval.py --frames 200 --fast-scatter` on T4. Confirm 90.3 / 65.2 and the ULP bounds hold on a different GPU. | Research-log entry for the AWS reproduction. Start prior-art on deterministic GPU reduction (`04` §3). | FRNet reproduces on a clean machine |
| **3** | **Take the cupy seam.** Port `bin_points` first (elementwise, no atomics). Then `scatter_sorted`. Run `make test-determinism` on device. | Write up the int32-atomicAdd determinism argument as a report section — it is our best original systems claim. | `bin_points` + `scatter` on device, determinism test green |
| **4** | Port `visibility_cleanup` — 26 ms of 89, and the most parallel stage. Profile against CPU. | R4 test spec in prose, so the grid pair can review the contract before code exists. | Cleanup on device with a measured delta |
| **5** | Write the R4 footprint-disjointness test (see §5). Run across the speed sweep, both frozen schedules. | Research-log for the port numbers. Begin `04` §4 reading (profiling/Nsight). | R4 green on both schedules at all speeds |
| **6** | **The contention question.** Grid engine + FRNet on one T4, measured not assumed. VRAM attribution — R9b. | Report section for R9b. The four-row table gains a VRAM column. | Combined budget measured, in or out of tolerance |
| **7** | Stage-attrition instrumentation at kernel level (Rule 3). | Draft the attrition table format from the review's Rule 3. | Attrition numbers exist |
| **8** | Re-profile everything with R3/R4/R5 active. Confirm no regression, confirm 8.94 MB unmoved. | Consolidate all research-log entries into the report's performance section. | No regression; bound unchanged |
| **9** | Freeze. Re-run every script that produces a slide number, on both machines. | Final pass: every published number traceable to a script and a log entry. | Everything reproducible |
| **10** | Buffer | Buffer | Whatever slipped |

**Deliberate change from the roadmap:** the cupy port moved to Day 3, ahead of
R3/R4, because R9b, Day 6's contention question and Day 7's kernel-level
instrumentation all depend on it. In the original ordering the port never happens
and three later gates quietly have no substrate.

---

## 5. The R4 test, specified

This is the one piece of new test code that is unambiguously ours.

```
for every pair of occupied cells (c1, c2) at any two ring levels:
    assert not footprint(c1).contains(footprint(c2))

run across the speed range so a_f(v) sweeps its whole clamp range
run against BOTH frozen schedules: 5/10/20/40 and 5/10/50
```

**Why the existing partition test cannot see this.** It asserts each point maps
to exactly one cell *per ring*, over 10⁶ seeded points against exact rational
arithmetic. Good test. But this bug leaves the per-ring partition intact and
creates containment *across* rings — the points are partitioned perfectly and
two footprints still overlap. Their measurement is the proof: 82 overlapping
footprints, **zero points lost or double counted.**

**Why the speed sweep matters.** At v = 0 all anisotropy factors are 1 and the
test reduces to the isotropic case, which already passes. The failure only
appears once `a_f` leaves 1.0. A test that runs at rest is a test that cannot
fail.

**Expected cost when R3's fix lands:** ~+0.1% cells (theirs: 48,837 → 48,909).
**The 8.94 MB figure is a preallocated bound and does not move.** Confirm that
explicitly — it is a headline number and Day 8's gate.

---

## 6. What our pair should be able to say at the finals

Three claims, in order of strength:

1. **"Our determinism guarantee survives the GPU port, and here is why."**
   Integer `atomicAdd` is exact and associative, so the map is bit-identical
   regardless of scheduling order. Most projects trade reproducibility for
   device speed. We do not, because of a decision made on Day 0.
2. **"Our compression ratio contains no sparsity."** 21.5× is foveation alone,
   against the competing team's 1.37×.
3. **"Here is the per-stage table, on CPU and on device, with memory attributed
   per row."** Nobody else in this problem statement will have both columns.

Everything in this lane is in service of being able to say those three things
with a script behind each one.
