#!/usr/bin/env python3
"""Residuals as FEATURES, not as a threshold. The LiDAR-MOS lesson, cheaply.
[Shrestha, staging experiment]

    python scripts/mos_learned.py --train-seq 00 --train-frames 150 \
                                  --eval-seq 08 --eval-frames 200

`docs/gpu-lane/14-MOS-RESEARCH.md` concluded that no hand-tuned threshold on a
range residual works -- four sweeps said so, including the literature's own
normalised formula, which scored WORSE as a rule than the cruder one it was
meant to replace. What the literature actually does is concatenate residual
images as INPUT CHANNELS to a network and let it learn the decision.

This is the cheapest possible test of that claim: the same residuals this
project already computes, at several time lags, fed to a small per-point MLP
instead of to a comparison. If the claim holds, this beats 16.3% precision by
a wide margin. If it does not, the next step is not worth the T4 time.

PROTOCOL. Train on one sequence, evaluate on another -- seq 08 is
SemanticKITTI's official validation sequence and is never trained on here.
Evaluating on held-out frames of the SAME sequence would score a road the model
had already seen.

⚑ The headline metric is IoU ON THE MOVING CLASS, which is what the
  SemanticKITTI-MOS benchmark reports, so the number is comparable to the
  59.9 / 62.5 / 76.7 in the research note. Accuracy is meaningless here: moving
  points are ~2% of returns, so predicting "static" always scores 98%.

⚑ NOT a reimplementation of LiDAR-MOS. They train a full range-image CNN on 8
  residual channels; this is a per-point MLP on a handful of scalars. It tests
  the PREMISE -- residual-as-feature beats residual-as-threshold -- at a cost
  of minutes. Treat the result as a lower bound on what the real thing does.
"""
import argparse
import json
import warnings
from collections import deque
from pathlib import Path

import numpy as np

LAGS = (1, 2, 4, 8)          # LiDAR-MOS ablates N=1..8; these are the lags used
#: Box-filter widths, in range-image pixels, used to give each point the
#: residual of its NEIGHBOURHOOD as well as its own. This is the cheap stand-in
#: for a CNN's receptive field, and it is the whole hypothesis under test: a
#: moving object is a spatially coherent blob of residual, and a lone elevated
#: pixel is an occlusion edge. A per-point classifier cannot tell those apart.
CONTEXT = (3, 7, 15)


def _box(img, k):
    """Mean of `img` over a k x k window, ignoring NaN. Summed-area, no scipy.

    NaN-aware by averaging the VALID entries only: sum over the window divided
    by the count of finite pixels in it, rather than by k*k. A window half in
    the sky would otherwise read as half the residual it actually saw.
    """
    m = np.isfinite(img)
    pad = k // 2
    h, w = img.shape

    def windowed(x):
        xp = np.pad(x.astype(np.float64), ((pad, pad), (pad, pad)), mode="edge")
        c = np.cumsum(np.cumsum(xp, axis=0), axis=1)
        c = np.pad(c, ((1, 0), (1, 0)))
        return (c[k:k + h, k:k + w] - c[0:h, k:k + w]
                - c[k:k + h, 0:w] + c[0:h, 0:w])

    num = windowed(np.where(m, img, 0.0))
    den = windowed(m.astype(np.float64))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / np.maximum(den, 1e-6), 0.0).astype(np.float32)


def _residuals(points, history, t_s_w, lags=LAGS):
    """Range-normalised residual per point, per lag, plus a validity mask.

    `d = |r_now - r_prev| / r_now`, the LiDAR-MOS formula (arXiv:2105.08971).
    `history` holds previous scans already in WORLD coordinates, newest last.
    """
    from vrgrid.perception import range_image as ri

    n = len(points)
    r_now = np.linalg.norm(points[:, :3], axis=1).astype(np.float32)
    v, u, finite = ri.point_bins(points)
    w_to_s = np.linalg.inv(np.asarray(t_s_w, np.float64))

    from vrgrid.perception import range_image as _ri
    cur_img, _ = _ri.project(points)
    r_now_img = np.asarray(cur_img)[:, :, 0]

    feats = np.zeros((n, len(lags)), np.float32)
    ctx = np.zeros((n, len(lags) * len(CONTEXT)), np.float32)
    valid = np.zeros((n, len(lags)), np.float32)
    for k, lag in enumerate(lags):
        if len(history) < lag:
            continue
        prev = np.asarray(history[-lag], np.float64)
        prev_s = (prev @ w_to_s[:3, :3].T) + w_to_s[:3, 3]
        p4 = np.empty((len(prev_s), 4), np.float32)
        p4[:, :3] = prev_s
        p4[:, 3] = 1.0
        img, _ = ri.project(p4)
        r_prev = np.asarray(img)[:, :, 0][v, u]
        ok = finite & np.isfinite(r_prev)
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.abs(r_now - r_prev) / np.maximum(r_now, 1e-3)
        # Clipped: a disocclusion produces an enormous residual that would
        # otherwise dominate the input scale and teach the net to watch edges.
        feats[ok, k] = np.clip(d[ok], 0.0, 2.0)
        valid[ok, k] = 1.0

        # The same residual as an IMAGE, box-filtered, sampled back per point.
        r_prev_img = np.asarray(img)[:, :, 0]
        with np.errstate(invalid="ignore", divide="ignore"):
            d_img = np.abs(r_now_img - r_prev_img) / np.maximum(r_now_img, 1e-3)
        d_img = np.clip(d_img, 0.0, 2.0)
        for c, kk in enumerate(CONTEXT):
            ctx[:, k * len(CONTEXT) + c] = _box(d_img, kk)[v, u]
    return feats, valid, r_now, ctx


def _features(points, history, t_s_w, ground_mask):
    res, valid, r_now, ctx = _residuals(points, history, t_s_w)
    z = points[:, 2].astype(np.float32)
    return np.concatenate([
        res,                                   # residual per lag
        ctx,                                   # NEIGHBOURHOOD residual per lag
        valid,                                 # was that lag observable
        (r_now / 50.0)[:, None],               # range, roughly unit-scaled
        (z / 3.0)[:, None],                    # height in the sensor frame
        ground_mask.astype(np.float32)[:, None],
    ], axis=1)


def _collect(seq, n_frames, subsample=0):
    """Features and `moving` labels for one sequence."""
    from vrgrid.perception import ground as G
    from vrgrid.perception import loader, semantics, transforms

    G.reset_estimator()
    hist = deque(maxlen=max(LAGS))
    X, y = [], []
    rng = np.random.default_rng(0)
    for i, (pts, lab, pose) in enumerate(loader.scans(seq, max_frames=n_frames)):
        t_s_w = transforms.sensor_to_world(pose, sequence=seq)
        gm, _ = G.segment_ground_or_fallback(
            pts, semantics.semantic_labels(lab), use_patchworkpp=True)
        if i:                                  # frame 0 has no history
            f = _features(pts, hist, t_s_w, gm)
            m = semantics.is_moving(lab)
            if subsample:
                # Keep every moving point and a sample of the rest: moving is
                # ~2% of returns and an unbalanced batch teaches "always static".
                keep = m | (rng.random(len(m)) < subsample)
                f, m = f[keep], m[keep]
            X.append(f.astype(np.float32))
            y.append(m)
        hist.append(transforms.transform_points(pts[:, :3], t_s_w))
    return np.concatenate(X), np.concatenate(y)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train-seq", default="01,02,03,04,10",
                    help="comma-separated. Moving content varies 40-fold "
                         "between sequences: over the first 100 frames seq 00 "
                         "is 0.021%% moving and seq 04 is 0.847%%, so training "
                         "on 00 alone gives ~2,500 positives and learns "
                         "nothing. Several dynamic sequences beats one.")
    ap.add_argument("--train-frames", type=int, default=150)
    ap.add_argument("--eval-seq", default="08")
    ap.add_argument("--eval-frames", type=int, default=200)
    ap.add_argument("--subsample", type=float, default=0.08,
                    help="fraction of STATIC points kept for training")
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    warnings.simplefilter("ignore")
    import torch

    seqs = [x.strip() for x in args.train_seq.split(",") if x.strip()]
    print(f"collecting train: seqs {seqs}, {args.train_frames} frames each", flush=True)
    parts = [_collect(sq, args.train_frames, subsample=args.subsample) for sq in seqs]
    Xtr = np.concatenate([a for a, _ in parts])
    ytr = np.concatenate([b for _, b in parts])
    print(f"  {len(Xtr):,} points, {ytr.mean():.2%} moving", flush=True)
    print(f"collecting eval:  seq {args.eval_seq}, {args.eval_frames} frames", flush=True)
    Xev, yev = _collect(args.eval_seq, args.eval_frames)
    print(f"  {len(Xev):,} points, {yev.mean():.2%} moving", flush=True)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    Xt = torch.from_numpy(Xtr).to(dev)
    yt = torch.from_numpy(ytr.astype(np.float32)).to(dev)
    net = torch.nn.Sequential(
        torch.nn.Linear(Xtr.shape[1], args.hidden), torch.nn.ReLU(),
        torch.nn.Linear(args.hidden, args.hidden), torch.nn.ReLU(),
        torch.nn.Linear(args.hidden, 1)).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=1e-4)
    # Positive weight from the TRAINING mix, which subsampling has already
    # rebalanced; without it the optimiser still finds "always static" first.
    pw = torch.tensor([(1 - ytr.mean()) / max(ytr.mean(), 1e-6)], device=dev)
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=pw)
    g = torch.Generator(device="cpu").manual_seed(0)
    for step in range(args.steps):
        idx = torch.randint(0, len(Xt), (8192,), generator=g).to(dev)
        opt.zero_grad()
        loss = lossf(net(Xt[idx]).squeeze(1), yt[idx])
        loss.backward()
        opt.step()
        if (step + 1) % 1000 == 0:
            print(f"  step {step + 1}: loss {loss.item():.4f}", flush=True)

    # Chunked: the eval split is tens of millions of points and a single
    # forward pass asked for 3.49 GiB of activations on an 8 GB card.
    with torch.no_grad():
        chunks = []
        for a in range(0, len(Xev), 1_000_000):
            block = torch.from_numpy(Xev[a:a + 1_000_000]).to(dev)
            chunks.append(net(block).squeeze(1).cpu().numpy())
        logits = np.concatenate(chunks)

    print(f"\nseq {args.eval_seq}, {args.eval_frames} frames, trained on seq "
          f"{args.train_seq} -- never seen\n")
    print(f"{'threshold':>10} {'precision':>11} {'recall':>9} {'F1':>8} {'moving IoU':>12}")
    print("-" * 54)
    best = None
    for thr in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        est = logits > thr
        tp = int((est & yev).sum()); fp = int((est & ~yev).sum())
        fn = int((~est & yev).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if tp else 0.0
        iou = tp / (tp + fp + fn) if tp + fp + fn else 0.0
        print(f"{thr:>10.1f} {p:>10.1%} {r:>8.1%} {f1:>7.1%} {iou:>11.1%}")
        if best is None or iou > best["iou"]:
            best = {"threshold": thr, "precision": p, "recall": r, "f1": f1, "iou": iou}
    print(f"\nbest moving IoU {best['iou']:.1%} at logit threshold {best['threshold']}")
    print("baseline, the hand-tuned free-space rule on this sequence: "
          "precision 16.3%, recall 15.0%, IoU 8.5%")
    if args.out:
        Path(args.out).write_text(json.dumps(
            {"train_seq": args.train_seq, "train_frames": args.train_frames,
             "eval_seq": args.eval_seq, "eval_frames": args.eval_frames,
             "lags": list(LAGS), "best": best}, indent=2))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
