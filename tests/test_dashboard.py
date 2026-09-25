"""Dashboard controls: ghost toggle, blind cone, schedule selector. [JP]

`get_display_points()` is the ghost-removal swap point -- it filters is_moving()
points from the rendered cloud, and its body is the only thing that changes when
the grid's transient layer is the source. The blind-cone radius and the schedule
selector are read from `configs/` through `vrgrid.dash._config` (no rerun), so
those tests run in CI without the `[dash]` extra.
"""

import numpy as np
import pytest

pytest.importorskip("rerun")

from vrgrid.dash._config import (
    DENSE_VOXEL_BYTES,
    available_schedules,
    blind_cone_radius_m,
    dense_3d_baseline,
    grid_memory_stats,
    memory_overlay_markdown,
    schedule_legend_markdown,
)
from vrgrid.dash.pipeline_view import COLOR_BY, get_display_points
from vrgrid.grid.schedule import CONFIG_DIR, load_thresholds
from vrgrid.grid.schedule import load as load_schedule
from vrgrid.perception.loader import _velodyne_path, verify_sequence_exists

_HAS_DATA = verify_sequence_exists("00") and _velodyne_path("00", 10).exists()
needs_data = pytest.mark.skipif(not _HAS_DATA, reason="KITTI seq 00 not present -- set VRGRID_DATA_ROOT")


class _Frame:
    """Minimal PerceptionFrame stand-in with a known motion mask."""

    def __init__(self, n=200, n_moving=17, seed=0):
        rng = np.random.default_rng(seed)
        self.points_sensor = rng.random((n, 4)).astype(np.float32)
        self.points_world = (rng.random((n, 3)) * 40 - 20).astype(np.float32)
        self.semantic = rng.integers(-1, 19, n)
        self.ground = rng.random(n) > 0.5
        self.reflectivity8 = rng.integers(0, 256, n).astype(np.uint8)
        self.moving = np.zeros(n, dtype=bool)
        self.moving[rng.choice(n, n_moving, replace=False)] = True


# --------------------------------------------------------------------------
# synthetic -- exact filtering
# --------------------------------------------------------------------------


def test_ghost_removal_on_drops_exactly_the_moving_points():
    f = _Frame(n=200, n_moving=17)
    xyz, colors = get_display_points(f, ghost_removal=True)
    assert len(xyz) == 200 - 17
    assert len(colors) == len(xyz)
    # every kept point is a static one, and all static points are kept
    kept = {tuple(p) for p in xyz}
    assert kept == {tuple(p) for p in f.points_world[~f.moving]}
    assert not (kept & {tuple(p) for p in f.points_world[f.moving]})


def test_ghost_removal_off_shows_everything():
    f = _Frame(n=200, n_moving=17)
    xyz, colors = get_display_points(f, ghost_removal=False)
    assert len(xyz) == 200 and len(colors) == 200
    assert np.array_equal(np.sort(xyz, axis=0), np.sort(f.points_world, axis=0))


def test_static_points_identical_with_toggle_either_way():
    f = _Frame(n=300, n_moving=25)
    on, _ = get_display_points(f, ghost_removal=True)
    off, _ = get_display_points(f, ghost_removal=False)
    static = f.points_world[~f.moving]
    on_set = {tuple(p) for p in on}
    off_set = {tuple(p) for p in off}
    assert {tuple(p) for p in static} <= on_set
    assert {tuple(p) for p in static} <= off_set
    assert on_set < off_set  # ON is a strict subset of OFF


@pytest.mark.parametrize("color_by", COLOR_BY)
def test_colours_stay_aligned_with_points_for_every_layer(color_by):
    f = _Frame(n=150, n_moving=12)
    for gr in (True, False):
        xyz, colors = get_display_points(f, ghost_removal=gr, color_by=color_by)
        assert colors.shape == (len(xyz), 3) and colors.dtype == np.uint8


def test_frame_with_no_moving_points_is_a_noop():
    f = _Frame(n=100, n_moving=0)
    on, _ = get_display_points(f, ghost_removal=True)
    off, _ = get_display_points(f, ghost_removal=False)
    assert len(on) == len(off) == 100


# --------------------------------------------------------------------------
# real scan -- frame 10 has a moving motorcyclist + pedestrian
# --------------------------------------------------------------------------


@needs_data
def test_frame_10_ghost_toggle_removes_the_moving_objects():
    from vrgrid.run.__main__ import iter_pipeline

    frame = list(iter_pipeline("00", max_frames=11))[10]
    n_moving = int(frame.moving.sum())
    total = len(frame.points_sensor)
    assert 40 < n_moving < 120, f"frame 10 moving count {n_moving} (expected ~66)"

    on_xyz, _ = get_display_points(frame, ghost_removal=True)
    off_xyz, _ = get_display_points(frame, ghost_removal=False)

    assert len(off_xyz) == total
    assert len(on_xyz) == total - n_moving
    # the removed set is exactly the moving points
    removed = {tuple(p) for p in off_xyz} - {tuple(p) for p in on_xyz}
    assert removed == {tuple(p) for p in frame.points_world[frame.moving].astype(np.float32)}
    # the moving objects are near the vehicle, not scattered across the map
    ghosts = frame.points_world[frame.moving]
    assert np.linalg.norm(ghosts - frame.vehicle_xyz_world, axis=1).max() < 60


# --------------------------------------------------------------------------
# blind cone -- radius read from config, the corrected 3.74 m value
# --------------------------------------------------------------------------


def test_blind_cone_radius_is_374_and_comes_from_config():
    from_config = load_thresholds()["sensor"]["blind_cone_m"]
    assert from_config == pytest.approx(3.74)
    assert blind_cone_radius_m() == pytest.approx(from_config)
    # the corrected value -- master v4 flagged the earlier 1-2 m assumption
    assert blind_cone_radius_m() > 3.0


# --------------------------------------------------------------------------
# schedule selector -- reads configs/schedule_*.yaml, no hardcoded ring sizes
# --------------------------------------------------------------------------


def test_available_schedules_are_discovered_from_config_dir():
    got = available_schedules()
    on_disk = sorted(p.stem.removeprefix("schedule_") for p in CONFIG_DIR.glob("schedule_*.yaml"))
    assert got == on_disk
    assert "5_10_20_40" in got and "5_10_50" in got


def test_schedule_legend_matches_the_config_ring_boundaries():
    md = schedule_legend_markdown("5_10_20_40")
    assert "**(active)**" in md
    for name in available_schedules():
        s = load_schedule(name)
        assert f"`{name}`" in md
        for r in s.rings:
            # half-width / cell-cm pair, straight from the yaml, appears verbatim
            assert f"{r.half_width_m:g}/{r.cell_m * 100:g}" in md
        assert f"{s.total_cells:,}" in md


def test_pipeline_view_logs_rings_from_the_passed_schedule(tmp_path):
    from vrgrid.dash.pipeline_view import PipelineView

    # both schedules build without error and use their own ring count
    for name, n_rings in [("5/10/20/40", 4), ("5/10/50", 3)]:
        s = load_schedule(name)
        assert len(s.rings) == n_rings
        PipelineView(s, spawn=False, save_path=str(tmp_path / f"{n_rings}.rrd"))


# --------------------------------------------------------------------------
# Gate 3 -- the occupied-cell surface, drawn from MapEngine.occupied_cells()
# --------------------------------------------------------------------------


def _wall_frame(index: int):
    """A minimal PerceptionFrame: a ground disc + a static wall at x = 25 m,
    built the way test_engine.py builds its scenes (range image from the same
    points, so cloud and image agree)."""
    from types import SimpleNamespace

    ri = pytest.importorskip("vrgrid.perception.range_image")
    rng = np.random.default_rng(index)
    ground = np.column_stack([
        (r := rng.uniform(3.0, 12.0, 5000)) * np.cos(a := rng.uniform(-np.pi, np.pi, 5000)),
        r * np.sin(a), np.full(5000, -1.73)])
    wall = np.column_stack([np.full(7000, 25.0), rng.uniform(-8, 8, 7000),
                            rng.uniform(-3.0, 2.0, 7000)])
    pts = np.vstack([ground, wall])
    p4 = np.column_stack([pts, np.full(len(pts), 0.4)])
    image, inverse = ri.project(p4)
    gmask = np.zeros(len(pts), bool)
    gmask[:5000] = True
    return SimpleNamespace(
        index=index, points_sensor=p4,
        points_world=pts + np.array([0.0, 0.0, 1.73]),
        pose=np.eye(4)[:3], vehicle_xyz_world=np.zeros(3),
        semantic=np.zeros(len(pts), np.int8), moving=np.zeros(len(pts), bool),
        ground=gmask, reflectivity8=np.full(len(pts), 90, np.uint8),
        range_image=image, inverse_index=inverse)


def test_pipeline_view_draws_the_engine_occupied_surface(tmp_path):
    from vrgrid.dash.pipeline_view import PipelineView, _height_ramp
    from vrgrid.run.engine import MapEngine

    sched = load_schedule("5/10/20/40")
    engine = MapEngine(sched, ghost_removal=True)
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "map.rrd"),
                        engine=engine)

    for i in range(3):
        f = _wall_frame(i)
        engine.step(f)
        view.log_frame(f)          # must not raise -- draws world/map/occupied

    slots, _x, _y, z = engine.occupied_cells()
    assert len(slots) > 100, "the wall + ground should occupy cells"

    # per-slot cell size comes from the ring: near cells are 5 cm, the wall at
    # 25 m falls in ring 1 (10 cm) or ring 2 (20 cm) -- strictly more than one
    # distinct size, which is the foveation the surface is meant to show
    cell_m = view._cell_m_per_slot(slots)
    assert np.isclose(cell_m.min(), 0.05)          # near cells are the base 5 cm
    assert cell_m.max() > cell_m.min()             # farther rings are coarser
    assert np.unique(np.round(cell_m, 3)).size >= 2

    # colour tracks height and is a valid uint8 triple per cell
    c = _height_ramp(z)
    assert c.shape == (len(z), 3) and c.dtype == np.uint8


def test_pipeline_view_separates_occupied_free_unknown(tmp_path):
    """math §10.1 / CLAUDE.md: unknown is not free. The view must keep the
    three occupancy states on distinct entities, driven only by the engine's
    occ_state (refreshed by the occupied_cells() call log_frame already makes)."""
    from vrgrid.cell import OCC_FREE, OCC_OCCUPIED, OCC_UNKNOWN
    from vrgrid.dash.pipeline_view import PipelineView
    from vrgrid.run.engine import MapEngine

    sched = load_schedule("5/10/20/40")
    engine = MapEngine(sched, ghost_removal=True)
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "occ.rrd"),
                        engine=engine)
    for i in range(4):
        f = _wall_frame(i)
        engine.step(f)
        view.log_frame(f)   # logs world/map/{occupied,free,unknown}, must not raise

    st = engine.occ_state
    assert set(np.unique(st)) <= {OCC_UNKNOWN, OCC_FREE, OCC_OCCUPIED}
    assert (st == OCC_OCCUPIED).sum() > 100
    # centres for the free set resolve through the engine's own inverse, no NaN
    free = np.flatnonzero(st == OCC_FREE)
    fx, fy, fz = view._centres_world(free)
    assert np.isfinite(np.concatenate([fx, fy, fz])).all()
    # never-observed slots are UNKNOWN and are NOT handed to the renderer
    obs = engine.handle.grid["obs_count"]
    assert ((st == OCC_UNKNOWN) & (obs == 0)).sum() > 0
    drawn_unknown = np.flatnonzero((st == OCC_UNKNOWN) & (obs > 0))
    assert len(drawn_unknown) < (st == OCC_UNKNOWN).sum()   # the bulk is left undrawn


def test_pipeline_view_without_engine_skips_the_surface(tmp_path):
    from vrgrid.dash.pipeline_view import PipelineView

    view = PipelineView(load_schedule("5/10/20/40"), spawn=False,
                        save_path=str(tmp_path / "n.rrd"), engine=None)
    view.log_frame(_wall_frame(0))  # no engine -> no occupied surface, no error
    view.finish()                   # and no final map either


# --------------------------------------------------------------------------
# viewer frame rate -- points, not boxes; the map redrawn every MAP_INTERVAL
# --------------------------------------------------------------------------


def _spy_logs(monkeypatch):
    """Record every `rr.log(path, archetype)` call, still passing it through."""
    import rerun as rr

    calls, real = [], rr.log

    def spy(path, *args, **kw):
        calls.append((path, args[0] if args else None))
        return real(path, *args, **kw)

    monkeypatch.setattr(rr, "log", spy)
    return calls


def test_dense_map_layers_are_points_sized_to_the_cell(tmp_path, monkeypatch):
    """Rerun processes box instances one at a time on the CPU; points take the
    GPU path, ~100x faster (rerun-io/rerun#10276). ~205,000 map cells a frame
    as boxes is what stalled the viewer, so the dense layers must stay points
    -- and each radius must be half its ring's cell, or the 5 -> 10 -> 20 ->
    40 cm foveation the view exists to show stops reading."""
    import rerun as rr
    from vrgrid.dash.pipeline_view import PipelineView
    from vrgrid.run.engine import MapEngine

    sched = load_schedule("5/10/20/40")
    engine = MapEngine(sched, ghost_removal=True)
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "pts.rrd"),
                        engine=engine, map_interval=1)
    calls = _spy_logs(monkeypatch)
    for i in range(3):
        f = _wall_frame(i)
        engine.step(f)
        view.log_frame(f)

    dense = {"world/map/occupied", "world/map/free", "world/map/unknown"}
    drawn = [(p, a) for p, a in calls if p in dense and not isinstance(a, rr.Clear)]
    assert "world/map/occupied" in {p for p, _ in drawn}
    assert all(isinstance(a, rr.Points3D) for _, a in drawn)
    # no tile meshes or extra colour-mode layers: they made the live demo stutter
    assert not [p for p, _ in calls if p.startswith(("world/map/by_ring", "world/map/by_class"))]

    occupied = [a for p, a in drawn if p == "world/map/occupied"][-1]
    radii = occupied.radii.as_arrow_array().to_numpy(zero_copy_only=False)
    want = view._cell_m_per_slot(engine.occupied_slots()) / 2.0
    assert np.allclose(np.sort(radii), np.sort(want))
    assert np.unique(np.round(radii, 3)).size >= 2     # more than one cell size


def test_map_redraws_on_the_interval_and_finish_draws_the_final_state(tmp_path, monkeypatch):
    """The map is drawn every `map_interval` frames, the point cloud every
    frame, and `finish()` redraws once so a run that stops between intervals
    still ends on the true final map."""
    from vrgrid.dash.pipeline_view import MAP_INTERVAL, PipelineView
    from vrgrid.run.engine import MapEngine

    assert MAP_INTERVAL > 1, "a map redraw every frame is what stalled the viewer"

    sched = load_schedule("5/10/20/40")
    engine = MapEngine(sched, ghost_removal=True)
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "int.rrd"),
                        engine=engine, map_interval=3)
    calls = _spy_logs(monkeypatch)
    for i in range(8):                      # draws on 0, 3, 6; stops one past
        f = _wall_frame(i)
        engine.step(f)
        view.log_frame(f)

    def count(path):
        return sum(1 for p, _ in calls if p == path)

    assert count("world/points") == 8
    assert count("world/map/occupied") == 3
    assert count("panel/status") == 8        # the side panel is never left stale

    view.finish()
    assert count("world/map/occupied") == 4
    assert view._last_occupied_n == len(engine.occupied_slots())


def test_playback_fps_is_the_sensor_rate_from_config():
    from vrgrid.dash._config import playback_fps

    assert playback_fps() == pytest.approx(1.0 / load_thresholds()["fusion"]["frame_dt_s"])
    assert playback_fps() == pytest.approx(10.0)     # KITTI HDL-64E, 10 Hz


# --------------------------------------------------------------------------
# live memory overlay -- occupied cells * CELL_BYTES vs the dense-3D baseline
# --------------------------------------------------------------------------


def test_dense_3d_baseline_is_derived_not_a_magic_number():
    from vrgrid.cell import CELL_BYTES

    sched = load_schedule("5/10/20/40")
    d = dense_3d_baseline(sched)

    # exactly the documented formula, recomputed from the schedule
    footprint = 2.0 * sched.rings[-1].half_width_m
    lo, hi = sched.vertical_extent_m
    vertical = hi - lo
    res = sched.base_cell_m
    assert d["footprint_m"] == footprint == 200.0
    assert d["vertical_m"] == vertical == 8.0
    assert d["res_m"] == res == 0.05
    assert d["voxels"] == (footprint / res) ** 2 * (vertical / res) == 2.56e9
    assert d["bytes"] == d["voxels"] * DENSE_VOXEL_BYTES == 2.56e9   # 1 B/voxel

    # matches the report's 286x headline against the 8.94 MB logical map
    assert d["bytes"] / (sched.total_cells * CELL_BYTES) == pytest.approx(286.4, abs=0.5)


def test_grid_memory_stats_is_exactly_occupied_count_times_cell_bytes():
    from vrgrid.cell import CELL_BYTES

    sched = load_schedule("5/10/20/40")
    for n in (0, 1, 42, 187_808, 745_000):
        s = grid_memory_stats(n, sched)
        assert s["live_bytes"] == n * CELL_BYTES        # exact, no rounding
        assert s["cell_bytes"] == CELL_BYTES
        assert s["dense_bytes"] == dense_3d_baseline(sched)["bytes"]
        if n:
            assert s["ratio"] == s["dense_bytes"] / (n * CELL_BYTES)


@needs_data
def test_memory_overlay_tracks_the_real_occupied_count(tmp_path):
    """The overlay number must equal len(occupied_cells()) * CELL_BYTES for the
    frame it was logged on -- no drift between what is drawn and what is counted."""
    from vrgrid.cell import CELL_BYTES
    from vrgrid.dash.pipeline_view import PipelineView
    from vrgrid.run.__main__ import iter_pipeline
    from vrgrid.run.engine import MapEngine

    sched = load_schedule("5/10/20/40")
    engine = MapEngine(sched, ghost_removal=True)
    # map_interval=1: this pins the drawn count to the counted one on EVERY
    # frame, so the map has to be drawn on every frame for it to be checkable.
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "mem.rrd"),
                        engine=engine, map_interval=1)

    seen = []
    for f in iter_pipeline("00", 20):
        engine.step(f)
        view.log_frame(f)
        n = len(engine.occupied_slots())
        assert view._last_occupied_n == n
        s = grid_memory_stats(n, sched)
        assert s["live_bytes"] == n * CELL_BYTES
        assert str(f"{n:,}") in memory_overlay_markdown(n, sched)
        seen.append((n, s["live_bytes"], s["ratio"]))

    ns = [x[0] for x in seen]
    assert ns[-1] > ns[0] > 0                     # the map fills as frames arrive
    assert all(0 < x[2] < 1e7 for x in seen)      # ratio stays a sane finite number


def test_height_ramp_table_matches_the_exact_ramp():
    """Height colours come from a precomputed table -- interpolating them was
    12 of the 34 ms a map redraw took. The table must stay within one uint8
    level of the exact ramp everywhere, including outside the clipped band,
    and a non-default band must still take the exact path."""
    from vrgrid.dash.pipeline_view import _height_ramp, _height_ramp_exact

    z = np.linspace(-6.0, 20.0, 50_001)
    fast, exact = _height_ramp(z), _height_ramp_exact(z, -3.0, 15.0)
    assert fast.dtype == np.uint8 and fast.shape == exact.shape
    assert np.abs(fast.astype(int) - exact.astype(int)).max() <= 1
    assert np.array_equal(_height_ramp(z, -1.0, 5.0), _height_ramp_exact(z, -1.0, 5.0))


# --------------------------------------------------------------------------
# the demo layout -- key numbers, two-line charts, legend strip, the car
# --------------------------------------------------------------------------


def test_live_numbers_table_shows_this_frame_beside_the_whole_run():
    from types import SimpleNamespace

    from vrgrid.dash._config import status_markdown

    sched = load_schedule("5/10/20/40")
    run = {"n": 8, "perception": 8 * 84.0, "engine": 8 * 55.0, "dashboard": 8 * 13.0,
           "total": 8 * 152.0, "cleared": 50_841, "protected": 56_107, "truncated": 0,
           "peak_occupied": 225_916}
    md = status_markdown(
        1284, 139_143, sched, ghost_removal=True,
        counters=SimpleNamespace(cleared=9_214, protected=8_057, truncated=0), run=run,
        timing_ms={"perception": 84.0, "engine": 55.0, "dashboard": 13.0, "total": 152.0},
        ground_method="patchworkpp")
    assert "### Frame 1,284" in md and "ghost removal ON" in md and "Patchwork++" in md
    assert "| Frame time | 152 ms · 6.6 fps | 152 ms · 6.6 fps |" in md
    # the pipeline (what the budget is for) apart from the dashboard's drawing
    assert "| Pipeline (perception + map) | 139 ms · 7.2 fps | 139 ms · 7.2 fps |" in md
    assert "| Dashboard drawing | 13 ms | 13 ms |" in md
    assert "| Cells cleared (seen through) | 9,214 | 50,841 |" in md
    assert "| Cells kept (seen this scan) | 8,057 | 56,107 |" in md
    assert "| Skipped by candidate cap | 0 | 0 |" in md           # no flag when it is 0
    assert "Ghost cells" not in md and "guard" not in md
    # 139,143 / 225,916 cells x 12 B, against the fixed 745,000-cell allocation
    assert "| Map cells in use | 1.67 MB | peak 2.71 MB |" in md
    assert "| Map allocation | 8.94 MB, fixed at startup | never grows |" in md   # the real footprint
    assert "Map memory" not in md                                  # no ambiguous footprint figure
    # the static tables are on the Details tab, not repeated every frame
    assert "Measured" not in md and "Dense" not in md

    off = status_markdown(5, 10, sched, ghost_removal=False)
    assert "ghost removal OFF" in off and "| Cells cleared (seen through) | off | off |" in off
    assert "| Frame time | — | — |" in off                       # no timing: a dash, not a zero
    assert "| Pipeline (perception + map) | — | — |" in off
    capped = dict(run, truncated=7)
    assert "Skipped by candidate cap ⚑" in status_markdown(5, 10, sched, ghost_removal=True,
                                                           run=capped)


def test_details_tab_follows_the_deck_and_derives_every_figure():
    from vrgrid.cell import CELL_BYTES
    from vrgrid.dash._config import DECK_MEASURED, details_markdown, uniform_2_5d_baseline

    sched = load_schedule("5/10/20/40")
    assert uniform_2_5d_baseline(sched)["bytes"] == (200 / 0.05) ** 2 * CELL_BYTES == 192e6
    alloc = sched.total_cells * CELL_BYTES
    md = details_markdown(sched)
    assert "SIH26053" in md and "Chronicles.exe" in md
    # the deck's memory table, derived from the schedule
    assert "| **vrgrid 5/10/20/40 cm** | **8.94 MB** | **1×** |" in md
    assert f"| Uniform 5 cm 2.5D | 192.00 MB | {192e6 / alloc:.1f}× |" in md          # 21.5x
    assert f"{dense_3d_baseline(sched)['bytes'] / alloc:,.0f}× |" in md               # 286x
    assert "Sparse / hashed 3D" in md
    # the deck's measured results and scope limits
    for label, value in DECK_MEASURED:
        assert f"| {label} | {value} |" in md
    # scope limits: three rows, each with its unit and what it means
    assert f"| Blind spot radius | {blind_cone_radius_m():.2f} m — no ground seen closer |" in md
    assert "| 30 cm pothole | detectable up to 8.3 m |" in md
    assert "| Pedestrian motion | detectable up to 25 m |" in md
    # refinement is not in the live view, and the tab says so rather than leaving a gap
    assert "evaluated offline in the harness" in md
    # plain wording, not internal jargon
    assert "| Accuracy loss when merging, ρ (1.0 = none) |" in md
    assert "| Cleanup failures | 0 of 4,071 frames (seq 08) |" in md
    assert "Coarsening" not in md and "inert" not in md


def test_legend_strip_names_every_ring_and_the_blind_cone():
    from vrgrid.dash._config import map_legend_markdown

    sched = load_schedule("5/10/20/40")
    md = map_legend_markdown(sched, color_by="class", blind_cone_m=blind_cone_radius_m())
    for r in sched.rings:                   # every ring's cell size AND its reach
        assert f"{r.cell_m * 100:g} cm cells, out to {r.half_width_m:g} m" in md
    assert f"blind spot {blind_cone_radius_m():.2f} m" in md and "path driven" in md
    assert "free space" in md and "unknown" in md                  # plain names first
    assert "Ring 3 confidence" not in md          # the features note only with --features
    assert "Ring 3 confidence" in map_legend_markdown(sched, color_by="class",
                                                      blind_cone_m=3.74, features=True)


def test_rings_are_drawn_as_squares_at_their_half_width(tmp_path, monkeypatch):
    """Ring membership is the L-infinity distance (lattice.ring_of), so the
    boundary is a square -- a circle understates ring 0's corners by 4.1 m."""
    import rerun as rr
    from vrgrid.dash.pipeline_view import PipelineView

    calls = _spy_logs(monkeypatch)
    sched = load_schedule("5/10/20/40")
    PipelineView(sched, spawn=False, save_path=str(tmp_path / "rings.rrd"))
    rings = [(p, a) for p, a in calls if p.startswith("world/vehicle/rings/")]
    assert len(rings) == len(sched.rings)
    for (path, strip), ring in zip(rings, sched.rings):
        assert isinstance(strip, rr.LineStrips3D)
        pts = strip.strips.as_arrow_array().to_pylist()[0]
        xy = np.abs(np.array(pts)[:, :2])
        assert len(pts) == 5 and np.allclose(xy, ring.half_width_m)
    # the vehicle is one small flat arrow, logged once -- no car model
    assert not [p for p, _ in calls if p in ("world/vehicle/body", "world/vehicle/heading")]
    markers = [a for p, a in calls if p == "world/vehicle/marker"]
    assert len(markers) == 1 and isinstance(markers[0], rr.Mesh3D)
    verts = np.array(markers[0].vertex_positions.as_arrow_array().to_pylist())
    assert verts.shape == (3, 3) and np.ptp(verts[:, 0]) <= 4.0     # small: under 4 m long
    assert verts[:, 0].argmax() == 0 and np.allclose(verts[0, 1], 0.0)   # the tip points forward


def test_demo_panels_and_graphs_update_every_frame(tmp_path, monkeypatch):
    import rerun as rr
    from vrgrid.dash.pipeline_view import PipelineView
    from vrgrid.run.engine import MapEngine

    sent = []
    real_send = rr.send_blueprint
    monkeypatch.setattr(rr, "send_blueprint", lambda bp, **kw: (sent.append(bp), real_send(bp, **kw)))
    sched = load_schedule("5/10/20/40")
    engine = MapEngine(sched, ghost_removal=True)
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "ui.rrd"), engine=engine,
                        map_interval=2)
    view._gpu.stop()
    view._gpu = _FakeGpu(None)           # machine-independent: no GPU for this test
    calls = _spy_logs(monkeypatch)
    for i in range(3):
        f = _wall_frame(i)
        c = engine.step(f)
        view.log_frame(f, counters=c, timing_ms={"perception": 60.0, "engine": 40.0})

    def count(path):
        return sum(1 for p, _ in calls if p == path)

    assert len(sent) == 1
    for path in ("panel/status", "panel/header", "panel/kpi/memory", "panel/kpi/frame_time",
                 "proximity/vehicle", "proximity/objects",     # the near-field verdict
                 "stats/cleanup/cleared", "stats/cleanup/kept",
                 "world/follow"):              # the chase camera moves every frame
        assert count(path) == 3, path
    stats = {p for p, _ in calls if p.startswith("stats/")}
    assert not [p for p in stats if p.startswith("stats/gpu_pct")]   # no GPU: no GPU lines
    assert not [p for p in stats if p.startswith("stats/ghosts")]    # the old two-line chart is gone
    assert not [p for p in stats if p.startswith("stats/memory_mb")]  # the flat graph is gone too
    # the hazard timeline drew the whole recording -- hazards still to come -- so it is gone
    assert not [p for p in stats if p.startswith("stats/hazard")]
    # the frame-time graph's slot is the GPU's; the tile, table and feed keep frame time
    assert not [p for p in stats if p.startswith("stats/frame_ms")]
    # map_interval=2 over 3 timed frames: one full window, so exactly one feed line
    feed = [a for p, a in calls if p == "panel/feed/frames"]
    assert len(feed) == 1 and isinstance(feed[0], rr.TextLog)
    assert view._run["n"] == 3 and view._run["truncated"] == 0
    assert view._run["perception"] == 180.0 and view._run["peak_occupied"] > 0
    assert count("world/trajectory") == 1          # frames 0 and 2 redraw; frame 0 has 1 point
    assert count("panel/rings") == 2               # with the map, not every frame
    assert count("panel/near_occupancy") == 2
    assert count("panel/proximity") == 0           # the nearest-hazard readout is gone

    view.log_frame(_wall_frame(3))           # no counters or timing: tiles still update, no blank
    assert count("panel/kpi/frame_time") == 4
    view.finish()
    assert count("world/trajectory") == 2


class _FakeGpu:
    """Stands in for gpu_stats.GpuSampler so tests do not depend on the machine."""

    def __init__(self, reading):
        self._reading = reading

    def latest(self):
        return self._reading

    def stop(self):
        pass


def test_gpu_reading_reaches_its_chart_and_the_live_table(tmp_path, monkeypatch):
    from vrgrid.dash._config import status_markdown
    from vrgrid.dash.gpu_stats import GpuReading
    from vrgrid.dash.pipeline_view import PipelineView
    from vrgrid.run.engine import MapEngine

    reading = GpuReading("NVIDIA GeForce RTX 4050 Laptop GPU", 37.0, 1536.0, 6141.0)
    sched = load_schedule("5/10/20/40")
    engine = MapEngine(sched, ghost_removal=True)
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "gpu.rrd"), engine=engine)
    view._gpu.stop()
    view._gpu = _FakeGpu(reading)
    calls = _spy_logs(monkeypatch)
    f = _wall_frame(0)
    view.log_frame(f, counters=engine.step(f), timing_ms={"perception": 60.0, "engine": 40.0})

    paths = [p for p, _ in calls]
    assert paths.count("stats/gpu_pct/usage") == 1 and paths.count("stats/gpu_pct/memory") == 1
    assert view._run["gpu_peak_pct"] == 37.0
    md = status_markdown(1, 10, sched, ghost_removal=True, run=view._run, gpu=reading)
    assert "| GPU (RTX 4050 Laptop GPU) | 37% · 1.5 / 6.0 GB | peak 37% |" in md
    assert "GPU" not in status_markdown(1, 10, sched, ghost_removal=True)   # no reading, no row


def test_feed_line_colour_follows_the_worst_frame_in_its_window(tmp_path, monkeypatch):
    import rerun as rr
    from vrgrid.dash.pipeline_view import (
        _FEED_BAD_RGB,
        _FEED_OK_RGB,
        _FEED_WARN_RGB,
        PipelineView,
    )

    sched = load_schedule("5/10/20/40")
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "feed.rrd"), map_interval=2)
    view._gpu.stop()
    view._gpu = _FakeGpu(None)
    calls = _spy_logs(monkeypatch)
    frame = _wall_frame(0)
    for perception in (10.0, 10.0,     # window 1: well within 100 ms -> green
                       10.0, 85.0,     # window 2: worst ~85 ms, near -> yellow
                       10.0, 150.0):   # window 3: worst over budget -> red
        view.log_frame(frame, timing_ms={"perception": perception, "engine": 0.0})

    lines = [a for p, a in calls if p == "panel/feed/frames"]
    assert len(lines) == 3
    colours = []
    for line in lines:
        packed = int(line.color.as_arrow_array().to_pylist()[0])
        colours.append(((packed >> 24) & 255, (packed >> 16) & 255, (packed >> 8) & 255))
    assert colours == [_FEED_OK_RGB, _FEED_WARN_RGB, _FEED_BAD_RGB]
    assert isinstance(lines[2], rr.TextLog)


def test_startup_feed_lines_do_not_overwrite_each_other_or_the_frame_lines(tmp_path, monkeypatch):
    """Static data on an entity replaces everything else logged there. Both
    start-up lines on one path showed only the last, and hid every per-frame
    line behind it -- so each kind of line gets its own entity."""
    from vrgrid.dash.pipeline_view import PipelineView

    calls = _spy_logs(monkeypatch)
    view = PipelineView(load_schedule("5/10/20/40"), spawn=False,
                        save_path=str(tmp_path / "startup.rrd"), map_interval=1)
    view._gpu.stop()
    feed_paths = [p for p, _ in calls if p.startswith("panel/feed")]
    assert sorted(feed_paths) == ["panel/feed/startup/alloc", "panel/feed/startup/gpu"]
    view._gpu = _FakeGpu(None)
    view.log_frame(_wall_frame(0), timing_ms={"perception": 10.0, "engine": 0.0})
    assert [p for p, _ in calls if p == "panel/feed/frames"] == ["panel/feed/frames"]
    assert not [p for p, _ in calls if p == "panel/feed"]          # nothing on the bare path


def test_a_live_viewer_and_a_file_are_both_logged_to(tmp_path, monkeypatch):
    """--viz with --save must render AND record. `rr.save` alone replaces the
    viewer connection, so the GPU chart of such a recording showed an idle GPU
    rather than the load of rendering the run it records."""
    import rerun as rr
    from vrgrid.dash.pipeline_view import PipelineView

    spawned, sinks = [], []
    monkeypatch.setattr(rr, "spawn", lambda **kw: spawned.append(kw))
    monkeypatch.setattr(rr, "set_sinks", lambda *s, **kw: sinks.extend(s))
    view = PipelineView(load_schedule("5/10/20/40"), spawn=True,
                        save_path=str(tmp_path / "both.rrd"))
    view._gpu.stop()
    assert view.rendering_live
    assert spawned and spawned[0].get("connect") is False
    assert {type(s).__name__ for s in sinks} == {"GrpcSink", "FileSink"}


def test_saving_without_a_viewer_is_labelled_as_not_rendering(tmp_path):
    from vrgrid.dash.pipeline_view import PipelineView

    view = PipelineView(load_schedule("5/10/20/40"), spawn=False,
                        save_path=str(tmp_path / "file.rrd"))
    view._gpu.stop()
    assert view.rendering_live is False


# --------------------------------------------------------------------------
# the KPI layout -- tiles, colour modes, tiles-as-cells, swatches, glow
# --------------------------------------------------------------------------


def test_kpi_tiles_say_two_numbers_big_and_plainly():
    from vrgrid.dash._config import (
        header_markdown,
        kpi_frame_time_markdown,
        kpi_memory_markdown,
    )

    sched = load_schedule("5/10/20/40")
    md = kpi_memory_markdown(257_500, sched)                  # 257,500 cells x 12 B = 3.09 MB
    assert md.startswith("## 8.94 MB fixed")                  # the allocation is the headline
    assert "**21.5× smaller** than uniform 5 cm (192 MB)" in md   # same figure as Details
    assert "3.09 MB in use" in md
    bar = md.split("`")[1]
    assert len(bar) == 16 and bar.count("█") == 6             # 34.6% of 16 blocks
    assert kpi_memory_markdown(1, sched).split("`")[1].count("█") == 1   # never empty for a live map
    assert kpi_memory_markdown(0, sched, has_map=False).startswith("## —")

    assert "✓ under budget" in kpi_frame_time_markdown(60.0, 100.0)
    assert "△ near budget" in kpi_frame_time_markdown(95.0, 100.0)
    assert "✗ over budget" in kpi_frame_time_markdown(140.0, 100.0)
    assert kpi_frame_time_markdown(None, 100.0).startswith("## —")


    header = header_markdown(1284, ghost_removal=True)
    assert "SIH26053" in header and "Chronicles.exe" in header and "frame 1,284" in header
    assert "`GHOST REMOVAL: ON`" in header and "`LABELS: GT`" in header
    assert "Patchwork" not in header                           # ground method lives in Details
    assert "`GHOST REMOVAL: OFF`" in header_markdown(1, ghost_removal=False)
    assert "RINGS" not in header                               # no schedule, no badge
    assert "`RINGS: 5/10/20/40 cm`" in header_markdown(1, ghost_removal=True, schedule=sched)
    assert "`RINGS: 5/10/50 cm`" in header_markdown(
        1, ghost_removal=True, schedule=load_schedule("5/10/50"))




def test_legend_is_a_row_of_real_colour_swatches(tmp_path, monkeypatch):
    import rerun as rr
    from vrgrid.dash.pipeline_view import PipelineView, legend_items

    sched = load_schedule("5/10/20/40")
    items = legend_items(sched)
    labels = [t for t, _ in items]
    assert labels[:3] == ["height: low", "mid", "high"]
    assert {"rings", "moving", "car", "path", "blind spot", "free space", "unknown"} <= set(labels)
    # the swatches are the map's own colours, so the legend cannot drift from the map
    from vrgrid.dash.palettes import GHOST_RGB
    assert dict(items)["moving"] == tuple(GHOST_RGB)
    # translucent layers as they show over the background, not at full strength
    from vrgrid.dash.pipeline_view import _BACKGROUND_RGB, _FREE_RGBA, _PROX_RGB
    free = dict(items)["free space"]
    assert free != _FREE_RGBA[:3]
    assert all(min(b, c) <= f <= max(b, c) for f, b, c in zip(free, _BACKGROUND_RGB, _FREE_RGBA))
    # the blind spot is unknown ground, never the near-field panel's hazard red
    assert dict(items)["blind spot"] != _PROX_RGB["dynamic"]

    calls = _spy_logs(monkeypatch)
    PipelineView(sched, spawn=False, save_path=str(tmp_path / "legend.rrd"))
    swatches = [a for p, a in calls if p == "panel/legend_swatches"]
    assert len(swatches) == 1 and isinstance(swatches[0], rr.Points2D)
    assert swatches[0].labels.as_arrow_array().to_pylist() == labels


def test_the_demo_layout_builds_for_every_schedule():
    from vrgrid.dash.pipeline_view import _demo_blueprint

    for name in available_schedules():
        _demo_blueprint(load_schedule(name))
    _demo_blueprint(load_schedule("5/10/20/40"), background=(235, 238, 242))   # light test
    _demo_blueprint(load_schedule("5/10/20/40"), live=True)      # a live run follows the data


# the near-field panel -- green clear, yellow road anomaly, red object
# --------------------------------------------------------------------------


def test_proximity_config_resolves_class_names_through_the_one_table():
    from vrgrid.dash._config import load_proximity
    from vrgrid.grid.traversability import class_ids

    cfg = load_proximity()
    ids = class_ids()
    assert cfg["outer_m"] == max(cfg["half_widths_m"])
    assert set(cfg["person_ids"]) == {ids["person"], ids["bicyclist"], ids["motorcyclist"]}
    assert ids["car"] not in cfg["person_ids"]          # a PARKED car is not red
    assert set(cfg["surface_ids"]) == {ids["road"], ids["parking"]}


def test_proximity_verdict_red_beats_yellow_beats_green():
    from vrgrid.dash._config import (
        PROXIMITY_ANOMALY,
        PROXIMITY_CLEAR,
        PROXIMITY_DYNAMIC,
        load_proximity,
        proximity_verdict,
    )

    cfg = load_proximity()
    many, few = cfg["min_points"], cfg["min_points"] - 1
    holes, pits = cfg["min_cells"], cfg["min_cells"] - 1
    state, label = proximity_verdict(many, 4.2, holes, 6.0, cfg)
    assert state == PROXIMITY_DYNAMIC and "4.2 m" in label
    state, label = proximity_verdict(few, 4.2, holes, 6.0, cfg)   # a stray return is not an object
    assert state == PROXIMITY_ANOMALY and "6.0 m" in label
    assert proximity_verdict(few, 4.2, pits, 6.0, cfg)[0] == PROXIMITY_CLEAR
    assert proximity_verdict(0, None, 0, None, cfg)[0] == PROXIMITY_CLEAR


def test_near_field_panel_turns_red_for_a_person_and_green_without(tmp_path, monkeypatch):
    from vrgrid.dash._config import load_proximity
    from vrgrid.dash.pipeline_view import _PROX_RGB, PipelineView, _to_panel
    from vrgrid.grid.traversability import class_ids

    # Forward is up and left is left: vehicle +x -> screen -v, vehicle +y -> screen -u.
    assert _to_panel([2.0], [0.0]).tolist() == [[-0.0, -2.0]]
    assert _to_panel([0.0], [3.0]).tolist() == [[-3.0, -0.0]]

    sched = load_schedule("5/10/20/40")
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "p.rrd"))
    view._gpu.stop()
    view._gpu = _FakeGpu(None)
    calls = _spy_logs(monkeypatch)

    def vehicle_colour():
        tri = [a for p, a in calls if p == "proximity/vehicle"][-1]
        rgba = tri.colors.as_arrow_array().to_pylist()[0]     # packed 0xRRGGBBAA
        return (rgba >> 24 & 255, rgba >> 16 & 255, rgba >> 8 & 255)

    f = _wall_frame(0)                     # ground disc + wall at 25 m: nothing near
    view.log_frame(f)
    assert vehicle_colour() == _PROX_RGB["clear"]

    f = _wall_frame(1)
    person = class_ids()["person"]
    near = np.flatnonzero(np.hypot(*f.points_sensor[:, :2].T) < load_proximity()["outer_m"])
    f.semantic[near[:load_proximity()["min_points"]]] = person
    view.log_frame(f)
    assert vehicle_colour() == _PROX_RGB["dynamic"]
    objects = [a for p, a in calls if p == "proximity/objects"][-1]
    assert len(objects.positions) == load_proximity()["min_points"]


def test_ring_cells_panel_counts_each_ring_from_the_schedule():
    from vrgrid.dash._config import ring_cells_markdown

    sched = load_schedule("5/10/20/40")
    md = ring_cells_markdown([600, 300, 100, 0], sched)
    assert "5 cm  ███░░  60%" in md
    assert "10 cm ██░░░  30%" in md
    assert "20 cm █░░░░  10%" in md                  # a small share never shows empty
    assert "40 cm ░░░░░   0%" in md                  # an empty ring does
    assert "1,000 occupied" in md
    # cell sizes come from the schedule, never typed in
    assert "50 cm" in ring_cells_markdown([1, 1, 1], load_schedule("5/10/50"))
    assert ring_cells_markdown([], sched, has_map=False) == "back end off"
    assert "0 occupied" in ring_cells_markdown([0, 0, 0, 0], sched)       # no divide by zero


def test_side_panels_fit_their_column():
    """The two panels beside the near-field view get ~170 pt on the demo
    laptop. Every line in their code blocks stays inside PANEL_MAX_CHARS, for
    every schedule -- the table they replaced was ~245 pt wide and clipped."""
    from vrgrid.dash._config import (
        PANEL_MAX_CHARS,
        near_occupancy_markdown,
        ring_cells_markdown,
    )

    docs = [near_occupancy_markdown(123_456, 98_765, 4_321, load_schedule("5/10/20/40").rings[0])]
    for name in available_schedules():
        sched = load_schedule(name)
        docs.append(ring_cells_markdown([999_999] * len(sched.rings), sched))
    for md in docs:
        lines = md.split("```")[1].strip("\n").splitlines()
        assert lines and max(len(line) for line in lines) <= PANEL_MAX_CHARS, md
        bar_starts = {min(i for i, ch in enumerate(line) if ch in "█░") for line in lines}
        assert len(bar_starts) == 1, md                   # the bars line up


def test_graph_lines_never_wear_a_status_colour():
    """The feed's green / yellow / red mean OK / near / over. A graph line in
    one of them reads as a verdict -- both graph lines used to be the OK green."""
    from vrgrid.dash.pipeline_view import (
        _FEED_BAD_RGB,
        _FEED_OK_RGB,
        _FEED_WARN_RGB,
        _series_styles,
    )

    status = {_FEED_OK_RGB, _FEED_WARN_RGB, _FEED_BAD_RGB}
    styles = _series_styles(load_schedule("5/10/20/40"))
    assert not status & {tuple(c[:3]) for _, c, _ in styles.values()}
    for graph in {p.rsplit("/", 1)[0] for p in styles}:   # no two lines on a graph alike
        looks = [(tuple(c), w) for p, (_, c, w) in styles.items() if p.startswith(graph + "/")]
        assert len(set(looks)) == len(looks), graph
    # each frame faint and thin, its average solid and bold, in the same hue
    (_, c_raw, w_raw), (_, c_avg, w_avg) = (styles["stats/gpu_pct/usage"],
                                            styles["stats/gpu_pct/usage_trend"])
    assert c_raw[:3] == c_avg[:3] and len(c_raw) == 4 and c_raw[3] < 128
    assert w_raw < w_avg
    # the cleanup graph compares two outcomes: two solid lines, two hues
    cleared, kept = styles["stats/cleanup/cleared"], styles["stats/cleanup/kept"]
    assert cleared[1][:3] != kept[1][:3] and len(cleared[1]) == len(kept[1]) == 3


def test_cleanup_graph_is_cleared_and_kept_running_averages_in_thousands(tmp_path, monkeypatch):
    from vrgrid.dash._config import playback_fps
    from vrgrid.dash.pipeline_view import TREND_S, PipelineView

    view = PipelineView(load_schedule("5/10/20/40"), spawn=False,
                        save_path=str(tmp_path / "trend.rrd"))
    view._gpu.stop()
    view._gpu = _FakeGpu(None)
    calls = _spy_logs(monkeypatch)

    class C:        # a StepCounters stand-in: only what _log_stats reads
        truncated = 0

        def __init__(self, cleared, protected):
            self.cleared, self.protected = cleared, protected

    n = round(TREND_S * playback_fps())
    cleared = [2_000 * (i + 1) for i in range(n + 3)]
    kept = [9_000 - 100 * i for i in range(n + 3)]
    for i, (c, k) in enumerate(zip(cleared, kept)):
        view.log_frame(_wall_frame(i), counters=C(c, k))

    def last(path):
        return [a for p, a in calls if p == path][-1].scalars.as_arrow_array().to_pylist()[0]

    assert last("stats/cleanup/cleared") == pytest.approx(np.mean(cleared[-n:]) / 1e3)
    assert last("stats/cleanup/kept") == pytest.approx(np.mean(kept[-n:]) / 1e3)
    assert not [p for p, _ in calls if p.startswith("stats/moving")]    # the old series


def test_near_occupancy_panel_keeps_unknown_apart_from_free():
    from vrgrid.dash._config import near_occupancy_markdown

    ring0 = load_schedule("5/10/20/40").rings[0]
    md = near_occupancy_markdown(200, 600, 200, ring0)
    assert "occupied █░░░░  20%" in md
    assert "free     ███░░  60%" in md
    assert "unknown  █░░░░  20%" in md                # its own row, never free
    assert "unknown ≠ free" in md
    assert "free     ░░░░░   0%" in near_occupancy_markdown(0, 0, 0, ring0)
    assert near_occupancy_markdown(0, 0, 0, ring0, has_map=False) == "back end off"


def test_near_field_labels_do_not_overlap():
    """Every label on the near-field panel, as a text box at the panel's
    scale, meets no other and fits the view. The same labels as before --
    only their positions moved: the axis captions sat among the tick numbers,
    and the bottom-left corner's two numbers sat a metre apart.

    Box size: `_LABEL_CHAR_M` x `_LABEL_LINE_M`, the panel's own estimate.
    The car's label is the longest it gets, centred on the car."""
    from vrgrid.dash._config import load_proximity
    from vrgrid.dash.pipeline_view import (
        _LABEL_CHAR_M,
        _LABEL_LINE_M,
        _prox_bounds,
        _prox_grid_half_m,
        _prox_text_layout,
    )

    cfg = load_proximity()
    char_m, line_m = _LABEL_CHAR_M, _LABEL_LINE_M
    boxes = []
    for pos, texts in _prox_text_layout(cfg).values():
        boxes += [(float(u), float(v), t) for (u, v), t in zip(pos, texts)]
    assert [t for *_, t in boxes].count("x (m) · forward +") == 1      # nothing dropped
    assert {"5 m", "10 m", "y (m) · left +"} <= {t for *_, t in boxes}
    boxes.append((0.0, 0.0, "MOTORCYCLIST 9.9 m · held"))

    def extent(b):
        u, v, t = b
        return u - len(t) * char_m / 2, u + len(t) * char_m / 2, v - line_m / 2, v + line_m / 2

    (u0, u1), (v0, v1) = _prox_bounds(cfg)
    for i, a in enumerate(boxes):
        a0, a1, a2, a3 = extent(a)
        assert u0 <= a0 and a1 <= u1 and v0 <= a2 and a3 <= v1, a[2]   # not clipped
        for b in boxes[i + 1:]:
            b0, b1, b2, b3 = extent(b)
            assert a1 <= b0 or b1 <= a0 or a3 <= b2 or b3 <= a2, (a[2], b[2])

    # No empty band: every side of the view ends within a label's reach of the
    # grid. The symmetric box it replaced left 3.5 m of nothing on the right.
    g = _prox_grid_half_m(cfg)
    assert u1 - g < 2.0 and -g - u0 < 4.0 and -g - v0 < 3.0 and v1 - g < 4.0
    assert 0.9 < (u1 - u0) / (v1 - v0) < 1.1                    # about square, like the grid


def test_ring_cells_panel_total_is_the_memory_tiles_count(tmp_path, monkeypatch):
    from vrgrid.dash.pipeline_view import PipelineView
    from vrgrid.run.engine import MapEngine

    sched = load_schedule("5/10/20/40")
    engine = MapEngine(sched, ghost_removal=True)
    view = PipelineView(sched, spawn=False, save_path=str(tmp_path / "rings.rrd"), engine=engine)
    view._gpu.stop()
    view._gpu = _FakeGpu(None)
    calls = _spy_logs(monkeypatch)
    f = _wall_frame(0)
    view.log_frame(f, counters=engine.step(f))
    md = [a for p, a in calls if p == "panel/rings"][-1].text.as_arrow_array().to_pylist()[0]
    assert view._last_occupied_n > 0
    assert md.endswith(f"{view._last_occupied_n:,} occupied")


def test_near_field_holds_a_hazard_but_never_shows_it_late(tmp_path, monkeypatch):
    """seq 00's cyclist 2.5 m ahead gives 0-14 points a scan, straddling
    min_points: without the hold the panel blinked red/green 28 times in 160
    frames. Red must still appear on the frame it is seen."""
    from vrgrid.dash._config import load_proximity
    from vrgrid.dash.pipeline_view import _PROX_RGB, PipelineView
    from vrgrid.grid.traversability import class_ids

    cfg = load_proximity()
    assert cfg["hold_frames"] > 1
    view = PipelineView(load_schedule("5/10/20/40"), spawn=False,
                        save_path=str(tmp_path / "hold.rrd"))
    view._gpu.stop()
    view._gpu = _FakeGpu(None)
    calls = _spy_logs(monkeypatch)

    def shown():
        tri = [a for p, a in calls if p == "proximity/vehicle"][-1]
        rgba = tri.colors.as_arrow_array().to_pylist()[0]
        return (rgba >> 24 & 255, rgba >> 16 & 255, rgba >> 8 & 255)

    def frame(i, person):
        f = _wall_frame(i)
        if person:
            near = np.flatnonzero(np.hypot(*f.points_sensor[:, :2].T) < cfg["outer_m"])
            f.semantic[near[:cfg["min_points"]]] = class_ids()["person"]
        return f

    view.log_frame(frame(0, False))
    assert shown() == _PROX_RGB["clear"]
    view.log_frame(frame(1, True))
    assert shown() == _PROX_RGB["dynamic"]                    # on the frame it is seen
    for i in range(2, 1 + cfg["hold_frames"]):                # lost for hold_frames - 1
        view.log_frame(frame(i, False))
        assert shown() == _PROX_RGB["dynamic"], i
    tri = [a for p, a in calls if p == "proximity/vehicle"][-1]
    assert tri.labels.as_arrow_array().to_pylist()[0].endswith(" · held")   # says so
    view.log_frame(frame(1 + cfg["hold_frames"], False))     # then it lets go
    assert shown() == _PROX_RGB["clear"]
