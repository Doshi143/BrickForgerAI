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
