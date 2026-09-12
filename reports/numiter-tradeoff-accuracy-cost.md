# The accuracy cost of the `num_iter=2` latency tradeoff

**Verdict: do not apply it.** The 5.42 ms latency win costs **19-54% of ring-0
elevation RMSE**, and the flipped ground verdicts concentrate on **sloped
ground** — where a wrong ground verdict does the most damage. Curbs are clean.

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

## 4. Recommendation

**Reject the `num_iter=2` tradeoff.** Reasons, in order:

1. **19-54% worse ring-0 RMSE** for 5.42 ms. On seq 07 that is 1.77 -> 2.74 cm.
2. **The error concentrates on slopes** (2.3-4.5× flip rate), which is both the
   hardest terrain and a direct traversability input.
3. **It does not fix p99 anyway** (120-147 ms against a 100 ms budget, unmoved
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
- `scratchpad/numiter_r1_r7.py` — R1 per-ring and R7 hazard-miss comparison.

Requires `VRGRID_DATA_ROOT=C:/KITTI/dataset`.
