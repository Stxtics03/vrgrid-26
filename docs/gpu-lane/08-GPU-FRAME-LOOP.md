# The pipeline on the GPU

*Shrestha, 2026-09-17. Supersedes the 2026-09-16 version of this file, which
moved only scatter and the cleanup kernel and left the map on the host.*

```bash
python -m vrgrid.run --seq 08 --device cuda --viz                   # Rerun, on the card
python scripts/gpu_parity.py --seq 08 --frames 200                 # bit-identical, every frame
python scripts/timing_table.py --seq 08 --frames 200 --device cuda  # latency
```

**Headline: the whole frame runs at 22.3 ms p50 / 26.7 ms p99 on the card,
against 88.6 / 107.2 ms on the CPU on the same machine, same session. That is
45 FPS, and it meets 10 Hz at p99 with 3.7x headroom. The CPU pipeline misses
it. Range image, labels, reflectivity, the map grid and every map stage run on
the GPU, and the output is bit-identical to the CPU pipeline on every one of
200 real frames.**

## What runs where

| stage | where | how |
|---|---|---|
| load | host | disk |
| transform | host | one BLAS pose product, ~1.4 ms, uploaded |
| **range image** | **device** | CUDA kernel + 64-bit key sort (closest return wins) |
| **semantics, motion** | **device** | LUT built from JP's own functions over all 65,536 label words |
| ground | host | **Patchwork++**, a C++ CPU library, runs while the card works |
| **reflectivity** | **device** | per-pixel kernel, scattered to points |
| **shift, datum** | **device** | strip clear; re-base kernel |
| **bin** | **device** | ring + lattice + toroidal slot in one kernel |
| **scatter** | **device** | payload kernel + `scatter_sorted` on cupy |
| **fuse** | **device** | Kalman, ceiling, occupancy, Boyer-Moore, reflectivity, counts: one kernel |
| **occupancy, centres, guard, eq (32), misses** | **device** | kernels + cupy |

**The grid lives in device memory.** `MapEngine.handle.grid` becomes a
`MirroredGrid`: a read-only host copy that refreshes on the first read after a
frame. The dashboard, `map_hash`, the feature detectors and `occupied_cells()`
keep reading numpy and pay the 10.9 MB copy only when they look. A write to it
raises, because the next sync would silently overwrite it.

Frames from `iter_pipeline(device="cuda")` are `DeviceFrame`s. Their
perception outputs stay on the card for the engine. `semantic`,
`range_image` and the other perception fields download only if something reads
them (the dashboard does, a headless run does not), and they refuse to once
the next frame has reused the buffers.

What stays on the host: Patchwork++ (CLAUDE.md: wire it in, do not
reimplement it), the pose transform (its BLAS rounding cannot be promised on
device) and the disk read.

## Parity — seq 08, frames 0–199, Patchwork++, ghost removal on

For each scan `gpu_parity.py` runs perception on both paths and folds each
frame into its own engine. After every frame it compares exactly: the range
image (NaN-aware), inverse index, reflectivity bytes, semantic labels, motion
flags, every counter, and the full-grid hash. Patchwork++ runs once and both
paths get its mask; running it twice would compare D1, not the GPU.

- **identical on 200 / 200 frames**, final map hash `4e180a121d7b5aaac95df6a97fe2374b`.
  (Before 2026-09-17 it was `4313df1a58e68f0ed69a6e5417db4000`. The change is the
  per-block ring rule of open item D2 on BOTH paths -- 0.224% of returns that
  used to be dropped are now binned -- and the two paths still agree.)
- 7,609,197 cells cleared by §10.4 over the run, so the comparison exercises the cleanup
- also identical with `--max-points 100000`, where the engine truncates each scan

## What it took to make "identical" true

Each of these was measured before it was relied on. Each would otherwise have
produced a map that looked right and hashed differently.

1. **NVRTC fuses `a*b + c` by default.** `x*0.1 + 0.7` over 1M doubles: 289,150
   mismatches with contraction, 0 with `--fmad=false`. Every kernel is compiled
   with the flag and written in the numpy reference's operation order.
2. **cupy's float `//` is not numpy's.** `1.0 // 0.1` is 9 in numpy and 10 in
   cupy, and 42,425 of 5M lattice-scale coordinates disagreed. `bin_points`
   floors every world coordinate onto the 5 cm lattice, so the kernel carries
   numpy's `npy_divmod` line for line.
3. **atan2 / asin.** The float32 device overloads put 116 of 24.5M points in a
   different range-image pixel over 200 frames. numpy's float32 results are
   correctly rounded on glibc 2.42, and double-precision device results rounded
   to float32 matched them on all 3.7M points tested. The kernel computes in
   double and rounds.
4. **The variance codec uses `log`,** which is not guaranteed to agree across
   libms. The kernel does not call it. `variance_code_thresholds()` bisects
   Aakash's `quantise_variance_cm2` over double bit patterns for the 255 code
   boundaries, checks monotonicity, and the kernel binary-searches the table.
   It matches the codec on 2M values including every boundary ±1 ulp.
5. **"Closest return wins"** is JP's stable argsort by range plus
   first-per-pixel. On device it is a sort of unique `pixel | range bits |
   index` keys, which selects the same winner including on exact range ties.

## Latency — seq 08, 200 frames, same session, back to back

| stage | cpu p50 | cpu p99 | **cuda p50** | **cuda p99** |
|---|---|---|---|---|
| load | 0.51 | 0.93 | 0.46 | 0.84 |
| transform | 1.45 | 2.66 | 1.43 | 2.16 |
| range_image | 22.96 | 29.05 | **1.13** | **2.85** |
| semantics + motion | 0.50 | 0.75 | **0.10** | **0.14** |
| ground (Patchwork++, host both) | 12.54 | 14.59 | 12.57 | 14.86 |
| reflectivity | 3.53 | 4.98 | **0.02** | **0.04** |
| bin | 6.77 | 9.82 | **0.18** | **0.23** |
| bin, after D2 (2026-09-17) | 10.27 | 12.92 | **0.35** | **0.42** |
| scatter | 7.08 | 10.86 | **1.47** | **2.02** |
| fuse | 4.11 | 5.70 | **0.05** | **0.07** |
| cleanup | 26.70 | 34.79 | **1.65** | **2.40** |
| shift | 2.11 | 5.81 | 2.94 | 4.64 |
| **FRAME** | **88.62** | **107.19** | **22.27** | **26.73** |
| 10 Hz at p99 | misses | | **meets, 3.7x** | |

Stage rows on cuda synchronise the device at each boundary, so each row is
real work and not a kernel launch. The free-running pass, with no per-stage
synchronisation, gives 22.23 / 27.89 ms: the staged table is not flattering
the device. On cuda, `shift` includes uploading the frame's ground mask.

The `bin` row after D2 is the per-block ring rule: three levels of a coarse-to-fine
descent per point instead of one comparison. Whole frame after it, same command:
cpu 91.73 / 102.77 ms, cuda **22.26 / 26.74 ms** -- the device frame does not
move, and the host frame still misses 10 Hz at p99 as it did before.

**Patchwork++ is now 56% of the frame.** It is the only large stage left and
it is a CPU library by project rule. Everything else in the frame totals under
10 ms.

## Device memory

134.96 MB preallocated on the card (grid 10.9 MB, scatter scratch, and the
eq (32) candidate buffers sized to the structural cap of 910,000 slots). The
pool reports ~145 MB used and up to ~416 MB reserved, because cupy caches the
per-frame temporaries of `flatnonzero`, `searchsorted` and the sort. The host
allocation and every memory figure on a slide are unchanged: `report()`
describes the CPU configuration, and the device bytes are declared separately
through `MapEngine.device_bytes()`.

## Tests

`tests/test_device.py`, 13 tests:
- each kernel against its reference on adversarial inputs: lattice-boundary
  coordinates, exact range ties, codec boundaries ±1 ulp
- the engine on both devices over the Gate 3 ghost scene, with ghost removal
  on and off, hashing the grid every frame
- stale-frame refusal, the read-only mirror, and host allocation per step

The codec table test needs no card and runs in CI; the rest skip without one.

## Hand-offs, not done here

- **`dashboard/__main__.py:66`** builds `MapEngine` without `device`, so
  `python -m vrgrid.dash` stays on CPU. `python -m vrgrid.run --viz --device
  cuda` is the GPU dashboard today. Passing it through is one line for the
  dashboard owner.
- **`dashboard/gpu_stats.py` docstring** ("`src/gpu/` is NumPy on the CPU") is
  out of date for `--device cuda`.
- **T4 column** on the AWS instance, per port plan §7.
