import numpy as np
import pytest

from brickforge import PartCatalog
from brickforge.pipeline.grid import VoxelGrid
from brickforge.pipeline.legalize import (
    _build_below_grid,
    _candidate_footprints,
    _tile_layer_region,
    legalize,
)

RED = 4


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


@pytest.fixture(scope="module")
def plate_candidates(catalog):
    return _candidate_footprints(catalog, "plate")


def test_seam_penalty_avoids_reproducing_exact_tile_below(plate_candidates):
    # An 8-wide, 1-deep fully-occupied strip, with a tile below it that
    # EXACTLY matches the naive greedy solution (one 8-wide plate at (0,0)).
    # Without the seam penalty, raster-order greedy would pick that same
    # 8-wide plate again -- a fully aligned vertical crack. With it, a
    # same-anchor 8-wide candidate scores worse than a 6-wide one, so a
    # different split should win.
    mask = np.ones((8, 1), dtype=bool)
    below_id_grid, below_bounds = _build_below_grid(8, 1, [(0, 0, 8, 1)])
    raster_order = [(x, 0) for x in range(8)]

    placements = _tile_layer_region(mask, plate_candidates, below_id_grid, below_bounds, raster_order)

    is_single_full_width_duplicate = len(placements) == 1 and placements[0][0] == 0 and placements[0][2].footprint == (8, 1)
    assert not is_single_full_width_duplicate


def test_no_seam_penalty_without_a_below_layer(plate_candidates):
    # Same strip, no layer below at all (below_id_grid=None) -- should
    # still prefer the single largest plate, exactly like the old v1
    # behavior with no seam awareness in play.
    mask = np.ones((8, 1), dtype=bool)
    raster_order = [(x, 0) for x in range(8)]

    placements = _tile_layer_region(mask, plate_candidates, None, {}, raster_order)

    assert len(placements) == 1
    assert placements[0][2].footprint == (8, 1)


def test_end_to_end_legalize_staggers_a_repeated_full_width_run(catalog):
    # Two stacked, fully-occupied, same-color 8x1 layers -- naive
    # per-layer-independent greedy would place an identical 8-wide plate on
    # both layers (see mesh_demo-style walls). After legalize(), the two
    # layers' tile sets must not be identical.
    grid = VoxelGrid.empty(8, 2, 1)
    grid.occupied[:, :, :] = True
    color_codes = np.full((8, 2, 1), RED, dtype=np.int32)

    model = legalize(grid, color_codes, catalog)

    layer0 = sorted((b.part.id, b.pos.x, b.pos.z, b.rotation) for b in model if b.pos.y == 0)
    layer1 = sorted((b.part.id, b.pos.x, b.pos.z, b.rotation) for b in model if b.pos.y == 1)
    assert layer0 != layer1


def test_restarts_never_score_worse_than_deterministic_baseline(catalog):
    # restarts=1 is exactly the deterministic raster-order pass (no
    # randomization attempted). restarts=5 must never produce MORE total
    # parts on a case where randomization can't help (a simple, already-
    # optimal single-layer rectangle) -- the deterministic option is always
    # included in the candidate pool, so it can only match or improve.
    grid = VoxelGrid.empty(4, 1, 2)
    grid.occupied[:, :, :] = True
    color_codes = np.full((4, 1, 2), RED, dtype=np.int32)

    deterministic = legalize(grid, color_codes, catalog, restarts=1)
    randomized = legalize(grid, color_codes, catalog, restarts=5)

    assert len(randomized) <= len(deterministic)


def test_legalize_is_reproducible_for_a_fixed_seed(catalog):
    grid = VoxelGrid.empty(6, 3, 6)
    grid.occupied[:, :, :] = True
    color_codes = np.full((6, 3, 6), RED, dtype=np.int32)

    model_a = legalize(grid, color_codes, catalog, seed=42)
    model_b = legalize(grid, color_codes, catalog, seed=42)

    a = sorted((b.part.id, b.pos.x, b.pos.y, b.pos.z, b.rotation, b.color) for b in model_a)
    b = sorted((b.part.id, b.pos.x, b.pos.y, b.pos.z, b.rotation, b.color) for b in model_b)
    assert a == b
