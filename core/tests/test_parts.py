import pytest

from brickforge import PartCatalog, Rotation


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_loads_expected_part_count(catalog):
    # 44 + the 33-degree slope family (4286/3298/4161/3297) + 87087 (the
    # first SNOT part, Phase A -- see catalog/parts_v1.yaml's own SNOT
    # section comment).
    assert len(catalog) == 50


def test_slope_footprints_verified_from_raw_geometry(catalog):
    # 3040's footprint and height were computed from the full raw vertex
    # data of parts/3040b.dat + s/3040s01.dat (X:20 LDU/1 stud, Y:0-24
    # LDU/3 plates, Z:40 LDU/2 studs) -- not read off the name.
    slope = catalog.get("3040")
    assert slope.category == "slope"
    assert slope.footprint == (1, 2)
    assert slope.height_plates == 3
    assert slope.top == "none"
    assert slope.bottom == "full"
    assert slope.y_anchor == "top"


def test_2plate_slope_footprints_verified_from_raw_geometry(catalog):
    # 54200/85984/7825/7835's footprints and height were computed from
    # their raw vertex data (X: 20/40/60/80 LDU = 1/2/3/4 studs, symmetric
    # about 0; Y: 0 to -15.6ish LDU, i.e. 2 plates; Z: a single stud,
    # nominally symmetric about 0 once corner-rounding is accounted for)
    # -- not read off the "31 1 x N" name.
    for part_id, expected_footprint in [
        ("54200", (1, 1)),
        ("85984", (2, 1)),
        ("7825", (3, 1)),
        ("7835", (4, 1)),
    ]:
        part = catalog.get(part_id)
        assert part.category == "slope"
        assert part.footprint == expected_footprint
        assert part.height_plates == 2
        assert part.top == "none"
        assert part.bottom == "full"
        assert part.local_offset == (0, 0)
        # The real finding: this family's origin is at the BOTTOM of its
        # own geometry, not the top like every other part -- confirmed
        # from raw Y coordinates (all <= 0) and 61409's own !HISTORY
        # ("Updated origin to bottom center"), not assumed to match the
        # 3-plate slopes above just because both are "slopes".
        assert part.y_anchor == "bottom"


def test_inverted_slope_has_flipped_connector_coverage(catalog):
    # Inverted slopes mount upside down: flat face (full studs) on top,
    # sloped/cut face on the bottom -- opposite of an upright slope.
    inverted = catalog.get("3665")
    assert inverted.top == "full"
    assert inverted.bottom == "none"


def test_expanded_tile_footprints_match_verified_raw_geometry(catalog):
    # Same discipline as the brick/plate catalog: pinned directly from
    # fetching parts/2431.dat (Tile 1 x 4: X=80 LDU/4 studs, Z=20 LDU/1
    # stud), confirming the same "second name-number is X" convention
    # holds for tiles, not re-derived from the naming convention.
    assert catalog.get("2431").footprint == (4, 1)  # Tile 1 x 4
    assert catalog.get("1751").footprint == (4, 4)  # Tile 4 x 4 (square, unaffected either way)
    for tile_id in ["63864", "2431", "6636", "4162", "26603", "87079", "69729", "1751"]:
        part = catalog.get(tile_id)
        assert part.category == "tile"
        assert part.top == "none"
        assert part.bottom == "full"


def test_2x4_brick_present_with_correct_geometry(catalog):
    part = catalog.get("3001")
    assert part.name == "Brick 2 x 4"
    assert part.category == "brick"
    # Verified against raw geometry in parts/3001.dat: X spans 80 LDU
    # (4 studs), Z spans 40 LDU (2 studs). The longer number in the part
    # name runs along local X, not Z -- see catalog/parts_v1.yaml header.
    assert part.footprint == (4, 2)
    assert part.height_plates == 3
    assert part.ldraw_file == "3001.dat"


def test_footprint_x_axis_matches_verified_raw_geometry(catalog):
    # Regression test for a real bug: an earlier catalog encoded footprint
    # as [first_number, second_number] read directly off the part name
    # ("1 x 4" -> [1, 4]), which is backwards for every non-square part and
    # silently transposed every rotated/unrotated placement 90 degrees from
    # its true rendered footprint. These values are pinned directly from
    # fetching and inspecting parts/3010.dat, parts/3004.dat, and
    # parts/3001.dat -- not re-derived from the naming convention.
    assert catalog.get("3010").footprint == (4, 1)  # Brick 1 x 4: X=80 LDU, Z=20 LDU
    assert catalog.get("3004").footprint == (2, 1)  # Brick 1 x 2: X=40 LDU, Z=20 LDU
    assert catalog.get("3001").footprint == (4, 2)  # Brick 2 x 4: X=80 LDU, Z=40 LDU


def test_tile_has_no_top_studs(catalog):
    tile = catalog.get("3070b")
    assert tile.top_studs(Rotation.YAW_0) == []
    assert tile.bottom_studs(Rotation.YAW_0) == [(0, 0)]


def test_brick_top_studs_cover_full_footprint(catalog):
    brick = catalog.get("3001")  # footprint (4, 2) unrotated
    studs = brick.top_studs(Rotation.YAW_0)
    assert len(studs) == 8
    assert set(studs) == {(x, z) for x in range(4) for z in range(2)}


def test_rotated_footprint_swaps_stud_grid(catalog):
    brick = catalog.get("3001")  # (4,2) -> (2,4) at YAW_90
    studs = brick.top_studs(Rotation.YAW_90)
    assert set(studs) == {(x, z) for x in range(2) for z in range(4)}


def test_unknown_part_raises(catalog):
    with pytest.raises(KeyError):
        catalog.get("99999999")


def test_known_colors_present(catalog):
    assert catalog.color_name(4) == "Red"
    assert catalog.color_name(71) == "Light_Bluish_Gray"
    assert catalog.has_color(0)
    assert not catalog.has_color(9999)
