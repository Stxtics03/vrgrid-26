#!/usr/bin/env python3
"""Is the estimated motion flag any good? Scored against `moving-*`. [Shrestha]

    python scripts/motion_eval.py --seq 08 --frames 200

`perception.motion.estimate_moving` replaces SemanticKITTI's ground-truth
motion flag with a free-space violation against the previous scan, so that a
`--semantics frnet` run is not quietly taking motion from the label file. This
prices it: precision, recall and F1 against those same `moving-*` ids, which
are the only ground truth there is.

⚑ RECALL WILL BE LOW AND THAT IS STRUCTURAL, not a tuning failure. A two-frame
  free-space test cannot see an object that never entered space the previous
  scan observed as empty -- a vehicle ahead holding its distance is invisible
  to it, and a receding one is deliberately not flagged (motion.py says why).
  Read precision first: it answers "when this says moving, is it?", which is
  the question that matters for a map that is about to delete cells.

⚑ Ground truth here counts every point of a `moving-*` object, including the
  far side of a car that has not swept any new space. Nothing geometric can
  recover those from two frames, so the recall ceiling is well under 100% and
  this number should never be compared against a tracker's.
"""
import argparse
import json
import warnings
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", default="08")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--floor", type=float, default=0.30,
                    help="pose-error floor on the range agreement band, metres")
    ap.add_argument("--no-ground-mask", action="store_true",
                   help="do NOT exclude ground returns -- shows what the mask buys")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    warnings.simplefilter("ignore")
    from vrgrid.perception import (
        ground as ground_mod,
    )
    from vrgrid.perception import loader, motion, semantics, transforms
    ground_mod.reset_estimator()

    tp = fp = fn = tn = 0
    prev_world = None
    frames = 0
    per_frame = []
    for i, (points, labels, pose) in enumerate(
            loader.scans(args.seq, max_frames=args.frames)):
        t_s_w = transforms.sensor_to_world(pose, sequence=args.seq)
        gmask, _ = ground_mod.segment_ground_or_fallback(
            points, semantics.semantic_labels(labels), use_patchworkpp=True)
        est = motion.estimate_moving(points, prev_world, t_s_w, floor_m=args.floor,
                                     ground_mask=None if args.no_ground_mask else gmask)
        gt = semantics.is_moving(labels)
        if i:                       # frame 0 has no previous scan; not scored
            tp += int((est & gt).sum())
            fp += int((est & ~gt).sum())
            fn += int((~est & gt).sum())
            tn += int((~est & ~gt).sum())
            per_frame.append({"frame": i, "est": int(est.sum()), "gt": int(gt.sum())})
            frames += 1
        prev_world = transforms.transform_points(points[:, :3], t_s_w)

    if not frames:
        print(f"no frames read for sequence {args.seq} -- is VRGRID_DATA_ROOT set?")
        return 1

    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if tp else float("nan")
    total = tp + fp + fn + tn
    print(f"\nsequence {args.seq}, {frames} scored frames "
          f"(frame 0 excluded: no previous scan), floor {args.floor} m\n")
    print(f"  true positives   {tp:>12,}")
    print(f"  false positives  {fp:>12,}")
    print(f"  false negatives  {fn:>12,}")
    print(f"  true negatives   {tn:>12,}")
    print(f"\n  precision  {prec:>8.1%}   when it says moving, how often it is")
    print(f"  recall     {rec:>8.1%}   of truly moving points, how many it finds")
    print(f"  F1         {f1:>8.1%}")
    print(f"\n  moving points are {(tp + fn) / total:.2%} of all returns, so a "
          f"detector that\n  never fires scores {1 - (tp + fn) / total:.2%} accuracy. "
          f"Accuracy is the wrong metric here.")
    if args.out:
        Path(args.out).write_text(json.dumps(
            {"sequence": args.seq, "frames": frames, "floor_m": args.floor,
             "tp": tp, "fp": fp, "fn": fn, "tn": tn,
             "precision": prec, "recall": rec, "f1": f1}, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
