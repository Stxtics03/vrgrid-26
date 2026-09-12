# pending-review: the `num_iter` latency tradeoff — MEASURED AND REJECTED

**Status:** proposal, **withdrawn on the evidence**. **Nothing applied.** No
change was made to `src/perception/ground.py`.
**Outcome:** do not apply. It buys 5.42 ms of p50, costs 19-54% of ring-0
elevation RMSE concentrated on slopes (§5a), and does not fix p99 (§0).
**Code it would touch:** `src/perception/ground.py` (`_get_estimator`) and
`configs/thresholds.yaml` (**frozen** — needs Shrestha).
**Measurement:** `reports/latency-gap-investigation.md`
**Written:** 2026-09-12, against `main` @ `675d24b`.

---

## 0. Read this first: p99 misses the budget and this proposal does not move it

**p99 stays out of budget, and nothing in this proposal moves it.** Whole-frame
p99 on seq 08 is **127-146 ms** over full runs, and ranges **115-147 ms** across
windows within a single 221-frame run — against a 100 ms budget. **No parameter
tested changed it:** not `num_iter`, not the optional stages, not `max_range`,
not warm-up length, not the library version.

A 5.42 ms saving in a 20 ms stage cannot close a 30 ms p99 overshoot whose
cause is elsewhere and was not located.

So the honest framing of this proposal is: **it buys p50, at a cost in ground
accuracy, and leaves the p99 problem untouched.** If the 10 Hz target is a p99
target, do not ship this expecting to hit it, and do not let the p50 number
stand in for the claim anywhere it gets quoted.

**And the accuracy cost turned out to be real — see §5a. On the measurement now
available I recommend AGAINST applying this.** The §4 recommendation below is
retained as written for the record, but §5a supersedes it.

---

## 1. What is actually costing the frame

`ground` is **20-21 ms p50** on this machine with real Patchwork++, against
**0.33 ms** for the semantic-class fallback — measured with scans preloaded
into RAM so neither disk nor page cache is in the loop (3 reps, ±4%).

Whole-frame p50 on real seq 08 is **100.6-112.8 ms** depending on how many
frames are discarded first. So `ground` is ~20% of the frame and the single
largest lever that is a *parameter* rather than a rewrite.

## 2. The knob nobody set

`_get_estimator` sets exactly two fields:

```python
params = _pw.Parameters()
params.sensor_height = SENSOR_HEIGHT_M
params.verbose = False
```

Everything else is library default. The relevant default is
**`num_iter = 3`** — plane-fit iterations per zone. Patchwork++ also ships
three optional stages on by default: `enable_RNR` (reflected-noise removal),
`enable_RVPF`, `enable_TGR`.

## 3. What each one buys, measured

Seq 08, 40 frames, own estimators built outside `ground.py`, 3 warm frames
each so the stateful estimator starts from the same place. "Flipped" = the
fraction of points whose ground/non-ground verdict changes relative to the
shipped configuration.

| configuration | p50 ms | vs shipped | flipped |
|---|---|---|---|
| **SHIPPED** (`num_iter=3`, all stages on) | 20.36 | — | — |
| `num_iter` 3 -> 2 | 16.44 | **−3.92** | **0.57%** |
| `num_iter` 3 -> 1 | 12.68 | −7.67 | 1.55% |
| `enable_RNR` off | 19.22 | −1.14 | 0.14% |
| `enable_TGR` off | 20.12 | −0.24 | 0.00% |
| `enable_RVPF` off | 19.77 | −0.59 | 0.01% |
| `max_range` 80 -> 60 | 19.86 | −0.50 | **2.35%** |
| `max_range` 80 -> 50 | 19.18 | −1.18 | **2.83%** |
| `num_lpr` 20 -> 10 | 19.93 | −0.43 | 0.57% |

Combined:

| configuration | p50 ms | vs shipped | flipped |
|---|---|---|---|
| **A** — `num_iter=2`, RNR off, RVPF off | 14.99 | **−5.42** | **0.72%** |
| B — `num_iter=1`, RNR off, RVPF off | 11.11 | −9.30 | 1.72% |

Reproducible: the shipped row measured 20.16 / 20.36 / 20.41 across three
independent runs, and `num_iter=1` measured 12.68 twice.

## 4. Recommendation: config A, and only config A

**−5.42 ms for 0.72% of verdicts moving.** Against a best-window whole-frame
p50 of 100.59 ms that lands near **95 ms — inside the 10 Hz budget**, with
real Patchwork++ and no fallback.

**Reject `max_range`.** It is the worst trade on the table: under 1.2 ms for
2.35-2.83% of verdicts flipped, and it also blinds the segmenter beyond 50-60 m
while ring 3 spans 50-100 m. Cutting it would change what the outer ring
reports, not just how fast it reports it.

**Reject B (`num_iter=1`).** 1.72% flipped for another 3.9 ms. A single
plane-fit iteration on a sloped or uneven patch is exactly where Patchwork++
earns its keep over a height threshold, and the extra margin is not needed if
A already fits.

**`enable_TGR` is free to leave on** — 0.00% flipped and −0.24 ms is noise in
both columns. Do not touch it; there is nothing to win.

## 5. [!] What this does NOT fix

**p99 stays out of budget.** 115-147 ms across every window measured, and
**no parameter tested moved it**. A 5 ms shift in a 20 ms stage cannot fix a
30 ms p99 overshoot whose cause is elsewhere. If the 10 Hz claim is meant to
be a p99 claim, this proposal does not deliver it and should not be presented
as if it does.

**0.72% is not free.** On ~180k points a frame that is ~1,300 points changing
verdict. Nobody has checked *which* points: if they cluster on curbs, slopes,
or the far field, a 0.72% aggregate could still move a hazard-relevant number.
See §7.

## 5a. MEASURED: the accuracy cost, and it rejects the proposal

The 0.72% was measured properly after this document was first written. Full
result in **`reports/numiter-tradeoff-accuracy-cost.md`**; the decisive part:

| seq | ring-0 RMSE shipped | proposed | relative |
|---|---|---|---|
| 07 | 1.77 cm | **2.74 cm** | **+54%** |
| 08 | 1.17 cm | **1.39 cm** | +19% |
| 00 | 2.74 cm | **3.73 cm** | **+36%** |

(Baseline gate passed first: shipped reproduces the published 1.78 / 1.17 /
2.74.)

And the flips are **not** spread evenly. Flip rate by local surface slope:

| local slope | 07 | 08 | 00 |
|---|---|---|---|
| 0-2% | 0.89% | 0.59% | 0.80% |
| 10-20% | **3.57%** | **2.65%** | **1.82%** |
| >20% | **3.39%** | **2.57%** | **1.85%** |

**Monotone on all three sequences, 2.3-4.5× from flattest to steepest.** Exactly
what truncating a plane fit should do, and the worst place to do it: slope is
itself a traversability input (`traversability` bit 1), so the error feeds the
hazard decision that slope drives. `terrain` carries the highest within-class
flip rate (3.6-3.8% on 07 and 00) and `vegetation` is ~half of all flips on 08
and 00.

**Curbs are clean** — flip rate at the road/sidewalk boundary is *lower* than
away from it on all three sequences (0.17-1.06% vs 0.74-1.11%). That hypothesis
is ruled out; slope replaces it.

**Conclusion: reject.** 5.42 ms is not worth 19-54% of ring-0 accuracy
concentrated on slopes, and per §0 it does not deliver the 10 Hz claim anyway.

## 6. Where the value would live

`num_iter` is a **threshold and belongs in `configs/thresholds.yaml`**, not
hardcoded in `ground.py` — same rule the four queued keys follow. That file is
`frozen: true`, so this needs Shrestha's sign-off, and it is the gating step
for the whole proposal. Suggested shape:

```yaml
ground:
  patchworkpp_num_iter: 2     # library default 3; see pending-review
  patchworkpp_enable_rnr: false
  patchworkpp_enable_rvpf: false
```

Reading them in `_get_estimator` is a 3-line change. **Do not** apply it
before the config keys exist, or the value ends up hardcoded and the next
person has no idea it was a deliberate tradeoff.

## 7. Before this ships, one thing must be checked — DONE, and it failed

**This section is now answered by §5a: the check was run and the proposal did
not survive it.** Kept below as written, because the list is the right list for
any future change to the ground mask.

**Re-run the accuracy numbers that depend on the ground mask**, not just the
timing. At minimum:

- ring-0 elevation RMSE against M\* — must stay 2.73 / 1.76 / 1.16 cm on
  seqs 00 / 07 / 08. This is the known-good baseline and it is the fastest
  way to see if the mask got worse.
- `reports/r7-hazard-miss-rate.md` — the 8/19, 0/3, 4/38 counts. A changed
  ground mask changes drivability directly.
- `reports/r1-accuracy-by-class-and-range-band.md` — per-band, because a
  uniform 0.72% could be concentrated in one band.

**A latency win that silently costs elevation accuracy is not a win**, and
0.72% is small enough to look free while being large enough not to be. The
timing half of this proposal is measured; the accuracy half is not, and I did
not measure it because verifying it properly means rebuilding M\* and
re-running three reports, which is more than a parameter probe.

## 8. Also worth doing, independent of this

**Pin `pypatchworkpp`.** `pyproject.toml:25` says `pypatchworkpp>=1.2` — a
floating lower bound with no lockfile. Installed here is 1.4.1. Two developers
can be running different segmenters and comparing latency numbers as if they
were comparable, which is a live possibility for the unexplained ~1.7x `ground`
difference between this machine and Shrestha's (20-21 ms vs 12.41 ms). Pinning
it is cheap and makes every future timing comparison mean something.
