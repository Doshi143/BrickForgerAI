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


def test_seam_penalty_still_prefers_a_different_shape_of_equal_area(plate_candidates):
    # SEAM_CANDIDATE_PENALTY_WEIGHT was lowered from 0.9 to 0.25 at the
    # user's explicit request, to trade seam-violation resistance for far
    # more Stage B brick consolidation (measured, real result: e.g. the
    # mushroom example model went from 88 to 608 bricks and 4219 to 2673
    # total parts -- see CLAUDE.md).
    #
    # What's still true, and load-bearing, at ANY nonzero weight: given two
    # candidates of the SAME area but DIFFERENT shape, only one of which
    # exactly reproduces the tile below, the non-duplicate must still win
    # outright, since its score isn't discounted at all. The mask below is
    # an L-shape (NOT a plain rectangle) specifically so that no larger,
    # higher-area candidate (e.g. an 8-area 2x4) can fit at all -- the only
    # two area-4 rectangles that fit the occupied cells are a 4-wide x
    # 1-deep plate (3710) and a 2x2 plate (3022); a below-layer 2x2 at
    # (0,0) exactly matches (and thus penalizes) only the 2x2 option, so
    # the 4x1 must win regardless of the exact weight value (any weight in
    # (0, 1] makes the 2x2's discounted score strictly less than the 4x1's
    # undiscounted one).
    mask = np.zeros((4, 2), dtype=bool)
    mask[:, 0] = True  # z=0 row: all 4 cells
    mask[0:2, 1] = True  # z=1 row: only x=0,1 -- makes this an L, not a rectangle
    below_id_grid, below_bounds = _build_below_grid(4, 2, [(0, 0, 2, 2)])
    raster_order = [(x, z) for z in range(2) for x in range(4)]

    placements = _tile_layer_region(mask, plate_candidates, below_id_grid, below_bounds, raster_order)

    first_part, first_rot = placements[0][2], placements[0][3]
    assert first_part.footprint_at(first_rot) == (4, 1), (
        "the equal-area, non-duplicate 4x1 should still beat the "
        "seam-penalized 2x2, regardless of the exact weight value"
    )


def test_no_seam_penalty_without_a_below_layer(plate_candidates):
    # Same strip, no layer below at all (below_id_grid=None) -- should
    # still prefer the single largest plate, exactly like the old v1
    # behavior with no seam awareness in play.
    mask = np.ones((8, 1), dtype=bool)
    raster_order = [(x, 0) for x in range(8)]

    placements = _tile_layer_region(mask, plate_candidates, None, {}, raster_order)

    assert len(placements) == 1
    assert placements[0][2].footprint == (8, 1)


def test_end_to_end_legalize_now_allows_a_repeated_full_width_run(catalog):
    # This is the poster-child case for the SEAM_CANDIDATE_PENALTY_WEIGHT
    # reduction (0.9 -> 0.25): a full 8-wide, 1-deep, 3-plate-tall, single-
    # color column is fully occupied on every layer, so an 8-wide plate is
    # the only largest-area option and, at this weight, is never penalized
    # into losing to a smaller split (0.25x its own area is still cheaper
    # than any alternative), meaning all 3 layers get tiled identically.
    # That's exactly Stage B's brick-consolidation trigger.
    #
    # A consolidated brick is a SINGLE placed object whose .pos.y is the
    # brick's base layer (0 here) -- it does not also appear as a separate
    # entry at y=1 or y=2, since those plates were consumed, not placed.
    # (An earlier version of this test grouped placements by .pos.y and
    # asserted all 3 groups were equal, which is wrong once consolidation
    # happens: groups 1 and 2 are correctly EMPTY after their plates are
    # folded into the single brick recorded at y=0 -- that emptiness is the
    # evidence consolidation worked, not a bug.)
    grid = VoxelGrid.empty(8, 3, 1)
    grid.occupied[:, :, :] = True
    color_codes = np.full((8, 3, 1), RED, dtype=np.int32)

    model = legalize(grid, color_codes, catalog)

    assert len(model) == 1, "3 identical full-width plate layers should consolidate into a single brick"
    brick = model.bricks[0]
    assert brick.part.category == "brick"
    assert brick.pos.y == 0


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
