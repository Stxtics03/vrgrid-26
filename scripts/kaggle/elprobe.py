"""Which side moved? Elevation for frame 7's offending points, three ways.

Run on the laptop and on the Kaggle Xeon and diff. Nothing here touches the
GPU -- it isolates numpy's own float32 transcendentals, which are SIMD
dispatched and need not agree across CPU architectures.
"""
import platform

import numpy as np
from vrgrid.perception import loader

IDX = [56230, 58375, 58376, 89740, 89741]
PHI_MAX, D_PHI = None, None
from vrgrid.perception import range_image as RI

cfg = RI.load_sensor_config()
d_theta, d_phi = RI.bin_widths(cfg)
phi_max = np.deg2rad(cfg["phi_max_deg"])

pts = None
for i, (p, l, pose) in enumerate(loader.scans("08", max_frames=8)):
    if i == 7:
        pts = p
        break

print(f"host: {platform.processor() or platform.machine()} | numpy {np.__version__}")
print(f"simd: {getattr(np.core, '_multiarray_umath', None) and 'n/a'}")
print(f"{'idx':>7} {'el_f32(numpy)':>22} {'el_f64->f32':>22} {'v_f32':>6} {'v_dbl':>6}")
for k in IDX:
    xyz = pts[k, :3]
    r32 = np.linalg.norm(xyz)                      # float32, as project() does
    zr32 = np.float32(xyz[2]) / r32
    el32 = np.arcsin(np.clip(zr32, -1.0, 1.0))     # numpy float32 arcsin

    x, y, z = map(np.float64, xyz)
    r64 = np.sqrt(x*x + y*y + z*z)
    el_narrowed = np.float32(np.arcsin(np.clip(z / r64, -1.0, 1.0)))  # the kernel's way

    v_f32 = int(np.floor((phi_max - el32) / d_phi))
    v_dbl = int(np.floor((phi_max - np.float64(el_narrowed)) / d_phi))
    print(f"{k:>7} {el32.item():>22.17g} {el_narrowed.item():>22.17g} {v_f32:>6} {v_dbl:>6}"
          + ("   <-- el DIFFERS" if el32 != el_narrowed else ""))
