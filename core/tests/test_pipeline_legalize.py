import numpy as np
import pytest

from brickforge import PartCatalog
from brickforge.pipeline.grid import VoxelGrid
from brickforge.pipeline.legalize import legalize

RED = 4


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def _grid_and_colors(nx, ny, nz, color=RED):
    grid = VoxelGrid.empty(nx, ny, nz)
    grid.occupied[:, :, :] = True
    codes = np.full((nx, ny, nz), color, dtype=np.int32)
    return grid, codes


def test_single_layer_prefers_largest_fitting_plate(catalog):
    # a fully-occupied 4x2 (x,z) single-color single layer should tile as
    # ONE 2x4 plate (part 3020, footprint (4,2)), not eight separate 1x1s.
    grid, codes = _grid_and_colors(4, 1, 2)
    model = legalize(grid, codes, catalog)
    assert len(model) == 1
    brick = model.bricks[0]
    assert brick.part.id == "3020"
    assert brick.color == RED


def test_three_identical_stacked_layers_consolidate_to_a_brick(catalog):
    grid, codes = _grid_and_colors(1, 3, 1)
    model = legalize(grid, codes, catalog)
    assert len(model) == 1
    brick = model.bricks[0]
    assert brick.part.id == "3005"  # Brick 1x1, not three 3024 plates
    assert brick.part.category == "brick"
    assert brick.pos.y == 0


def test_four_identical_stacked_layers_yield_one_brick_and_one_plate(catalog):
    grid, codes = _grid_and_colors(1, 4, 1)
    model = legalize(grid, codes, catalog)
    assert len(model) == 2
    parts = sorted(b.part.id for b in model.bricks)
    assert parts == ["3005", "3024"]  # one consolidated brick + one leftover plate


def test_different_colors_are_not_merged_across_a_layer(catalog):
    grid = VoxelGrid.empty(2, 1, 1)
    grid.occupied[:, :, :] = True
    codes = np.array([[[RED]], [[15]]])  # x=0 red, x=1 white
    model = legalize(grid, codes, catalog)
    assert len(model) == 2
    colors = sorted(b.color for b in model.bricks)
    assert colors == [4, 15]


def test_output_model_has_no_internal_collisions(catalog):
    # legalize() calls Model.place() for every tile, which itself raises on
    # overlap -- a nontrivial multi-layer, multi-color grid running to
    # completion without PlacementError is itself a real assertion.
    grid, codes = _grid_and_colors(6, 4, 5, color=RED)
    codes[3:, :, :] = 15  # split into two colored halves
    model = legalize(grid, codes, catalog)
    assert len(model) > 0
