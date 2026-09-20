#!/usr/bin/env python3
"""N-3: is seq 00's ring-2 outlier range-dependent registration? [Shrestha]

    python scripts/crosslook_probe.py --seqs 00,05,07 --frames 250

`known-limitations.md` §9 narrowed seq 00's ring-2 outlier to dispersion across
looks: ρ 2.20 against M* but **1.02 against M*|ring**, so the map agrees with
the returns it integrated and those returns disagree with returns of the same
ground seen from other ranges, by ~33 cm RMS. "Cause still open --
range-dependent registration on a long urban loop is the leading hypothesis."

This tests that hypothesis directly. Every ground return is put in a world
column, and for each column observed more than once the pairs of observations
are compared: how far apart in HEIGHT, against how far apart in RANGE the two
looks were taken from. If registration degrades with range, height
disagreement rises with range separation. If it does not, the hypothesis is
wrong and the cause is something else.

Other sequences are run as controls. If every sequence shows the same slope,
the effect is generic and says nothing about 00 specifically; if 00's is much
steeper, it is 00's problem and the hypothesis survives.

⚑ GROUND RETURNS ONLY. A column through a tree or a wall contains many real
  heights and would report disagreement that is not error. Ground is the
  surface §3 estimates and the one ring-2 RMSE is computed over.

⚑ Columns, not voxels: the quantity ring-2 RMSE measures is the ELEVATION of a
  patch of ground, so two looks at the same (x, y) should agree in z whatever
  else differs.
"""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np


def _cols(w, cell_m):
    q = np.floor(np.asarray(w[:, :2], np.float64) / cell_m).astype(np.int64)
    return ((q[:, 0] + (1 << 24)) << 25) | (q[:, 1] + (1 << 24))


def probe(seq, frames, cell_m, lo_m, hi_m):
    from vrgrid.perception import ground as G
    from vrgrid.perception import loader, semantics, transforms

    G.reset_estimator()
    obs: dict[int, list] = {}
    for _i, (pts, lab, pose) in enumerate(loader.scans(seq, max_frames=frames)):
        t = transforms.sensor_to_world(pose, sequence=seq)
        gm, _ = G.segment_ground_or_fallback(
            pts, semantics.semantic_labels(lab), use_patchworkpp=True)
        r = np.linalg.norm(pts[:, :3], axis=1)
        keep = gm & (r >= lo_m) & (r < hi_m)
        if not keep.any():
            continue
        w = transforms.transform_points(pts[keep, :3], t)
        k = _cols(w, cell_m)
        for kk, zz, rr in zip(k.tolist(), w[:, 2].tolist(), r[keep].tolist(),
                              strict=True):
            b = obs.setdefault(kk, [])
            if len(b) < 24:          # cap: a column seen 500 times adds nothing
                b.append((rr, zz, _i))

    # Pair up observations within each column and bin by range separation.
    edges = [0, 2, 5, 10, 20, 40, 1e9]
    # A SECOND axis: how far apart in TIME the two looks were. Seq 00 is a long
    # urban loop, so it revisits ground minutes later, and pose drift around a
    # loop separates two looks that may be at the SAME range. Range separation
    # turned out to be generic across sequences; this is the axis on which 00
    # is actually different from a sequence that never comes back.
    fedges = [0, 5, 20, 100, 500, 1e9]
    sq = np.zeros(len(edges) - 1)
    cnt = np.zeros(len(edges) - 1, np.int64)
    fsq = np.zeros(len(fedges) - 1)
    fcnt = np.zeros(len(fedges) - 1, np.int64)
    rng = np.random.default_rng(0)
    for b in obs.values():
        if len(b) < 2:
            continue
        a = np.array(b)
        # Sample pairs rather than take all of them: a 24-deep column has 276
        # pairs and the deep columns would otherwise dominate every bin.
        n = min(len(a) * 2, 40)
        i = rng.integers(0, len(a), n)
        j = rng.integers(0, len(a), n)
        ok = i != j
        dr = np.abs(a[i[ok], 0] - a[j[ok], 0])
        dz = a[i[ok], 1] - a[j[ok], 1]
        idx = np.searchsorted(edges, dr, side="right") - 1
        d2 = (dz ** 2).tolist()
        for b_, d_ in zip(idx.tolist(), d2, strict=True):
            if 0 <= b_ < len(sq):
                sq[b_] += d_
                cnt[b_] += 1
        df = np.abs(a[i[ok], 2] - a[j[ok], 2])
        fidx = np.searchsorted(fedges, df, side="right") - 1
        for b_, d_ in zip(fidx.tolist(), d2, strict=True):
            if 0 <= b_ < len(fsq):
                fsq[b_] += d_
                fcnt[b_] += 1
    rmse = np.where(cnt > 0, np.sqrt(np.divide(sq, np.maximum(cnt, 1))) * 100, np.nan)
    frmse = np.where(fcnt > 0, np.sqrt(np.divide(fsq, np.maximum(fcnt, 1))) * 100, np.nan)
    return edges, rmse, cnt, len(obs), fedges, frmse, fcnt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seqs", default="00,05,07")
    ap.add_argument("--frames", type=int, default=250)
    ap.add_argument("--cell", type=float, default=0.20, help="ring-2 cell, metres")
    ap.add_argument("--lo", type=float, default=20.0, help="ring 2 inner, metres")
    ap.add_argument("--hi", type=float, default=50.0, help="ring 2 outer, metres")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    warnings.simplefilter("ignore")

    print(f"\nground returns {args.lo:g}-{args.hi:g} m (ring 2), "
          f"{args.cell * 100:g} cm columns, {args.frames} frames")
    print("height RMSE between two looks at the same ground column, "
          "binned by how far\napart in RANGE the two looks were taken\n")
    rows = {}
    hdr = None
    for seq in [s.strip() for s in args.seqs.split(",") if s.strip()]:
        edges, rmse, cnt, ncol, fedges, frmse, fcnt = probe(
            seq, args.frames, args.cell, args.lo, args.hi)
        if hdr is None:
            labels = [f"{edges[i]:g}-{edges[i + 1]:g}" if edges[i + 1] < 1e8
                      else f">{edges[i]:g}" for i in range(len(edges) - 1)]
            hdr = labels
            print(f"{'seq':>5} {'columns':>10} " + "".join(f"{x:>12}" for x in labels))
            print("-" * (17 + 12 * len(labels)))
        cells = "".join(f"{v:>11.1f}u" if np.isfinite(v) else f"{'-':>12}"
                        for v in rmse)
        print(f"{seq:>5} {ncol:>10,} " + cells.replace("u", " "))
        rows[seq] = {"bins": hdr, "rmse_cm": [None if not np.isfinite(v) else float(v)
                                              for v in rmse],
                     "pairs": [int(c) for c in cnt], "columns": ncol,
                     "frame_bins": [f"{fedges[i]:g}-{fedges[i+1]:g}"
                                    for i in range(len(fedges) - 1)],
                     "frame_rmse_cm": [None if not np.isfinite(v) else float(v)
                                       for v in frmse],
                     "frame_pairs": [int(c) for c in fcnt]}

    print("\n\nsame pairs, binned by how far apart in TIME (frames) the two "
          "looks were:\n")
    flabels = rows[next(iter(rows))]["frame_bins"]
    print(f"{'seq':>5} {'':>10} " + "".join(f"{x:>12}" for x in flabels))
    print("-" * (17 + 12 * len(flabels)))
    for seq, r in rows.items():
        print(f"{seq:>5} {'':>10} " + "".join(
            f"{v:>12.1f}" if v is not None else f"{'-':>12}"
            for v in r["frame_rmse_cm"]))

    print("\n  units are cm. Read ACROSS a row: if registration degrades with "
          "range,\n  a row rises left to right. Read DOWN a column: if seq 00 "
          "is the problem,\n  its row sits above the controls at the same "
          "range separation.")
    if args.out:
        Path(args.out).write_text(json.dumps(
            {"cell_m": args.cell, "lo_m": args.lo, "hi_m": args.hi,
             "frames": args.frames, "sequences": rows}, indent=2))
        print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
