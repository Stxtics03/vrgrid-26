#!/usr/bin/env python3
"""What `--semantics-every N` buys in latency and costs in accuracy. [Shrestha]

    python scripts/semantics_rate.py --seq 08 --frames 22 --rates 1,2,3,5

FRNet costs about 88 ms a frame and the whole 10 Hz budget is 100 ms, so
inferring every frame puts the pipeline at 7.6 FPS. Running it every Nth frame
and reusing the labels between is the obvious answer. This prices it.

⚑ READ THE p99 COLUMN, NOT THE p50. Skipping frames moves the MEDIAN and
  leaves the TAIL where it was: the frames that do infer still pay full price,
  and they are the tail. `src/gpu/CLAUDE.md` is explicit that "a 10 Hz claim is
  about the tail", so a p50 that crosses 10 Hz while p99 does not has not met
  the requirement -- it has only moved the number that is easier to move.

Accuracy is measured against the ground-truth `.label` files, so it folds in
BOTH the model's own error and the staleness of a reused label. That is the
honest quantity: it is what the map actually receives.
"""
import argparse
import json
import time
import warnings
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", default="08")
    ap.add_argument("--frames", type=int, default=22)
    ap.add_argument("--rates", default="1,2,3,5")
    ap.add_argument("--warmup", type=int, default=2,
                    help="frames dropped before timing; the first carry CUDA "
                         "context creation and the model's first forward")
    ap.add_argument("--fast-scatter", action="store_true", default=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    warnings.simplefilter("ignore")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if args.fast_scatter:
        from frnet_fast_scatter import enable
        enable(verify=False)

    from vrgrid.perception import loader
    from vrgrid.perception import semantics as S
    from vrgrid.run.__main__ import iter_pipeline

    gts = [S.semantic_labels(lab)
           for _, lab, _ in loader.scans(args.seq, max_frames=args.frames)]

    rows = []
    print(f"\nsequence {args.seq}, {args.frames} frames, {args.warmup} warm-up dropped")
    print(f"{'every':>6} {'p50 ms':>9} {'p99 ms':>9} {'FPS p50':>9} {'FPS p99':>9} "
          f"{'acc vs GT':>11} {'10 Hz at p99':>13}")
    print("-" * 74)
    for every in [int(x) for x in args.rates.split(",")]:
        ts, agree = [], []
        prev = time.perf_counter()
        for k, f in enumerate(iter_pipeline(args.seq, args.frames,
                                            semantic_source="frnet",
                                            semantic_every=every)):
            now = time.perf_counter()
            if k >= args.warmup:
                ts.append((now - prev) * 1e3)
                ok = gts[k] >= 0
                agree.append(float((f.semantic[ok] == gts[k][ok]).mean()))
            prev = now
        a = np.array(ts)
        # Nearest-rank, like gpu/timing.py: numpy's default interpolation
        # invents a latency no frame ever took and rounds the tail down.
        p50 = float(np.percentile(a, 50, method="nearest"))
        p99 = float(np.percentile(a, 99, method="nearest"))
        acc = float(np.mean(agree))
        meets = p99 <= 100.0
        print(f"{every:>6} {p50:>9.1f} {p99:>9.1f} {1000 / p50:>9.1f} "
              f"{1000 / p99:>9.1f} {acc:>10.1%} {'YES' if meets else 'no':>13}")
        rows.append({"every": every, "p50_ms": p50, "p99_ms": p99,
                     "fps_p50": 1000 / p50, "fps_p99": 1000 / p99,
                     "acc_vs_gt": acc, "meets_10hz_p99": meets})

    print("\nIf p50 crosses 10 Hz and p99 does not, the requirement is not met.\n"
          "Skipping frames cannot move the tail: the frames that infer still pay\n"
          "full price, and those frames ARE the tail. Making the tail fit needs\n"
          "the inference itself to get cheaper, or to overlap the map.")
    if args.out:
        Path(args.out).write_text(json.dumps(
            {"sequence": args.seq, "frames": args.frames, "rates": rows}, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
