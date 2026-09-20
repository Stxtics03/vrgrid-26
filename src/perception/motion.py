"""Per-point motion from two scans, instead of from the label file. [Shrestha]

`semantics.is_moving()` reads SemanticKITTI's `moving-*` ids, which is ground
truth. FRNet predicts a CLASS -- car, person, cyclist -- and says nothing about
whether the thing is moving right now, so a pipeline running `--semantics frnet`
still had its motion flag handed to it. This estimates it.

The rule is a FREE-SPACE VIOLATION, the same idea as the §10.4 visibility
cleanup and deliberately so: the previous scan is re-projected into the current
sensor pose, and a current return that arrives **closer** than the surface the
previous scan saw at that bearing is a return from something that was not there
before. Static geometry re-projects onto itself and cancels.

⚑ ONE DIRECTION ONLY, AND THAT IS THE POINT. An object moving AWAY also
  disturbs its bearing, but what is revealed behind it is static background --
  flagging those returns would label a wall as moving. Only the near side is
  attributable to the points actually in front of us, so only the near side is
  flagged. The cost is recall on receding objects and the benefit is that
  precision means something.

⚑ It cannot see an object that is moving but never occupied free space -- a car
  driving in the lane ahead at the same speed, holding its range. No two-frame
  geometric method can; that needs tracking over a window. Do not describe this
  as motion DETECTION, describe it as what it is: free-space violation against
  the previous scan.

Scored by `scripts/motion_eval.py` against the `moving-*` ids.
"""
from __future__ import annotations

import numpy as np

#: Floor on the range agreement band, metres. Covers pose and registration
#: error, which -- unlike sensor noise -- does not widen with distance. Same
#: role and default as `gpu.visibility.clear_tolerance_m`'s floor.
POSE_FLOOR_M = 0.30


def _tolerance_m(range_m: np.ndarray, floor_m: float = POSE_FLOOR_M) -> np.ndarray:
    """3σ of the range model, floored. Mirrors `visibility.clear_tolerance_m`."""
    from vrgrid.gpu.visibility import clear_tolerance_m

    return clear_tolerance_m(range_m, floor_m=floor_m)


def estimate_moving(points_sensor: np.ndarray,
                    prev_points_world: np.ndarray | None,
                    sensor_to_world: np.ndarray,
                    sensor_cfg: dict | None = None,
                    floor_m: float = POSE_FLOOR_M,
                    ground_mask: np.ndarray | None = None) -> np.ndarray:
    """(N,) bool: this return arrived in space the previous scan saw as empty.

    Args:
        points_sensor: (N, 4) current scan, sensor frame.
        prev_points_world: (M, 3) previous scan in WORLD coordinates, or None
            for the first frame of a sequence.
        sensor_to_world: (4, 4) for the CURRENT frame. Inverted here to bring
            the previous cloud into the current sensor frame, which is what
            makes the comparison ego-motion free.
        sensor_cfg: sensor block; loaded from configs/frnet.yaml if None.
        ground_mask: (N,) bool from `ground.segment_ground_or_fallback`. Ground
            returns are never flagged. This is not a convenience -- the ground
            plane is seen at grazing incidence, where a bearing difference of
            one bin is metres of range, so it manufactures free-space
            violations wherever the ego moves. Measured on seq 08: without the
            mask precision is 11.6%, and the road is most of the error.

    Returns all-False on the first frame, which is honest rather than
    convenient: with one scan there is no evidence of motion either way.
    """
    from vrgrid.perception import range_image as ri

    n = len(points_sensor)
    if prev_points_world is None or len(prev_points_world) == 0:
        return np.zeros(n, np.bool_)

    if sensor_cfg is None:
        sensor_cfg = ri.load_sensor_config()

    # Previous cloud -> current sensor frame. Static geometry lands on itself.
    w_to_s = np.linalg.inv(np.asarray(sensor_to_world, np.float64))
    prev = np.asarray(prev_points_world, np.float64)
    prev_s = (prev @ w_to_s[:3, :3].T) + w_to_s[:3, 3]

    # Its range image: per bearing, how far away the world was last frame.
    prev4 = np.empty((len(prev_s), 4), np.float32)
    prev4[:, :3] = prev_s
    prev4[:, 3] = 1.0
    prev_img, _ = ri.project(prev4)
    prev_range = np.asarray(prev_img)[:, :, 0]          # (H, W), NaN where unseen

    v, u, finite = ri.point_bins(points_sensor, sensor_cfg)
    r_now = np.linalg.norm(np.asarray(points_sensor)[:, :3], axis=1)
    r_prev = prev_range[v, u]

    # NaN r_prev = that bearing was never observed last frame (newly in view,
    # or shadowed). No evidence, so no claim: comparison is False there.
    with np.errstate(invalid="ignore"):
        closer_by = r_prev - r_now
        moving = finite & np.isfinite(r_prev) & (closer_by > _tolerance_m(r_now, floor_m))
    if ground_mask is not None:
        moving &= ~np.asarray(ground_mask, np.bool_)
    return np.asarray(moving, np.bool_)
