import pytest

from brickforge import Model, PartCatalog, Rotation
from brickforge.pipeline.grid import VoxelGrid
from brickforge.structure import analyze, bridge_disconnected_pieces

RED = 4


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_two_adjacent_grounded_plates_get_welded_into_one_piece(catalog):
    # Two separate 1x1 plates, each independently touching y=0, sitting in
    # laterally adjacent columns -- both individually "grounded" (the old,
    # wrong notion), but never physically connected to each other. This is
    # the exact real-world case (an adjacent legalizer tiling seam) this
    # module exists to fix.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    model.place("3024", RED, 1, 0, 0)

    report_before = analyze(model)
    assert report_before.is_single_piece is False
    assert len(report_before.components) == 2

    result = bridge_disconnected_pieces(model)

    assert result.unresolved_pieces == []
    assert len(result.added) == 1
    assert result.added[0].part.id == "3023"  # 1x2 plate spanning both columns

    report_after = analyze(result.model)
    assert report_after.is_single_piece is True
    assert report_after.critical_bricks == set()


def test_a_gap_between_two_pieces_is_reported_unresolved_not_guessed_at(catalog):
    # Two grounded plates with an empty column between them -- not
    # laterally adjacent, so no single connector plate can span the gap.
    # Must be reported as unresolved, not silently ignored or wrongly
    # "fixed" by reaching past the gap.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    model.place("3024", RED, 2, 0, 0)  # column (1, 0) deliberately left empty

    result = bridge_disconnected_pieces(model)

    assert result.added == []
    assert len(result.unresolved_pieces) == 1

    report_after = analyze(result.model)
    assert report_after.is_single_piece is False


def test_mismatched_top_heights_cannot_be_bridged_by_a_flat_plate(catalog):
    # Adjacent columns, but one piece is 1 plate tall and the other is 3 --
    # a flat connector plate can't rest across a step, so this must stay
    # unresolved rather than placing a plate that would float in mid-air
    # over the shorter side or clip into the taller one.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)  # top = 1
    model.place("3005", RED, 1, 0, 0)  # 1x1 brick, top = 3

    result = bridge_disconnected_pieces(model)

    assert result.added == []
    assert len(result.unresolved_pieces) == 1


def test_a_chain_of_three_adjacent_pieces_fully_resolves_in_one_call(catalog):
    # A - B - C, where B is a single WIDER plate spanning two columns: one
    # adjacent to A, a DIFFERENT one adjacent to C. A connector always
    # sits one layer above whatever it spans, so bridging A onto B's
    # left column raises that specific column's height by one plate --
    # deliberately using a *different* column for B's connection to C
    # means that height bump doesn't get in the way of C's own bridge.
    # This is what the outer while-loop (not a single inner pass) is
    # for: welding A onto B updates `main` in time for C's own
    # neighbour check to succeed later in the same call.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)  # A
    model.place("3023", RED, 1, 0, 0)  # B: 1x2 plate spanning columns (1,0) and (2,0)
    model.place("3024", RED, 2, 0, 1)  # C, adjacent to B's OTHER column (2,0)

    report_before = analyze(model)
    assert len(report_before.components) == 3

    result = bridge_disconnected_pieces(model)

    assert result.unresolved_pieces == []
    assert len(result.added) == 2

    report_after = analyze(result.model)
    assert report_after.is_single_piece is True


def test_already_single_piece_model_is_left_untouched(catalog):
    model = Model(catalog=catalog)
    model.place("3023", RED, 0, 0, 0)  # one 1x2 plate -- already one piece by construction

    result = bridge_disconnected_pieces(model)

    assert result.added == []
    assert result.unresolved_pieces == []
    assert len(result.model) == len(model)


def test_overhang_with_its_own_grounded_leg_is_bridged_by_a_hidden_pillar(catalog):
    # The real-world case the lateral weld alone can't reach: main is a
    # trunk with a wide "roof" plate cantilevered out over column (1, 0);
    # stray is a short leg, independently grounded at that SAME column,
    # too short to touch the roof directly (a 2-plate vertical gap). No
    # single connector plate can span this -- it's not lateral adjacency
    # at all, it's a straight vertical reach, exactly the hidden-pillar
    # fallback this module gained to handle overhanging segments.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)  # trunk, column (0, 0)
    model.place("3024", RED, 0, 1, 0)  # trunk continues
    model.place("3024", RED, 0, 2, 0)  # trunk top = 3
    model.place("3023", RED, 0, 3, 0, rotation=Rotation.YAW_0)  # roof: spans (0,0)-(1,0) at y=3
    model.place("3024", RED, 1, 0, 0)  # stray: independently grounded leg, column (1, 0), top = 1

    report_before = analyze(model)
    assert report_before.is_single_piece is False
    assert len(report_before.components) == 2

    result = bridge_disconnected_pieces(model)

    assert result.unresolved_pieces == []
    assert len(result.added) >= 1
    # A lateral weld can't produce this: the leg's own column is entirely
    # shadowed by the taller roof in _column_tops, so a real vertical
    # pillar must have fired instead.
    assert all(b.part.id in ("3024", "3022") for b in result.added)

    report_after = analyze(result.model)
    assert report_after.is_single_piece is True
    assert report_after.critical_bricks == set()


def test_single_hop_elbow_bridges_a_leg_that_a_straight_pillar_cannot_reach(catalog):
    # Stray's own column (2, 0) never lines up with any of main's material
    # (columns 0 and 1 only) -- no straight pillar in stray's own column
    # can ever find main, so this only resolves via the elbow: one hop
    # sideways into column (1, 0) (empty there below the roof), then a
    # short straight run up to the roof's own extension cell.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)  # trunk
    model.place("3024", RED, 0, 1, 0)
    model.place("3024", RED, 0, 2, 0)  # trunk top = 3
    model.place("3023", RED, 0, 3, 0, rotation=Rotation.YAW_0)  # roof: spans (0,0)-(1,0) at y=3
    model.place("3024", RED, 2, 0, 0)  # stray: grounded leg, column (2, 0), not adjacent to column 0

    result = bridge_disconnected_pieces(model)

    assert result.unresolved_pieces == []
    assert len(result.added) == 2  # one elbow plate + one straight continuation cell
    assert any(b.part.id == "3023" for b in result.added)  # the elbow itself

    report_after = analyze(result.model)
    assert report_after.is_single_piece is True
    assert report_after.critical_bricks == set()


def _solid_column(nx: int, ny: int, nz: int, solid_xz: set[tuple[int, int]]) -> VoxelGrid:
    grid = VoxelGrid.empty(nx, ny, nz)
    for x, z in solid_xz:
        grid.occupied[x, :, z] = True
    return grid


def test_solid_grid_blocks_a_hidden_pillar_that_would_poke_through_open_air(catalog):
    # Same shape as the straight-pillar success case above, but column
    # (1, *) is NOT part of the mesh's original solid silhouette anywhere
    # -- a pillar there would be a visible pole through open air, not a
    # hidden brace, so this must stay unresolved rather than add one.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    model.place("3024", RED, 0, 1, 0)
    model.place("3024", RED, 0, 2, 0)
    model.place("3023", RED, 0, 3, 0, rotation=Rotation.YAW_0)
    model.place("3024", RED, 1, 0, 0)  # stray leg, column (1, 0)
    solid_grid = _solid_column(5, 6, 5, {(0, 0)})  # only the trunk's own column is "solid"

    result = bridge_disconnected_pieces(model, solid_grid=solid_grid)

    assert result.added == []
    assert len(result.unresolved_pieces) == 1
