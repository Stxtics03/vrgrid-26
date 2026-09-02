"""End-to-end evaluation on a synthetic sequence. [Aakash]

    python scripts/eval_synthetic.py [--frames 12] [--keep]

Gate 6 says every number on a slide comes from a script. This is the script
for the per-ring table, running the whole chain with no data and no network:

    synthetic sequence on disk  ->  reference map M* (§9.1)
                                ->  scatter + fuse per schedule (§3)
                                ->  traversability bitfield (§7.1)
                                ->  per-ring RMSE / rho / IoU / fill (§9.2-9.3)

⚑ The numbers it prints are NOT reportable. The terrain is analytic, so there
  is no sensor noise, no occlusion and no registration error; what is measured
  is the pipeline against a surface it can in principle recover exactly. It is
  the right thing to develop against and the wrong thing to put on a slide.
  Swap `read_sequence` for `perception.loader` and sequence 07 when the
  download lands, and the same script prints reportable numbers.
"""

import argparse
import shutil
import tempfile
from pathlib import Path

import numpy as np
from vrgrid.eval.harness import (
    build_gridmap,
    evaluate,
    format_result,
    memory_vs_regret_row,
    run_sequence,
    uniform_schedule,
)
from vrgrid.eval.plan_regret import (
    common_support,
    costmap_from_gridmap,
    costmap_from_reference,
    regret,
    restrict,
    weights,
)
from vrgrid.eval.reference_map import build_from_scans
from vrgrid.eval.synthetic import (
    POTHOLE_RADIUS_M,
    POTHOLE_XY_M,
    read_sequence,
    write_sequence,
)
from vrgrid.grid.schedule import load, load_thresholds
from vrgrid.grid.transient import TrackList

SCHEDULES = ["5/10/20/40", "5/10/50"]

# §8.2 sweeps "5/10/20/40, 5/10/50, uniform 5, uniform 10, uniform 20, ...".
# The uniform points are what give the curve a knee: the two frozen schedules
# share rings 0 and 1 and differ only past 25 m, so a near-field planning
# problem reports the same regret for both.
UNIFORM_CELLS_M = [0.10, 0.20, 0.40, 0.80]


def vehicle_frame_scans(root, sequence, keep_moving=False):
    """(points, RAW label ids, is_ground, pose) per frame, in vehicle frame.

    The synthetic writer stores points already in vehicle frame with the pose
    separately, which is what a real loader gives you too -- so this is the
    seam `perception.loader` slots into unchanged.

    RAW ids, not learning ids: `moving-*` (250-259) is what the transient
    layer separates on, and the 19-class collapse destroys exactly that.
    The pipeline routes dynamic returns away from the persistent map itself
    now -- this used to strip them by hand, which was a stand-in for the
    transient layer and stopped being possible the moment real data landed.

    `--keep-moving` bypasses the separation to show what it is worth: on this
    sequence ring 1's RMSE goes from 0.48 cm to 11.71 cm, its entire error
    budget, from one car 12 m ahead.
    """
    for pts, labels, pose in read_sequence(root, sequence):
        # Raw `car` (10), not raw `outlier` (1). `--keep-moving` is meant to
        # show what the transient layer is worth, so the car has to survive as
        # the thing it is; folding it onto an id the 19-class map sends to
        # ignore would answer a different question.
        out = np.where(labels >= 250, 10, labels) if keep_moving else labels
        yield pts, out, np.ones(len(pts), dtype=bool), pose


# The planning problem the regret is measured on. Placed RELATIVE to the
# vehicle's final pose, and behind it: that is the road the sequence has
# actually driven over, so the map has been filled by ego-motion (§1.3) rather
# than by one sparse sweep.
#
# ⚑ This placement is a measurement decision, not a detail. Put the window
#   ahead of the final pose and most of it has been seen once, at range, at
#   P_fill < 2%; the fine rings are then mostly UNKNOWN, they pay w_unknown,
#   and the regret measures how sparse the map is rather than what the
#   coarsening cost. It inverts the result -- a coarse grid whose big cells
#   each caught a return scores BETTER than a fine one full of holes. The
#   `unknown` column is what makes that visible, which is why it is printed
#   next to R(S) and not buried.
PLAN_BEHIND_M, PLAN_N = -11.0, 44
PLAN_Y0_M = -5.5

# Two queries, and reporting both is the point.
#
# "hazard" is the one the figure is about. Its lane is derived FROM THE TERRAIN
# -- it is the y of the scene's only impassable feature, read out of
# `POTHOLE_XY_M`, not a number chosen to make a curve look right. So the
# straight line from start to goal runs through the pothole and the planner has
# to decide about it. `assert_hazard_in_window` refuses to run it if the window
# does not contain the pothole, because at `--frames 16` it does not and a
# hazard query with no hazard in it is exactly the failure this is fixing.
#
# "control" is the ORIGINAL query, kept unchanged: a lane six cells off centre
# that no hazard is on. Its job is to come out at R(S) = 0 for every schedule.
# That is what makes the pair evidence rather than a repositioning: the two
# queries run on the same maps over the same window, and the only difference
# between them is whether a decision is at stake. If the control moves, the
# difference between them is not the pothole.
#
# ⚑ The old comment here said the centreline "drops out of the common support
#   and the centreline corridor is severed", which is why the lane was offset.
#   That is no longer true -- the beam-surface intersection fix raised coverage
#   in every ring -- so the offset is kept as a control rather than as a
#   workaround.
PLAN_LANE_CELLS = 6
PLAN_QUERIES = ("hazard", "control")


def plan_cell_m() -> float:
    return float(weights().get("cell_m", 0.25))


def window_origin(vehicle_xy_m):
    """(x0, y0) of the planning window, and the vehicle's (x, y)."""
    vx, vy = ((float(vehicle_xy_m), 0.0) if np.isscalar(vehicle_xy_m)
              else (float(vehicle_xy_m[0]), float(vehicle_xy_m[1])))
    return vx + PLAN_BEHIND_M, vy + PLAN_Y0_M, vx, vy


def assert_hazard_in_window(vehicle_xy_m) -> None:
    """The hazard query is only posed if the hazard is inside the window.

    Not a nicety. At `--frames 16` the window is x = 19-30 m and the pothole is
    at x = 18, so M* over it contains ZERO impassable cells -- and a regret
    measured there is comparing two maps of empty road and reporting the
    tie-breaking between equal-cost paths. Raising is the only way that does
    not silently become a number on a slide.
    """
    x0, y0, _, _ = window_origin(vehicle_xy_m)
    c = plan_cell_m()
    x1, y1 = x0 + PLAN_N * c, y0 + PLAN_N * c
    hx, hy = POTHOLE_XY_M
    if not (x0 <= hx < x1 and y0 <= hy < y1):
        raise ValueError(
            f"the hazard query needs the pothole at {POTHOLE_XY_M} inside the "
            f"planning window x [{x0:.2f}, {x1:.2f}] y [{y0:.2f}, {y1:.2f}], "
            "and it is not. The window is placed PLAN_BEHIND_M behind the "
            "final pose, so this is a statement about the frame count: use "
            "one that leaves the pothole behind the vehicle and inside 11 m "
            "of it. Run scripts/plan_query_survey.py to see the window."
        )


def plan_query(which: str, vehicle_xy_m):
    """(start, goal) in lattice cells for one of `PLAN_QUERIES`.

    Every number here is read off the scene or the sensor. None of them is a
    knob, and that is the point -- the query this replaces was diagnosed as
    running down a lane the hazards were not on, and a replacement chosen by
    trying placements until R(S) looked right would be worse than the original.

    **i of the start** is 1, not 0: `_slope` and `_max_step` zero the one-cell
    border of the lattice, so cell 0 has no gradient on either map.

    **i of the goal** is the last cell fully outside the BLIND CONE at the
    final pose. `sensor.blind_cone_m` is 3.74 m of ground the sensor cannot
    see in any single frame (§1.4), so the last few metres behind the vehicle
    are held by the fewest observations in the whole window -- and with the
    common support now restricted to CONFIDENTLY observed ground, a goal in
    there is simply not in the mask and no path exists. That is what the
    original edge-to-edge query hit: `--frames 12`, both endpoints outside the
    mask, R(S) undefined for every schedule.

    **j** is the hazard's own y for the hazard query, so the straight line
    from start to goal runs through the pothole and the planner has to decide.

    The margin is the run-in an 8-connected planner needs to offset around the
    hazard and come back: it can move one cell laterally per cell forward, so
    clearing a hazard of radius `r` and returning needs about `4r` of run-in
    at each end. Less than that and the endpoints sit on top of the hazard,
    which is a sidestep rather than a decision.
    """
    if which not in PLAN_QUERIES:
        raise ValueError(f"query must be one of {PLAN_QUERIES}, not {which!r}")
    x0, y0, vx, _ = window_origin(vehicle_xy_m)
    c = plan_cell_m()
    if which == "control":
        j = PLAN_N // 2 - PLAN_LANE_CELLS
        return (1, j), (PLAN_N - 2, j)

    assert_hazard_in_window(vehicle_xy_m)
    blind_m = float(load_thresholds()["sensor"]["blind_cone_m"])
    i_start = 1
    i_goal = min(PLAN_N - 2, int(np.floor((vx - blind_m - x0) / c - 0.5)))
    i_hazard = int(np.floor((POTHOLE_XY_M[0] - x0) / c))
    j = int(np.floor((POTHOLE_XY_M[1] - y0) / c))

    margin = int(np.ceil(4.0 * POTHOLE_RADIUS_M / c))
    if not (i_start + margin <= i_hazard <= i_goal - margin):
        raise ValueError(
            f"the hazard query needs the pothole at i={i_hazard} to sit at "
            f"least {margin} cells inside the run from i={i_start} to "
            f"i={i_goal}, and it does not. The goal is capped at the last cell "
            f"outside the {blind_m:.2f} m blind cone behind the vehicle, so "
            "this is a statement about the frame count: the window is placed "
            f"{-PLAN_BEHIND_M:.1f} m behind the final pose and the pothole is "
            f"at x={POTHOLE_XY_M[0]:.1f} m. Run scripts/plan_query_survey.py "
            "to see the window."
        )
    return (i_start, j), (i_goal, j)


def costmaps_for(gm, reference, vehicle_xy_m):
    """(M*, M_S) on one shared planning lattice. M_S through query() only.

    `vehicle_xy_m` is the vehicle's final world position, `(x, y)`. A float is
    accepted and read as `(x, 0.0)` -- the synthetic sequence drives straight
    down y = 0, and every caller here predates real data.

    ⚑ The y was hardcoded to `PLAN_Y0_M` about the world origin, which is only
      the vehicle's lane while the trajectory is a straight line along +x. On
      a real KITTI sequence the car turns, so the window stayed near the
      origin while the vehicle drove away from it: the regret would have been
      measured over ground the map never saw, on both maps equally, and come
      out as a confident zero. Worth being explicit about, because that
      failure produces a *better-looking* number than the truth.
    """
    x0, y0, vx, vy = window_origin(vehicle_xy_m)
    return (costmap_from_reference(reference, x0, y0, PLAN_N, PLAN_N),
            costmap_from_gridmap(gm, x0, y0, PLAN_N, PLAN_N,
                                 vehicle_xy_m=(vx, vy)))


def plan_regret_for(gm, reference, vehicle_xy_m, mask=None, which="hazard"):
    """R(S) for one map, through query() only. Math §8.1.

    `mask` restricts both maps to the common support -- ground every schedule
    in the comparison CONFIDENTLY observed. Without it the number measures
    fill rate rather than coarsening; see the confound note in
    eval/plan_regret.py.

    `which` selects the query: "hazard" runs through the pothole, "control"
    down the original off-centre lane that nothing is on. Report both.
    """
    star, mine = costmaps_for(gm, reference, vehicle_xy_m)
    if mask is not None:
        star, mine = restrict(star, mask), restrict(mine, mask)
    start, goal = plan_query(which, vehicle_xy_m)
    return regret(star, mine, start, goal)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--out", default=None, help="keep the sequence here")
    ap.add_argument("--keep-moving", action="store_true",
                    help="do not strip moving-* before scatter; shows what the "
                         "missing transient layer costs")
    ap.add_argument("--confound", action="store_true",
                    help="also print R(S) WITHOUT the common-support "
                         "restriction, next to how much of each planning "
                         "window was low-confidence -- the table in "
                         "eval/plan_regret.py's confound note")
    args = ap.parse_args()

    root = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="vrgrid-syn-"))
    try:
        write_sequence(root, "99", n_frames=args.frames)
        print(f"synthetic sequence: {args.frames} frames in {root}")

        reference = build_from_scans(read_sequence(root, "99"))
        print(f"reference map:      {reference}\n")

        vehicle_x = (args.frames - 1) * 2.0
        schedules = ([load(n) for n in SCHEDULES]
                     + [uniform_schedule(c, half_width_m=24.0)
                        for c in UNIFORM_CELLS_M])

        # Two passes. Every map is built first so the common support -- ground
        # EVERY schedule observed -- is known before anything is scored. A
        # cross-schedule regret computed without it measures fill rate.
        built = []
        for schedule in schedules:
            gm = build_gridmap(schedule)
            tracks = TrackList(gm.allocation.max_tracks,
                               arrays=gm.allocation.tracks)
            stats = run_sequence(
                gm, vehicle_frame_scans(root, "99", args.keep_moving),
                tracks=tracks)
            built.append((schedule, gm, evaluate(gm, reference, stats.frames), stats))

        mask = common_support(*[costmaps_for(gm, reference, vehicle_x)[1]
                                for _, gm, _, _ in built])
        print(f"common support: {mask.mean():.1%} of the planning window was "
              f"observed by every schedule")
        print()

        rows, unrestricted = [], []
        for schedule, gm, result, stats in built:
            if args.confound:
                _, mine = costmaps_for(gm, reference, vehicle_x)
                raw_u = plan_regret_for(gm, reference, vehicle_x)
                # ⚑ This read `mine.unknown` -- never-observed -- and the
                #   column is headed "low-confidence". They are different
                #   arrays: on this sweep 0.9% against 91.9%, and the small
                #   one was being quoted as evidence the confound had closed.
                #   `low_confidence` is bit 5, which is the set `w_unknown` is
                #   actually charged on.
                unrestricted.append((schedule.name, raw_u,
                                     float(np.mean(mine.low_confidence))))
            ctrl = plan_regret_for(gm, reference, vehicle_x, mask, "control")
            if schedule.name.startswith("uniform"):
                rows.append((result,
                             plan_regret_for(gm, reference, vehicle_x, mask),
                             ctrl))
                continue
            print(format_result(result, schedule))
            print(f"  transient: {stats.dynamic_points:,} dynamic returns routed "
                  f"out of the persistent map, {stats.tracks} tracks alive; "
                  f"§9.4 DR={stats.removal['DR']:.2f} SP={stats.removal['SP']:.2f} "
                  f"F={stats.removal['F']:.2f}")
            print(f"  gate:      fired {stats.gate_fired}, acquired "
                  f"{stats.gate_acquired}, refused {stats.gate_refused}, "
                  f"released {stats.gate_released}; pool "
                  f"{gm.pool.blocks - gm.pool.free_blocks}/{gm.pool.blocks} blocks")
            reg = plan_regret_for(gm, reference, vehicle_x, mask)
            raw = plan_regret_for(gm, reference, vehicle_x)
            print(f"  plan regret R(S) = {reg.regret:.3f} on the common support   "
                  f"({raw.regret:.3f} unrestricted, path "
                  f"{raw.low_confidence_fraction:.0%} below n_min / "
                  f"{raw.unknown_fraction:.0%} unobserved -- those measure fill "
                  f"rate, not coarsening)")
            print(f"  control query R(S) = {ctrl.regret:.3f} down the lane "
                  f"nothing is on -- this one is SUPPOSED to be 0.000")
            print()
            rows.append((result, reg, ctrl))

        print("§8.2, the money plot: memory on x, plan regret on y.")
        print("  R(S) = J_M*(pi_S) - J_M*(pi*), BOTH paths scored on M*.")
        print("  The query runs through the pothole; `control` is the same "
              "sweep down a lane")
        print("  no hazard is on, and it is the negative control -- it must "
              "read 0.000.")
        print(f"  {'schedule':<12} {'MB':>7} {'cells':>10} {'RMSE':>7} {'rho':>6} "
              f"{'R(S)':>8} {'control':>8} {'frechet':>8} {'unknown':>8}")
        for r, reg, ctrl in rows:
            m = memory_vs_regret_row(r, reg)
            blocked = " BLOCKED" if m["blocked_on_reference"] else ""
            print(f"  {m['schedule']:<12} {m['megabytes']:>7.2f} "
                  f"{m['logical_cells']:>10,} {m['worst_ring_rmse_cm']:>6.2f}c "
                  f"{m['mean_rho']:>6.2f} {m['regret']:>8.3f} "
                  f"{ctrl.regret:>8.3f} "
                  f"{m['frechet_m']:>7.2f}m {m['unknown_fraction']:>7.1%}{blocked}")
        if unrestricted:
            print()
            print("The confound, unrestricted. Math §8.2, and the note in "
                  "eval/plan_regret.py.")
            print("  R(S) here is NOT on the common support, so it is not "
                  "comparable across")
            print("  cell sizes -- that is the whole point of printing it.")
            print(f"  {'schedule':<14} {'R(S)':>8} {'window low-confidence':>22}")
            for name, raw_u, low in unrestricted:
                print(f"  {name:<14} {raw_u.regret:>8.3f} {low:>21.0%}")
            print()
            print("  A finer schedule holds fewer returns per cell, so more of "
                  "its window is")
            print("  below n_min; it pays w_unknown and the planner routes "
                  "around a map that")
            print("  is merely SPARSE. Read across this table and finer looks "
                  "worse, which is")
            print("  precisely backwards. `common_support()` is the fix and the "
                  "money plot")
            print("  above uses it.")

        print()
        print("  R(S) = 0 means the coarsening did not change the decision -- the")
        print("  only sense in which a saving is free. Read it WITH `unknown`:")
        print("  zero regret along a mostly-unknown path says the sequence was too")
        print("  short to fill the map, not that the schedule cost nothing.")
    finally:
        if args.out is None:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
