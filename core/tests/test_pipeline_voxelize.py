import numpy as np
import pytest
import trimesh

from brickforge.lattice import STUD_LDU
from brickforge.pipeline.voxelize import condition_mesh, voxelize_mesh


def test_condition_mesh_scales_to_target_width():
    mesh = trimesh.creation.box(extents=[10, 10, 10])
    conditioned = condition_mesh(mesh, target_width_studs=5)
    horizontal = max(conditioned.extents[0], conditioned.extents[2])
    assert horizontal == pytest.approx(5 * STUD_LDU)


def test_condition_mesh_sits_on_ground():
    mesh = trimesh.creation.box(extents=[10, 10, 10])
    mesh.apply_translation([0, 137, 0])  # arbitrary starting height
    conditioned = condition_mesh(mesh, target_width_studs=5)
    assert conditioned.bounds[0][1] == pytest.approx(0.0)


def test_voxelize_solid_box_is_fully_occupied():
    # a box exactly 2 studs x 1 plate x 2 studs (in warped-space units) after
    # conditioning should voxelize to a fully solid 2x1x2-ish grid -- no
    # holes, since a box is trivially watertight and convex.
    mesh = trimesh.creation.box(extents=[10, 10, 10])
    conditioned = condition_mesh(mesh, target_width_studs=8)
    grid = voxelize_mesh(conditioned)
    assert grid.occupied.all()
    # roughly cubic footprint: X and Z extents should match (box is a cube)
    nx, ny, nz = grid.shape
    assert nx == nz


def test_voxelize_samples_vertex_color():
    mesh = trimesh.creation.box(extents=[10, 10, 10])
    mesh.visual.vertex_colors = np.tile([10, 200, 50, 255], (len(mesh.vertices), 1))
    conditioned = condition_mesh(mesh, target_width_studs=8)
    grid = voxelize_mesh(conditioned)
    occupied_colors = grid.color[grid.occupied]
    # every occupied cell should have sampled close to the uniform mesh color
    assert np.all(np.abs(occupied_colors.astype(int) - np.array([10, 200, 50])) <= 2)
