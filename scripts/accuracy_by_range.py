#!/usr/bin/env python3
"""Classification accuracy against DISTANCE, binned to the ring boundaries.
[Shrestha]

    python scripts/accuracy_by_range.py --seq 08 --frames 200 --fast-scatter

The problem statement asks for "evidence of ... high accuracy in object
classification across varying distances". Every accuracy number this project
has published so far is a single figure pooled over a whole scan, which cannot
answer it: a foveated map coarsens with range on purpose, and the question is
whether classification survives that.

So the bins are the RING boundaries, not round numbers -- 0-10, 10-25, 25-50,
50-100 m are rings 0..3 of the 5/10/20/40 schedule. Each row is therefore
"how well does the system classify inside the ring that stores it at this
resolution", which is the claim the design actually makes.

Three groupings are reported per bin, because they answer different questions:

  19-class      point accuracy and mIoU, comparable to the headline 90.3/65.2
  3-group       terrain / static obstacle / dynamic object -- the statement's
                own categories, and the one to put in the report
  drivable      the five classes math 7.1 consults; everything else is simply
                "not drivable" to the map, so this is what a planner sees

⚑ WHAT THIS MEASURES. Predictions come from the FRNet model, ground truth from
  the SemanticKITTI `.label` files. It scores the MODEL, not the map: the map's
  own semantics come from the same `.label` files, so its class accuracy is
  1.0 by construction and measuring it would be circular. When the pipeline is
  run with `--semantics frnet` the model is what feeds the map, and then this
  table is the map's class accuracy too.

⚑ Range is measured in the SENSOR frame, which is what "distance from the
  sensor" means and is not the same as distance from the map origin.
"""
import argparse
import json
from itertools import pairwise
from pathlib import Path

import numpy as np

# The statement's three categories, over the 19 SemanticKITTI classes.
TERRAIN = ("road", "parking", "sidewalk", "other-ground", "terrain")
STATIC = ("building", "fence", "vegetation", "trunk", "pole", "traffic-sign")
DYNAMIC = ("car", "bicycle", "motorcycle", "truck", "other-vehicle",
           "person", "bicyclist", "motorcyclist")
#: math 7.1: the only five the map distinguishes. Same tuple as frnet_eval.
DRIVABLE = ("road", "parking", "sidewalk", "other-ground", "terrain")


def _group_lut(names) -> np.ndarray:
    """Per-class -> 0 terrain, 1 static, 2 dynamic."""
    lut = np.full(len(names), -1, np.int8)
    for i, n in enumerate(names):
        if n in TERRAIN:
            lut[i] = 0
        elif n in STATIC:
            lut[i] = 1
        elif n in DYNAMIC:
            lut[i] = 2
    return lut


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", default="08",
                    help="SemanticKITTI's official validation sequence")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--edges", default="10,25,50,100",
                    help="ring half-widths in metres; the bins are the gaps "
                         "between them, plus everything beyond the last")
    ap.add_argument("--fast-scatter", action="store_true",
                    help="torch.scatter_reduce for FRNet's frustum reductions "
                         "(scripts/frnet_fast_scatter.py) -- minutes, not hours")
    ap.add_argument("--out", default=None, help="write the table as JSON here")
    args = ap.parse_args()

    if args.fast_scatter:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from frnet_fast_scatter import enable
        enable()

    import torch
    from vrgrid.perception import loader, semantics

    names = semantics.FRNET_CLASS_NAMES[:19]
    glut = _group_lut(names)
    drivable_ids = [names.index(n) for n in DRIVABLE]

    edges = [float(x) for x in args.edges.split(",")]
    # (lo, hi) per bin; the last one is open-ended so no return is discarded.
    bins = [(0.0, edges[0])] + list(pairwise(edges)) + [(edges[-1], np.inf)]
    labels = [f"ring {i}" if i < len(edges) else "beyond" for i in range(len(bins))]

    model = semantics.FRNetInference()
    dev = model.device

    nb, nc = len(bins), 19
    inter = np.zeros((nb, nc), np.int64)
    union = np.zeros((nb, nc), np.int64)
    support = np.zeros((nb, nc), np.int64)
    correct = np.zeros(nb, np.int64)
    total = np.zeros(nb, np.int64)
    g_correct = np.zeros(nb, np.int64)
    g_total = np.zeros(nb, np.int64)
    returns = np.zeros(nb, np.int64)

    root = Path(loader.DATA_ROOT) / "sequences" / args.seq
    frames = 0
    for i in range(args.frames):
        scan = root / "velodyne" / f"{i:06d}.bin"
        label = root / "labels" / f"{i:06d}.label"
        if not (scan.exists() and label.exists()):
            break
        pts = loader.load_velodyne_scan(scan)
        gt = semantics.semantic_labels(loader.load_labels(label))
        with torch.no_grad():
            pred = model.model.predict(
                [torch.from_numpy(pts).float().to(dev)])[0].cpu().numpy()

        rng = np.linalg.norm(pts[:, :3], axis=1)
        ok = gt >= 0                      # unlabelled points are not scored
        for b, (lo, hi) in enumerate(bins):
            inbin = (rng >= lo) & (rng < hi)
            returns[b] += int(inbin.sum())   # counted even when none is scorable
            m = ok & inbin
            if not m.any():
                continue
            p, g = pred[m], gt[m]
            correct[b] += int((p == g).sum())
            total[b] += int(m.sum())
            for c in range(nc):
                pc, gc = p == c, g == c
                inter[b, c] += int((pc & gc).sum())
                union[b, c] += int((pc | gc).sum())
                support[b, c] += int(gc.sum())
            # 3-group: only points whose TRUE class has a group (all 19 do)
            gp, gg = glut[np.clip(p, 0, nc - 1)], glut[g]
            valid = gg >= 0
            g_correct[b] += int((gp[valid] == gg[valid]).sum())
            g_total[b] += int(valid.sum())
        frames += 1

    if not frames:
        print(f"no frames read for sequence {args.seq} -- is VRGRID_DATA_ROOT set?")
        return 1

    rows = []
    print(f"\nsequence {args.seq}, {frames} frames, predictions from FRNet, "
          f"ground truth from the .label files")
    print(f"bins are ring half-widths {args.edges} m, measured in the sensor frame\n")
    print(f"{'bin':>8} {'range m':>12} {'returns':>12} {'scored':>12} "
          f"{'19-class acc':>13} {'mIoU':>8} {'3-group acc':>12} {'drivable mIoU':>14}")
    print("-" * 101)
    for b, (lo, hi) in enumerate(bins):
        hi_s = "inf" if np.isinf(hi) else f"{hi:g}"
        if not total[b]:
            # Print it anyway. A bin with returns and no ground truth is not an
            # empty bin, and silently dropping the row is how "accuracy across
            # varying distances" gets claimed for a range nothing scored.
            if returns[b]:
                print(f"{labels[b]:>8} {f'{lo:g}-{hi_s}':>12} {returns[b]:>12,} "
                      f"{0:>12,}   -- no ground truth at this range, NOT SCORABLE")
                rows.append({"bin": labels[b], "lo_m": lo,
                             "hi_m": None if np.isinf(hi) else hi,
                             "returns": int(returns[b]), "scored": 0,
                             "scorable": False})
            continue
        present = support[b] > 0
        iou = np.divide(inter[b], union[b], out=np.zeros(nc), where=union[b] > 0)
        miou = float(iou[present].mean()) if present.any() else float("nan")
        dpresent = [c for c in drivable_ids if support[b, c] > 0]
        dmiou = float(iou[dpresent].mean()) if dpresent else float("nan")
        acc = correct[b] / total[b]
        gacc = g_correct[b] / g_total[b] if g_total[b] else float("nan")
        print(f"{labels[b]:>8} {f'{lo:g}-{hi_s}':>12} {returns[b]:>12,} {total[b]:>12,} "
              f"{acc:>12.1%} {miou:>8.1%} {gacc:>11.1%} {dmiou:>13.1%}")
        rows.append({"bin": labels[b], "lo_m": lo, "hi_m": None if np.isinf(hi) else hi,
                     "returns": int(returns[b]), "scored": int(total[b]), "scorable": True,
                     "acc19": acc, "miou": miou, "group_acc": gacc,
                     "drivable_miou": dmiou, "classes_present": int(present.sum())})

    pooled = correct.sum() / total.sum()
    print("-" * 101)
    print(f"{'pooled':>8} {'0-inf':>12} {returns.sum():>12,} {total.sum():>12,} "
          f"{pooled:>12.1%}")
    unscored = int(returns.sum() - total.sum())
    if unscored:
        print(f"\n{unscored:,} returns ({unscored / returns.sum():.1%}) carry no "
              f"ground-truth label and are excluded above.")
    print("\nThe pooled figure is the one previously published. It is an average "
          "weighted by\npoint density, and point density falls off with range -- "
          "which is exactly why it\ncannot answer the question this table answers.")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"sequence": args.seq, "frames": frames, "edges_m": edges,
             "pooled_acc19": pooled, "returns_total": int(returns.sum()),
             "scored_total": int(total.sum()), "bins": rows}, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
