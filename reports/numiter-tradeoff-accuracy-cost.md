# The accuracy cost of the `num_iter=2` latency tradeoff

**Verdict: do not apply it.** The 5.42 ms latency win costs **19-54% of ring-0
elevation RMSE** (and +56% at ring 1 on seq 07), and the flipped ground verdicts
concentrate on **sloped ground** — where a wrong ground verdict does the most
damage. **Curbs are clean.** Hazard misses move the wrong way too (8 -> 10 on
seq 07), though on denominators far too small to be significant on their own.

All three published baselines were reproduced before any delta was believed:
ring-0 RMSE on all three sequences, and the full R7 support / non-drivable /
miss triple on all three.

**Written:** 2026-09-12, against `main` @ `fac61c2`.
**Proposal under test:** `pending-review/patchworkpp-num-iter-tradeoff.md`
(`num_iter` 3 -> 2, `enable_RNR` off, `enable_RVPF` off).
**Scope:** measurement only. **`src/perception/ground.py` was not modified.**
The proposed configuration is installed by assigning `ground._estimator`, the
module-level singleton, from a scratch script. A fresh estimator is built per
configuration, because that singleton is stateful (the known determinism bug)
and a shared one would let one config's history leak into the other's numbers.

---

## 1. Baseline gate — passed before anything else was believed

The shipped configuration reproduces the published ring-0 RMSE. 40 frames,
schedule `5/10/20/40`, ring-0 ALL, centimetres:

| seq | published | measured | |
|---|---|---|---|
| 07 | 1.78 | **1.77** | PASS |
| 08 | 1.17 | **1.17** | PASS |
| 00 | 2.74 | **2.74** | PASS |

(An earlier pass of this harness read 100× high — `height_rmse_per_ring`
returns **centimetres**, not metres. The corrected figures reproduce R1's stated
gate of 2.7377 cm on seq 00 to four decimals, which is the check that the
harness is the published one.)

## 2. Ring-0 RMSE under the proposed configuration

| seq | shipped | proposed | delta | relative |
|---|---|---|---|---|
| 07 | 1.77 | **2.74** | +0.963 | **+54%** |
| 08 | 1.17 | **1.39** | +0.222 | +19% |
| 00 | 2.74 | **3.73** | +0.989 | **+36%** |

**This is the finding.** A 0.7-1.1% ground-verdict flip rate produces a
**19-54% degradation in ring-0 elevation accuracy**. Ring 0 is the
finest ring, the drivable surface, and the number the accuracy claim rests on.

For scale: seq 07 degrades from 1.77 cm to 2.74 cm — i.e. to *worse than seq
00's baseline*, the sequence already flagged as the weakest of the three.

## 3. Where the flipped verdicts land

40 frames per sequence, per-point, both masks computed on the same scans with
the four columns the real pipeline passes (`segment_ground` pads to 4 and hands
intensity through, so `enable_RNR` is live).

### Overall rate and direction

| seq | points | flipped | rate | ground -> non-ground | non-ground -> ground |
|---|---|---|---|---|---|
| 07 | 4,901,223 | 54,169 | 1.11% | 33,066 (61%) | 21,103 (39%) |
| 08 | 4,939,649 | 35,454 | 0.72% | 30,087 (85%) | 5,367 (15%) |
| 00 | 4,928,184 | 48,618 | 0.99% | 39,434 (81%) | 9,184 (19%) |

The dominant direction is **ground -> non-ground**: the proposed configuration
mostly *discards* genuine ground returns. That thins the surface M\* is built
from, which is consistent with the RMSE rising rather than the map acquiring a
gross bias. The 15-39% flowing the other way is the more dangerous minority —
non-ground classified as ground puts facades and foliage into the ground
surface, the failure mode `eval_synthetic.py` already warns about at +139.86 cm.

### [!] SLOPE — yes, and this is the mechanism

Flip rate by local surface gradient (2 m mean-height grid):

| local slope | seq 07 | seq 08 | seq 00 |
|---|---|---|---|
| 0-2% | 0.89% | 0.59% | 0.80% |
| 2-5% | 1.12% | 0.29% | 0.66% |
| 5-10% | 0.94% | 1.22% | 1.69% |
| 10-20% | **3.57%** | **2.65%** | **1.82%** |
| >20% | **3.39%** | **2.57%** | **1.85%** |

**Monotone rise on all three sequences, 2.3-4.5× from flattest to steepest
band.** This is exactly what dropping a plane-fit iteration should do: on flat
ground one iteration is nearly enough and the third is redundant, but on a
sloped patch the fit needs its iterations to converge, and truncating it
mis-classifies the returns there.

It is also the worst possible place to lose accuracy. Slope is a traversability
input in its own right (`traversability` bit 1 is `||grad z|| > tan(theta_max)`),
so degrading the height estimate specifically on slopes feeds error directly
into the hazard decision that slope drives.

### Curbs — no. The concern does not reproduce

SemanticKITTI has no `curb` class, so a curb is taken as the road/sidewalk
boundary: 0.5 m cells holding both a road-ish (`road`, `parking`) and a
sidewalk-ish (`sidewalk`, `other-ground`) label.

| seq | away from boundary | at road/sidewalk boundary | |
|---|---|---|---|
| 07 | 1.11% | **1.06%** | slightly lower |
| 08 | 0.74% | **0.17%** | 4.4× lower |
| 00 | 1.00% | **0.60%** | 1.7× lower |

**Flip rate at the boundary is lower than away from it on all three
sequences.** Curb-adjacent ground is dense, near, and well sampled, which is
where the fit converges fastest. This one is a clean negative — the curb
hypothesis is ruled out, and the slope hypothesis is confirmed in its place.

### By class — vegetation and terrain, not the road

Flip rate *within* class (the cut that shows disproportion), plus that class's
share of all flips:

| class | seq 07 | seq 08 | seq 00 |
|---|---|---|---|
| terrain | **3.63%** (5.1%) | 0.79% (16.2%) | **3.80%** (2.8%) |
| vegetation | 1.40% (12.4%) | **2.21% (48.1%)** | **2.55% (45.8%)** |
| building | 0.99% (19.2%) | 1.59% (6.8%) | 0.64% (16.5%) |
| fence | 1.83% (8.0%) | 0.49% (0.3%) | 1.48% (1.0%) |
| sidewalk | 1.57% (21.3%) | 0.17% (5.7%) | 0.64% (8.3%) |
| road | 0.39% (9.8%) | 0.25% (9.4%) | 0.73% (16.2%) |
| car | 0.30% (1.5%) | 0.11% (0.5%) | 0.13% (0.8%) |

Two things stand out:

- **`terrain` has the highest within-class flip rate** on 07 and 00 (3.6-3.8%).
  `terrain` is drivable-adjacent ground — a packed verge — so this is ground
  being mis-verdicted, not clutter.
- **`vegetation` is ~half of all flips** on 08 and 00 (48.1% / 45.8%). Foliage
  overhanging ground is the classic ambiguous case, and it is the population
  most likely to end up averaged into the surface when it flips the wrong way.

`road` itself is comparatively robust (0.25-0.73%), which is why the damage
shows up in RMSE rather than in a catastrophic drivability failure.

### By range — weak and inconsistent

| band | seq 07 | seq 08 | seq 00 |
|---|---|---|---|
| 0-10 m | 0.73% | 0.75% | 0.92% |
| 10-25 m | 1.61% | 0.55% | 1.10% |
| 25-50 m | 1.68% | 0.84% | 0.92% |
| 50-100 m | 1.29% | 1.26% | 0.77% |

No consistent direction across sequences. **Not a real effect** — reported for
completeness, not as a finding.

---

## 3a. R1: the damage is not confined to ring 0

Per-ring RMSE (cm), same 40 frames and schedule. Ring 0 is gated against the
published value on all three sequences (§1), so the ring-0 column is trustworthy;
see the caveat below for the rest.

| seq | config | ring 0 | ring 1 | ring 2 | ring 3 |
|---|---|---|---|---|---|
| 07 | shipped | 1.77 | 3.04 | 5.91 | 16.93 |
| 07 | **proposed** | **2.74** | **4.75** | 5.96 | 16.58 |
| 08 | shipped | 1.17 | 2.31 | 4.89 | 54.86 |
| 08 | **proposed** | **1.39** | **2.46** | 4.61 | 23.09 |
| 00 | shipped | 2.74 | 6.46 | 34.10 | 9.11 |
| 00 | **proposed** | **3.73** | 6.62 | 34.80 | 8.98 |

**Ring 1 degrades too, and on seq 07 as badly as ring 0** — 3.04 -> 4.75 cm,
**+56%**. So this is not a ring-0-only effect; the two finest rings, which carry
the accuracy claim, both move the wrong way on the sequence that is clean enough
to carry it.

Rings 2 and 3 are **not** evidence either way:

- Ring 2 barely moves (07 +0.05, 08 −0.28, 00 +0.70) against baselines of
  4.89-34.10 cm — noise on an already-poor number, and seq 00's ring 2 is the
  known vegetation outlier.
- **Ring 3's apparent 2.4× improvement on seq 08 (54.86 -> 23.09) should be
  ignored.** Ring 3 is 100% unlabelled, and seq 08 is explicitly **not
  reportable for anything built on world-registered accumulation** per
  `1c7c24d` — the per-frame registration fault. A large move in the one ring
  with no class information, on the one sequence with a known accumulation bug,
  is not a finding.

### [!] Caveat: rings 1+ do not all reproduce the published R1 values

Against `reports/r1-accuracy-by-class-and-range-band.md`:

| | ring 0 | ring 1 | ring 2 |
|---|---|---|---|
| seq 07 published / measured | 1.78 / **1.77** | 3.60 / **3.04** | 5.91 / **5.91** |
| seq 08 published / measured | 1.17 / **1.17** | 2.31 / **2.31** | 4.89 / **4.89** |
| seq 00 published / measured | 2.74 / **2.74** | 6.77 / **6.46** | 34.10 / **34.10** |

Rings 0 and 2 reproduce **exactly** on all three sequences, and seq 08
reproduces exactly at every ring. Ring 1 is off by −0.56 on 07 and −0.31 on 00.

I do not know why, and I am not going to guess at it. The most plausible
candidate is the **known Patchwork++ singleton determinism bug** — the scored
population shifts slightly between replays, and ring 1 may simply be the ring
most sensitive to that — but I have not tested it and it should not be written
down as the cause. The practical consequence is bounded: the ring-1 *comparison*
above is shipped-vs-proposed within one harness, so it is internally valid, but
the ring-1 *absolute* numbers should not be quoted against the published table
until this is resolved. **It is also a live reason to fix the determinism bug
before any further accuracy work** — an eval harness that does not reproduce its
own published numbers to the last digit cannot adjudicate a 0.3 cm question.

## 3b. R7: hazard misses move the wrong way, but the denominators are too small to prove it

**The R7 harness was reproduced exactly** before any comparison was drawn —
support, non-drivable count and misses all match the published table on all
three sequences:

| seq | published support / non-drivable / misses | measured | |
|---|---|---|---|
| 07 | 1,724 / 19 / 8 | **1,724 / 19 / 8** | PASS |
| 08 | 1,917 / 3 / 0 | **1,917 / 3 / 0** | PASS |
| 00 | 1,914 / 38 / 4 | **1,914 / 38 / 4** | PASS |

Recovering it took two corrections, both recorded in §5: the window sits
*behind* the vehicle, and **"non-drivable" is `TRAV_SLOPE | TRAV_STEP` only** —
equivalently `isinf(cost)`, the hard-impassable cells. `TRAV_ROUGHNESS` and
`TRAV_CLASS` are *not* part of it. That is worth writing down; it was not
recorded anywhere and four other plausible bit masks give four different
answers. (One small residual: seq 07's false alarms read 74 against the
published 71. Support, non-drivable and misses are exact, so I have not chased
the difference, but it is not a perfect reproduction.)

### Reference held FIXED at the shipped mask — the meaningful comparison

| seq | map built with | non-drivable | misses | miss rate | false alarms |
|---|---|---|---|---|---|
| 07 | shipped | 19 | 8 | 42.11% | 74 |
| 07 | **proposed** | 19 | **10** | **52.63%** | 77 |
| 08 | shipped | 3 | 0 | 0.00% | 4 |
| 08 | **proposed** | 3 | **0** | 0.00% | 4 |
| 00 | shipped | 38 | 4 | 10.53% | 59 |
| 00 | **proposed** | 38 | **5** | **13.16%** | 52 |

**Misses increase on both sequences that have hazards to miss**, and never
decrease. Direction is consistent with the RMSE result.

### [!] But this does not carry the argument, and it must not be quoted as if it does

**The denominators are 19, 3 and 38** — R7's whole point. The 95% interval for
the shipped 8/19 is [23.1%, 63.7%], and the proposed 10/19 = 52.63% sits
*inside* it. **This difference is not statistically significant.** Two extra
missed cells on a denominator of 19 is not evidence, and "0 of 3" on seq 08 was
never evidence of anything.

The rejection in §4 rests on the ring-0 and ring-1 RMSE — which are large,
unambiguous and reproduce — **not on R7.** R7 is corroborating direction only.

### [!] A methodological trap worth recording

Rebuilding M\* with the proposed mask as well gives a *different and flattering*
answer on seq 07:

| seq | | shipped | proposed (M\* rebuilt too) |
|---|---|---|---|
| 07 | non-drivable in M\* | 19 | **16** |
| 07 | misses | 8 | **7** |
| 00 | non-drivable in M\* | 38 | **40** |
| 00 | misses | 4 | **10** |

Seq 07's miss count *improves* (8 -> 7) — but only because **M\* itself lost
three non-drivable cells** (19 -> 16). The degraded ground mask makes the
reference blind to hazards, and a reference that cannot see a hazard cannot
record a miss against it.

**So a worse ground mask can look like a safer map.** Any future A/B on the
ground mask must hold M\* fixed at the best available mask, or it will score
its own degradation as an improvement. This is the same family of error as the
ground-mask-less M\* that read 22.10 cm on seq 07 — the artifact you measure
against cannot be built from the thing under test.

## 4. Recommendation

**Reject the `num_iter=2` tradeoff.** Reasons, in order:

1. **19-54% worse ring-0 RMSE** for 5.42 ms. On seq 07 that is 1.77 -> 2.74 cm,
   and ring 1 degrades with it (3.04 -> 4.75 cm, +56%).
2. **The error concentrates on slopes** (2.3-4.5× flip rate), which is both the
   hardest terrain and a direct traversability input.
3. **Hazard misses increase** on both sequences that have hazards — 8 -> 10
   (seq 07) and 4 -> 5 (seq 00) against a fixed reference, never decreasing.
   Not significant at these denominators (§3b), but the direction agrees.
4. **It does not fix p99 anyway** (120-147 ms against a 100 ms budget, unmoved
   by every parameter tested), so it does not deliver the 10 Hz claim even if
   the accuracy cost were acceptable.

`num_iter` is the right knob to have found — it is the only parameter with a
real latency payoff — but at 3 it is buying something. The library default is
not conservative padding here.

### What is still worth taking from the proposal

- **Pin `pypatchworkpp` to `==1.4.1`.** Independent of this rejection. 1.4.1 is
  both the fastest installable version (18.58 ms vs 23.8-25.1 for 1.2.0-1.4.0)
  and removes a free variable from every cross-machine comparison.
- **`enable_TGR`** measured 0.00% flipped and −0.24 ms — genuinely nothing on
  either side. Leave it alone; there is no win to take.

### If latency still has to come out of `ground`

Do not look for it in the fit parameters. The measured options are all bad
trades. The remaining directions, none measured here:

- **Cache the mask across frames** for static regions rather than re-segmenting
  every return every frame. This is a design change, not a parameter, and it
  interacts with the known singleton/determinism bug — which must be fixed
  first, not worked around.
- **Find the p99 cause instead.** A 30-45 ms p99 overshoot is a larger prize
  than 5 ms of p50 and nothing in this investigation located it. That is where
  the next effort belongs.

---

## 5. Reproduce

Scratch harnesses, session-local, not committed (measurement, not deliverables):

- `scratchpad/numiter_accuracy.py` — ring-0 gate and comparison.
- `scratchpad/flip_location.py` — direction, class, slope, curb, range cuts.
- `scratchpad/numiter_r1_r7.py` — R1 per-ring table.
- `scratchpad/numiter_r7.py` — R7 with the canonical planning window.
- `scratchpad/dump_costmaps.py` + `find_r7_predicate.py` — dumps the costmaps
  once so drivability predicates can be searched without a 12-minute rebuild.

Requires `VRGRID_DATA_ROOT=C:/KITTI/dataset`.

Two traps worth recording for whoever runs these next:

- **`height_rmse_per_ring` returns centimetres and a `{ring: rmse}` dict.**
  Multiplying by 100 gives a table that is exactly 100x out but otherwise
  plausible; iterating the return value yields the ring *indices* (0, 1, 2, 3),
  which looks like a clean ascending RMSE curve and is not one. Both mistakes
  produced believable-looking tables here before the gate caught them.
- **The planning window is not centred on the vehicle.**
  `eval_synthetic.costmaps_for` places it at `x0 = vx - 11.0`, `y0 = vy - 5.5`,
  44x44 — i.e. entirely *behind* the vehicle, over ground it has actually
  driven and therefore observed — and passes `vehicle_xy_m` to
  `costmap_from_gridmap`. Centring it instead drops support from 1,724 to 955 on
  seq 07, because half the window is ground the map never saw.
