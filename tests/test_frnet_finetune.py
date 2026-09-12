"""The fine-tune's frame-picking stream, and the way a continuation could lie. [Shrestha]

`scripts/frnet_finetune.py --resume` exists so a rejected experiment can be
re-derived and a promising one continued. Continuing is the part with a trap in
it: the run reports a training loss and a held-out score, and NEITHER can tell
you that the second leg trained on the same frames as the first. The loss falls
either way -- faster, if anything, when the frames are ones the weights have
already seen -- and the held-out score just comes out disappointing, which reads
as "fine-tuning does not help" rather than as "the continuation never happened".
So the property has to be asserted here, where it is visible.

torch is not a dependency of this project (not in `dependencies`, not in
`dev`), so these skip in CI the way the Patchwork++ and fast-scatter tests do,
and run for anyone who has the environment the fine-tune needs anyway.
"""

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

pytest.importorskip("torch")
pytest.importorskip("vrgrid.perception.frnet")

import frnet_finetune as ft

#: The real numbers this is protecting: 19,130 labelled frames over the ten
#: training sequences, and the 4,000-step legs the 4 Sep continuations ran.
FRAMES = 19130
LEG = 4000


def _picks(seed: int, step0: int, n: int = LEG) -> list[int]:
    """The frames a leg starting at `step0` would train on, batch 1."""
    rng = ft.frame_stream(seed, step0)
    return [rng.randrange(FRAMES) for _ in range(n)]


def test_a_continuation_does_not_replay_the_first_legs_frames():
    """The regression. Seeding one global stream from --seed made these equal."""
    first = _picks(0, 0)
    second = _picks(0, LEG)
    assert first != second
    #: Not merely "not equal" -- position-by-position agreement must be at
    #: chance (1/19,130 per draw, so ~0.2 hits expected in 4,000), because a
    #: stream that shares a prefix or a period would pass a bare `!=`.
    aligned = sum(a == b for a, b in zip(first, second))
    assert aligned <= 5, f"{aligned} of {LEG} draws coincide -- the streams are related"


def test_the_second_leg_sees_mostly_frames_the_first_did_not():
    """What the replay actually cost: 4,000 more steps over one fixed sample."""
    first, second = set(_picks(0, 0)), set(_picks(0, LEG))
    #: Sampling with replacement from 19,130, two independent 4,000-draw legs
    #: share ~19% of their distinct frames. Replay shared 100%.
    assert len(second - first) / len(second) > 0.7


def test_a_continuation_is_reproducible_from_the_same_checkpoint():
    """Not replaying is not the same as being random: --resume must re-derive."""
    assert _picks(0, LEG) == _picks(0, LEG)


def test_continuations_of_different_checkpoints_diverge():
    """B1 resumed at 2,000 and B2 at 4,000 must not train on the same frames."""
    assert _picks(0, 2000) != _picks(0, 4000)


def test_different_seeds_still_differ_at_the_same_step():
    """step0 must not swamp the seed -- both halves of the key have to matter."""
    assert _picks(0, LEG) != _picks(1, LEG)


def test_the_stream_is_immune_to_anything_else_that_touches_random():
    """It owns its Random. A global reseed between draws must not move it."""
    rng = ft.frame_stream(0, LEG)
    before = [rng.randrange(FRAMES) for _ in range(50)]
    random.seed(999)
    after = [rng.randrange(FRAMES) for _ in range(50)]
    expected = _picks(0, LEG, 100)
    assert before + after == expected
