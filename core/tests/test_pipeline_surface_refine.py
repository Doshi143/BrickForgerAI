import pytest

from brickforge import Model, PartCatalog
from brickforge.pipeline.surface_refine import substitute_tiles
from brickforge.structure import analyze

RED = 4


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_top_exposed_plate_is_substituted_with_matching_tile(catalog):
    model = Model(catalog=catalog)
    model.place("3020", RED, 0, 0, 0)  # Plate 2x4, nothing on top

    refined = substitute_tiles(model)

    assert len(refined) == 1
    brick = refined.bricks[0]
    assert brick.part.id == "87079"  # Tile 2 x 4
    assert brick.pos == model.bricks[0].pos
    assert brick.rotation == model.bricks[0].rotation
    assert brick.color == RED


def test_plate_with_something_resting_on_it_is_not_substituted(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)  # Plate 1x1
    model.place("3024", RED, 0, 1, 0)  # another plate resting directly on top

    refined = substitute_tiles(model)

    bottom = next(b for b in refined if b.pos.y == 0)
    assert bottom.part.id == "3024"  # left as a plate, not swapped for a tile


def test_plate_with_no_matching_tile_footprint_is_left_alone(catalog):
    model = Model(catalog=catalog)
    model.place("3034", RED, 0, 0, 0)  # Plate 2x8 -- no verified 2x8 tile exists in this catalog

    refined = substitute_tiles(model)

    assert refined.bricks[0].part.id == "3034"


def test_bricks_are_never_substituted(catalog):
    model = Model(catalog=catalog)
    model.place("3003", RED, 0, 0, 0)  # Brick 2x2, top-exposed

    refined = substitute_tiles(model)

    assert refined.bricks[0].part.id == "3003"


def test_plate_facing_a_sealed_interior_cavity_is_not_substituted(catalog):
    # A fully sealed hollow 3x3x3 shell -- floor, a wall ring (leaving the
    # center cell empty at y=1, the cavity), and a roof that seals it from
    # above. The floor plate directly under the cavity has nothing resting
    # on its own top (the old occupancy-only check would have tiled it),
    # but that empty cell is enclosed, not open air -- exactly the "looks
    # identical to the occupancy check, but nobody will ever see it" case
    # this function's docstring describes. A separate, genuinely exposed
    # plate far away is the control: it must still tile normally, proving
    # the new check narrows *this* case specifically, not tiling in general.
    model = Model(catalog=catalog)
    for x in range(3):
        for z in range(3):
            model.place("3024", RED, x, 0, z)  # floor, full 3x3
    for x in range(3):
        for z in range(3):
            if (x, z) == (1, 1):
                continue  # leave the center empty -- the cavity
            model.place("3024", RED, x, 1, z)  # wall ring
    for z in range(3):
        # Plate 1x3 (footprint 3x1), not three separate 1x1s: the roof's
        # own center cell would otherwise have nothing below it (the
        # cavity) and nothing beside it either (same-layer plates never
        # share a stud connection in this catalog), leaving it a genuinely
        # disconnected node -- a real artifact of this test's own
        # construction, not something the code under test should have to
        # tolerate. One piece per row gives every roof row 2 real stud
        # connections to the wall ring below (the row's two end cells),
        # keeping the whole shell a single connected piece.
        model.place("3623", RED, 0, 2, z)  # roof row, full 3x3 -- seals the cavity

    control = model.place("3024", RED, 10, 0, 10)  # far away, genuinely open air

    report_before = analyze(model)
    refined = substitute_tiles(model)
    report_after = analyze(refined)

    cavity_floor = next(b for b in refined if b.pos.x == 1 and b.pos.y == 0 and b.pos.z == 1)
    assert cavity_floor.part.id == "3024"  # left as a plate -- faces a sealed cavity, not open air

    control_after = next(b for b in refined if b.pos == control.pos)
    assert control_after.part.id == "3070b"  # Tile 1x1 -- genuinely open air, still substituted

    assert report_before.critical_bricks == set()
    assert report_after.critical_bricks == set()
    assert report_before.is_single_piece == report_after.is_single_piece


def test_tile_substitution_does_not_introduce_new_structural_issues(catalog):
    # Build a small multi-layer structure with a top-exposed "roof" plate,
    # substitute tiles, and confirm the structural report is identical
    # before and after -- exactly the claim surface_refine.py's docstring
    # makes, checked rather than assumed.
    model = Model(catalog=catalog)
    model.place("3001", RED, 0, 0, 0)  # 2x4 brick, grounded
    model.place("3020", RED, 0, 3, 0)  # 2x4 plate "roof" on top, itself top-exposed

    report_before = analyze(model)
    refined = substitute_tiles(model)
    report_after = analyze(refined)

    assert report_before.critical_bricks == set()
    assert report_after.critical_bricks == set()
    assert report_before.is_single_piece == report_after.is_single_piece
    assert len(refined) == len(model)
    assert refined.bricks[1].part.id == "87079"  # roof plate did get swapped
