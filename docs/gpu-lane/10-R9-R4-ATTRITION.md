# R9's missing rows, R4's cost, and stage attrition

*Shrestha, 2026-09-17. Roadmap Days 1, 4 and 7 in the GPU/CUDA column
(`VRgrid-10-Day-Roadmap.docx`), for the items that do not need AWS. All on the
RTX 5050 laptop, real SemanticKITTI seq 08.*

## 1. R9: split/merge and the pyramid (Day 1)

`timing_table.py --seq` covered ground, scatter and fuse, and printed
split/merge as "absent". R9 asks for split/merge and the pyramid too. Neither
runs in `MapEngine`'s frame loop. The refinement pool that splits cells lives in
the eval harness's map, and the pyramid reduces the §7.1 layer that only the
harness updates. So `scripts/r9_stages.py` drives `harness.run_sequence` and
times the real `gate.apply`, `traversability.update` and `pyramid.build` calls
on the same frames. It reimplements nothing.

```
python scripts/r9_stages.py --seq 08 --frames 200     # 10 warm-up frames discarded

  stage             p50 ms   p99 ms   max ms     n
  split_merge        49.59    63.50    67.79   200
  traversability     37.35    49.22    53.32   200
  pyramid             2.81     3.72     4.78   200

  refinement pool per frame (p50 / max): fired 4104/4923  acquired 141/522  released 5/115  refused 3492/4125
  pool occupancy at the end: 512/512 blocks
  pyramid memory: 2.73 MB nodes + 0.38 MB scratch
```

**What this says, plainly.** The pyramid is cheap: 2.8 ms, 36× headroom. **The
refinement pool and the §7.1 pass are not.** Together they are 87 ms p50, four
times the whole 22 ms CUDA frame. The pool is full after a few frames and then
refuses about 3,500 gate requests a frame, while still paying to evaluate every
one in a Python per-cell loop. If both are enabled in a deployed 10 Hz pipeline,
**they, not the GPU frame, set the latency.** Both are CPU-only NumPy/Python in
`src/grid` today. Moving them onto the card, or making the gate stop
re-evaluating refused cells, is the obvious next GPU item. Flagged here, not
started.

## 2. R4: what the block-level ring rule costs in cells (Day 4)

The roadmap's gate is "0 overlapping footprints, cost ~0.1% cell increase,
8.94 MB unchanged". Overlaps are 0 by CI test (`known-limitations.md` §8). The
cost was never measured. Distinct cells written per frame, seq 08, 40 frames,
the old per-point rule (`6af6907`) against the per-block rule, same points,
same windows:

| ring | old | new | change |
|---|---|---|---|
| 0 | 29,105 | 29,005 | −0.34% |
| 1 | 23,148 | 23,144 | −0.02% |
| 2 | 9,514 | 9,489 | −0.26% |
| 3 | 2,176 | 2,198 | +1.01% |
| **all** | **63,944** | **63,837** | **−0.17%** |

The cost is effectively zero, slightly negative overall. The old figure includes
cells for returns the old rule then dropped at the window, which the new rule
keeps in a coarser ring instead. **8.94 MB cannot move:** every ring is
preallocated at its fixed half-width, whatever the ring rule decides.

## 3. Stage attrition (Day 7, Rule 3)

`MapEngine(attrition=True)` counts, per frame, the pipeline stage where each
return ends. The counts are identical on CPU and CUDA every frame, and
`gpu_parity.py` now compares them. `engine.attrition_codes()` returns the
per-point stage as `uint8`. That is the input for the "examined and rejected vs
never reached" map colouring in Aakash/Srinivas's Day 7 column (`gpu/attrition.py`).

| terminal stage | meaning |
|---|---|
| capped | beyond `max_points`, never binned |
| outside_map | past the coarsest ring's window |
| nonground | in the map; occupancy, class and ceiling only, no height |
| ground_out_of_band | ground, in the map, outside the 8 m band; height weight 0 |
| ground_fused | ground, in the map, height fused |

Seq 08, 200 frames (`gpu_parity.py --seq 08 --frames 200`):

```
capped 0.00%   outside_map 0.00%   nonground 36.65%   ground_out_of_band 0.18%   ground_fused 63.17%
beside the chain: moving 1.94%, projected 20.92%
```

**The number worth a slide is `projected`.** Only **20.9% of returns win a
64 × 512 range-image pixel.** The other 79% never feed §10.4's current-return
guard or reflectivity. That is exactly the "never reached the stage" share
Rule 3 says to publish next to any cleanup or reflectivity number. Nothing is
lost from the MAP: capping and out-of-map are both 0.00% on seq 08, and 99.8%
of in-map returns reach fusion. Tested in `tests/test_attrition.py`, including
CPU and CUDA agreement return by return.

## Still open in this column

- **AWS (Days 1, 2, 6, 9):** scripted in `scripts/aws/t4.sh`. Waiting for AWS
  credentials on this machine; the account is on the Free plan.
- **Day 5 kernel side of R5 (sticky VRU bit):** R5's design is JP and Hriday's,
  and not written yet.
- **Day 8 ROS-loop re-profile:** needs Aakash and Srinivas's ROS adapter.
