"""Color quantization (DESIGN.md pipeline step 7).

Two real fixes over the original v1 simplification, both measured, not
assumed:

1. **CATALOG_RGB is now real, verified LDraw color data, not approximate
   guesses.** The original 14-entry palette was, by its own prior
   docstring's admission, "commonly-published approximate sRGB values...
   NOT individually verified against an authoritative source." Fetched
   `library.ldraw.org`'s actual `LDConfig.ldr` (the file LDraw/BrickLink
   tools themselves use) and pulled real hex values for a curated ~40-color
   subset of commonly-available, non-vintage LEGO colors (excludes
   Fabuland/rare/discontinued entries also present in that file) --
   verified the same way this catalog verifies part geometry: from the
   authoritative source file, not a paraphrase of it.

2. **Distance metric is CIELAB, not raw sRGB Euclidean** -- matches
   DESIGN.md sec. 3's stated intent, not left as the "left for a follow-up"
   v1 shortcut. Raw sRGB distance is perceptually uneven (an equally
   visible shift in blue scores very differently than the same shift in
   green); CIELAB is designed so Euclidean distance in that space tracks
   *perceived* color difference much more closely, which is what actually
   matters for "does this quantize to the LDraw color a human would pick."
   The sRGB->CIELAB conversion below is the standard formula (D65
   whitepoint), implemented directly rather than pulling in a new
   dependency for it.
"""

from __future__ import annotations

import numpy as np

# Real hex values from LDraw.org's own LDConfig.ldr (the "LDraw Solid
# Colours" section), not approximations. A curated subset of that file's 102
# solid colors: commonly-available, current LEGO colors, excluding vintage/
# Fabuland/rare entries that exist in LDConfig but aren't realistically
# purchasable today (matches this project's existing "don't invent/include
# what isn't real and buyable" discipline, same reasoning as the missing
# 2x8 tile / missing 1-plate slope).
CATALOG_RGB: dict[int, tuple[int, int, int]] = {
    0: (27, 42, 52),  # Black
    1: (30, 90, 168),  # Blue
    2: (0, 133, 43),  # Green
    4: (180, 0, 0),  # Red
    6: (84, 51, 36),  # Brown
    7: (138, 146, 141),  # Light_Grey
    8: (84, 89, 85),  # Dark_Grey
    9: (151, 203, 217),  # Light_Blue
    10: (88, 171, 65),  # Bright_Green
    12: (240, 109, 97),  # Salmon
    13: (246, 169, 187),  # Pink
    14: (250, 200, 10),  # Yellow
    15: (244, 244, 244),  # White
    19: (215, 186, 140),  # Tan
    22: (103, 31, 129),  # Purple
    25: (214, 121, 35),  # Orange
    27: (165, 202, 24),  # Lime
    28: (137, 125, 98),  # Dark_Tan
    30: (160, 110, 185),  # Medium_Lavender
    31: (205, 164, 222),  # Lavender
    70: (95, 49, 9),  # Reddish_Brown
    71: (150, 150, 150),  # Light_Bluish_Grey
    72: (100, 100, 100),  # Dark_Bluish_Grey
    73: (115, 150, 200),  # Medium_Blue
    74: (127, 196, 117),  # Medium_Green
    78: (255, 201, 149),  # Light_Nougat
    84: (170, 125, 85),  # Medium_Nougat
    92: (187, 128, 90),  # Nougat
    110: (38, 70, 154),  # Violet
    191: (252, 172, 0),  # Bright_Light_Orange
    212: (157, 195, 247),  # Bright_Light_Blue
    226: (255, 236, 108),  # Bright_Light_Yellow
    272: (25, 50, 90),  # Dark_Blue
    288: (0, 69, 26),  # Dark_Green
    308: (53, 33, 0),  # Dark_Brown
    320: (114, 0, 18),  # Dark_Red
    321: (70, 155, 195),  # Dark_Azure
    322: (104, 195, 226),  # Medium_Azure
    326: (226, 249, 154),  # Yellowish_Green
    330: (119, 119, 78),  # Olive_Green
    353: (255, 109, 119),  # Coral
    378: (112, 142, 124),  # Sand_Green
    379: (112, 129, 154),  # Sand_Blue
    484: (145, 80, 28),  # Dark_Orange
}


def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# sRGB (D65) -> CIE XYZ, standard matrix.
_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)
_D65_WHITE = np.array([0.95047, 1.0, 1.08883])
_LAB_DELTA = 6.0 / 29.0


def _xyz_to_lab(xyz: np.ndarray) -> np.ndarray:
    normalized = xyz / _D65_WHITE
    f = np.where(
        normalized > _LAB_DELTA**3,
        np.cbrt(normalized),
        normalized / (3 * _LAB_DELTA**2) + 4.0 / 29.0,
    )
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return np.stack([L, a, b], axis=-1)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Vectorized sRGB (0-255, any leading shape, last axis size 3) ->
    CIELAB (D65 whitepoint). Standard formula, not an approximation."""
    rgb = np.asarray(rgb, dtype=np.float64)
    linear = _srgb_to_linear(rgb)
    xyz = linear @ _RGB_TO_XYZ.T
    return _xyz_to_lab(xyz)


def quantize_color(rgb: tuple[int, int, int], palette: dict[int, tuple[int, int, int]] = CATALOG_RGB) -> int:
    """Return the LDraw color code in `palette` nearest to `rgb`, by
    Euclidean distance in CIELAB space (perceptual, not raw sRGB)."""
    codes = list(palette.keys())
    values_lab = rgb_to_lab(np.array([palette[c] for c in codes], dtype=np.float64))
    target_lab = rgb_to_lab(np.array(rgb, dtype=np.float64))
    dists = np.sum((values_lab - target_lab) ** 2, axis=1)
    return codes[int(np.argmin(dists))]


def quantize_grid_colors(occupied: np.ndarray, color: np.ndarray, palette: dict[int, tuple[int, int, int]] = CATALOG_RGB) -> np.ndarray:
    """Vectorized quantization of an entire VoxelGrid's color array.
    Returns an int array, same (nx, ny, nz) shape as `occupied`, holding the
    LDraw color code at each occupied cell and -1 elsewhere."""
    codes = list(palette.keys())
    values_lab = rgb_to_lab(np.array([palette[c] for c in codes], dtype=np.float64))  # (K, 3)

    flat_colors = color.reshape(-1, 3).astype(np.float64)
    flat_lab = rgb_to_lab(flat_colors)  # (N, 3)
    dists = np.sum((flat_lab[:, None, :] - values_lab[None, :, :]) ** 2, axis=2)  # (N, K)
    nearest = np.argmin(dists, axis=1)  # (N,)
    result_flat = np.array(codes, dtype=np.int32)[nearest]

    result = result_flat.reshape(occupied.shape)
    result[~occupied] = -1
    return result
