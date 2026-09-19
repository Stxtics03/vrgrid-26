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

## Which side moved: not the GPU

`scripts/kaggle/elprobe.py` computes the elevation of the five points involved
two ways -- numpy's float32 `arcsin`, and `asin` in double rounded to float32,
which is what `project_keys` does -- and was run on both machines.

    point 58375                 laptop (numpy 2.5.3)      Kaggle Xeon (numpy 2.0.2)
    numpy float32 arcsin    -0.082030467689037323      -0.08203047513961792
    double asin -> float32  -0.082030467689037323      -0.082030467689037323
    resulting row                             15                            16

**The kernel's value is bit-identical on both machines. numpy's is not.** The
CUDA path is the stable one; the host path changed underneath it, and the
parity test -- which compares host against device on one machine -- reported
that as the device disagreeing.

The two hosts differ in both numpy version (2.5.3 against 2.0.2) and CPU
(i7-14650HX against a Xeon @ 2.00 GHz), and this experiment does not separate
those. It does not need to: either way the float32 transcendental is the part
that is not portable, and the double-then-round is.

That also explains the kernel's own documented rule, "atan2/asin in double then
round to float32", listed in `src/gpu/CLAUDE.md` as one of three traps. It is
not a workaround for the GPU being awkward. It is the numerically stable
choice, and the host is the side that has not adopted it.

## A device-side fix was tried, and it is wrong

The obvious reading of the above is that the device should match the host's
float32 binning, since `(phi_max - elevation) / d_phi` is float32 in numpy
(confirmed: float32 in, float32 out, under numpy 2.x weak promotion). It was
implemented -- `float vt = ((float)phi_max - el) / (float)d_phi` -- and it
**fails parity on the laptop at frame 4**, worse than the double version it
replaced, which passes 200/200 there. Reverted, with the reason recorded in
the kernel so it is not retried.

The reason it fails is the line above: the host's float32 `arcsin` is not the
same function as this kernel's double `asin` rounded to float32. The double
subtraction is currently what absorbs that difference. Narrowing it exposes
the difference instead.

There is no device-only fix. The device is already doing the stable thing.

## The fix, and who owns it

`src/perception/range_image.py` should compute elevation and the row index in
**float64**: promote `xyz` before `arctan2`/`arcsin`, or at minimum compute
`elevation` in float64 and keep the bin arithmetic there. float64
transcendentals are far less likely to differ across numpy builds and CPUs,
and it would match what the kernel already does.

**That is JP's file, and his call.** The device half needs no change and must
not be "fixed" to match a host that is itself unstable.

## What to claim until then

The determinism guarantee holds **on a single machine**: same input, same
machine, same bits, run to run. That is what `make test-determinism` checks and
it is unaffected.

What does not hold is bitwise reproducibility **across host environments**, and
the honest statement of the cause is that it is numpy's float32 `arcsin`, not
the CUDA kernels. Three pixels in 131,072 over eight frames is small, and it
still reaches `inverse_index` and therefore reflectivity and everything
downstream of it.
