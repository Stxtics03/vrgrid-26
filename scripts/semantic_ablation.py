#!/usr/bin/env python3
"""What the map loses when semantics come from FRNet instead of ground truth.

    python scripts/semantic_ablation.py --seq 08 --frames 500 --fast-scatter

The pipeline reads its 19-class semantic label from the SemanticKITTI `.label`
files on purpose, so that §9's evaluation measures the MAPPING contribution and
not somebody's segmentation. Everywhere that decision is written down it is
stated as a disclaimer -- "the mapping contribution is evaluated independently
of segmentation quality" -- and a disclaimer is a promise, not a measurement.
This script measures it: how far does the map actually move when the labels
come from the model instead of the ground truth?

⚑ THIS IS AN ABLATION, NOT A PIPELINE CHANGE. CLAUDE.md's "don't run inference
  for labels" governs the shipping path and still does; nothing here is wired
  into `python -m vrgrid.run`, and the reported map is the ground-truth one.
  The DL half is reported ALONGSIDE the map, and this is the one number that
  connects them.

⚑ ONE PERCEPTION PASS, TWO MAPS. Both engines are fed the SAME
  `PerceptionFrame` -- same points, same poses, same Patchwork++ ground, same
  motion flags -- with only `semantic` swapped. Running the sequence twice
  instead would let frame-to-frame nondeterminism anywhere in perception leak
  into the difference and be read as segmentation error.

⚑ WHAT IS NOT SWAPPED, AND WHY IT MATTERS TO THE READING. FRNet predicts the
  19 semantic classes and nothing else. The `moving-*` motion flag has no
  counterpart in the model, so it stays ground truth in BOTH maps -- which
  means ghost removal is identical by construction and this measures the
  semantic layer alone. Ground is Patchwork++, geometric, and never consults
  semantics while Patchwork++ is on. Both facts are asserted below, not
  assumed: `--no-patchworkpp` falls back to a SEMANTIC ground proxy and would
  silently make ground part of the difference, so it is refused.

⚑ THE SAFETY-RELEVANT NUMBER IS NOT THE AGREEMENT RATE. A cell the ground-truth
  map calls untraversable and the FRNet map calls traversable is a place the
  planner would drive into. That direction is counted separately and is the
  number to put on a slide; a symmetric "97% of cells agree" hides it.
"""
import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from vrgrid.grid import schedule as schedule_mod
from vrgrid.grid import traversability
from vrgrid.grid.fusion import unpack_class
from vrgrid.run.__main__ import iter_pipeline
from vrgrid.run.engine import MapEngine

#: FRNet's own ignore slot. `semantics.semantic_labels` spells the same thing
#: -1, and the engine maps anything negative to 0 -- so the two label sources
#: must be brought to the SAME convention before either reaches the map, or
#: the difference measured here would include a bookkeeping mismatch.
FRNET_IGNORE = 19


def build_model(checkpoint: Path, device: str):
    """Exactly the construction scripts/frnet_eval.py uses. See its header for
    why the FOV constants are the checkpoint's projection and not the sensor's."""
    import torch
    from vrgrid.perception import semantics
    from vrgrid.perception.frnet import FRNet

    model = FRNet(num_classes=20, ignore_index=FRNET_IGNORE, output_shape=(64, 512),
                  fov_up=semantics.FRNET_TRAIN_FOV_UP_DEG,
                  fov_down=semantics.FRNET_TRAIN_FOV_DOWN_DEG)
    blob = torch.load(checkpoint, map_location="cpu", weights_only=False)
    missing, unexpected = model.load_state_dict(blob.get("state_dict", blob), strict=False)
    model.to(device).eval()
    print(f"{checkpoint.name} on {device}: {len(missing)} missing, "
          f"{len(unexpected)} unexpected tensors (auxiliary heads are training-only)")
    return model


def rings_of(engine: MapEngine):
    """(slice, side) per ring, the shape `traversability.update` wants."""
    return [(slice(r.offset, r.offset + r.side * r.side), r.side)
            for r in engine.handle.rings]


def cell_classes(soa) -> np.ndarray:
    """The §10.2 class candidate per slot, through `unpack_class` never a shift.

    Takes the SoA dict, not the engine: `semantic_class` packs the id with the
    §10.2 counter in one field, and reading it with a literal shift is the bug
    that makes every drivable class fail the drivable-set test.
    """
    return unpack_class(soa["semantic_class"])[0].astype(np.int32)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", default="08")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--schedule", default="5/10/20/40")
    ap.add_argument("--checkpoint", default="checkpoints/frnet-semantickitti_seg.pth")
    ap.add_argument("--fast-scatter", action="store_true",
                    help="torch.scatter_reduce for the frustum reductions; without "
                         "it FRNet costs ~10.5 s a frame and this run takes hours")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    import torch

    if args.fast_scatter:
        sys.path.insert(0, str(Path(__file__).parent))
        from frnet_fast_scatter import enable
        enable(verify=True)

    ckpt = Path(args.checkpoint)
    if not ckpt.exists():
        print(f"checkpoint not found: {ckpt}", file=sys.stderr)
        return 2
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model(ckpt, dev)

    sched = schedule_mod.load(args.schedule)
    gt_engine = MapEngine(sched)
    dl_engine = MapEngine(sched)
    print(f"schedule {sched.name}: {len(sched.rings)} rings, {sched.total_cells:,} cells")
    print(f"two maps, {gt_engine.handle.allocated_slots:,} slots each; "
          f"semantics is the ONLY input that differs\n")

    pt_agree = pt_total = 0
    frames = 0
    for frame in iter_pipeline(args.seq, args.frames, use_patchworkpp=True):
        if frame.ground_method != "patchworkpp":
            print(f"[!] ground fell back to {frame.ground_method}, which consults "
                  f"SEMANTICS -- ground would become part of the measured difference. "
                  f"Install pypatchworkpp and rerun.", file=sys.stderr)
            return 2

        with torch.no_grad():
            pred = model.predict(
                [torch.from_numpy(frame.points_sensor).float().to(dev)])[0].cpu().numpy()
        # Bring FRNet's ignore slot to the loader's convention before the map
        # sees it, so the engine's `semantic < 0 -> 0` rule applies identically
        # to both sources and no part of the difference is bookkeeping.
        pred = np.where(pred >= FRNET_IGNORE, -1, pred).astype(frame.semantic.dtype)

        ok = frame.semantic >= 0
        pt_agree += int((pred[ok] == frame.semantic[ok]).sum())
        pt_total += int(ok.sum())

        gt_engine.step(frame)
        dl_engine.step(replace(frame, semantic=pred))
        frames += 1
        if frames % 100 == 0:
            print(f"  frame {frame.index}: {frames} folded, "
                  f"point agreement so far {pt_agree / max(pt_total, 1):.1%}")

    if not frames:
        print("no frames", file=sys.stderr)
        return 1

    for eng in (gt_engine, dl_engine):
        traversability.update(eng.handle.grid, sched, rings_of(eng), eng.thresholds)

    gt, dl = gt_engine.handle.grid, dl_engine.handle.grid

    # ⚑ The controls come FIRST. If height, observation count or occupancy moved
    #   at all, then something other than the semantic layer differs between the
    #   two runs and every number below it is measuring the wrong thing.
    print(f"\n{frames} frames of sequence {args.seq}\n")
    print("controls -- these must be identical, or the ablation is not isolated:")
    controls_ok = True
    for field in ("ground_height", "ceiling_height", "obs_count", "log_odds"):
        same = np.array_equal(gt[field], dl[field])
        controls_ok &= same
        print(f"  {field:<16} {'identical' if same else '*** DIFFERS ***'}")
    if not controls_ok:
        print("\n[!] a control moved: the two maps differ by more than semantics. "
              "Every number below is unsafe to quote.", file=sys.stderr)
        return 1

    observed = np.asarray(gt["obs_count"]) > 0
    n_obs = int(observed.sum())
    gt_cls, dl_cls = cell_classes(gt), cell_classes(dl)
    cls_agree = int((gt_cls[observed] == dl_cls[observed]).sum())

    gt_trav = traversability.is_traversable_bits(gt["traversability"])[observed]
    dl_trav = traversability.is_traversable_bits(dl["traversability"])[observed]
    flips = gt_trav != dl_trav
    false_safe = int((~gt_trav & dl_trav).sum())     # GT blocked, FRNet says go
    false_block = int((gt_trav & ~dl_trav).sum())    # GT clear, FRNet says stop

    print(f"\npoints:  FRNet agrees with the .label files on "
          f"{pt_agree / pt_total:.1%} of {pt_total:,} labelled points")
    print(f"cells:   {n_obs:,} observed of {gt['obs_count'].size:,} slots")
    print(f"         class agreement {cls_agree / n_obs:.1%}")
    print("\n§7.1 traversability decision, the thing a planner consumes:")
    print(f"  cells that flip           {int(flips.sum()):>10,}  {flips.mean():>7.2%}")
    print(f"  ⚑ FALSE-SAFE              {false_safe:>10,}  {false_safe / n_obs:>7.2%}"
          f"   GT says blocked, FRNet says drivable")
    print(f"  false-blocked             {false_block:>10,}  {false_block / n_obs:>7.2%}"
          f"   GT says drivable, FRNet says blocked")
    print(f"  agreement                 {int((~flips).sum()):>10,}  {(~flips).mean():>7.2%}")

    # ⚑ From configs/thresholds.yaml through traversability.drivable_ids, never
    #   an inline list. The drivable set is frozen before schedules are compared
    #   (CLAUDE.md), and a private copy of it here would go stale silently and
    #   quote a §7.1 number for a set §7.1 no longer uses.
    ids = traversability.drivable_ids(gt_engine.thresholds)
    by_id = {i: n for n, i in traversability.class_ids().items()}
    names = ", ".join(by_id[int(i)] for i in ids)
    gt_drive = np.isin(gt_cls[observed], ids)
    dl_drive = np.isin(dl_cls[observed], ids)
    print(f"\ndrivable-class cells ({len(ids)} from thresholds.yaml: {names}):")
    print(f"  ground truth              {int(gt_drive.sum()):>10,}")
    print(f"  FRNet                     {int(dl_drive.sum()):>10,}"
          f"   {(int(dl_drive.sum()) - int(gt_drive.sum())) / max(int(gt_drive.sum()), 1):>+7.2%}")
    print(f"  both                      {int((gt_drive & dl_drive).sum()):>10,}")

    print("\nGhost removal and heights are identical by construction: the motion flag "
          "\nhas no counterpart in FRNet and stays ground truth in both maps, and "
          "\nheights do not depend on class. This isolates the semantic layer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
