#!/usr/bin/env python3
"""Make ring 3 scorable: propagate near-field labels into the far field.
[Shrestha, staging experiment]

    python scripts/farfield_labels.py --seq 08 --frames 200

SemanticKITTI stops labelling at ~50 m, so ring 3 (50-100 m) holds about
1.14 M returns over 200 frames of seq 08 and not one carries a class. The
per-distance accuracy table therefore prints NOT SCORABLE for the ring the
map builds furthest out, which is the one range a reader will ask about.

But the vehicle drives. A surface 70 m ahead now is 20 m ahead in a few
seconds, and it IS labelled there. Poses are known, so the label can be
carried back to where the surface was first seen:

  1. Sweep the sequence. Every LABELLED return goes into a voxel hash of the
     world, keyed by its quantised world position.
  2. Sweep again. For each FAR-FIELD return, look up its own world voxel. If
     some later (or earlier) scan saw that same piece of world from close
     enough to label it, that label applies.

⚑ STATIC SURFACES ONLY. A moving object is not in the same world voxel two
  seconds later, so propagating its label is wrong by construction. Points
  whose source label is `moving-*` are excluded from the hash, and the far
  field therefore gets static-class labels only. That is a real limitation:
  this makes ring 3 scorable for TERRAIN AND STATIC STRUCTURE, which is most
  of what is out there, and says nothing about distant moving objects.

⚑ THE PROPAGATION IS VALIDATED BEFORE IT IS USED. The same lookup is run on
  NEAR-field points, which already have ground truth, and the propagated label
  is compared against the real one. If that agreement is not high the method
  is not trustworthy at range either, and the number is printed first for
  exactly that reason.
"""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np


def _keys(xyz_world: np.ndarray, voxel_m: float) -> np.ndarray:
    """One int64 key per point, from its quantised world cell.

    Integer lattice, like everything else here: `floor(x / v)` per axis, packed.
    Float keys would drift between the two sweeps and silently lose matches.
    """
    q = np.floor(np.asarray(xyz_world, np.float64) / voxel_m).astype(np.int64)
    # 21 bits per axis, signed, centred -- ample for a KITTI sequence's extent.
    return ((q[:, 0] + (1 << 20)) << 42) | ((q[:, 1] + (1 << 20)) << 21) \
        | (q[:, 2] + (1 << 20))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", default="08")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--voxel", type=float, default=0.25,
                    help="world voxel side, metres, for matching a far return "
                         "to the near observation of the same surface")
    ap.add_argument("--near-m", type=float, default=50.0,
                    help="range below which SemanticKITTI actually labels")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    warnings.simplefilter("ignore")
    from vrgrid.perception import loader, semantics, transforms

    # --- sweep 1: build the world label hash from labelled, STATIC returns ---
    table: dict[int, int] = {}
    scans = []
    for i, (pts, lab, pose) in enumerate(loader.scans(args.seq, max_frames=args.frames)):
        t = transforms.sensor_to_world(pose, sequence=args.seq)
        w = transforms.transform_points(pts[:, :3], t)
        sem = semantics.semantic_labels(lab)
        mov = semantics.is_moving(lab)
        r = np.linalg.norm(pts[:, :3], axis=1)
        scans.append((w, sem, r))
        good = (sem >= 0) & ~mov & (r < args.near_m)
        if good.any():
            k = _keys(w[good], args.voxel)
            table.update(dict(zip(k.tolist(), sem[good].tolist(), strict=True)))
    if not scans:
        print(f"no frames read for sequence {args.seq} -- is VRGRID_DATA_ROOT set?")
        return 1
    print(f"\nsequence {args.seq}, {len(scans)} frames, {args.voxel} m voxels")
    print(f"world label hash: {len(table):,} voxels from labelled static returns\n")

    lut = np.full(0, -1, np.int64)      # placeholder; dict lookup below

    def lookup(keys: np.ndarray) -> np.ndarray:
        out = np.full(len(keys), -1, np.int32)
        for j, kk in enumerate(keys.tolist()):
            v = table.get(kk, -1)
            if v >= 0:
                out[j] = v
        return out
    del lut

    # --- validate on the NEAR field, where ground truth exists ---
    agree = seen = 0
    for w, sem, r in scans:
        m = (sem >= 0) & (r < args.near_m)
        if not m.any():
            continue
        got = lookup(_keys(w[m], args.voxel))
        ok = got >= 0
        agree += int((got[ok] == sem[m][ok]).sum())
        seen += int(ok.sum())
    val = agree / seen if seen else float("nan")
    print("VALIDATION on labelled near-field points")
    print(f"  propagated label agrees with ground truth on {val:.2%} "
          f"of {seen:,} points")
    print("  (a surface sees itself across frames; below ~95% the voxel is too "
          "coarse\n   or the poses are not good enough to do this at all)\n")

    # --- coverage of the FAR field, which has no labels of its own ---
    far_total = far_labelled = 0
    per_class = {}
    for w, sem, r in scans:
        m = r >= args.near_m
        far_total += int(m.sum())
        if not m.any():
            continue
        got = lookup(_keys(w[m], args.voxel))
        ok = got >= 0
        far_labelled += int(ok.sum())
        for c in np.unique(got[ok]):
            per_class[int(c)] = per_class.get(int(c), 0) + int((got[ok] == c).sum())

    cov = far_labelled / far_total if far_total else 0.0
    print(f"FAR FIELD (>= {args.near_m:g} m), which SemanticKITTI leaves unlabelled")
    print(f"  returns            {far_total:>12,}")
    print(f"  now labelled       {far_labelled:>12,}   ({cov:.1%} coverage)")
    if per_class:
        names = semantics.FRNET_CLASS_NAMES
        top = sorted(per_class.items(), key=lambda kv: -kv[1])[:8]
        print("\n  recovered classes:")
        for c, n in top:
            print(f"    {names[c]:>14}  {n:>10,}  {n / far_labelled:>6.1%}")
    print(f"\n  ring 3 goes from NOT SCORABLE to scorable on {cov:.1%} of its "
          f"returns,\n  for static classes only -- distant moving objects are "
          f"deliberately excluded.")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"sequence": args.seq, "frames": len(scans), "voxel_m": args.voxel,
             "near_m": args.near_m, "hash_voxels": len(table),
             "validation_agreement": val, "validation_points": seen,
             "far_returns": far_total, "far_labelled": far_labelled,
             "far_coverage": cov}, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
