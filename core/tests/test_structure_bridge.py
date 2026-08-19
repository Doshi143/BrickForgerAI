import pytest

from brickforge import Model, PartCatalog
from brickforge.pipeline.grid import VoxelGrid
from brickforge.structure import analyze, bridge_unstable

RED = 4


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_bridge_connects_a_one_layer_gap_to_ground_without_solid_grid(catalog):
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)  # unrelated grounded brick
    model.place("3005", RED, 5, 1, 5)  # floating, 1 empty layer above bare ground
    result = bridge_unstable(model)  # no solid_grid -> interior check is a no-op

    assert len(result.removed) == 0
    assert len(result.added) == 1
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_one_pillar_grounds_an_entire_multi_brick_island(catalog):
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)
    model.place("3005", RED, 5, 4, 5)  # floating
    model.place("3005", RED, 5, 7, 5)  # rests on the floating brick -- same island
    result = bridge_unstable(model)

    assert len(result.removed) == 0
    assert len(result.added) == 4  # one pillar, y=3 down to y=0 at (5, *, 5)
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()
    assert len(result.model) == 7


def _solid_column(nx, ny, nz, solid_xz: set[tuple[int, int]]) -> VoxelGrid:
    grid = VoxelGrid.empty(nx, ny, nz)
    for x, z in solid_xz:
        grid.occupied[x, :, z] = True
    return grid


def test_pillar_through_open_air_is_rejected_when_solid_grid_says_exterior(catalog):
    # The island's only column (5, *, 5) is NOT part of the original solid
    # silhouette anywhere -- exactly the ear-tip case: a straight-down
    # pillar there would be a pole through open air, not a hidden brace.
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)
    model.place("3005", RED, 5, 4, 5)
    solid_grid = _solid_column(10, 10, 10, {(0, 0)})  # only the grounded brick's column is "solid"

    result = bridge_unstable(model, solid_grid=solid_grid)

    assert len(result.added) == 0  # no interior pillar exists -- must not add an external one
    assert len(result.removed) == 1  # the floating brick gets pruned instead
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_pillar_through_the_solid_silhouette_is_accepted(catalog):
    # Same setup, but now (5, *, 5) IS part of the original solid silhouette
    # all the way down -- a pillar there would be hidden inside the model,
    # not sticking out, so it should be used.
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)
    model.place("3005", RED, 5, 4, 5)
    solid_grid = _solid_column(10, 10, 10, {(0, 0), (5, 5)})

    result = bridge_unstable(model, solid_grid=solid_grid)

    assert len(result.removed) == 0
    assert len(result.added) == 4  # y=3,2,1,0 at (5, *, 5)
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_shortest_interior_column_is_preferred(catalog):
    # A 1x2 plate (rotated to footprint (1,2)) spans two columns, z=5 and
    # z=6. Only z=6's column is part of the solid silhouette (all the way
    # to the ground); z=5 is never solid anywhere, so a pillar there would
    # be a visible external pole and must be rejected regardless of length.
    from brickforge import Rotation

    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)  # unrelated grounded brick
    model.place("3023", RED, 5, 4, 5, rotation=Rotation.YAW_90)  # island: footprint (1,2) -> z:5-6

    solid_grid = _solid_column(10, 10, 10, {(0, 0), (5, 6)})  # only z=6's column is solid

    result = bridge_unstable(model, solid_grid=solid_grid)

    assert len(result.removed) == 0
    assert len(result.added) == 4  # fills y=3,2,1,0 at (5, *, 6) down to bare ground
    for brick in result.added:
        assert brick.pos.z == 6
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_bridge_is_a_no_op_on_a_sound_model(catalog):
    model = Model(catalog=catalog)
    model.place("3001", RED, 0, 0, 0)
    model.place("3001", RED, 0, 3, 0)
    result = bridge_unstable(model)
    assert result.added == []
    assert result.removed == []
    assert len(result.model) == len(model)


def test_thin_island_gets_a_second_independent_pillar_when_a_second_column_exists(catalog):
    # Same shape as test_shortest_interior_column_is_preferred (a 1x2 plate,
    # footprint spanning z=5 and z=6 at x=5), but this time BOTH columns are
    # part of the solid silhouette, not just one -- neither is wide enough
    # for a 2x2 anchor (the solid region is only 1 cell wide in x), so both
    # can only ever offer the thin single-stud pillar. A single connection
    # here would be exactly the "detached-looking despite analyze() calling
    # it sound" case measured on a real job (see bridge_unstable's own
    # docstring) -- with a second valid column available, this island
    # should get reinforced at both, not just the shorter/first one found.
    from brickforge import Rotation

    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)  # unrelated grounded brick
    model.place("3023", RED, 5, 4, 5, rotation=Rotation.YAW_90)  # island: footprint (1,2) -> z:5-6

    solid_grid = _solid_column(10, 10, 10, {(0, 0), (5, 5), (5, 6)})

    result = bridge_unstable(model, solid_grid=solid_grid)

    assert len(result.removed) == 0
    assert len(result.added) == 8  # two independent pillars, y=3..0, at z=5 AND z=6
    added_columns = {(b.pos.x, b.pos.z) for b in result.added}
    assert added_columns == {(5, 5), (5, 6)}
    for z in (5, 6):
        ys = sorted(b.pos.y for b in result.added if b.pos.z == z)
        assert ys == [0, 1, 2, 3]
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_single_column_island_still_gets_only_one_pillar(catalog):
    # The mitigation must not fire when there's genuinely nowhere else to
    # attach -- a lone 1x1 island only ever has one column, so it should
    # come back byte-for-byte the same as before this change
    # (test_bridge_connects_a_one_layer_gap_to_ground_without_solid_grid,
    # repeated here specifically to pin that the new second-pillar search
    # doesn't add anything when it has nothing else to find).
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)
    model.place("3005", RED, 5, 1, 5)
    result = bridge_unstable(model)

    assert len(result.removed) == 0
    assert len(result.added) == 1
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()
