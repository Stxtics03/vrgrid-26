# The 10 Hz latency claim — diagnosis

*2026-09-12. No fix attempted, as instructed. Diagnosis only.*

> **[!] SUPERSEDED 2026-09-12 by `reports/latency-gap-investigation.md`.**
> Kept for the record; do not quote from it without checking the newer report.
>
> What this document got RIGHT and the newer one confirms: 80.78 / 97.72 is not
> a whole-frame seq-08 number, and it is the mapping back half on a synthetic
> sweep.
>
> What it got WRONG: the reasoning that the figure was measured with
> `--no-patchworkpp`. Shrestha's run has `ground` at 12.41 ms -- the geometric
> segmenter -- so Patchwork++ was active, and the figure reproduces to 1.1% as
> `timing_table.py --cells 910000` with no fallback involved. That inference is
> withdrawn.
>
> Also superseded: the claim that the figure cannot be reproduced under any
> configuration. It reproduces.

---

## Summary

**The handover's 80.78 / 97.72 ms is not a whole-frame number and never was.**
It is the **mapping back half on a synthetic sweep**, mislabelled in the
handover as `frame p50 / p99` from `timing_table.py --seq 08`. Both halves of
that label are wrong: the scope (back half, not frame) and the data source
(synthetic, not seq 08).

**This was already diagnosed in the repo**, by Shrestha on 4 September
(`docs/research-log.md`, commit `adb2c73`):

> the 80.78 / 97.72 in the handover is **not comparable** to this — it is the
> back half on a synthetic sweep, where the same back half on real seq 08 data
> costs 46.32 ms p50.

**The correct whole-frame number already exists in the same entry: 89.18 p50 /
100.43 p99, which misses 10 Hz at p99 by 0.43 ms.** It was never propagated to
the handover, which still says "meets 10 Hz" in its *proven* table.

### ⚑ I am withdrawing my own overnight claim

My 2026-09-11 report said the 10 Hz claim *"does not reproduce under any
configuration"* and hypothesised the logged figure had been measured with
`--no-patchworkpp`. **Both are wrong.**

- The hypothesis is wrong: Shrestha's run had `ground` at 12.41 ms p50, so
  Patchwork++ **was** active. My `--no-patchworkpp` arithmetic (87.95 ≈ 80.78)
  was a coincidence.
- The claim is not supported: **this machine cannot measure whole-frame latency
  reliably tonight** (§3). My numbers were not stable enough to contradict
  anything.

What survives is a *documentation* fact, not a measurement one: the handover's
label is wrong, and the corrected number was never carried across.

---

## 1. What the 80.78 / 97.72 run actually was

| question | answer | evidence |
|---|---|---|
| Which commit introduced it? | `464ad8b`, Stxtics03, **2026-09-02 20:51:13 +0530** | `git log -S '80.78'` |
| Whole frame or back half? | **Back half only** | research-log `adb2c73`, 4 Sep |
| Real seq 08 or synthetic? | **Synthetic sweep** | same |
| Did any log survive? | **No.** No `.log`, no `*_out.txt`, no `scratchpad/` — none ever committed to the repo | `git log --diff-filter=A` over those globs |

### The SEMANTIC-CLASS FALLBACK banner cannot settle it, because it did not exist

You asked me to look for the fallback banner in that run's logs. Two reasons
that is a dead end, and the second is decisive:

1. **No logs from that run survive** — nothing was ever committed.
2. **The banner post-dates the run by 10.7 hours.** It was introduced by PR #32
   (`c6fad5e`, "make the Patchwork++ fallback loud"), merged as `bc11caf` at
   **2026-09-03 07:33:42 +0530**. The handover commit is **2026-09-02
   20:51:13 +0530**. The code that prints the banner did not exist when the
   number was produced, so **no log from that run could contain it, whether or
   not the fallback was used.**

It is moot anyway: the run was synthetic, and the synthetic path never calls
`ground` at all — `timing_table.py` lists `ground` among the six stages it
cannot measure without SemanticKITTI on disk.

### A useful control

`scripts/timing_table.py` is **byte-identical** between `464ad8b` and now,
apart from the 2-character unicode fix applied today. `--seq` existed then, and
the synthetic defaults (`--points 120_000`, `--cells 200_000`) are unchanged.
So the tool is not the variable.

---

## 2. The real number, and what changes if we accept it

Shrestha's whole-frame run — one `Timer` shared across both halves, 200 frames
of seq 08, **quiet machine**, stages flat and disjoint:

| stage | p50 | p99 | | stage | p50 | p99 |
|---|---|---|---|---|---|---|
| cleanup | 26.22 | 33.43 | | reflectivity | 3.49 | 4.64 |
| range_image | 24.45 | 29.27 | | shift | 2.07 | 5.52 |
| **ground** | **12.41** | 14.50 | | transform | 1.53 | 2.56 |
| scatter | 7.06 | 8.20 | | load | 0.58 | 0.86 |
| bin | 6.84 | 8.33 | | semantics | 0.45 | 0.68 |
| fuse | 4.13 | 5.28 | | motion | 0.06 | 0.09 |
| | | | | **TOTAL** | **89.18** | **100.43** |

`ground` at 12.41 ms confirms **Patchwork++ was active** — the semantic-class
fallback costs ~0.4 ms.

### Here is the real number under real Patchwork++

> **p50 89.18 ms, p99 100.43 ms, max 109.28 ms, on real seq 08.**
> The median clears 10 Hz with 10.8 ms to spare. **The p99 is 0.43 ms over the
> 100 ms budget.**

### What changes if we accept that instead

**The honest sentence stops being "meets 10 Hz" and becomes "meets 10 Hz on the
median, misses it at p99 by 0.43 ms."** That is not a rounding detail — the
project's own standard rejects it. `src/gpu/timing.py`'s `headroom()` docstring:

> *"A pipeline that clears 10 Hz on the median and misses it one frame in a
> hundred has dropped a frame of obstacles."*

Concretely:

1. **`docs/handover-2026-09-02.md:23` moves out of "Measured on real data and
   holding."** The row currently reads *"latency | frame p50 80.78 ms, p99
   97.72 — meets 10 Hz | `timing_table.py --seq 08`"*. Every element of it is
   wrong: the numbers are the back half, the source is synthetic not `--seq 08`,
   and the verdict flips.
2. **Any slide saying "10 Hz" needs the qualifier.** Shrestha's own conclusion:
   *"the latency claim needs to say whether it is quoting the back half or the
   frame."*
3. **It is 0.43 ms, and that is recoverable.** `cleanup` (26.22) and
   `range_image` (24.45) are 57% of the frame between them. This is a
   near-miss, not a structural failure — which is a far better position to
   present than a wrong "meets".
4. **`load` at 0.58 ms is page-cache-warm and would not exist on a live
   sensor** — Shrestha's own caveat. On a live sensor the frame arrives over
   the wire, so that stage disappears rather than grows.

---

## 3. Why my own overnight numbers cannot be used

I re-ran repeatedly today. **The machine is memory-bound and the measurement is
not stable.** RAM: **2.48 GB free of 16.9 GB**, with Windows `MemCompression`
holding 649 MB — i.e. actively compressing pages. CPU was idle (7%) throughout.

Identical back-to-back runs of the same command:

| run | synthetic, 100 frames | synthetic, 200 frames | real seq 08, 200 frames |
|---|---|---|---|
| 1 | p50 44.03 / p99 269.36 | p50 42.15 / p99 52.46 | p50 152.27 / p99 187.68 |
| 2 | p50 45.56 / p99 338.63 | p50 146.54 / p99 197.03 | p50 106.74 / p99 132.22 |
| 3 | p50 44.42 / p99 179.39 | p50 155.18 / p99 259.10 | p50 137.62 / p99 510.07 |
| 4 | — | p50 155.26 / p99 201.89 | p50 107.34 / p99 121.51 |

- **p99 varies up to 4.2×** across identical runs (121.51 → 510.07 on real data).
- **p50 at 200 frames varies 3.7×** (42.15 → 155.26) on the *same* synthetic command.
- **p50 at 100 frames is stable (±2%)** but **~3.4× lower per frame than at 200
  frames** on identical code — superlinear in run length, which is the signature
  of accumulating memory pressure, not of compute.

A latency measurement on this machine tonight is measuring paging. **Shrestha's
"quiet machine" 89.18 / 100.43 is the more trustworthy figure and should be
treated as the current best estimate.**

**What would settle it:** one whole-frame run on a machine with headroom —
close the browsers, or run it anywhere with >8 GB free — reporting p50, p99 and
max together. Until then nothing here should be used to revise 89.18 / 100.43
in either direction.

---

## 4. The actionable item

Not a code fix. **The correction exists and was never propagated.**
`research-log.md` (4 Sep) records it; `handover-2026-09-02.md:23` still carries
the wrong number, the wrong scope, the wrong source and the wrong verdict, in
the table headed *"Measured on real data and holding."*

Both files are Shrestha's. Not edited here.
