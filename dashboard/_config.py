"""Config- and schedule-derived values for the dashboard. [JP]

Imports no rerun. These read the frozen config files (`configs/thresholds.yaml`,
`configs/schedule_*.yaml`) via `vrgrid.grid.schedule`, and `tests/test_dashboard.py`
exercises them in CI where the optional `[dash]` extra (rerun-sdk) is not
installed. `pipeline_view.py` imports from here; `palettes.py` stays
colours-only, so the split is: colours in `palettes`, config/schedule wiring
here, rerun logging in `pipeline_view`.

Nothing in this project may hardcode a threshold or a ring size inline
(CLAUDE.md, "Don't"); this module is where the dashboard reads them instead.
"""

from vrgrid.cell import CELL_BYTES
from vrgrid.grid.schedule import CONFIG_DIR, load_thresholds
from vrgrid.grid.schedule import load as _load_schedule

# Bytes per voxel assumed for the dense-3D baseline. A dense voxel needs only an
# occupancy state, so 1 B is the charitable figure for the baseline -- the same
# convention `scripts/memory_table.py` uses for the report's 286x headline.
# (Our cell is CELL_BYTES = 12 because it also carries height, variance, class
# and flags; the ratio is deliberately measured against the baseline's best
# case, not ours.)
DENSE_VOXEL_BYTES = 1


def blind_cone_radius_m() -> float:
    """Blind-cone radius from `configs/thresholds.yaml` `sensor.blind_cone_m`.

    Math §1.4 eq (5): r_blind = h_s / tan|phi_min| = 1.73 / tan(24.8 deg) =
    3.74 m. The earlier plan assumed 1-2 m; master v4 corrected it. Read from
    the frozen config through the one cached reader (`load_thresholds`), never
    hardcoded -- a second literal is how the file and the running system drift.
    """
    return float(load_thresholds()["sensor"]["blind_cone_m"])


def playback_fps() -> float:
    """Timeline playback rate for recordings: the sensor's own frame rate,
    `1 / fusion.frame_dt_s` (10 Hz on KITTI), so a baked scene plays back in
    real time. Read from the frozen config, like every other rate here."""
    return 1.0 / float(load_thresholds()["fusion"]["frame_dt_s"])


def frame_budget_ms() -> float:
    """The per-frame budget: one sensor period, `1e3 * fusion.frame_dt_s`
    (100 ms at KITTI's 10 Hz). The line the frame-time chart is read against."""
    return 1e3 * float(load_thresholds()["fusion"]["frame_dt_s"])


def available_schedules() -> list[str]:
    """Schedule names discovered from `configs/schedule_*.yaml` -- no hardcoding.

    Returns the bare names (`5_10_20_40`, `5_10_50`) as `grid.schedule.load`
    accepts them.
    """
    return sorted(
        p.stem.removeprefix("schedule_") for p in CONFIG_DIR.glob("schedule_*.yaml")
    )


def schedule_legend_markdown(active: str) -> str:
    """Markdown table of every available schedule and its ring boundaries, read
    from the config files, with the active one marked.

    This is the (display-only) schedule selector: switching schedules mid-run is
    not wired -- `--schedule <name>` on `vrgrid.dash` / `vrgrid.run` picks one at
    startup. Ring half-widths and cell sizes come straight from the yaml via
    `grid.schedule.load`, so this cannot drift from what the engine uses.
    """
    lines = [
        "**Schedule selector** (display only -- `--schedule <name>` picks it at startup)",
        "",
        "| schedule | rings: half-width m / cell cm | cells | MB |",
        "|---|---|---|---|",
    ]
    for name in available_schedules():
        s = _load_schedule(name)
        rings = ", ".join(f"{r.half_width_m:g}/{r.cell_m * 100:g}" for r in s.rings)
        mark = " **(active)**" if name == active else ""
        lines.append(
            f"| `{name}`{mark} | {rings} | {s.total_cells:,} | "
            f"{s.total_cells * CELL_BYTES / 1e6:.2f} |"
        )
    return "\n".join(lines)


def dense_3d_baseline(schedule) -> dict:
    """The dense 5 cm 3-D voxel grid this map replaces, derived from the schedule.

    Not a magic number: the covered volume is the outer ring's square footprint
    (`2 * half_width` on a side) times the schedule's own vertical extent, at the
    schedule's finest resolution (`base_cell_m`) applied uniformly in all three
    axes -- the resolution the variable grid only spends in ring 0.

        footprint_m = 2 * schedule.rings[-1].half_width_m
        vertical_m  = hi - lo   from schedule.vertical_extent_m
        res_m       = schedule.base_cell_m
        voxels      = (footprint_m / res_m) ** 2 * (vertical_m / res_m)
        bytes       = voxels * DENSE_VOXEL_BYTES

    For `5_10_20_40`: (200 / 0.05)^2 * (8 / 0.05) = 2.56e9 voxels = 2.56 GB.
    """
    footprint_m = 2.0 * schedule.rings[-1].half_width_m
    lo, hi = schedule.vertical_extent_m
    vertical_m = hi - lo
    res_m = schedule.base_cell_m
    voxels = (footprint_m / res_m) ** 2 * (vertical_m / res_m)
    return {
        "footprint_m": footprint_m,
        "vertical_m": vertical_m,
        "res_m": res_m,
        "voxels": voxels,
        "bytes": voxels * DENSE_VOXEL_BYTES,
    }


def uniform_2_5d_baseline(schedule) -> dict:
    """A uniform grid at the schedule's finest cell over the outer ring's
    footprint, with the same `CELL_BYTES` cell -- the row `scripts/memory_table.py`
    prints, derived the same way. For `5_10_20_40`: (200 / 0.05)^2 * 12 B = 192 MB.
    It is a pure cell-count ratio against ours, so it does not depend on bytes
    per cell."""
    footprint_m = 2.0 * schedule.rings[-1].half_width_m
    cells = (footprint_m / schedule.base_cell_m) ** 2
    return {"footprint_m": footprint_m, "cells": cells, "bytes": cells * CELL_BYTES}


def grid_memory_stats(n_occupied: int, schedule) -> dict:
    """Live map memory vs the dense-3D baseline for `n_occupied` occupied cells.

    `live_bytes` is exactly `n_occupied * CELL_BYTES` -- the real storage the
    occupied cells take, not a fixed allocation figure. `ratio` is how many
    times bigger the dense-3D baseline for the same covered volume would be.
    """
    dense = dense_3d_baseline(schedule)
    live_bytes = int(n_occupied) * CELL_BYTES
    return {
        "n_occupied": int(n_occupied),
        "cell_bytes": CELL_BYTES,
        "live_bytes": live_bytes,
        "dense_voxels": dense["voxels"],
        "dense_bytes": dense["bytes"],
        "ratio": (dense["bytes"] / live_bytes) if live_bytes else float("inf"),
        "footprint_m": dense["footprint_m"],
        "vertical_m": dense["vertical_m"],
        "res_m": dense["res_m"],
    }


def _fmt_bytes(b: float) -> str:
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if b >= scale:
            return f"{b / scale:.2f} {unit}"
    return f"{b:.0f} B"


def memory_overlay_markdown(n_occupied: int, schedule) -> str:
    """The per-frame live memory overlay (a Rerun TextDocument).

    Shows the real occupied-cell storage now, the derived dense-3D baseline for
    the same covered volume, and the live ratio -- all recomputed each frame
    from `n_occupied`."""
    s = grid_memory_stats(n_occupied, schedule)
    return "\n".join([
        "**Live map memory**",
        "",
        "| | value |",
        "|---|---|",
        f"| occupied cells | {s['n_occupied']:,} |",
        f"| cell size | {s['cell_bytes']} B (`CELL_BYTES`) |",
        f"| **map in use now** | **{_fmt_bytes(s['live_bytes'])}** |",
        (
            f"| dense-3D baseline | {_fmt_bytes(s['dense_bytes'])} "
            f"({s['dense_voxels'] / 1e9:.2f} G voxels @ {DENSE_VOXEL_BYTES} B) |"
        ),
        f"| **live ratio** | **{s['ratio']:,.0f}x smaller** |",
        "",
        (
            f"dense volume: {s['footprint_m']:g} x {s['footprint_m']:g} x "
            f"{s['vertical_m']:g} m at {s['res_m'] * 100:g} cm uniform "
            f"= ({s['footprint_m']:g}/{s['res_m']:g})^2 x ({s['vertical_m']:g}/{s['res_m']:g}) voxels"
        ),
        "",
        (
            "_live ratio counts only occupied cells; the fixed preallocation is "
            f"{schedule.total_cells * CELL_BYTES / 1e6:.2f} MB "
            f"({s['dense_bytes'] / (schedule.total_cells * CELL_BYTES):,.0f}x -- the report figure)._"
        ),
    ])


def status_markdown(frame_index: int, n_occupied: int, schedule, *, ghost_removal: bool,
                    counters=None, totals: dict | None = None, frame_ms: float | None = None,
                    ground_method: str | None = None, has_map: bool = True) -> str:
    """The "Live" side panel: what a judge should be able to read off the screen
    at any frame. Logged every frame, so it is never blank between map redraws.

    The memory rows are the report's figures, derived here rather than typed:
    live storage (`n_occupied * CELL_BYTES`), the fixed allocation it can never
    exceed, and that allocation against the uniform-2.5D and dense-3D baselines
    -- the same two ratios `scripts/memory_table.py` prints. `counters` is a
    `StepCounters`; `totals` sums them over the run.
    """
    base_cm = f"{schedule.base_cell_m * 100:g} cm"
    rows = [f"**Frame {frame_index:,}**", "", "| | |", "|---|---|"]
    if has_map:
        alloc = schedule.total_cells * CELL_BYTES
        uniform = uniform_2_5d_baseline(schedule)["bytes"]
        dense = dense_3d_baseline(schedule)["bytes"]
        rows += [
            (f"| **Map memory now** | **{_fmt_bytes(int(n_occupied) * CELL_BYTES)}** · "
             f"{int(n_occupied):,} occupied cells |"),
            (f"| Fixed allocation | {_fmt_bytes(alloc)} · {schedule.total_cells:,} cells, "
             "never grows |"),
            (f"| vs uniform {base_cm} 2.5D | {_fmt_bytes(uniform)} · "
             f"**{uniform / alloc:.1f}× smaller** |"),
            f"| vs dense {base_cm} 3D | {_fmt_bytes(dense)} · **{dense / alloc:,.0f}× smaller** |",
        ]
        if not ghost_removal:
            rows.append("| Ghost removal | **OFF** · trails stay in the map |")
        elif counters is not None:
            rows.append(f"| Ghost removal | ON · {counters.cleared:,} cleared, "
                        f"{counters.protected:,} spared this frame |")
        else:
            rows.append("| Ghost removal | ON |")
        if ghost_removal and totals is not None:
            flag = "" if totals["truncated"] == 0 else " ⚑ cap hit"
            rows.append(f"| Run totals | {totals['cleared']:,} cleared · "
                        f"{totals['protected']:,} spared · {totals['truncated']:,} truncated{flag} |")
    else:
        rows.append("| Map | back end off (`--no-map`) |")
    if frame_ms:
        budget = frame_budget_ms()
        verdict = "within" if frame_ms <= budget else "over"
        rows.append(f"| Frame time | {frame_ms:.0f} ms · {1e3 / frame_ms:.1f} fps · "
                    f"{verdict} the {budget:.0f} ms budget |")
    if ground_method:
        ground = "Patchwork++" if ground_method == "patchworkpp" else "⚑ semantic-class fallback"
        rows.append(f"| Ground | {ground} |")
    return "\n".join(rows)


def map_legend_markdown(schedule, *, color_by: str, blind_cone_m: float,
                        palette_legend: str | None = None, features: bool = False,
                        feature_interval: int = 20) -> str:
    """The "Legend" side panel: the colour key and each ring's cell size, read
    from the schedule. Logged once, static. Replaces the long instructions
    document, which read as developer notes on a demo screen."""
    rows = [
        # Rings first, as one line: they are the foveation claim, and at demo
        # resolution the panel shows about eight lines before it has to scroll.
        "**Rings** (squares) · " + " · ".join(
            f"{r.cell_m * 100:g} cm to {r.half_width_m:g} m" for r in schedule.rings),
        "",
        "| colour | means |",
        "|---|---|",
        "| blue → orange | occupied, by height |",
        "| slate | free · seen and clear |",
        "| violet | unknown · never free |",
        f"| red circle | blind cone {blind_cone_m:.2f} m |",
        "| red dots | moving (ghosts) |",
        "",
        "**Map** · one point per cell, sized to its ring",
    ]
    rows += ["", f"**Point cloud** · coloured by `{color_by}`"]
    if palette_legend:
        rows += ["", palette_legend]
    if features:
        rows += [
            "",
            f"**Features** · §7.4 / §7.5, refreshed every {feature_interval} frames",
            "",
            "| colour | meaning |",
            "|---|---|",
            "| orange boxes | curbs, standing at their measured height |",
            "| vermillion boxes | potholes, sunk to their measured depth |",
            "| dark → light points | drivability confidence, none → full |",
            "",
            ("⚑ Ring 3 confidence reads 0 on the live path: beyond ~50 m SemanticKITTI is "
             "unlabelled, and `run/engine.py` stores unlabelled as class 0 (`car`). Dark there "
             "means unlabelled, not hazardous."),
        ]
    return "\n".join(rows)
