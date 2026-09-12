# src/perception — JP

- **Frames.** Vehicle frame is x forward, y left, z up. Every transform you
  write goes in `docs/frames.md` in the same commit — origin, axes,
  handedness, units. Frame confusion is the most common silent bug here: the
  map looks plausible and slowly rotates. Run the static-wall test on Day 0.
- **Wire things in, do not rebuild them.** Patchwork++ for ground, KISS-ICP
  for odometry. The standalone FRNet port in `frnet/` **works as of 2 Sep** —
  **90.3% point accuracy and 65.2% mIoU over 200 frames of seq 08**, against
  the paper's 73.3%. (65.2% is THE figure. 69.8% -- still in the handover, the
  runbook and `perception-dashboard-summary.md:150` -- is an arithmetic error,
  not a denominator choice: it divides the same 15 per-class IoUs by 14,
  dropping `other-ground`, which has 150 GT points and IoU 0.0% and is
  therefore present and countable (research-log.md, 3 Sep).
  **98.3% is a single-frame port sanity check, seq 00 frame 43** — not the
  headline, and not comparable to a 200-frame mIoU.) It is still not the map's
  semantic source, and that is a choice rather than a defect: GT `.label` files
  isolate the mapping contribution from segmentation quality. Run it with
  `scripts/frnet_eval.py`; report it alongside the map, never swapped into it.
- **The FOV bug was in `semantics.py`, not in `frnet/`.** `configs/frnet.yaml`
  carries the HDL-64E's *physical* vertical FOV (2.0 / −24.8) for the range
  image; the checkpoint learned a *fixed* spherical projection (3.0 / −25.0).
  They are different quantities and feeding the first to the model was one of
  the three things that held it at ~15%. The training values are pinned as
  `FRNET_TRAIN_FOV_UP_DEG` / `_DOWN_DEG` where a sensor config cannot reach
  them — do not re-plumb them from a config.
- **Both semantic class and motion are ground truth**, read from the raw
  `.label` files: 19-class semantic via `semantics.semantic_labels()`, motion
  (`moving-*`, IDs 250-259) via `semantics.is_moving()`. Disclose it; it
  isolates the mapping contribution from segmentation error, which is what a
  careful evaluator wants. Zero training, zero inference.
- **Dataset:** all 22 SemanticKITTI sequences are on disk — **43,552 scans,
  84.8 GB** — with point-wise `.label` files on **sequences 00 through 10
  only**; 11–21 are the unlabelled test split. `python scripts/data_status.py`
  re-verifies and exits 0 when whole. Cache format is yours to choose, but it
  must be deterministic — the same sequence must produce byte-identical inputs
  twice.
- **Units.** Ranges and gradients are float metres, heights are int16 in 1 cm.
  Suffix every variable `_m` or `_cm`. Never mix silently.
- **Checkpoint and dataset paths live in `configs/`**, never inline.
