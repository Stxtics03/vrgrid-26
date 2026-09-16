"""The frame loop's device half: scatter and §10.4 cleanup on the card. [Shrestha]

`scatter_sorted` and `visibility_cleanup` have run on device since 13 Sep, bit-
identical to CPU, but only in their own benchmarks -- nothing on the real frame
path ever called them there. This is the seam that does, and it is deliberately
narrow:

    host  bin_points (grid)     ->  upload  ->  scatter_sorted            (device)
          fuse (grid)           <-  download aggregate
          occupancy_state (grid) ->  upload occupied slots + their heights
                                          slot -> centre, guard, eq (32)  (device)
          apply_miss            <-  download see-through mask

**The grid itself stays on the host.** `fuse`, `occupancy_state` and
`bin_points` are numpy in `src/grid` (Aakash), and moving the SoA arrays to the
card means porting them, which is not this directory's call. So the device
receives exactly what the two ported kernels read and hands back exactly what
the host stages consume -- and the map a device run builds is required to hash
identically to a CPU run's, frame for frame (`scripts/gpu_parity.py`).

⚑ NOTHING IS ALLOCATED PER FRAME ON EITHER SIDE. Every device buffer is sized
  at construction from the same caps the CPU scratch uses, and every host
  mirror is pinned memory allocated once, so a download is a DMA copy into a
  fixed page rather than a staging copy cupy invents. The only per-frame
  device allocations are the ones inside `compat.segment_min` and cupy's
  casting in `scatter_sorted`; they come from cupy's pool, which reuses the
  same blocks every frame, and `device_bytes()` reports the pool's high-water
  mark so they are declared rather than hidden.

⚑ THE SYNCHRONISATION IS INSIDE THE STAGE. The downloads block until the
  kernels finish, so a Timer stage around `scatter()` or `cleanup_slots()` measures
  upload + kernel + download, which is what a frame actually pays. Timing the
  kernel call alone would time the launch, not the work (port plan §7).
"""

import numpy as np
from vrgrid.gpu.kernels import CEILING_NONE, CellAggregate, new_sorted_scratch, scatter_sorted
from vrgrid.gpu.visibility import CleanupResult, new_visibility_scratch, visibility_cleanup

DEVICES = ("cpu", "cuda")

# The aggregate columns in the order `CellAggregate` takes them.
_AGG = ("cells", "wz_sum", "w_sum", "n", "ceiling_cm", "refl_sum", "class_id")


def cuda_available() -> bool:
    """A usable card AND a cupy that can launch a kernel on it.

    Importing cupy is not enough: a missing CUDA header only fails at the first
    JIT, which is exactly the "broken GPU" `07-LOCAL-BUILD.md` warns about. So
    this launches one elementwise kernel and reads the answer back.
    """
    try:
        import cupy
        if cupy.cuda.runtime.getDeviceCount() < 1:
            return False
        return int((cupy.arange(4, dtype=cupy.int32) * 2).sum()) == 12
    except Exception:  # noqa: BLE001 -- any failure here means "not usable"
        return False


def resolve_device(device: str) -> str:
    """Validate a `--device` value. Fails loudly: a run asked for on the card
    that silently fell back to the CPU would publish a CPU number as a GPU one."""
    if device not in DEVICES:
        raise ValueError(f"device must be one of {DEVICES}, not {device!r}")
    if device == "cuda" and not cuda_available():
        raise RuntimeError(
            "--device cuda was requested but no working CUDA device was found "
            "(cupy import, device count, or first kernel launch failed). Run "
            "scripts/verify_env.py; the usual cause is cupy not finding its "
            "CUDA headers -- see docs/gpu-lane/07-LOCAL-BUILD.md.")
    return device


class DeviceKernels:
    """Preallocated device buffers and pinned host mirrors for one engine.

    `max_points` and `n_cells` size the scatter exactly as `allocate()` sizes
    the host scratch; `max_candidates` sizes the cleanup exactly as the engine
    sizes its candidate buffers. The two paths therefore refuse the same
    inputs, which is part of what makes a parity check meaningful.
    """

    def __init__(self, max_points: int, n_cells: int, max_candidates: int):
        import cupy
        import cupyx

        self.cp = cupy
        self.pool = cupy.get_default_memory_pool()
        used_before = self.pool.used_bytes()

        self.max_points = max_points
        self.max_candidates = max_candidates
        self.scatter_scratch = new_sorted_scratch(max_points, n_cells, xp=cupy)
        self.vis_scratch = new_visibility_scratch(max_candidates, np.float32, xp=cupy)

        # Upload staging, one buffer per input column, in the width the host
        # stages already produce so `.set()` is a straight copy with no cast.
        self.inp = {
            "idx": cupy.zeros(max_points, np.int64),
            "z_cm": cupy.zeros(max_points, np.int16),
            "w_q": cupy.zeros(max_points, np.int32),
            "refl": cupy.zeros(max_points, np.uint8),
            "cls": cupy.zeros(max_points, np.uint8),
            "ground": cupy.zeros(max_points, np.bool_),
        }
        self.cand = {n: cupy.zeros(max_candidates, np.float64) for n in "xyz"}
        self.guard = cupy.zeros(max_candidates, np.bool_)
        # Slot -> centre inverse and the current-return guard, on device.
        self.slots = cupy.zeros(max_candidates, np.int64)
        self.work = cupy.zeros(max_candidates, np.int64)
        self.row = cupy.zeros(max_candidates, np.int64)
        self.ceil = cupy.zeros(max_candidates, np.int16)
        self.ground = cupy.zeros(max_candidates, np.int16)
        self.touched = cupy.zeros(len(self.scatter_scratch["cells"]), np.int64)
        self.pos = cupy.zeros(max_candidates, np.int64)
        self.ceil_host = cupyx.empty_pinned(max_candidates, np.int16)
        self.ground_host = cupyx.empty_pinned(max_candidates, np.int16)
        self.image = None           # sized at the first frame, as on the host

        # Pinned host mirrors of what comes back.
        cells_cap = len(self.scatter_scratch["cells"])
        self.agg_host = {
            name: cupyx.empty_pinned(cells_cap, self.scatter_scratch[name].dtype)
            for name in _AGG
        }
        self.see_through_host = cupyx.empty_pinned(max_candidates, np.bool_)

        self.static_bytes = self.pool.used_bytes() - used_before

    # -- scatter ------------------------------------------------------------

    def scatter(self, idx, z_cm, w_q, refl, cls, ground) -> CellAggregate:
        """`scatter_sorted` on the card; the aggregate comes back as views into
        pinned host memory, with the same lifetime contract as the CPU path's
        views into its scratch: valid until the next `scatter()`."""
        n = len(idx)
        if n > self.max_points:
            raise ValueError(f"{n:,} points exceeds the device scratch capacity "
                             f"of {self.max_points:,}")
        for name, host in (("idx", idx), ("z_cm", z_cm), ("w_q", w_q),
                           ("refl", refl), ("cls", cls), ("ground", ground)):
            buf = self.inp[name]
            self._upload(buf[:n], host)
        d = self.inp
        agg = scatter_sorted(d["idx"][:n], d["z_cm"][:n], d["w_q"][:n],
                             d["refl"][:n], d["cls"][:n], d["ground"][:n],
                             scratch=self.scatter_scratch)
        k = len(agg.cells)
        if k == 0 or not isinstance(agg.cells, self.cp.ndarray):
            return agg            # the empty aggregate is already host-side
        out = []
        for name in _AGG:
            host = self.agg_host[name][:k]
            getattr(agg, name).get(out=host)
            out.append(host)
        return CellAggregate(*out)

    # -- cleanup ------------------------------------------------------------

    def cleanup_slots(self, occupied, touched, grid, rings, buffers, ego, z_datum,
                      range2d, sensor, floor_m) -> CleanupResult:
        """The whole §10.4 step from occupied SLOTS, not centres.

        `MapEngine._centres` + `np.isin` + `visibility_cleanup`, with the first
        two moved onto the card as well: measured on seq 08 the host inverse
        was 12.7 ms and the guard 1.9 ms against 3.2 ms for the kernel itself,
        so porting only the kernel left most of the stage behind.

        ⚑ Must equal the CPU path bit for bit, and it is written to: the same
          float64 expression in the same operation order, `(ix + 0.5) * cell_m
          - ego`, one ufunc per step so nothing can be contracted into a fused
          multiply-add. `scripts/gpu_parity.py` hashes the map every frame.

        `occupied` must be sorted ascending (it is `np.flatnonzero`), which is
        what lets each ring be one contiguous range instead of a mask: rings
        occupy disjoint, ascending slot ranges. `touched` is the aggregate's
        cell column, sorted and unique, which is what makes the guard a
        `searchsorted` rather than a set membership.
        """
        cp = self.cp
        m = len(occupied)
        if m > self.max_candidates:
            raise ValueError(f"{m:,} candidates exceeds the device capacity of "
                             f"{self.max_candidates:,}")
        if m == 0:
            return CleanupResult(self.see_through_host[:0], 0, 0, 0, 0)

        occupied = np.asarray(occupied)
        slots = self.slots[:m]
        self._upload(slots, occupied.astype(np.int64, copy=False))

        # Heights: gathered on the host (the grid lives there) into pinned
        # buffers, then one upload each. intp indices + clip: no copy.
        np.take(grid["ceiling_height"], occupied, out=self.ceil_host[:m], mode="clip")
        np.take(grid["ground_height"], occupied, out=self.ground_host[:m], mode="clip")
        self._upload(self.ceil[:m], self.ceil_host[:m])
        self._upload(self.ground[:m], self.ground_host[:m])

        cx, cy, cz = self.cand["x"][:m], self.cand["y"][:m], self.cand["z"][:m]
        work, row = self.work, self.row
        for layout, buf in zip(rings, buffers):
            lo, hi = np.searchsorted(occupied, (layout.offset, layout.offset + layout.slots))
            lo, hi = int(lo), int(hi)
            if lo == hi:
                continue
            W = buf.side
            local, r = work[lo:hi], row[lo:hi]
            cp.subtract(slots[lo:hi], layout.offset, out=local)
            cp.floor_divide(local, W, out=r)
            cp.remainder(local, W, out=local)             # col
            # ix = x0 + mod(col - x0, W), then (ix + 0.5) * cell_m - ego_x
            cp.subtract(local, buf.x0, out=local)
            cp.remainder(local, W, out=local)
            cp.add(local, buf.x0, out=local)
            cp.add(local, 0.5, out=cx[lo:hi])
            cp.multiply(cx[lo:hi], layout.cell_m, out=cx[lo:hi])
            cp.subtract(cx[lo:hi], float(ego[0]), out=cx[lo:hi])
            cp.subtract(r, buf.y0, out=r)
            cp.remainder(r, W, out=r)
            cp.add(r, buf.y0, out=r)
            cp.add(r, 0.5, out=cy[lo:hi])
            cp.multiply(cy[lo:hi], layout.cell_m, out=cy[lo:hi])
            cp.subtract(cy[lo:hi], float(ego[1]), out=cy[lo:hi])

        # z: ceiling where one was seen, else ground; cm -> m; datum; vehicle.
        ceil, ground = self.ceil[:m], self.ground[:m]
        cp.copyto(ground, ceil, where=ceil != CEILING_NONE)
        cp.divide(ground, 100.0, out=cz)
        cp.add(cz, float(z_datum), out=cz)
        cp.subtract(cz, float(ego[2]), out=cz)

        # Guard: slot in this frame's touched cells. `touched` is sorted and
        # unique, so the insertion point holds the slot exactly when it is in.
        k = len(touched)
        guard = self.guard[:m]
        if k:
            t = self.touched[:k]
            self._upload(t, np.asarray(touched, dtype=np.int64))
            pos = self.pos[:m]
            pos[...] = cp.searchsorted(t, slots)
            cp.minimum(pos, k - 1, out=pos)
            cp.equal(t[pos], slots, out=guard)
        else:
            guard.fill(False)

        if self.image is None or self.image.shape != range2d.shape:
            self.image = cp.zeros(range2d.shape, np.float32)
        self._upload(self.image, range2d)
        res = visibility_cleanup(cx, cy, cz, self.image, has_return_now=guard,
                                 sensor=sensor, floor_m=floor_m,
                                 protect_current_returns=True,
                                 scratch=self.vis_scratch)
        host = self.see_through_host[:m]
        res.see_through.get(out=host)
        return CleanupResult(host, res.tested, res.out_of_view, res.protected,
                             res.cleared)

    # -- accounting ---------------------------------------------------------

    def device_bytes(self) -> dict:
        """What this engine holds on the card, pool and driver both shown --
        `03-CUDA-PORT-PLAN.md` §5: cupy's pool caches, so `used` is what our
        arrays hold and `reserved` is what cupy has taken from the driver."""
        return {"static": self.static_bytes,
                "pool_used": self.pool.used_bytes(),
                "pool_reserved": self.pool.total_bytes()}

    @staticmethod
    def _upload(dst, host):
        """Host column -> device buffer of the same width. A dtype mismatch is
        an error rather than a cast, because a cast here would allocate a host
        temporary every frame."""
        host = np.asarray(host)
        if host.dtype != dst.dtype:
            raise TypeError(f"upload expects {dst.dtype}, got {host.dtype}; "
                            "cast once on the host stage that produces it")
        dst.set(np.ascontiguousarray(host))
