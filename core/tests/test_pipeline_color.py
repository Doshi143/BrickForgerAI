import numpy as np

from brickforge.pipeline.color import CATALOG_RGB, quantize_color, quantize_grid_colors


def test_exact_match_returns_that_color():
    assert quantize_color((196, 40, 27)) == 4  # exact Red
    assert quantize_color((33, 33, 33)) == 0  # exact Black


def test_nearest_neighbor_for_off_palette_color():
    # a color close to White but not exact should still map to White
    assert quantize_color((240, 240, 240)) == 15


def test_grid_quantization_matches_scalar_quantization():
    occupied = np.array([[[True, False], [True, True]]])
    color = np.zeros((1, 2, 2, 3), dtype=np.uint8)
    color[0, 0, 0] = (196, 40, 27)
    color[0, 1, 0] = (33, 33, 33)
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
