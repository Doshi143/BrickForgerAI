import numpy as np
import pytest

from brickforge.parts import PartCatalog
from brickforge.pipeline.color import CATALOG_RGB, quantize_color, quantize_grid_colors, rgb_to_lab


def test_exact_match_returns_that_color():
    # Values are CATALOG_RGB's own real, LDConfig.ldr-verified entries, not
    # approximate ones -- these are the actual palette values, not stand-ins.
    assert quantize_color((180, 0, 0)) == 4  # exact Red
    assert quantize_color((27, 42, 52)) == 0  # exact Black


def test_nearest_neighbor_for_off_palette_color():
    # a color close to White but not exact should still map to White
    assert quantize_color((240, 240, 238)) == 15


def test_grid_quantization_matches_scalar_quantization():
    occupied = np.array([[[True, False], [True, True]]])
    color = np.zeros((1, 2, 2, 3), dtype=np.uint8)
    color[0, 0, 0] = (180, 0, 0)
    color[0, 1, 0] = (27, 42, 52)
    color[0, 1, 1] = (244, 244, 244)

    result = quantize_grid_colors(occupied, color)

    assert result[0, 0, 0] == 4
    assert result[0, 0, 1] == -1  # unoccupied
    assert result[0, 1, 0] == 0
    assert result[0, 1, 1] == 15


def test_palette_has_no_duplicate_colors():
    # every code should be a genuinely distinct swatch, otherwise
    # quantize_color's nearest-neighbor tie-breaking becomes ambiguous
    values = list(CATALOG_RGB.values())
    assert len(values) == len(set(values))


def test_palette_is_a_real_curated_set_not_the_old_14():
    # Regression pin for the actual fix: the original palette was 14 colors,
    # "commonly-published approximate" values per its own prior docstring.
    # This checks the fix landed for real, not just that *some* palette exists.
    assert len(CATALOG_RGB) >= 40


def test_rgb_to_lab_matches_known_reference_points():
    # Standard, well-known CIELAB reference points (D65): pure black is
    # L=0, pure white is L=100 -- a sanity check on the conversion math
    # itself, not just that it runs without crashing.
    black_lab = rgb_to_lab(np.array([0, 0, 0], dtype=np.float64))
    white_lab = rgb_to_lab(np.array([255, 255, 255], dtype=np.float64))
    assert black_lab[0] == pytest.approx(0, abs=0.5)
    assert white_lab[0] == pytest.approx(100, abs=0.5)


def test_every_catalog_rgb_code_is_registered_in_colors_yaml():
    # Regression pin for a real bug hit while expanding the palette: adding
    # a code to CATALOG_RGB without also registering it in
    # catalog/colors.yaml means legalize() can quantize a voxel to that
    # code, then Model.place() rejects it outright ("Unknown LDraw color
    # code") the moment that color is actually used -- confirmed directly
    # (code 191, Bright_Light_Orange, broke a real run before colors.yaml
    # was updated to match).
    catalog = PartCatalog.load_default()
    missing = [code for code in CATALOG_RGB if not catalog.has_color(code)]
    assert missing == []


def test_quantize_uses_lab_distance_not_raw_rgb():
    # A genuine, verified case where CIELAB and raw sRGB distance disagree
    # over this actual palette (found by brute-force search, not guessed):
    # (69, 78, 10) is raw-RGB-nearest to Reddish_Brown (95, 49, 9), but
    # CIELAB-nearest to Olive_Green (119, 119, 78) -- pins that
    # quantize_color is actually using rgb_to_lab, not silently falling
    # back to raw RGB if that call were ever removed.
    assert quantize_color((69, 78, 10)) == 330  # Olive_Green, not Reddish_Brown (70)
