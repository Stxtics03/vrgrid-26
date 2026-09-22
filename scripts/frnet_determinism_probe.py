#!/usr/bin/env python3
"""Is `--semantics frnet` reproducible, and if not, at what thread count?

The 19 Sep entry in `docs/research-log.md` recorded run-to-run label
disagreement on the frnet path and blamed FRNet's CUDA `scatter_mean`. That
cannot be the cause of the CPU-vs-CPU half of it, and it is not: the site is
the duplicate-index write in `FRNet.range_interpolation`, and the variable the
entry never recorded is `torch.get_num_threads()`. This reproduces that.

    python scripts/frnet_determinism_probe.py                  # all conditions
    python scripts/frnet_determinism_probe.py --frames 3       # fewer frames

Each condition runs in its OWN interpreter, because "two runs" in the original
entry meant two processes. `--in-process` adds the back-to-back check that
rules out a process-level artefact.

Needs `VRGRID_DATA_ROOT` (or the default `data/`) and, unless
`configs/frnet.yaml` resolves it, `VRGRID_FRNET_CHECKPOINT`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path(os.environ.get("VRGRID_DATA_ROOT", REPO / "data"))


def _scan_dir(seq: str) -> Path:
    return DEFAULT_ROOT / "sequences" / seq / "velodyne"


def worker(seq: str, frames: int, threads: int, out: str, repeats: int) -> None:
    """One interpreter: load FRNet, label `frames` scans, save the labels."""
    import torch

    if threads > 0:
        torch.set_num_threads(threads)

    sys.path.insert(0, str(REPO / "src"))
    from perception.semantics import FRNetInference

    inf = FRNetInference()
    print(
        f"[probe] torch {torch.__version__}  threads={torch.get_num_threads()}  "
        f"device={inf.device}",
        flush=True,
    )

    payload = {}
    for i in range(frames):
        pts = np.fromfile(_scan_dir(seq) / f"{i:06d}.bin", dtype=np.float32).reshape(-1, 4)
        for r in range(repeats):
            payload[f"f{i}r{r}"] = inf.infer_points(pts)
    np.savez(out, **payload)


def _disagreement(a: np.ndarray, b: np.ndarray) -> tuple[int, float]:
    d = int((a != b).sum())
    return d, 100.0 * d / len(a)


def _spawn(seq: str, frames: int, threads: int, cuda: bool, repeats: int, tag: str) -> Path:
    out = Path(tempfile.gettempdir()) / f"frnet_det_{tag}.npz"
    env = dict(os.environ)
    if not cuda:
        env["CUDA_VISIBLE_DEVICES"] = ""
    if threads > 0:  # keep the BLAS pools in step with torch's
        env["OMP_NUM_THREADS"] = env["MKL_NUM_THREADS"] = str(threads)
    subprocess.run(
        [sys.executable, __file__, "--worker", "--seq", seq, "--frames", str(frames),
         "--threads", str(threads), "--repeats", str(repeats), "--out", str(out)],
        env=env, cwd=REPO, check=True,
    )
    return out


def _compare(a_path: Path, b_path: Path, label: str, frames: int) -> None:
    a, b = np.load(a_path), np.load(b_path)
    cells = []
    for i in range(frames):
        _, pct = _disagreement(a[f"f{i}r0"], b[f"f{i}r0"])
        cells.append(f"{pct:9.4f}%")
    print(f"    {label:<50s}{''.join(cells)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", default="08")
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--in-process", action="store_true",
                    help="also check two back-to-back calls inside one interpreter")
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--threads", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--repeats", type=int, default=1, help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.worker:
        worker(a.seq, a.frames, a.threads, a.out, a.repeats)
        return 0

    if not _scan_dir(a.seq).is_dir():
        print(f"no scans at {_scan_dir(a.seq)} -- set VRGRID_DATA_ROOT", file=sys.stderr)
        return 2

    import torch  # only to report what "default" means on this host

    print(f"seq {a.seq}, frames 0-{a.frames - 1}, "
          f"PyTorch default thread count here = {torch.get_num_threads()}\n")
    print("    condition" + " " * 41 + "".join(f"  frame {i}" for i in range(a.frames)))

    for tag, label, threads, cuda in (
        ("cpu_dflt", "CPU, default threads, two processes", 0, False),
        ("cpu_t1", "CPU, torch.set_num_threads(1), two processes", 1, False),
        ("cuda", "CUDA, two processes", 0, True),
    ):
        if cuda and not torch.cuda.is_available():
            print(f"    {label:<50s}  (no CUDA on this host)")
            continue
        runs = [_spawn(a.seq, a.frames, threads, cuda, 1, f"{tag}_{r}") for r in "AB"]
        _compare(runs[0], runs[1], label, a.frames)

    if a.in_process:
        out = _spawn(a.seq, a.frames, 0, False, 2, "cpu_inproc")
        d = np.load(out)
        cells = [f"{_disagreement(d[f'f{i}r0'], d[f'f{i}r1'])[1]:9.4f}%" for i in range(a.frames)]
        print(f"    {'CPU, default threads, back-to-back in ONE process':<50s}{''.join(cells)}")

    print("\n    Zero on the one-thread row and non-zero on the others is the expected\n"
          "    result: the predictions are reproducible, just not at the default\n"
          "    thread count. See docs/research-log.md, 2026-09-20 (correction).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
