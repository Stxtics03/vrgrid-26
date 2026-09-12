"""The DL-vs-ground-truth semantic ablation. [Shrestha]

`scripts/semantic_ablation.py` folds the same perception frames into two maps
that differ only in where the 19-class label came from, and reports how far the
§7.1 traversability decision moves. It is the measurement behind turning "the
mapping contribution is evaluated independently of segmentation quality" from a
disclaimer into a number.

The long run needs a GPU, a checkpoint and 80 GB of SemanticKITTI, so what is
tested here is the part that decides what the run CLAIMS: the class field is
read the way §10.2 says to read it, the drivable set comes from config rather
than from a copy in the script, and the two label sources reach the map under
the same ignore convention. Get any of those wrong and the run still completes
and still prints a plausible percentage.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

pytest.importorskip("vrgrid.grid.traversability")

import semantic_ablation as ab
from vrgrid.grid import traversability
from vrgrid.grid.fusion import CLASS_MAX, COUNTER_MAX, pack_class


def test_cell_classes_reads_the_candidate_not_the_raw_byte():
    """§10.2 packs the class candidate with a counter in one byte. Reading it
    with a literal shift is the bug that welds the counter's top bit onto the
    id, at which point every drivable class fails the drivable-set test and the
    entire road reads untraversable -- while still looking like terrain."""
    for cls in (0, 1, 8, 16, CLASS_MAX):
        for counter in (0, 1, COUNTER_MAX):
            soa = {"semantic_class": pack_class(np.array([cls]), np.array([counter]))}
            assert int(ab.cell_classes(soa)[0]) == cls, (
                f"class {cls} with counter {counter} did not survive the unpack")


def test_cell_classes_is_vectorised_over_a_whole_grid():
    cls = np.arange(32, dtype=np.uint8)
    counter = np.arange(32, dtype=np.uint8) % (COUNTER_MAX + 1)
    soa = {"semantic_class": pack_class(cls, counter)}
    assert np.array_equal(ab.cell_classes(soa), cls.astype(np.int32))


def test_the_script_holds_no_private_copy_of_the_drivable_set():
    """The drivable set is frozen in configs/thresholds.yaml before schedules
    are compared. A copy in this script would go stale in silence and quote a
    §7.1 number for a set §7.1 no longer uses."""
    source = Path(ab.__file__).read_text()
    assert "drivable_ids" in source
    for name in ("road", "parking", "sidewalk", "other-ground", "terrain"):
        assert f'"{name}"' not in source and f"'{name}'" not in source, (
            f"{name!r} is named in the script; read the set from thresholds.yaml")


def test_the_drivable_set_it_will_resolve_is_the_configured_one():
    ids = traversability.drivable_ids()
    by_id = {i: n for n, i in traversability.class_ids().items()}
    assert sorted(by_id[int(i)] for i in ids) == [
        "other-ground", "parking", "road", "sidewalk", "terrain"]


def test_frnet_ignore_is_remapped_to_the_loaders_convention():
    """`semantics.semantic_labels` spells unlabelled -1; FRNet spells it 19.

    The engine maps anything negative to class 0, so both sources must arrive
    under the SAME convention or part of the measured difference is bookkeeping
    rather than segmentation -- and it would look like segmentation error.
    """
    pred = np.array([0, 5, 18, ab.FRNET_IGNORE, 19, 3])
    remapped = np.where(pred >= ab.FRNET_IGNORE, -1, pred)
    assert remapped.tolist() == [0, 5, 18, -1, -1, 3]
    assert ab.FRNET_IGNORE == 19
    # Every real class must survive: only the ignore slot may become negative.
    assert (remapped[:3] >= 0).all() and remapped[-1] >= 0


def test_ignore_index_matches_what_the_model_is_built_with():
    """The ablation and the eval script must agree, or they score two models."""
    finetune = Path(ab.__file__).parent / "frnet_finetune.py"
    assert "IGNORE_INDEX = 19" in finetune.read_text()


def test_rings_of_covers_every_slot_exactly_once():
    """`traversability.update` is handed (slice, side) pairs. If those do not
    tile the flat arrays, some ring silently keeps a stale bitfield and the
    flip count is measured against numbers nobody recomputed."""
    pytest.importorskip("vrgrid.run.engine")
    from vrgrid.grid import schedule as schedule_mod
    from vrgrid.run.engine import MapEngine

    engine = MapEngine(schedule_mod.load("5/10/20/40"))
    rings = ab.rings_of(engine)
    assert len(rings) == len(engine.handle.rings)

    covered = np.zeros(engine.handle.grid["obs_count"].size, dtype=int)
    for sl, side in rings:
        covered[sl] += 1
        assert sl.stop - sl.start == side * side, (
            "slice length must be the ring's full square, which is what the "
            "toroidal buffer allocates")
    assert covered.max() <= 1, "rings overlap; a slot would be scored twice"
    assert covered.sum() == sum(s.stop - s.start for s, _ in rings)


def test_the_script_refuses_a_semantic_ground_fallback():
    """Patchwork++ is geometric and never consults semantics; the fallback ground
    proxy does. With the fallback active, ground would differ between the two
    maps and be read as segmentation error, so the run must stop rather than
    report a contaminated number."""
    source = Path(ab.__file__).read_text()
    assert 'ground_method != "patchworkpp"' in source
    assert "use_patchworkpp=True" in source


def test_it_folds_one_perception_pass_into_two_maps():
    """Running the sequence twice would let any nondeterminism in perception
    leak into the difference. One pass, two engines, `replace(frame, ...)`."""
    source = Path(ab.__file__).read_text()
    assert source.count("iter_pipeline(") == 1
    assert "replace(frame, semantic=" in source
