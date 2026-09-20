# Getting motion segmentation to actually work: what the literature says

Written after `perception/motion.py` scored 16.3% precision / 15.0% recall on
seq 08 and the obvious fixes made it worse. This is the research on why, and
what to do instead.

## The one sentence that matters

**Nobody thresholds a residual. They feed it to a network as an input channel.**

Every hand-tuned rule tried here failed, and the failures were informative
rather than random:

    absolute, one-directional, ground excluded   P 36.4%  R 15.8%  F1 22.1%  (60 frames)
    the same over 200 frames                     P 16.3%  R 15.0%  F1 15.6%
    raising the tolerance to 0.5 / 1 / 2 m       P falls to 23 / 17 / 10%
    range-normalised |r_now - r_prev| / r_now    P ~10-12% at every threshold

That last one is the literature's own residual formula, thresholded directly,
and it is WORSE than the cruder absolute rule. The formula is not the problem.
Using it as a decision instead of as a feature is the problem.

## The established approach: residual images as network channels

`LiDAR-MOS` (Chen et al., RA-L 2021) is the foundational method and it is
directly applicable here because it is range-image based, which is what FRNet
already is.

Procedure:

1. Transform the previous scan `S_j` into the current frame with the pose
   `T_0^j` -- ego-motion compensation, which `motion.py` already does.
2. Re-project it into the current range image.
3. Per pixel, `d = |r_i - r_{j->0,i}| / r_i`, normalised by the CURRENT range,
   which makes the indicator scale invariant.
4. **Concatenate the residual images as extra input channels** to a
   range-projection segmentation network, and retrain with binary
   moving/non-moving labels.

Measured on SemanticKITTI-MOS validation, with SalsaNext as the backbone:

    single frame, no residual                51.9 IoU
    + N=1 residual image                     59.9 IoU     <- +8.0 from one channel
    concatenating raw previous frames        56.0 IoU     <- residuals beat raw frames
    N=8 residuals + semantic filtering       62.5 IoU (test)

So **one residual channel through a network is worth +8 IoU**, and the same
quantity through a threshold is worth nothing. That is the whole finding.

## Where the field is now

    MapMOS      86.1 IoU (val)   map-based, Bayes-filter belief fusion
    LiDAR-IMU-GNSS  79.0
    Two-streamMOS   77.9
    MF-MOS          76.7 (test, SOTA at time of writing)
    InsMOS          75.6
    RVMOS           74.7

## Why this project is unusually well placed

Three things are already built that these methods need:

- **A range-image network with a working checkpoint.** FRNet is exactly the
  kind of backbone LiDAR-MOS adapts (they used RangeNet++, SalsaNext, MINet).
  Adding input channels and a binary head is a fine-tune, not a new model.
- **The residual machinery.** `motion.estimate_moving` already does the pose
  transform, the re-projection and the per-point range comparison. It needs
  its output routed into a tensor instead of a threshold.
- **Training labels.** The `moving-*` ids in sequences 00-10 ARE the
  SemanticKITTI-MOS labels. No new annotation.

And one thing that is a genuine differentiator rather than a reimplementation:

**MapMOS's best idea is already half-built here.** It fuses per-scan MOS
predictions into a volumetric belief with a Bayes filter, which is what lifts
it from ~77 to 86 IoU. This project's grid already fuses occupancy in
LOG-ODDS over time (math 10.1) and already has a transient layer. Feeding
per-scan moving probabilities into that existing fusion is a small change to
something that exists, and it is the part of the story that is ours rather
than borrowed -- a variable-resolution grid whose cells carry a dynamic-object
belief, coarsening with range like everything else in it.

## The concrete plan, cheapest first

1. **Residual channels into FRNet, N=1.** Extend the input to carry the
   residual image alongside range, retrain the head on binary moving/static
   from the `moving-*` ids. The literature says +8 IoU from this single
   channel. Fine-tuning takes minutes on the T4 at 4,000 steps, which the
   training curve already established as the useful window.
2. **N=4 or N=8 residuals** if step 1 pays, following the ablation.
3. **Fuse into the grid's log-odds** rather than per-scan thresholding. This
   is the MapMOS lesson and the project's own novelty.

Step 1 is the one to do first: it is a fine-tune of a working network on labels
already on disk, and it replaces a 16%-precision rule with something the
literature puts near 60 IoU.

## What NOT to do

- Do not tune the threshold. Four sweeps say it does not move.
- Do not describe `motion.estimate_moving` as motion detection. It is a
  free-space violation test, its recall is structurally capped, and it should
  be kept as the geometric baseline the learned version is measured against.

## Sources

- Chen et al., "Moving Object Segmentation in 3D LiDAR Data: A Learning-based
  Approach Exploiting Sequential Data", RA-L 2021 -- arXiv:2105.08971
- Mersch et al., "Building Volumetric Beliefs for Dynamic Environments
  Exploiting Map-Based Moving Object Segmentation", RA-L 2023 --
  arXiv:2307.08314, github.com/PRBonn/MapMOS
- Cheng et al., "MF-MOS: A Motion-Focused Model for Moving Object
  Segmentation", 2024 -- arXiv:2401.17023
