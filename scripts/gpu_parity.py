#!/usr/bin/env python3
"""The GPU frame loop on real data: same map, and what it costs. [Shrestha]

    python scripts/gpu_parity.py --seq 08 --frames 200

One perception pass; every frame is handed to TWO engines, one `device="cpu"`
and one `device="cuda"`. After each step the full SoA grid of both is hashed
and the two hashes -- and every `StepCounters` field -- must agree. Any
disagreement stops the run and exits 1 naming the frame, because a device map
that differs from the CPU map by one cell is not a faster map, it is a
different one.

Why one perception pass rather than two runs: Patchwork++ is a stateful
singleton and two replays of the same sequence do not produce identical ground
masks (open item D1, `docs/gpu-lane/07-LOCAL-BUILD.md`). Feeding the SAME frame
object to both engines takes perception out of the comparison, so a mismatch
here can only be the map back end.

Benchmark discipline is `03-CUDA-PORT-PLAN.md` §7: the first `--warmup` frames
are discarded (JIT and first-touch), synchronisation happens inside the timed
stage (the downloads block), p50 and p99 nearest-rank, never the mean, and the
two devices are printed as two columns rather than a ratio alone. The GPU's
name, driver and current clock are recorded next to the table because a
throttled afternoon run and a boosted morning one are different experiments.
"""
import argparse
import platform
import subprocess
import sys
import time

import numpy as np

STAGES_SHOWN = ("bin", "scatter", "fuse", "cleanup", "shift", "total")


def _smi(query: str) -> str:
    try:
        return subprocess.run(["nvidia-smi", f"--query-gpu={query}",
                               "--format=csv,noheader"], capture_output=True, check=False,
                              text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "n/a"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seq", default="08")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--start-frame", type=int, default=0)
    ap.add_argument("--warmup", type=int, default=10,
                    help="frames excluded from timing (still hash-checked)")
    ap.add_argument("--schedule", default="5/10/20/40")
    ap.add_argument("--no-patchworkpp", action="store_true")
    ap.add_argument("--show-ghosts", action="store_true",
                    help="run both engines with the §10.4 cleanup OFF")
    args = ap.parse_args(argv)

    from vrgrid.gpu.kernels import map_hash
    from vrgrid.gpu.timing import STAGES, Timer
    from vrgrid.grid.schedule import load
    from vrgrid.run.__main__ import iter_pipeline
    from vrgrid.run.engine import MapEngine

    sched = load(args.schedule)
    timers = {d: Timer(stages=STAGES) for d in ("cpu", "cuda")}
    engines = {d: MapEngine(sched, ghost_removal=not args.show_ghosts,
                            timer=timers[d], device=d)
               for d in ("cpu", "cuda")}

    n, cleared = 0, 0
    for frame in iter_pipeline(args.seq, args.frames,
                               use_patchworkpp=not args.no_patchworkpp,
                               start_frame=args.start_frame):
        counters, hashes = {}, {}
        for d, eng in engines.items():
            t0 = time.perf_counter()
            counters[d] = eng.step(frame)
            timers[d].record("total", (time.perf_counter() - t0) * 1e3)
            hashes[d] = map_hash(eng.handle.grid)
        if hashes["cpu"] != hashes["cuda"] or counters["cpu"] != counters["cuda"]:
            print(f"MISMATCH at frame {frame.index}:\n"
                  f"  cpu  {hashes['cpu']}  {counters['cpu']}\n"
                  f"  cuda {hashes['cuda']}  {counters['cuda']}")
            return 1
        cleared += counters["cuda"].cleared
        n += 1
        if n == args.warmup:
            for t in timers.values():
                t.reset()
        if n % 25 == 0:
            print(f"  frame {frame.index}: identical, {counters['cuda'].occupied:,} "
                  f"occupied, {counters['cuda'].cleared:,} cleared, hash {hashes['cuda']}")

    if n <= args.warmup:
        print(f"only {n} frames; need more than --warmup {args.warmup}")
        return 1

    import cupy
    print(f"\nsequence {args.seq}, frames {args.start_frame}..{args.start_frame + n - 1} "
          f"({n}), schedule {args.schedule}, ghost removal "
          f"{'OFF' if args.show_ghosts else 'ON'}")
    print(f"map hash identical on all {n} frames; final {map_hash(engines['cuda'].handle.grid)}")
    print(f"cells cleared by §10.4 over the run: {cleared:,}\n")
    print(f"CPU     {platform.processor() or platform.machine()}, numpy {np.__version__}, "
          f"python {platform.python_version()}")
    print(f"GPU     {_smi('name,driver_version')}, cupy {cupy.__version__}, "
          f"CUDA runtime {cupy.cuda.runtime.runtimeGetVersion()}")
    print(f"clock   {_smi('clocks.sm,temperature.gpu,power.draw')}  (after the run)\n")

    head = f"{'stage':<9}{'cpu p50':>9}{'cpu p99':>9}{'cuda p50':>10}{'cuda p99':>10}{'p50 x':>8}"
    print(f"timed over {n - args.warmup} frames after {args.warmup} warm-up\n")
    print(head)
    print("-" * len(head))
    summ = {d: t.summary() for d, t in timers.items()}
    for s in STAGES_SHOWN:
        if s not in summ["cpu"]:
            continue
        c, g = summ["cpu"][s], summ["cuda"][s]
        label = "ENGINE" if s == "total" else s
        print(f"{label:<9}{c['p50_ms']:>9.2f}{c['p99_ms']:>9.2f}{g['p50_ms']:>10.2f}"
              f"{g['p99_ms']:>10.2f}{c['p50_ms'] / g['p50_ms']:>7.1f}x")
    print("\nENGINE is MapEngine.step only; perception is shared and not timed here "
          "(scripts/timing_table.py --seq 08 --device cuda gives the whole frame).")
    print("scatter and cleanup on cuda INCLUDE the host<->device copies.")

    b = engines["cuda"].device_bytes()
    print(f"\ndevice memory: {b['static'] / 1e6:.2f} MB preallocated buffers, "
          f"pool used {b['pool_used'] / 1e6:.2f} MB, pool reserved "
          f"{b['pool_reserved'] / 1e6:.2f} MB, card {_smi('memory.used')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
