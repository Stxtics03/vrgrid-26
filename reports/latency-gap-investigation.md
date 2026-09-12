# Latency-gap investigation: the 80.78 / 97.72 ms claim

**Question.** `docs/handover-2026-09-02.md:20` claims frame **p50 80.78 ms,
p99 97.72 ms**, cited to `timing_table.py --seq 08`. That command does not
produce those numbers on this machine. This is the reconstruction.

**Written:** 2026-09-12, against `main` @ `675d24b`.
**Scope:** measurement and archaeology only. Nothing in `src/`, `configs/` or
`docs/` was modified. All test scripts were written outside the repo.

---

## Confirmed

### 1. Patchwork++ is real on this machine, and it really executes

Checked directly, not inferred from a config flag:

```
pypatchworkpp    1.4.1
module           C:\Users\JAIPREET SINGH\anaconda3_2025\Lib\site-packages\
                 pypatchworkpp.cp313-win_amd64.pyd
ground._HAVE_PATCHWORKPP    True
```

On a real one-frame run the **`semantic-class FALLBACK` banner does not
appear**, `PatchWorkpp::PatchWorkpp() - INITIALIZATION COMPLETE` does, and the
run summary prints `ground: Patchwork++ (geometric segmenter)`. That triple is
the ground truth, and it says the real geometric segmenter ran.

> **Method note.** The banner grep must be case-insensitive. The warning text
> is mixed-case (`semantic-class FALLBACK`); `grep -c 'SEMANTIC-CLASS
> FALLBACK'` returns 0 on a run that *did* fall back. That false negative cost
> real time earlier in this investigation.

### 2. Which path each of the three benchmark configs actually took

| config | fallback banner | `INITIALIZATION COMPLETE` | verdict |
|---|---|---|---|
| cold (surviving log `/tmp/r9_seq08.txt`) | 0 | 1 | **real Patchwork++** |
| warm | 0 | 1 | **real Patchwork++** |
| `--no-patchworkpp` | 1 | 0 | **fallback**, as intended |

So no reported figure was silently a fallback run. The `--no-patchworkpp`
hypothesis for the gap is dead: the fast config was the one flagged as fast.

### 3. The isolated cost of Patchwork++

Whole-frame comparison between those configs was **worthless** — every stage
moved 2-3x between back-to-back runs, including `load` at 33.59 vs 1.23 ms
(27x). That is page cache, not the segmenter. Re-measured with all scans
preloaded into RAM, both paths alternating, 3 reps, same points:

```
Patchwork++ (geometric)   p50 21.01 ms   (reps 21.29, 20.82, 20.90)
semantic-class fallback   p50  0.33 ms   (reps  0.33,  0.34,  0.32)
                          delta +20.67 ms/frame, ratio 63.6x
agreement on labelled points, 20 frames: 96.5%
```

Repeated later in the session at 20.16 / 20.36 / 20.41 ms — stable to ~4%.

**Cross-machine anchor.** Shrestha's 4 Sep research-log run put `ground` at
**12.41 ms**. Same code, same data, ~1.7x slower here. That is a real
environment difference localised to this stage.

### 4. Hardware this was measured on

```
CPU     13th Gen Intel Core i7-13620H  (16 logical, laptop part)
RAM     15.7 GB
GPU     NVIDIA RTX 4060 Laptop + Intel UHD  -- NOT USED, see below
OS      Windows 11 26200
Python  3.13.9,  numpy 2.4.4
```

`src/gpu/` is a **naming convention for kernel-shaped numpy code**, not CUDA:
`cupy` is not installed, and nothing on the frame path imports a GPU runtime.
These timings are entirely CPU-bound and the discrete GPU is irrelevant to
them.

### 5. There is no version pin on Patchwork++

`pyproject.toml:25` — `perception = ["pypatchworkpp>=1.2"]`. A **floating
lower bound**, no lockfile, no upper bound. Installed here is **1.4.1**.
Whatever version produced the original number is unrecorded and unconstrained,
and a 1.2-vs-1.4 difference in the segmenter is entirely possible. This is
worth pinning regardless of how this investigation ends.

---

## Reproduced

### The number reproduces — but not from the command the doc cites

**What the cited command actually gives.** `timing_table.py --seq 08`,
real data, real Patchwork++:

| run | p50 | p99 |
|---|---|---|
| `--seq 08 --frames 20` | 109.71 | 129.52 |
| `--seq 08 --frames 200` | 108.65 | 127.23 |
| `--seq 08 --frames 5` | 105.58 | 107.25 |
| independent harness, 221 frames | 107.52 | 146.33 |

**Nowhere near 80.78 / 97.72, in any configuration, on any frame count.**

**What does reproduce it.** The *synthetic* path with the candidate-cell count
raised to the schedule's allocated slot count:

```
python scripts/timing_table.py --cells 910000        # --frames defaults to 200
```

| | p50 | p99 |
|---|---|---|
| rep 1 | 81.66 | 90.17 |
| rep 2 | 81.51 | 89.98 |
| **handover claim** | **80.78** | **97.72** |

**p50 lands within 1.1%.** And it scales cleanly, so the match is not a
coincidence of one lucky value:

| `--cells` | p50 | p99 |
|---|---|---|
| 700,000 | 72.46 | 79.58 |
| 800,000 | 77.57 | 84.36 |
| **910,000** | **82.81** | **90.78** |
| 1,000,000 | 87.93 | 93.14 |

(910,000 is the allocated slot count for schedule `5/10/20/40` — the number
the script prints in its own banner, so it is the natural value for someone
asking "what if every slot is a candidate".)

**Two independent lines of evidence agree on the same explanation.**
Shrestha's 4 Sep research-log entry (`adb2c73`), written without knowledge of
this reproduction, says the figure is

> "not comparable to this — it is the back half on a synthetic sweep, where
> the same back half on real seq 08 data costs 46.32 ms p50."

His 46.32 ms cross-checks against **48.07 ms** measured here for the same back
half on real seq 08 (bin 7.55 + scatter 7.22 + fuse 3.97 + cleanup 27.74 +
shift 1.59) — **4% apart**, which is good agreement across two machines and
independently corroborates that he and I are measuring the same thing.

### What this does and does not establish

**It does establish** that 80.78 ms is a reproducible measurement of
*something*, to 1.1% — and that the something is the synthetic back half at
full candidate occupancy, not a real seq-08 frame.

**It does not establish** that this is what was actually run. No record ties
`--cells 910000` to the handover (see below). The match is strong
circumstantial evidence, not a traced provenance.

**So the honest statement is: the number is probably sound and the citation
next to it is wrong.** `timing_table.py --seq 08` is not the command that
produces it, and a reader who runs the cited command to check the claim gets
109 ms and concludes the project misses its budget by 10%. Per the standing
constraint I am not calling the *number* right or wrong — only its label,
which is demonstrably not reproducible.

---

## Ruled out

Each of these was measured, not reasoned about.

| hypothesis | test | result |
|---|---|---|
| **Silent fallback** inflating/deflating a run | banner audit, all 3 configs | ruled out — §2 above |
| **Frame count** | seq 08 at 20 vs 200 frames | 109.71 vs 108.65 p50. No effect |
| **Sequence choice** | seq 00 at 20 / 200 frames | 128.87 / 116.35 p50 — *slower*, not faster |
| **A config default changed** since the handover | `git show 464ad8b:configs/thresholds.yaml` | `max_candidate_cells: null` **already**. Identical then and now |
| **The tool changed** since the handover | `git diff 464ad8b..HEAD -- scripts/timing_table.py` | only my 2-char unicode fix (`f3a0337`). A clean control |
| **`--cells` comes from config** | `args.cells` at `timing_table.py:288,291,292,570` | CLI-only. 910,000 had to be passed explicitly |
| **`--alloc` affects the real path** | reading `run_real` | silently ignored with `--seq`. Not a factor |
| **Longer warm-up closes the gap** | 221-frame windowed sweep | *partially* — see below. Does not close it |
| **`max_range` tradeoff** | parameter sweep | −0.50 to −1.18 ms for **2.35-2.83% of verdicts flipped**. Bad trade, rejected |

### Warm-up, measured properly (Step 4b)

Whole-frame p50 does drift downward as the map fills, so "warm" is not a
binary. 221 frames of seq 08, real Patchwork++, timed per frame:

| window | n | p50 | p99 |
|---|---|---|---|
| frame 0 only | 1 | 148.53 | 148.53 |
| 1-21 | 20 | 112.84 | 126.77 |
| 21-51 | 30 | 118.32 | 146.93 |
| 51-101 | 50 | 110.77 | 141.54 |
| 101-151 | 50 | 104.70 | 115.40 |
| 151-201 | 50 | **100.59** | 120.14 |
| **51+ discarded** | 170 | 105.37 | 130.58 |

A 50+ frame warm-up is worth **~7 ms p50** over the standard 20-frame window,
and the best window reaches 100.59 ms. **Real, and not enough** — still ~20 ms
above 80.78. `run_real` already discards frame 0, which the table shows is the
only truly anomalous frame (148.53 ms), so the existing warm-up is not the
defect.

---

## Unknown / unrecoverable

### The original run cannot be traced. This is a definitive negative.

`git blame docs/handover-2026-09-02.md:20`:

```
464ad8be (Stxtics03  2026-09-02 20:51:13 +0530)  | latency | frame p50
**80.78 ms**, p99 **97.72** — meets 10 Hz | `timing_table.py --seq 08` |
```

Everything checked, all of it negative:

- The **commit message states no method** — no flags, no frame count, no host.
- **Zero research-log lines** about latency were added in that commit, so
  there is no companion note.
- Only **5 files in all of history** have ever contained the string `80.78`,
  and **3 of them are mine from this week**.
- **No `.log`, `.txt`, `.csv` or `.json` results artifact was ever committed
  on any branch** (`git log --all --diff-filter=A`). There is no output file
  to inspect, because one was never saved.
- No script wrapping `timing_table.py` with a `--cells` value exists anywhere
  in history.

**There is no reproducible command, no log, and no artifact.** The `--cells
910000` reproduction above is the best available reconstruction and it is
inference, not provenance. I am not going to dress it up as a finding.

### Genuinely open

1. **The ~1.7x `ground` difference between machines is unexplained.** 12.41 ms
   there, 20-21 ms here, same code and data. Candidates: CPU (this is a
   *laptop* i7-13620H under sustained load, and the p99 spread in the table
   above is consistent with thermal behaviour), a different `pypatchworkpp`
   build given the unpinned `>=1.2`, or Windows vs Linux. **Untestable from
   this machine**, and I am neither ruling it in nor out. If nothing else
   explains a residual gap, this is the live candidate — and the missing
   version pin (§5) is the part of it that is actually fixable.
2. **p99 is duration-dependent and therefore a weak comparator.** It ranges
   115-147 across windows of the same run. Any p99 quoted without a frame
   count and a host is not a checkable claim — which is exactly the situation
   with 97.72.

---

## Is there a real path to 10 Hz with real Patchwork++?

**Yes for p50, no for p99.** Measured, and written up as a proposal in
`pending-review/patchworkpp-num-iter-tradeoff.md` — **not applied**.

The short version: `params.num_iter` is 3 by default and `ground.py` does not
set it. Dropping it to 2 buys **−3.9 ms** and flips **0.57%** of ground
verdicts; combined with `enable_RNR=False` and `enable_RVPF=False` it buys
**−5.42 ms** for **0.72%** flipped. Against a best-window 100.59 ms p50 that
lands near **95 ms — inside the 10 Hz budget**. p99 (120-130 ms) stays out,
and no parameter tested moves it.

## What I would change in the docs (not applied)

The defect worth fixing is **not** the number, it is that the claim is
uncheckable. A latency claim needs the recipe: exact command including
`--cells` and `--frames`, whether the figure is whole-frame or a subtotal,
the frame window, and the host. The current line has one of five, and the one
it has is wrong.

---

## Appendix: a trap for the next person

`VRGRID_DATA_ROOT` must be set to **`C:/KITTI/dataset`** for any real-sequence
run. The in-repo `data/` directory is a **partial stub** — it holds `calib.txt`
and `poses.txt` for seqs 00/07/08 but only 49 velodyne scans (seq 00 only) and
**zero `.label` files**. With the variable unset, `loader.DATA_ROOT` defaults to
`./data` and `--seq 08` dies with `FileNotFoundError: No velodyne frames found
for sequence 08`.

I hit this mid-investigation and briefly mistook it for the dataset having been
deleted. It had not: the real root has 4541 / 1101 / 4071 scans with matching
labels for seqs 00 / 07 / 08. Worth an explicit line in the run docs, because
the failure mode looks like data loss rather than a missing environment
variable.
