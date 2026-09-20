#!/usr/bin/env python3
"""MapMOS's idea on our grid: fuse motion evidence in log-odds. [Shrestha, staging]

    python scripts/mos_fused.py --eval-seq 08 --eval-frames 120

`14-MOS-RESEARCH.md` noted that MapMOS reaches 86.1 IoU where per-scan methods
sit near 77, and that the difference is a Bayes filter over VOLUMETRIC BELIEFS
-- "which parts of the environment can be occupied by moving objects". That is
a property of SPACE, not of an object: a traffic lane accumulates evidence that
things move through it, a wall accumulates the opposite.

This grid already fuses occupancy in log-odds (§10.1) and already has a
transient layer. So the test is whether the same accumulation helps motion:
carry a per-voxel dynamic-evidence log-odds through the sequence, and ask
whether a point's decision improves when the space it sits in is taken into
account alongside the per-scan prediction.

⚑ FUSING IN WORLD VOXELS IS ONLY VALID FOR THIS INTERPRETATION. An object
  moves, so its own evidence does not stay in one voxel -- accumulating "is
  this object moving" spatially would be meaningless. What accumulates here is
  "does traffic pass through this space", which is stationary and is exactly
  what MapMOS's belief models. Do not describe it as tracking.

⚑ CAUSAL. The belief at frame t is built only from frames before t, so this
  cannot peek at the future. An offline version that used the whole sequence
  would score better and would not be a thing a vehicle could run.
"""
import argparse
import json
import warnings
from collections import deque
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train-seq", default="01,02,03,04,10")
    ap.add_argument("--train-frames", type=int, default=100)
    ap.add_argument("--eval-seq", default="08")
    ap.add_argument("--eval-frames", type=int, default=120)
    ap.add_argument("--voxel", type=float, default=0.5,
                    help="belief voxel side, metres")
    ap.add_argument("--decay", type=float, default=0.95,
                    help="per-frame multiplicative decay on the belief, so a "
                         "lane that stops carrying traffic forgets")
    ap.add_argument("--clamp", type=float, default=4.0)
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    warnings.simplefilter("ignore")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import torch
    from mos_learned import LAGS, _collect, _features
    from vrgrid.perception import ground as G
    from vrgrid.perception import loader, semantics, transforms

    # --- the per-scan model, same as mos_learned ---
    seqs = [s.strip() for s in args.train_seq.split(",") if s.strip()]
    print(f"training per-scan model on {seqs}", flush=True)
    parts = [_collect(s, args.train_frames, subsample=0.08) for s in seqs]
    Xtr = np.concatenate([a for a, _ in parts])
    ytr = np.concatenate([b for _, b in parts])
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = torch.nn.Sequential(
        torch.nn.Linear(Xtr.shape[1], 64), torch.nn.ReLU(),
        torch.nn.Linear(64, 64), torch.nn.ReLU(),
        torch.nn.Linear(64, 1)).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=1e-4)
    pw = torch.tensor([(1 - ytr.mean()) / max(ytr.mean(), 1e-6)], device=dev)
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=pw)
    Xt = torch.from_numpy(Xtr).to(dev)
    yt = torch.from_numpy(ytr.astype(np.float32)).to(dev)
    g = torch.Generator(device="cpu").manual_seed(0)
    for _ in range(args.steps):
        idx = torch.randint(0, len(Xt), (8192,), generator=g).to(dev)
        opt.zero_grad()
        lossf(net(Xt[idx]).squeeze(1), yt[idx]).backward()
        opt.step()
    print(f"  trained on {len(Xtr):,} points", flush=True)

    def vkeys(w):
        q = np.floor(np.asarray(w, np.float64) / args.voxel).astype(np.int64)
        return ((q[:, 0] + (1 << 20)) << 42) | ((q[:, 1] + (1 << 20)) << 21) \
            | (q[:, 2] + (1 << 20))

    # --- causal pass over the eval sequence ---
    print(f"evaluating on seq {args.eval_seq}, causal belief fusion", flush=True)
    G.reset_estimator()
    hist = deque(maxlen=max(LAGS))
    belief: dict[int, float] = {}
    res = {"per_scan": [0, 0, 0], "fused": [0, 0, 0]}     # tp, fp, fn
    for i, (pts, lab, pose) in enumerate(
            loader.scans(args.eval_seq, max_frames=args.eval_frames)):
        t_s_w = transforms.sensor_to_world(pose, sequence=args.eval_seq)
        gm, _ = G.segment_ground_or_fallback(
            pts, semantics.semantic_labels(lab), use_patchworkpp=True)
        w = transforms.transform_points(pts[:, :3], t_s_w)
        if i:
            f = _features(pts, hist, t_s_w, gm)
            with torch.no_grad():
                logit = net(torch.from_numpy(f.astype(np.float32)).to(dev)
                            ).squeeze(1).cpu().numpy()
            gt = semantics.is_moving(lab)
            k = vkeys(w)
            # Belief BEFORE this frame contributes: causal.
            prior = np.array([belief.get(int(kk), 0.0) for kk in k], np.float32)

            per_scan = logit > 2.0
            fused = (logit + 0.5 * prior) > 2.0
            for name, est in (("per_scan", per_scan), ("fused", fused)):
                res[name][0] += int((est & gt).sum())
                res[name][1] += int((est & ~gt).sum())
                res[name][2] += int((~est & gt).sum())

            # Update the belief with this frame's evidence, then decay.
            for kk, lg in zip(k.tolist(), logit.tolist(), strict=True):
                b = belief.get(kk, 0.0) + (1.0 if lg > 2.0 else -0.05)
                belief[kk] = float(np.clip(b, -args.clamp, args.clamp))
            if args.decay < 1.0:
                belief = {kk: v * args.decay for kk, v in belief.items()
                          if abs(v * args.decay) > 0.01}
        hist.append(w)

    print(f"\nseq {args.eval_seq}, {args.eval_frames} frames, "
          f"{args.voxel} m belief voxels, decay {args.decay}\n")
    print(f"{'':>10} {'precision':>11} {'recall':>9} {'F1':>8} {'moving IoU':>12}")
    print("-" * 54)
    out = {}
    for name in ("per_scan", "fused"):
        tp, fp, fn = res[name]
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if tp else 0.0
        iou = tp / (tp + fp + fn) if tp + fp + fn else 0.0
        print(f"{name:>10} {p:>10.1%} {r:>8.1%} {f1:>7.1%} {iou:>11.1%}")
        out[name] = {"precision": p, "recall": r, "f1": f1, "iou": iou,
                     "tp": tp, "fp": fp, "fn": fn}
    d = out["fused"]["iou"] - out["per_scan"]["iou"]
    print(f"\n  belief fusion moves moving IoU by {d * 100:+.1f} points")
    print(f"  ({len(belief):,} voxels carrying belief at the end)")
    if args.out:
        Path(args.out).write_text(json.dumps(
            {"eval_seq": args.eval_seq, "frames": args.eval_frames,
             "voxel_m": args.voxel, "decay": args.decay, **out}, indent=2))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
