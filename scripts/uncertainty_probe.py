#!/usr/bin/env python3
"""Does FRNet's uncertainty know where FRNet is wrong? [Shrestha, staging]

    python scripts/uncertainty_probe.py --seq 08 --frames 40

The grid foveates on RANGE alone: near cells are fine, far cells coarse. The
proposal is to refine on PERCEPTION UNCERTAINTY as well -- a confidently flat
road at 15 m does not need 10 cm cells, an ambiguous blob at 30 m does. Master
v4 §3.4 already says "semantics can force local refinement" and `grid/gate.py`
already implements three reasons; this would be a fourth.

Before wiring anything into the gate, the signal has to be shown to carry
information. The gate spends a 512-block pool, so a refinement trigger that
fires where nothing is wrong is worse than no trigger at all.

The test: bin every point by the entropy of FRNet's softmax, and report how
often FRNet is actually right in each bin. If accuracy falls sharply as entropy
rises, uncertainty points at error and refining there is justified. If it is
flat, the idea is dead and this saves building it.

⚑ Logits are taken by replaying `FRNet.predict`'s own path -- range
  interpolation, forward, `seg_logit` -- rather than editing the frozen port,
  and the interpolated points are dropped exactly as it drops them. Returning
  them would hand back more labels than there are points.
"""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", default="08")
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--bins", type=int, default=8)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    warnings.simplefilter("ignore")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from frnet_fast_scatter import enable
    enable(verify=False)

    import torch
    from vrgrid.perception import loader, semantics

    model = semantics.FRNetInference()
    net, dev = model.model, model.device

    ent_all, ok_all, rng_all = [], [], []
    root = Path(loader.DATA_ROOT) / "sequences" / args.seq
    for i in range(args.frames):
        scan = root / "velodyne" / f"{i:06d}.bin"
        label = root / "labels" / f"{i:06d}.label"
        if not (scan.exists() and label.exists()):
            break
        pts = loader.load_velodyne_scan(scan)
        gt = semantics.semantic_labels(loader.load_labels(label))
        with torch.no_grad():
            t = [torch.from_numpy(pts).float().to(dev)]
            n_real = [p.shape[0] for p in t]
            dense = [net.range_interpolation(p) for p in t]
            vd = net.forward(dense)
            logit = vd["seg_logit"]
            mask = vd["coors"][:, 0] == 0
            logit = logit[mask][:n_real[0]]
            p = torch.softmax(logit.float(), dim=1)
            # Entropy over the 20 model classes, normalised to [0, 1] so the
            # bin edges mean the same thing whatever the class count.
            ent = -(p * torch.clamp(p, min=1e-12).log()).sum(1) / np.log(p.shape[1])
            pred = logit.argmax(1)
        ent = ent.cpu().numpy()
        pred = pred.cpu().numpy()
        scored = gt >= 0
        ent_all.append(ent[scored])
        ok_all.append(pred[scored] == gt[scored])
        rng_all.append(np.linalg.norm(pts[scored, :3], axis=1))

    if not ent_all:
        print(f"no frames read for sequence {args.seq} -- is VRGRID_DATA_ROOT set?")
        return 1
    ent = np.concatenate(ent_all)
    ok = np.concatenate(ok_all)
    rng = np.concatenate(rng_all)

    edges = np.quantile(ent, np.linspace(0, 1, args.bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    print(f"\nsequence {args.seq}, {len(ent_all)} frames, {len(ent):,} scored points")
    print("points are split into equal-SIZE entropy bins, so each row carries "
          "the same weight\n")
    print(f"{'bin':>5} {'entropy':>16} {'points':>12} {'FRNet correct':>15} "
          f"{'mean range m':>13}")
    print("-" * 68)
    rows = []
    for b in range(args.bins):
        m = (ent >= edges[b]) & (ent < edges[b + 1])
        if not m.any():
            continue
        acc = float(ok[m].mean())
        lo = ent[m].min()
        hi = ent[m].max()
        print(f"{b:>5} {f'{lo:.3f}-{hi:.3f}':>16} {int(m.sum()):>12,} "
              f"{acc:>14.1%} {rng[m].mean():>13.1f}")
        rows.append({"bin": b, "lo": float(lo), "hi": float(hi),
                     "points": int(m.sum()), "accuracy": acc,
                     "mean_range_m": float(rng[m].mean())})

    lowest, highest = rows[0]["accuracy"], rows[-1]["accuracy"]
    print(f"\n  most confident decile {lowest:.1%} correct, least confident "
          f"{highest:.1%}")
    # NOT a ratio of error rates: the most confident bin rounds to 100.0%
    # correct, so the denominator is ~0 and the ratio prints as hundreds of
    # millions. Report the difference, which is the honest statement.
    print(f"  {(highest - lowest) * -100:.1f} percentage points of accuracy "
          f"separate the two")

    # The question the gate actually asks: at a FIXED range, does uncertainty
    # still separate right from wrong? If it only tracks range it adds nothing
    # the ring schedule does not already know.
    print("\n  controlling for range -- uncertainty must beat 'far away':")
    print(f"  {'range band':>14} {'low-entropy acc':>17} {'high-entropy acc':>18}")
    ctrl = []
    for lo_r, hi_r in ((0, 10), (10, 25), (25, 50)):
        band = (rng >= lo_r) & (rng < hi_r)
        if band.sum() < 1000:
            continue
        med = np.median(ent[band])
        lo_acc = float(ok[band & (ent <= med)].mean())
        hi_acc = float(ok[band & (ent > med)].mean())
        print(f"  {f'{lo_r}-{hi_r} m':>14} {lo_acc:>16.1%} {hi_acc:>17.1%}")
        ctrl.append({"lo_m": lo_r, "hi_m": hi_r,
                     "low_entropy_acc": lo_acc, "high_entropy_acc": hi_acc})

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"sequence": args.seq, "points": len(ent),
             "bins": rows, "range_controlled": ctrl}, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
