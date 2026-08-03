import pytest

from brickforge import Model, PartCatalog, PlacementError, Rotation


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_place_adds_brick(catalog):
    model = Model(catalog=catalog)
    brick = model.place("3005", 4, 0, 0, 0)  # 1x1 brick, red, at origin
    assert len(model) == 1
    assert brick.part.id == "3005"
    assert brick.color == 4


def test_collision_is_detected(catalog):
    model = Model(catalog=catalog)
    model.place("3001", 71, 0, 0, 0)  # 2x4 brick at (0,0,0)-(1,2,3)
    with pytest.raises(PlacementError):
        model.place("3005", 4, 0, 0, 0)  # 1x1 brick overlapping same cell


def test_adjacent_bricks_do_not_collide(catalog):
    model = Model(catalog=catalog)
    model.place("3001", 71, 0, 0, 0)  # footprint (4,2): occupies x:[0,4) z:[0,2)
    model.place("3001", 71, 4, 0, 0)  # occupies x:[4,8) z:[0,2) -- adjacent, not overlapping
    assert len(model) == 2


def test_stacking_two_plates_does_not_collide(catalog):
    model = Model(catalog=catalog)
    model.place("3024", 15, 0, 0, 0)  # 1x1 plate at y=0..1
    model.place("3024", 15, 0, 1, 0)  # 1x1 plate at y=1..2, stacked on top
    assert len(model) == 2


def test_unknown_part_raises(catalog):
    model = Model(catalog=catalog)
    with pytest.raises(PlacementError):
        model.place("nonexistent", 4, 0, 0, 0)


def test_unknown_color_raises(catalog):
    model = Model(catalog=catalog)
    with pytest.raises(PlacementError):
        model.place("3005", 99999, 0, 0, 0)


def test_rotation_changes_occupied_footprint(catalog):
    model = Model(catalog=catalog)
    brick = model.place("3001", 71, 0, 0, 0, rotation=Rotation.YAW_90)  # (4,2) -> (2,4) at YAW_90
    cells = set(brick.occupied_cells())
    xs = {c[0] for c in cells}
    zs = {c[2] for c in cells}
    assert xs == {0, 1}
    assert zs == {0, 1, 2, 3}
