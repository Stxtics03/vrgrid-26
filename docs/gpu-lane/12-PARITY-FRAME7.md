# Why CPU/CUDA parity fails at frame 7 on a T4

`gpu_parity.py --seq 08 --frames 200` passes on the laptop RTX 5050 and fails
on a Kaggle Tesla T4 (driver 580.159.04) at frame 7, on `range_image`.
Reproduced and diagnosed by `scripts/kaggle/parity-frame7.ipynb`; raw output in
`t4/parity-frame7-diagnosis.log`.

## What it is not

**Not a tie-break race.** `project_keys` packs
`key = (pix << 49) | (range_bits << 18) | point_index`. The index is unique, so
every key is unique, `sort()` is a total order, and `project_write`'s winner is
deterministic by construction. Two points cannot tie.

**Not an overflow.** `device.py:176` raises if `npix > (1 << KEY_PIX_BITS)`.

**Not a grid or kernel bug.** The divergence is in perception's range image,
upstream of anything in `src/grid` or the map hash.

## What it is

Three differing pixels out of 32,768 (0.0092%), frame 7:

    pixel (v=15, u=165)   cpu winner 56230   gpu winner 58375
    pixel (v=16, u=165)   cpu winner 58375   gpu winner 58376
    pixel (v=39, u=468)   cpu winner 89740   gpu winner 89741

Read those two rows together. **Point 58375 is in row 15 on the GPU and row 16
on the CPU.** It is not a contested winner; it is one point landing in two
different rows, and everything else is the backfill. The diagnostic's own
counters say "same pixel, winner changed: 3" and "a point moved pixels: 0",
and that classification is WRONG -- it only counted a move when one side left
the pixel empty, and here another point immediately takes the vacated row.
Trust the indices, not the counter.

The mechanism is precision at a bin edge:

    6 offending points, distance to nearest bin edge
      azimuth    min 3.155e-05   median 3.756e-01   within 1e-6: 0
      elevation  min 5.227e-07   median 1.968e-01   within 1e-6: 2

Two of the six sit within 5.2e-7 of an **elevation** row boundary; none are
near an azimuth boundary. At that distance one ULP of float32 decides which
side of `floor()` the point falls on. The `r` values differ by ~1e-7, which is
about one ULP at these magnitudes:

    pt 58375  r f32 4.0192947   f64 4.0192947723959795   delta 3.363e-08
    pt 89740  r f32 8.376147    f64 8.376147395131717    delta 1.249e-07

## Why the two paths can disagree at all

They compute the same quantities differently, and agree on the laptop by luck.

| | CPU (`range_image.project`) | CUDA (`project_keys`) |
|---|---|---|
| `r` | `np.linalg.norm`, float32 | `sqrt(x*x+y*y+z*z)`, float32, **FMA-contractable** |
| `atan2`, `asin` | numpy float32 | libdevice **double**, then narrowed to float |
| azimuth bin | float32 | float32 |
| elevation bin | float32 | double, but from an already-narrowed float `el` |

Three separate opportunities to differ in the last bit. Turing (sm_75) and
Blackwell (sm_120) need not contract `x*x + y*y` into an FMA the same way, and
libdevice's transcendentals are not bit-identical across architectures. The
laptop agreement was a property of that machine, not of the code -- which is
exactly what running parity on a second card was for.

## The fix, and who owns it

Do the angle-to-bin arithmetic in **float64 on both paths**, so a float32 ULP
cannot flip a row:

- `src/gpu/cuda_kernels.py` (`project_keys`) -- stop narrowing: keep `az` and
  `el` as `double`, and do the azimuth division in double as the elevation
  division already is. **Shrestha's file.**
- `src/perception/range_image.py` -- promote `xyz` to float64 before
  `arctan2`/`arcsin`, or compute `u`/`v` in float64 explicitly. **JP's file --
  his call, not a unilateral edit.**

This does not make a point exactly on a boundary well-defined; that is
measure-zero and unfixable. It removes the ULP-scale wobble that currently
decides it differently on different hardware.

## What to claim until then

The determinism guarantee holds **on a single machine**: same input, same
machine, same bits, run to run. The cross-card claim does not currently hold
and should not be written as though it does. Three pixels in 131,072 over
eight frames is small, and it is still a real divergence that reaches
`inverse_index` and therefore reflectivity and everything downstream of it.
