"""The engine's device path: the same map as the CPU, frame for frame. [Shrestha]

`test_device_engine_is_bit_identical_to_cpu` is the requirement. It drives the
real `MapEngine` over the Gate 3 ghost scene from `test_engine.py`, one CPU and
one CUDA engine fed the same frames, and compares the full grid hash and every
counter after every step. It also asserts the scene exercised what matters --
cells were cleared and the guard protected some -- so it cannot pass on a run
where the cleanup never fired and both maps are trivially equal.

Every device test skips without a working card; the CPU-side checks on
`resolve_device` run everywhere, because a silent fallback from cuda to cpu is
the failure that would put a CPU number in a GPU column.
"""

import numpy as np
import pytest
from vrgrid.gpu import device as dev
from vrgrid.gpu.kernels import map_hash
from vrgrid.grid.schedule import load
from vrgrid.run.engine import MapEngine

needs_cuda = pytest.mark.skipif(not dev.cuda_available(),
                                reason="no working CUDA device")


def _frames(present_for=3, total=12, seed=0):
    import test_engine as te  # a failed import must fail, not skip
    rng = np.random.default_rng(seed)
    return [f for f, _ in te._sequence(rng, present_for, total)]


def _engine(device, **kw):
    return MapEngine(load("5/10/20/40"), max_points=40_000,
                     max_candidates=80_000, device=device, **kw)


def test_resolve_device_rejects_unknown_names():
    assert dev.resolve_device("cpu") == "cpu"
    with pytest.raises(ValueError):
        dev.resolve_device("gpu")


def test_cuda_without_a_card_fails_loudly(monkeypatch):
    monkeypatch.setattr(dev, "cuda_available", lambda: False)
    with pytest.raises(RuntimeError, match="no working CUDA device"):
        dev.resolve_device("cuda")


def test_cpu_engine_has_no_device_half():
    eng = _engine("cpu")
    assert eng.gpu is None and eng.device_bytes() is None


@needs_cuda
@pytest.mark.determinism
@pytest.mark.parametrize("ghost_removal", [True, False])
def test_device_engine_is_bit_identical_to_cpu(ghost_removal):
    cpu, gpu = _engine("cpu", ghost_removal=ghost_removal), \
        _engine("cuda", ghost_removal=ghost_removal)
    cleared = protected = 0
    for frame in _frames():
        c, g = cpu.step(frame), gpu.step(frame)
        assert c == g, f"counters diverge at frame {frame.index}"
        assert map_hash(cpu.handle.grid) == map_hash(gpu.handle.grid), \
            f"map diverges at frame {frame.index}"
        cleared += g.cleared
        protected += g.protected
    if ghost_removal:
        assert cleared > 0 and protected > 0, "scene did not exercise the cleanup"
    else:
        assert cleared == 0


@needs_cuda
def test_device_frame_loop_allocates_almost_nothing_on_the_host():
    """Same cap as the CPU engine's own test: the device path must not buy its
    speed with per-frame host staging copies."""
    import tracemalloc

    frames = _frames(total=6)
    eng = _engine("cuda")
    for f in frames[:3]:
        eng.step(f)
    eng.step(frames[3])
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        before = tracemalloc.get_traced_memory()[0]
        eng.step(frames[4])
        step = tracemalloc.get_traced_memory()[1] - before
    finally:
        tracemalloc.stop()
    assert step < 2_000_000, f"device step allocates {step:,} B on the host"


@needs_cuda
def test_upload_refuses_a_dtype_it_would_have_to_cast():
    k = dev.DeviceKernels(max_points=16, n_cells=64, max_candidates=16)
    with pytest.raises(TypeError, match="upload expects"):
        k.scatter(np.zeros(4, np.int32), np.zeros(4, np.int16), np.ones(4, np.int32),
                  np.zeros(4, np.uint8), np.zeros(4, np.uint8), np.ones(4, bool))


@needs_cuda
def test_device_buffers_are_declared():
    eng = _engine("cuda")
    b = eng.device_bytes()
    assert b["static"] > 0 and b["pool_reserved"] >= b["pool_used"] > 0
