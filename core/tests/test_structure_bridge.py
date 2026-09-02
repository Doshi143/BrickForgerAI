import pytest

from brickforge import Model, PartCatalog
from brickforge.pipeline.grid import VoxelGrid
from brickforge.structure import analyze, bridge_unstable

RED = 4


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def _place_ground_anchor(model: Model) -> None:
    """A grounded structure at a column far from any test's real island,
    deliberately made of 12 vertically-stacked (genuinely connected)
    plates rather than a single brick.

    Real bug this replaces, not a test quirk: find_bricks_outside_main_component
    used to treat EVERY y=0 brick as automatically part of "main" via a
    shared GROUND node, so a single unrelated grounded brick was always
    safely ignored regardless of size. That was the actual reported bug
    (see structure/weakpoints.py's own docstring) -- GROUND no longer
    joins separate regions together, which means an "anchor" this small
    would just be its own 1-node component, and once the real island
    under test gets bridged (growing to more than 1 node), the anchor
    would become the SMALLER of the two and get pruned by mistake
    instead of the island being tested. 12 nodes safely exceeds the
    largest bridged-island size any test in this file produces (9, in
    test_thin_island_gets_a_second_independent_pillar_when_a_second_column_exists),
    so this anchor always wins the "largest component" comparison
    honestly, the same way a real sculpture's own main body would."""
    for y in range(12):
        model.place("3024", RED, 0, y, 0)


def test_bridge_connects_a_one_layer_gap_to_ground_without_solid_grid(catalog):
    model = Model(catalog=catalog)
    _place_ground_anchor(model)
    model.place("3005", RED, 5, 1, 5)  # floating, 1 empty layer above bare ground
    result = bridge_unstable(model)  # no solid_grid -> interior check is a no-op

    assert len(result.removed) == 0
    assert len(result.added) == 1
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_one_pillar_grounds_an_entire_multi_brick_island(catalog):
    model = Model(catalog=catalog)
    _place_ground_anchor(model)
    model.place("3005", RED, 5, 4, 5)  # floating
    model.place("3005", RED, 5, 7, 5)  # rests on the floating brick -- same island
    result = bridge_unstable(model)

    assert len(result.removed) == 0
    assert len(result.added) == 4  # one pillar, y=3 down to y=0 at (5, *, 5)
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()
    assert len(result.model) == len(model) + 4


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
    _place_ground_anchor(model)
    model.place("3005", RED, 5, 4, 5)
    solid_grid = _solid_column(10, 12, 10, {(0, 0)})  # only the anchor's column is "solid"

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
    _place_ground_anchor(model)
    model.place("3005", RED, 5, 4, 5)
    solid_grid = _solid_column(10, 12, 10, {(0, 0), (5, 5)})

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
    _place_ground_anchor(model)
    model.place("3023", RED, 5, 4, 5, rotation=Rotation.YAW_90)  # island: footprint (1,2) -> z:5-6

    solid_grid = _solid_column(10, 12, 10, {(0, 0), (5, 6)})  # only z=6's column is solid

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
    _place_ground_anchor(model)
    model.place("3023", RED, 5, 4, 5, rotation=Rotation.YAW_90)  # island: footprint (1,2) -> z:5-6

    solid_grid = _solid_column(10, 12, 10, {(0, 0), (5, 5), (5, 6)})

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


def test_upward_reconnection_is_preferred_when_shorter_than_downward(catalog):
    # A tower + a shelf plate grounds column (2, *, 0) at y=12 (the
    # shelf's own bottom). A foot island sits at y=8-10 in that same
    # column, one empty cell short of the shelf above it (y=11) --
    # but there is nothing at all below it until bare ground at y=0,
    # 8 empty cells away. Only column (2, 0) is marked solid, so no 2x2
    # wide candidate exists anywhere (this isolates the comparison to the
    # thin tier specifically -- a wide candidate always wins over a thin
    # one regardless of length, which would otherwise mask this test).
    # The real-world case this mirrors: a foot a single cell short of the
    # leg it belongs to, where a downward-only search would either travel
    # a much longer, more visible route to the ground or find nothing at
    # all under a stricter solid_grid.
    from brickforge import Rotation

    model = Model(catalog=catalog)
    for y in (0, 3, 6, 9):
        model.place("3005", RED, 0, y, 0)  # tower, grounded, reaches top_y=12
    model.place("3623", RED, 0, 12, 0, rotation=Rotation.YAW_0)  # shelf, footprint (3,1): x=0,1,2 at z=0
    model.place("3005", RED, 2, 8, 0)  # foot island: y=8-10, top_y=11 -- 1 cell short of the shelf

    solid_grid = _solid_column(10, 20, 10, {(2, 0)})

    result = bridge_unstable(model, solid_grid=solid_grid)

    assert len(result.removed) == 0
    assert len(result.added) == 1  # the short upward fix, not a long downward one
    fix = result.added[0]
    assert (fix.pos.x, fix.pos.y, fix.pos.z) == (2, 11, 0)
    report = analyze(result.model)
    # Not report.ungrounded_bricks: the foot is now held up by the shelf
    # ABOVE it, not resting on anything below -- exactly the keystone
    # shape that check can't see by design (see weakpoints.py's own
    # docstring), same reason it's informational-only and not what
    # drives repair. critical_bricks/is_single_piece (undirected) is the
    # real, correct measure, same as everywhere else in this project.
    assert report.critical_bricks == set()
    assert report.is_single_piece


def test_single_column_island_still_gets_only_one_pillar(catalog):
    # The mitigation must not fire when there's genuinely nowhere else to
    # attach -- a lone 1x1 island only ever has one column, so it should
    # come back byte-for-byte the same as before this change
    # (test_bridge_connects_a_one_layer_gap_to_ground_without_solid_grid,
    # repeated here specifically to pin that the new second-pillar search
    # doesn't add anything when it has nothing else to find).
    model = Model(catalog=catalog)
    _place_ground_anchor(model)
    model.place("3005", RED, 5, 1, 5)
    result = bridge_unstable(model)

    assert len(result.removed) == 0
    assert len(result.added) == 1
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def _elbow_grid(nx, ny, nz) -> VoxelGrid:
    grid = VoxelGrid.empty(nx, ny, nz)
    grid.occupied[0, :, 0] = True  # ground anchor's own column
    return grid


def test_elbow_reaches_a_neighboring_column_when_its_own_column_is_blocked(catalog):
    # The island's own column, (5, *, 5), is interior ONLY at y=3 (the
    # elbow's own layer, one below the island brick at y=4) -- y=2 and
    # below are exterior, so a straight pillar down this column is
    # impossible regardless of length. The neighbor column, (6, *, 5), is
    # interior all the way from y=3 down to y=0. Neither a straight pillar
    # (blocked at y=2) nor a 2x2 wide pillar (the other 3 cells of any
    # offset are never marked interior at all) can reach ground here --
    # only the elbow, hinging from (5,3,5) to (6,3,5) and continuing
    # straight down from there, can.
    model = Model(catalog=catalog)
    _place_ground_anchor(model)
    model.place("3024", RED, 5, 4, 5)  # island: single 1x1 plate, one column

    grid = _elbow_grid(10, 12, 10)
    grid.occupied[5, 3, 5] = True  # island's own column, elbow layer only
    grid.occupied[6, 0:4, 5] = True  # neighbor column, elbow layer down to ground

    result = bridge_unstable(model, solid_grid=grid)

    assert len(result.removed) == 0
    assert len(result.added) == 4  # 1 elbow plate (2 cells) + 3 straight plates (y=2,1,0)
    elbow_bricks = [b for b in result.added if b.part.id == "3023"]
    assert len(elbow_bricks) == 1
    elbow = elbow_bricks[0]
    assert (elbow.pos.x, elbow.pos.y, elbow.pos.z) == (5, 3, 5)
    assert set(elbow.occupied_cells()) == {(5, 3, 5), (6, 3, 5)}
    continuation = [b for b in result.added if b.part.id != "3023"]
    assert sorted((b.pos.x, b.pos.y, b.pos.z) for b in continuation) == [(6, 0, 5), (6, 1, 5), (6, 2, 5)]

    report = analyze(result.model)
    # Not is_single_piece: the bridged group reaches ground on its own, at
    # a different column from the ground anchor -- two independently-
    # grounded pieces that never touch each other, correctly reported as
    # two pieces (find_disconnected_components) even though neither is at
    # risk of falling (find_bricks_outside_main_component's own second
    # refinement -- see weakpoints.py's own docstring), same reasoning
    # every other test in this file that bridges to a fresh column relies
    # on already.
    assert report.ungrounded_bricks == set()


def test_elbow_is_not_tried_when_a_straight_pillar_already_works(catalog):
    # Same neighbor-column setup as the test above, but this time the
    # island's OWN column also has a clean interior path to ground -- the
    # straight pillar must win, and no "3023" elbow plate should appear at
    # all, matching this module's own preference for the cheaper, simpler
    # connector whenever it's available.
    model = Model(catalog=catalog)
    _place_ground_anchor(model)
    model.place("3024", RED, 5, 4, 5)

    grid = _elbow_grid(10, 12, 10)
    grid.occupied[5, 0:4, 5] = True  # island's own column, fully solid down to ground
    grid.occupied[6, 0:4, 5] = True  # neighbor column, also solid (must not be preferred)

    result = bridge_unstable(model, solid_grid=grid)

    assert len(result.removed) == 0
    assert all(b.part.id != "3023" for b in result.added)
    assert len(result.added) == 4  # straight pillar y=3,2,1,0 at (5, *, 5)
    for b in result.added:
        assert (b.pos.x, b.pos.z) == (5, 5)
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_elbow_and_straight_column_are_both_blocked_still_prunes(catalog):
    # No solid_grid at all this island's column or any neighbor -- neither
    # a straight pillar nor an elbow has anywhere interior to go, so this
    # must fall back to pruning exactly as it did before elbows existed.
    model = Model(catalog=catalog)
    _place_ground_anchor(model)
    model.place("3024", RED, 5, 4, 5)

    grid = _elbow_grid(10, 12, 10)  # only the ground anchor's own column is solid

    result = bridge_unstable(model, solid_grid=grid)

    assert result.added == []
    assert len(result.removed) == 1
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()
