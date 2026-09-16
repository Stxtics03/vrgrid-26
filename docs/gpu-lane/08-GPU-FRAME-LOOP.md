# The GPU frame loop — the device kernels on the real pipeline

*Shrestha, 2026-09-16. Everything here is reproducible with the two commands
below, on the reference build in `07-LOCAL-BUILD.md`.*

```bash
python scripts/gpu_parity.py --seq 08 --frames 200               # same map, per stage
python scripts/timing_table.py --seq 08 --frames 200 --device cuda  # whole frame
python -m vrgrid.run --seq 08 --device cuda --viz                 # Rerun, on the card
```

**Headline: `MapEngine(device="cuda")` builds the same map as the CPU engine,
bit for bit, on every one of 200 real frames of seq 08. The map back end runs
2.3x faster at p50 and 2.3x at p99. Cleanup is the biggest win: 4.0x.**

Until today, `scatter_sorted` and `visibility_cleanup` ran on device only in
their own benchmarks (`06-DAY3-CUPY-FINDINGS.md`, commits 30f285b and dae46e6).
Nothing on the frame path called them there. `src/gpu/device.py` is the seam
that does.

## What runs where

| stage | where | owner |
|---|---|---|
| perception (load … reflectivity) | host | JP |
| `bin_points` | host | Aakash |
| upload columns → `scatter_sorted` → download aggregate | **device** | Shrestha |
| `fuse` | host | Aakash |
| `occupancy_state` | host | Aakash |
| upload slots + heights → slot→centre, guard, eq (32) → download mask | **device** | Shrestha |
| `apply_miss`, `shift` | host | Shrestha |

**The grid stays on the host**, because `fuse`, `occupancy_state` and
`bin_points` are numpy in `src/grid`. Moving the SoA arrays onto the card means
porting those, and that is Aakash's call, not something to do from
`src/gpu`. The device gets only what the ported stages read, and the host gets
back only what its own stages consume.

The slot→centre inverse (`MapEngine._centres`) moved to the device along with
the kernel. That was not planned. A breakdown after the first cut showed the
kernel at 3.2 ms and the host inverse at 12.7 ms, so porting only the kernel
left most of the stage behind. The CPU path still uses `_centres` unchanged.

## Parity — seq 08, frames 0–199, Patchwork++, ghost removal on

Both engines take the same `PerceptionFrame` object from one perception pass.
Two replays would differ in ground masks (D1, the Patchwork++ singleton), and
feeding the same frame to both keeps that out of the comparison. After every
step the script hashes the full grid and compares every `StepCounters` field.

- map hash identical on **200 / 200** frames, final `4313df1a58e68f0ed69a6e5417db4000`
- **7,609,197** cells cleared by §10.4 over the run, so the comparison is not vacuous
- `tests/test_device.py` does the same over the Gate 3 ghost scene, with
  ghost removal on and off, and asserts the scene cleared and protected cells.
  It skips without a card.

## Map back end, per stage (`gpu_parity.py`)

190 frames after 10 warm-up frames, interleaved on one machine, p50/p99 nearest-rank:

| stage | cpu p50 | cpu p99 | cuda p50 | cuda p99 |
|---|---|---|---|---|
| bin | 9.56 | 21.90 | 7.74 | 11.35 |
| scatter | 9.99 | 19.08 | **4.17** | **6.45** |
| fuse | 5.81 | 10.76 | 4.97 | 8.14 |
| cleanup | 35.76 | 49.18 | **8.86** | **13.79** |
| shift | 2.58 | 6.90 | 2.21 | 5.83 |
| **engine** | **65.83** | **88.19** | **29.21** | **39.08** |

⚠️ **bin, fuse and shift did not get faster.** Their code is identical in both
columns. The ~1.2x difference is an artefact of interleaving: the two engines
alternate every frame, so each one runs with the other's work in the caches.
Only scatter and cleanup changed, and the device numbers **include** the
host↔device copies. The downloads block, so the synchronisation is inside the
timed stage.

## Whole frame (`timing_table.py --seq 08`), same session, run back to back

| | cpu | cuda |
|---|---|---|
| FRAME p50 | 118.39 ms | **91.09 ms** |
| FRAME p99 | 152.88 ms | **117.25 ms** |
| 10 Hz at p50 | no | **yes** |
| 10 Hz at p99 | no | **no** |

⚠️ **The CPU column is slower than the 89.18 / 100.43 ms in the research log.**
That figure was taken on a quiet machine, and this laptop was not quiet today
(`range_image` alone went from 24.45 to 31.16 ms, and that stage has no device
code in it). Compare the two columns above with each other. Neither column is
comparable to the old figure.

**What is left is not in `src/gpu`.** On the CUDA frame, `range_image` (31.5 ms,
35%) and `ground` (16.9 ms, 19%) are the two largest stages, and both are in
JP's `src/perception`. `bin` (9.2 ms) is next and is Aakash's. Porting more of
my own code would not recover the p99. The next step is those owners' call.

## Device memory

| | |
|---|---|
| preallocated device buffers | 131.91 MB |
| cupy pool used | 132.04 MB |
| cupy pool reserved | 270.42 MB |
| whole card (`nvidia-smi`) | 457 MiB |

Most of the 132 MB is sized by `visibility.max_candidate_cells: null`, meaning
the structural cap of 910,000 slots. Every candidate buffer (centres, slots,
heights, eq (32) scratch) is sized to that cap. That is what makes it a bound
and not an estimate. A smaller cap chosen by the room shrinks it proportionally.
The pool reserves about 2x what it uses because of the per-frame device
temporaries inside `compat.segment_min` and cupy's casts. These are pool reuse,
not growth: `used` is flat from frame 10 onward.

The host allocation is unchanged. `allocate()` still commits the full CPU
scratch, so a device run does not change the memory figure on any slide. The
device bytes are declared separately through `MapEngine.device_bytes()`.

## Hand-offs — not done here, on purpose

- **`dashboard/__main__.py:66`** (dashboard owner) builds `MapEngine(sched,
  ghost_removal=…)` without `device`. `python -m vrgrid.dash --device cuda`
  needs one `add_argument` and `device=args.device` passed through.
  `python -m vrgrid.run --viz --device cuda` already works.
- **`dashboard/gpu_stats.py` docstring** says "`src/gpu/` is NumPy on the CPU;
  a panel implying the map is computed on the GPU would be false." That is
  still true for the default run. With `--device cuda` the GPU panel now shows
  real mapping load, so the caption can say so when the flag is set.
- **`scripts/demo.sh` / `gen_demo_rrds.py`** bake scenes on the CPU engine.
  Whether the demo should run on the card is a presentation decision.
- **T4 column.** Everything above is the RTX 5050 laptop (sm_120). Per port plan
  §7, re-run both scripts on the AWS instance and publish that as a separate
  column.
