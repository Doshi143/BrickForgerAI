import numpy as np

from brickforge.pipeline.grid import VoxelGrid
from brickforge.pipeline.shell import shell_and_support


def _solid_grid(nx, ny, nz, color=(200, 0, 0)) -> VoxelGrid:
    grid = VoxelGrid.empty(nx, ny, nz)
    grid.occupied[:, :, :] = True
    grid.color[:, :, :] = color
    return grid


def test_shelling_hollows_a_large_solid_block():
    grid = _solid_grid(9, 9, 9)
    result = shell_and_support(grid, shell_thickness=2, support_pitch=100)  # support_pitch huge -> no support walls
    # center cell (far from any face) must now be empty
    assert not result.occupied[4, 4, 4]
    # a face-adjacent cell must remain solid
    assert result.occupied[0, 4, 4]
    # shelling must strictly reduce occupied count for a block this size
    assert result.count() < grid.count()


def test_shelling_preserves_a_small_block_entirely():
    # a block smaller than 2*shell_thickness in every axis has no interior
    # to hollow out -- erosion should remove everything, leaving the
    # original solid untouched by the union with (empty) support.
    grid = _solid_grid(3, 3, 3)
    result = shell_and_support(grid, shell_thickness=2, support_pitch=100)
    assert result.occupied.all()


def test_support_lattice_adds_interior_walls():
    grid = _solid_grid(11, 3, 11)
    no_support = shell_and_support(grid, shell_thickness=1, support_pitch=100)
    with_support = shell_and_support(grid, shell_thickness=1, support_pitch=3)
    # support walls should add cells beyond the bare shell
    assert with_support.count() > no_support.count()
    # a support wall cell (x % 3 == 0, strictly interior) must be present
    assert with_support.occupied[3, 1, 3]


def test_color_is_dropped_where_cells_are_removed():
    grid = _solid_grid(9, 9, 9, color=(10, 20, 30))
    result = shell_and_support(grid, shell_thickness=2, support_pitch=100)
    assert tuple(result.color[4, 4, 4]) == (0, 0, 0)
    assert tuple(result.color[0, 4, 4]) == (10, 20, 30)
