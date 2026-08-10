from brickforge.lattice import GridPos, Rotation, STUD_LDU
from brickforge.model import Model
from brickforge.parts import PartCatalog
from brickforge.pipeline.grid import VoxelGrid
from brickforge.pipeline.snot_placement import place_snot_panels
from brickforge.snot import place_in_frame, snot_frame_for_brick
from brickforge.structure.report import analyze

_CATALOG = PartCatalog.load_default()


def _raw_geometry_bbox(pos_ldraw, matrix, half_x, half_z, height=8):
    a, b, c, d, e, f, g, h, i = matrix
    corners = [(dx, dy, dz) for dx in (-half_x, half_x) for dz in (-half_z, half_z) for dy in (0, height)]
    world_corners = [
        (a * lx + b * ly + c * lz + pos_ldraw[0], d * lx + e * ly + f * lz + pos_ldraw[1], g * lx + h * ly + i * lz + pos_ldraw[2])
        for (lx, ly, lz) in corners
    ]
    xs = [p[0] for p in world_corners]
    zs = [p[2] for p in world_corners]
    return (min(xs), max(xs)), (min(zs), max(zs))


def test_walled_1x1_brick_becomes_87087_with_a_flush_plate_attached():
    model = Model(catalog=_CATALOG)
    model.place("3024", 4, 0, 0, 0)  # thin backing plate at z=0 -- never itself a candidate (category != "brick")
    model.place("3005", 4, 0, 0, 1)  # index 1 -- backed on -z by the plate, open on +z

    result = place_snot_panels(model)

    assert result.swapped == 1
    assert result.attached == 1
    assert result.model.bricks[0].part.id == "3024"  # backing plate untouched
    assert result.model.bricks[1].part.id == "87087"
    # +x/-x have nothing on either side (no backing, correctly skipped -- see
    # test_fully_isolated_brick below); +z is the first face with real
    # backing (the plate sitting at -z).
    assert result.model.bricks[1].rotation == Rotation.YAW_180
    assert len(result.snot_children) == 1
    child = result.snot_children[0]
    assert child.parent_index == 1
    assert child.part.id == "3024"
    assert child.local_pos == GridPos(0, 0, 0)

    report = analyze(result.model, result.snot_children)
    assert report.is_single_piece
    assert report.critical_bricks == set()


def test_walled_4x1_brick_becomes_30414_on_one_of_its_long_faces():
    model = Model(catalog=_CATALOG)
    model.place("3710", 4, 0, 0, 0, rotation=Rotation.YAW_0)  # backing plate, footprint [4, 1]
    model.place("3010", 4, 0, 0, 1, rotation=Rotation.YAW_0)  # index 1 -- Brick 1x4, backed on -z

    result = place_snot_panels(model)

    assert result.swapped == 1
    assert result.model.bricks[1].part.id == "30414"
    assert result.model.bricks[1].rotation == Rotation.YAW_180
    assert result.snot_children[0].part.id == "3710"  # Plate 1x4

    report = analyze(result.model, result.snot_children)
    assert report.is_single_piece
    assert report.critical_bricks == set()


def test_fully_isolated_brick_with_no_backing_anywhere_is_not_swapped():
    # The real bug this pins down, found on the real turret example, not
    # hypothetical: a brick with nothing beside it on ANY axis (a
    # free-floating single-stud spike -- a crenellation tip, a corner
    # merlon) has no principled "outward" direction at all. An earlier
    # version always resolved this to the first face in _FACE_ORDER
    # regardless of the brick's actual position, which meant every
    # isolated spike on the turret got a panel pointing the SAME fixed
    # direction (+x) -- several of them pointing sideways at each other or
    # into gaps between merlons instead of a coherent outward direction.
    # Now: no face has real backing material opposite it, so none qualify,
    # and the brick is correctly left unswapped rather than given an
    # arbitrary panel.
    model = Model(catalog=_CATALOG)
    model.place("3005", 4, 0, 0, 0)  # completely alone -- no neighbor on any side

    result = place_snot_panels(model)

    assert result.swapped == 0
    assert result.model.bricks[0].part.id == "3005"
    assert result.snot_children == []


def test_brick_with_something_resting_on_top_is_not_swapped_to_87087():
    model = Model(catalog=_CATALOG)
    model.place("3024", 4, 0, 0, 0)  # backing plate at z=0
    model.place("3005", 4, 0, 0, 1)  # index 1 -- backed on -z, side faces would otherwise qualify
    model.place("3024", 4, 0, 3, 1)  # a plate resting directly on top of it

    result = place_snot_panels(model)

    assert result.model.bricks[1].part.id == "3005"  # unswapped -- top: none would sever a real connection
    assert all(child.parent_index != 1 for child in result.snot_children)


def test_solid_grid_gate_blocks_a_panel_that_would_poke_into_open_air():
    model = Model(catalog=_CATALOG)
    model.place("3024", 4, 0, 0, 0)  # backing plate at z=0
    model.place("3005", 4, 0, 0, 1)  # index 1 -- backed on -z, would otherwise get a +z panel
    # Sized to cover the backing plate and the candidate brick but nothing
    # past z=1 -- the +z outward step (z=2) is out of bounds, i.e.
    # definitively NOT part of the original solid mesh.
    solid_grid = VoxelGrid.empty(1, 3, 2)

    result = place_snot_panels(model, solid_grid=solid_grid)

    assert result.swapped == 0
    assert result.model.bricks[1].part.id == "3005"


def test_solid_grid_gate_allows_a_panel_when_the_original_mesh_extends_that_far():
    model = Model(catalog=_CATALOG)
    model.place("3024", 4, 0, 0, 0)  # backing plate at z=0
    model.place("3005", 4, 0, 0, 1)  # index 1
    solid_grid = VoxelGrid.empty(1, 3, 3)  # room for the backing, the brick, AND one stud of +z
    solid_grid.occupied[:, :, :] = True

    result = place_snot_panels(model, solid_grid=solid_grid)

    assert result.swapped == 1
    assert result.model.bricks[1].part.id == "87087"
    assert result.model.bricks[1].rotation == Rotation.YAW_180


def test_five_adjacent_candidates_merge_into_one_region_grown_run():
    # A real wall of 5 single-stud-wide bricks, all facing the same
    # direction, backed by one continuous plate behind them, with a
    # blocker at each end so +x/-x never compete with the intended +z
    # face. Should produce 5 swaps but a MERGED, tiled panel (4-wide +
    # 1-wide, greedy largest-first) instead of 5 separate 1x1 plates --
    # this is the actual "why just 1-2 plates on each face" fix.
    model = Model(catalog=_CATALOG)
    model.place("3460", 4, 0, 0, 0)  # Plate 1x8 backing wall, x:[0,8)
    for x in (1, 2, 3, 4, 5):
        model.place("3005", 4, x, 0, 1)
    model.place("3024", 4, 0, 0, 1)  # blocker at the row's -x end
    model.place("3024", 4, 6, 0, 1)  # blocker at the row's +x end

    result = place_snot_panels(model)

    assert result.swapped == 5
    for x in (1, 2, 3, 4, 5):
        # index shifts by 1 since the backing plate (index 0) comes first
        assert result.model.bricks[x].part.id == "87087"
        assert result.model.bricks[x].rotation == Rotation.YAW_180

    # One merged run tiled with the widest plates available (4 + 1), not
    # five separate 1x1 plates.
    assert len(result.snot_children) == 2
    assert {c.part.id for c in result.snot_children} == {"3710", "3024"}
    assert all(c.parent_index == result.snot_children[0].parent_index for c in result.snot_children)

    # Full raw-geometry check: the two tiles, placed within the SAME
    # anchor frame, must together span the world X range of the entire
    # 5-brick row with no gap or overlap -- not just "5 individual swaps
    # happened", but that the panel really covers all of them physically.
    anchor = result.model.bricks[result.snot_children[0].parent_index]
    frame = snot_frame_for_brick(anchor, anchor.part.side_stud_face, face_offset=anchor.part.side_stud_offset)
    x_ranges = []
    for child in result.snot_children:
        pos, matrix = place_in_frame(frame, child.part, child.local_pos, child.local_rotation)
        ew, ed = child.part.footprint
        x_range, _ = _raw_geometry_bbox(pos, matrix, ew * 10, ed * 10)
        x_ranges.append(x_range)
    x_ranges.sort()
    assert x_ranges[0][0] == 1 * STUD_LDU  # covers the row starting at brick x=1's own corner
    assert x_ranges[-1][1] == 6 * STUD_LDU  # through brick x=5's far corner (5 bricks * 20 LDU)
    for a, b in zip(x_ranges, x_ranges[1:]):
        assert a[1] == b[0]  # no gap or overlap between adjacent tiles

    report = analyze(result.model, result.snot_children)
    assert report.is_single_piece
    assert report.critical_bricks == set()


def test_no_snot_catalog_parts_is_a_no_op():
    # A catalog with no SNOT entries at all must return the model unchanged,
    # not crash -- the early-return path in place_snot_panels.
    parts_only_bricks = {pid: p for pid, p in _CATALOG._parts.items() if p.category != "snot"}
    catalog = PartCatalog(parts_only_bricks, dict(_CATALOG._colors))
    model = Model(catalog=catalog)
    model.place("3005", 4, 0, 0, 0)

    result = place_snot_panels(model)

    assert result.swapped == 0
    assert result.snot_children == []
    assert result.model is model
