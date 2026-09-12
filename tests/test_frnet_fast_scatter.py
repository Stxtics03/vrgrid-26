"""The native-scatter shim, guarded against the ways it could silently lie. [Shrestha]

`scripts/frnet_fast_scatter.py` swaps FRNet's frustum reductions for
`torch.Tensor.scatter_reduce` at runtime so a fine-tune takes minutes instead
of 3.3 hours. Every number the DL half reports then flows through it, so what
has to be tested is not that it is fast but that it computes the same thing.

torch is not a dependency of this project (not in `dependencies`, not in
`dev`), so these skip in CI the way the Patchwork++ tests do, and run for
anyone who has the environment the fine-tune needs anyway.

⚑ `scatter_max` is asserted EXACT and `scatter_mean` is not, and the asymmetry
  is the point. Max is order-independent, so no summation order can move it and
  anything but equality is a defect. Mean is not: the native kernel sums a
  slot's rows in a different order than `src[mask].mean(dim=0)` does, float
  addition is not associative, and the resulting few-ulp difference appears on
  CPU as well as CUDA -- it varies with rows-per-slot, not with device. Writing
  these tests is what showed the 3 Sep "bit-identical on CPU" result to have
  been one lucky shape. The mean bound is tight enough to be worth having: a
  genuinely wrong reduction misses by ~1e7 ulp, not by 4.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

torch = pytest.importorskip("torch")
pytest.importorskip("vrgrid.perception.frnet")

import frnet_fast_scatter as fs
from vrgrid.perception.frnet import frnet_backbone, frustum_encoder


@pytest.fixture(autouse=True)
def _restore_the_loops():
    """No test may leave the modules patched -- the next one would test itself."""
    yield
    fs.disable()
    assert frustum_encoder.scatter_max is fs.LOOP_SCATTER_MAX
    assert frnet_backbone.scatter_max is fs.LOOP_SCATTER_MAX


def _case(n=800, slots=200, channels=8, seed=0, leave_empty=True):
    """Rows, slot ids, and by default at least one slot nothing maps to."""
    g = torch.Generator().manual_seed(seed)
    src = torch.randn(n, channels, generator=g)
    index = torch.randint(0, slots, (n,), generator=g)
    if leave_empty:
        index[index == slots - 1] = 0
    return src, index, slots


def test_scatter_max_is_bit_identical_to_the_loop():
    src, index, slots = _case()
    ref, _ = fs.LOOP_SCATTER_MAX(src, index, dim=0, dim_size=slots)
    new, _ = fs.fast_scatter_max(src, index, dim=0, dim_size=slots)
    assert torch.equal(ref, new)


#: Matches the shim's own gate. Stated in ulp so it cannot quietly widen into
#: a real difference, and so the number means something on any dtype.
ULP = float(torch.finfo(torch.float32).eps)
MEAN_TOLERANCE = 8 * ULP


@pytest.mark.parametrize("n,slots,channels", [
    (800, 200, 8), (2000, 400, 8), (20000, 4000, 8), (5000, 100, 16),
])
def test_scatter_mean_matches_the_loop_to_within_float32_rounding(n, slots, channels):
    """Several shapes on purpose: the error grows with rows-per-slot, and a
    single shape is how the 3 Sep measurement concluded 'bit-identical'."""
    src, index, slots = _case(n=n, slots=slots, channels=channels)
    ref = fs.LOOP_SCATTER_MEAN(src, index, dim=0, dim_size=slots)
    new = fs.fast_scatter_mean(src, index, dim=0, dim_size=slots)
    d = (ref - new).abs().max().item()
    assert d <= MEAN_TOLERANCE, f"{d:.3e} ({d / ULP:.1f} ulp) exceeds the bound"


@pytest.mark.parametrize("n,slots,channels", [
    (800, 200, 8), (2000, 400, 8), (20000, 4000, 8), (5000, 100, 16),
])
def test_scatter_max_is_exact_at_every_shape(n, slots, channels):
    """No tolerance here, at any shape: max is order-independent."""
    src, index, slots = _case(n=n, slots=slots, channels=channels)
    ref, _ = fs.LOOP_SCATTER_MAX(src, index, dim=0, dim_size=slots)
    new, _ = fs.fast_scatter_max(src, index, dim=0, dim_size=slots)
    assert torch.equal(ref, new)


@pytest.mark.parametrize("loop,fast,tol", [
    ("LOOP_SCATTER_MAX", "fast_scatter_max", 0.0),
    ("LOOP_SCATTER_MEAN", "fast_scatter_mean", MEAN_TOLERANCE),
])
def test_gradients_match(loop, fast, tol):
    """A fine-tune needs the backward half, which the 3 Sep timing never covered.

    `amax` splits gradient evenly among tied maxima where `max(dim=0)` gives it
    all to the first, and ReLU emits exact zeros upstream, so ties are reachable
    and this is not a formality.
    """
    src, index, slots = _case()
    grads = []
    for fn in (getattr(fs, loop), getattr(fs, fast)):
        x = src.clone().requires_grad_(True)
        out = fn(x, index, dim=0, dim_size=slots)
        out = out[0] if isinstance(out, tuple) else out
        out.nan_to_num(neginf=0.0).square().sum().backward()
        grads.append(x.grad)
    d = (grads[0] - grads[1]).abs().max().item()
    assert d <= tol, f"backward differs by {d:.3e} ({d / ULP:.1f} ulp)"


def test_empty_slots_keep_the_loops_conventions():
    """-inf for max, 0 for mean -- what the loop leaves by skipping `mask.any()`.

    `torch.unique` gives every slot a point at the real call sites, so this
    convention is never exercised there. It is pinned anyway: the shim is a
    drop-in, and a drop-in that diverges at shapes it has not been shown is a
    trap for whoever reuses it.
    """
    src, index, slots = _case()
    empty = [i for i in range(slots) if not bool((index == i).any())]
    assert empty, "fixture failed to leave an empty slot"
    mx, _ = fs.fast_scatter_max(src, index, dim=0, dim_size=slots)
    mn = fs.fast_scatter_mean(src, index, dim=0, dim_size=slots)
    assert torch.isinf(mx[empty]).all() and (mx[empty] < 0).all()
    assert (mn[empty] == 0).all()


def test_enable_patches_the_backbone_and_not_only_the_encoder():
    """The trap this shim exists to avoid.

    `frnet_backbone` does `from .frustum_encoder import scatter_max` at import,
    which BINDS the function object into its own namespace. Rebinding only
    `frustum_encoder.scatter_max` leaves five of the seven per-forward calls on
    the Python loop, and the run comes out merely disappointing rather than
    visibly broken -- a fine-tune that should take two minutes takes forty and
    nobody is told why.
    """
    fs.enable(verify=False)
    assert frustum_encoder.scatter_max is fs.fast_scatter_max
    assert frustum_encoder.scatter_mean is fs.fast_scatter_mean
    assert frnet_backbone.scatter_max is fs.fast_scatter_max, (
        "frnet_backbone still holds the loop: it binds scatter_max at import, "
        "so patching frustum_encoder alone leaves most calls unpatched")


def test_argmax_return_is_none_rather_than_a_wrong_index():
    """The loop's second return value is already wrong -- it holds the index
    within the masked subset, not into the full input as torch_scatter returns.
    All three call sites discard it. `scatter_reduce` offers no argmax at all,
    so the shim returns None: a caller that starts using it gets a TypeError
    instead of a silently wrong index."""
    src, index, slots = _case()
    _, argmax = fs.fast_scatter_max(src, index, dim=0, dim_size=slots)
    assert argmax is None


def test_a_dim_the_shim_does_not_cover_is_refused():
    """Both call sites reduce along dim 0. Anything else raises rather than
    quietly reducing the wrong axis."""
    src, index, slots = _case()
    with pytest.raises(NotImplementedError):
        fs.fast_scatter_max(src, index, dim=1, dim_size=slots)
    with pytest.raises(NotImplementedError):
        fs.fast_scatter_mean(src, index, dim=1, dim_size=slots)


def test_dim_size_is_inferred_when_omitted():
    src, index, _ = _case(leave_empty=False)
    out, _ = fs.fast_scatter_max(src, index, dim=0)
    assert out.shape[0] == int(index.max()) + 1


def test_verify_equivalence_runs_and_would_raise_on_drift():
    """The shim refuses to patch unless it has just proved itself. Run the
    proof here too, on CPU, so a regression fails a test rather than only a
    long training run."""
    fs.verify_equivalence(n=2000, slots=400, channels=8, device="cpu")

    original = fs.fast_scatter_mean
    try:
        fs.fast_scatter_mean = lambda src, index, dim=0, dim_size=None: (
            original(src, index, dim, dim_size) + 1.0)
        with pytest.raises(AssertionError):
            fs.verify_equivalence(n=2000, slots=400, channels=8, device="cpu")
    finally:
        fs.fast_scatter_mean = original


def test_the_shim_covers_every_module_that_holds_a_reduction():
    """If someone adds a third importer of scatter_max, this fails until the
    shim's holder lists are updated -- rather than that module keeping the loop
    forever and nobody noticing."""
    import vrgrid.perception.frnet as pkg

    root = Path(pkg.__file__).parent
    holders = {m.__name__.rsplit(".", 1)[-1] for m in fs._MAX_HOLDERS}
    for path in root.glob("*.py"):
        text = path.read_text()
        if "scatter_max" in text and "import" in text and path.stem not in holders:
            assert "def scatter_max" in text, (
                f"{path.name} references scatter_max but is not in the shim's "
                f"holder list, so enable() would leave its calls on the loop")


def test_numpy_is_not_needed_for_any_of_this():
    """Guards the import list: the shim is torch-only on purpose, so it stays
    importable in a training environment that has nothing else installed."""
    assert "numpy" not in Path(fs.__file__).read_text().split("def ")[0]
    assert np is not None
