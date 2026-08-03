"""Color quantization (DESIGN.md pipeline step 7).

v1 simplification: plain nearest-neighbor in sRGB space, not the
CIELAB-with-spatial-smoothing approach DESIGN.md sec. 3 calls for (which
also enlarges mergeable regions for the legalizer -- a real quality
improvement left for a follow-up, not implemented here).

CATALOG_RGB below are ordinary, commonly-published approximate sRGB values
for each LDraw color code -- unlike the part numbers in catalog/parts_v1.yaml,
these were NOT individually verified against an authoritative source (e.g.
LDConfig.ldr's own RGB fields, which do exist and would be the right thing
to parse for anything beyond a development-stage nearest-color heuristic).
Treat them as approximate.
"""

from __future__ import annotations

import numpy as np

CATALOG_RGB: dict[int, tuple[int, int, int]] = {
    0: (33, 33, 33),  # Black
    1: (0, 85, 191),  # Blue
    2: (0, 133, 43),  # Green
    4: (196, 40, 27),  # Red
    6: (95, 49, 9),  # Brown
    14: (245, 205, 47),  # Yellow
    15: (244, 244, 244),  # White
    19: (228, 205, 158),  # Tan
    25: (218, 133, 64),  # Orange
    27: (164, 189, 70),  # Lime
    70: (105, 64, 40),  # Reddish_Brown
    71: (155, 161, 157),  # Light_Bluish_Gray
    72: (99, 95, 97),  # Dark_Bluish_Gray
    288: (39, 70, 44),  # Dark_Green
}


def quantize_color(rgb: tuple[int, int, int], palette: dict[int, tuple[int, int, int]] = CATALOG_RGB) -> int:
    """Return the LDraw color code in `palette` nearest to `rgb` (squared
    Euclidean distance in sRGB space)."""
    codes = list(palette.keys())
    values = np.array([palette[c] for c in codes], dtype=np.float32)
    target = np.array(rgb, dtype=np.float32)
    dists = np.sum((values - target) ** 2, axis=1)
    return codes[int(np.argmin(dists))]


def quantize_grid_colors(occupied: np.ndarray, color: np.ndarray, palette: dict[int, tuple[int, int, int]] = CATALOG_RGB) -> np.ndarray:
    """Vectorized quantization of an entire VoxelGrid's color array.
    Returns an int array, same (nx, ny, nz) shape as `occupied`, holding the
    LDraw color code at each occupied cell and -1 elsewhere."""
    codes = list(palette.keys())
    values = np.array([palette[c] for c in codes], dtype=np.float32)  # (K, 3)

    flat_colors = color.reshape(-1, 3).astype(np.float32)  # (N, 3)
    dists = np.sum((flat_colors[:, None, :] - values[None, :, :]) ** 2, axis=2)  # (N, K)
    nearest = np.argmin(dists, axis=1)  # (N,)
    result_flat = np.array(codes, dtype=np.int32)[nearest]

    result = result_flat.reshape(occupied.shape)
    result[~occupied] = -1
    return result
