from brickforge.lattice import GridPos, Rotation, SNOT_PLATE_RUN, STUD_LDU
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
    # Not report.is_single_piece: the backing plate sits BESIDE the wall
    # brick in the same layer, not stacked on/under it -- this catalog
    # never gives side-by-side, non-overlapping placements a stud edge
    # (see structure/graph.py), so the two are genuinely two separate,
    # independently-grounded components, correctly so (find_disconnected_
    # components no longer lets a shared GROUND node paper over that --
    # see weakpoints.py's own docstring). critical_bricks is the real
    # check here: both pieces independently rest on solid ground, so
    # neither is flagged as at risk of falling.
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
    # Not report.is_single_piece: the backing plate sits BESIDE the wall
    # brick in the same layer, not stacked on/under it -- this catalog
    # never gives side-by-side, non-overlapping placements a stud edge
    # (see structure/graph.py), so the two are genuinely two separate,
    # independently-grounded components, correctly so (find_disconnected_
    # components no longer lets a shared GROUND node paper over that --
    # see weakpoints.py's own docstring). critical_bricks is the real
    # check here: both pieces independently rest on solid ground, so
    # neither is flagged as at risk of falling.
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
    # Not report.is_single_piece: the backing plate sits BESIDE the wall
    # brick in the same layer, not stacked on/under it -- this catalog
    # never gives side-by-side, non-overlapping placements a stud edge
    # (see structure/graph.py), so the two are genuinely two separate,
    # independently-grounded components, correctly so (find_disconnected_
    # components no longer lets a shared GROUND node paper over that --
    # see weakpoints.py's own docstring). critical_bricks is the real
    # check here: both pieces independently rest on solid ground, so
    # neither is flagged as at risk of falling.
    assert report.critical_bricks == set()


def test_depth_control_converts_one_solid_stud_to_two_plates_not_rounded_up():
    # solid_grid extends exactly 1 stud past the candidate's own exposed
    # face (z=2 solid, z=3 out of bounds) -- the exact ratio (20/8 = 2.5)
    # must round DOWN, so 1 solid stud allows 2 plates, never 3 (which
    # would poke 4 LDU past the measured solid extent).
    model = Model(catalog=_CATALOG)
    model.place("3024", 4, 0, 0, 0)  # backing plate at z=0
    model.place("3005", 4, 0, 0, 1)  # candidate at z=1, backed on -z
    solid_grid = VoxelGrid.empty(1, 3, 3)  # z indices 0,1,2 valid; z=3 out of bounds
    solid_grid.occupied[:, :, :] = True

    result = place_snot_panels(model, solid_grid=solid_grid)

    assert result.swapped == 1
    layers = sorted({c.local_pos.y for c in result.snot_children})
    assert layers == [0, 1]  # 2 plate layers, not 1 and not 3

    # Full raw-geometry check: the two layers must be flush against each
    # other (no gap, no overlap) and against the parent's own face.
    anchor = result.model.bricks[result.snot_children[0].parent_index]
    frame = snot_frame_for_brick(anchor, anchor.part.side_stud_face, face_offset=anchor.part.side_stud_offset)
    z_ranges = []
    for child in sorted(result.snot_children, key=lambda c: c.local_pos.y):
        pos, matrix = place_in_frame(frame, child.part, child.local_pos, child.local_rotation)
        ew, ed = child.part.footprint
        _, z_range = _raw_geometry_bbox(pos, matrix, ew * 10, ed * 10)
        z_ranges.append(z_range)
    assert z_ranges[0][0] == 2 * STUD_LDU  # flush against the candidate's own +z face
    assert z_ranges[0][1] == z_ranges[1][0]  # layer 1 starts exactly where layer 0 ends
    assert z_ranges[1][1] - z_ranges[0][0] == 2 * 8  # 2 plates deep total, 8 LDU each


def test_depth_control_uses_the_minimum_across_a_merged_runs_members():
    # Two adjacent candidates (x=1, x=2) with DIFFERENT solid depths --
    # x=1's column is solid 2 studs deep, x=2's only 1 -- must produce ONE
    # uniform depth for the whole merged panel (the minimum, 1 stud -> 2
    # plates), not a jagged per-member stack and not an average.
    model = Model(catalog=_CATALOG)
    model.place("3710", 4, 0, 0, 0)  # Plate 1x4 backing, x:[0,4) -- covers both candidates
    model.place("3005", 4, 1, 0, 1)
    model.place("3005", 4, 2, 0, 1)
    model.place("3024", 4, 0, 0, 1)  # blocker at -x end
    model.place("3024", 4, 3, 0, 1)  # blocker at +x end

    solid_grid = VoxelGrid.empty(4, 3, 4)
    # Candidates sit at z=1 (footprint depth 1), so their own +z face is at
    # z=2: step 1 checks z=2, step 2 checks z=3.
    solid_grid.occupied[1, :, :] = True  # x=1 column: z=0..3 all solid -> depth 2 studs (step 2's z=3 is solid; step 3's z=4 is out of bounds)
    solid_grid.occupied[2, :, :3] = True  # x=2 column: z=0,1,2 solid, z=3 not -> depth 1 stud (step 2's z=3 fails)

    result = place_snot_panels(model, solid_grid=solid_grid)

    assert result.swapped == 2
    layers = sorted({c.local_pos.y for c in result.snot_children})
    assert layers == [0, 1]  # minimum of the two (1 stud -> 2 plates), not 2 studs -> 5 plates


def test_depth_control_is_capped_even_when_solid_grid_measures_much_deeper():
    # Real bug caught before shipping, not hypothetical: on the real
    # mushroom model, a candidate's "exposed" face turned out to face the
    # model's own HOLLOWED INTERIOR (empty in the final Model, but still
    # solid in solid_grid -- the PRE-shelling mesh -- since that interior
    # genuinely was part of the sculpture before hollowing). Measured 17-18
    # studs of "depth" there, which would tunnel dozens of plates toward
    # the model's core. This pins the cap that keeps that bounded.
    model = Model(catalog=_CATALOG)
    model.place("3024", 4, 0, 0, 0)
    model.place("3005", 4, 0, 0, 1)
    solid_grid = VoxelGrid.empty(1, 3, 30)  # room for 28 solid studs past the candidate's own face
    solid_grid.occupied[:, :, :] = True

    result = place_snot_panels(model, solid_grid=solid_grid)

    assert result.swapped == 1
    layers = {c.local_pos.y for c in result.snot_children}
    assert max(layers) + 1 == SNOT_PLATE_RUN  # capped at 5 plates, not floor(28 * 2.5) = 70


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
