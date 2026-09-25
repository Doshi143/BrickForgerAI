"""Designer engine + interpreter: parts-table sanity, the example specs build
clean, negative controls fire, and the finish/sideways options behave."""
import itertools
import os
from collections import Counter

import pytest

from brickforge_designer.engine import TABLE, pdef
from brickforge_designer.pipeline import CONFIG, build, check

SPECS = os.path.join(os.path.dirname(__file__), "..", "specs")
SPEC_NAMES = sorted(f[:-4] for f in os.listdir(SPECS) if f.endswith(".bfd"))
TILE_IDS = {"3070b", "3069b", "63864", "2431", "3068b", "87079", "6636", "4162", "98138"}
SNOT_IDS = {"30414", "87087"}
# attached details (glass, door leaf, wheel rim, tyre) are placed by their
# exact measured extent, not on the grid, so a thin pane may be 0 studs deep
ATTACHED = {"60603", "60623", "4624", "3641", "60601", "60602"}


def spec(name):
    with open(os.path.join(SPECS, f"{name}.bfd"), encoding="utf-8") as f:
        return f.read()


def run(text, **kw):
    D, it = build(text, **kw)
    problems, stats = check(D, it)
    return D, problems, stats


# ---------------------------------------------------------------- parts table
def test_parts_table_every_part_loads_and_is_at_least_a_plate_tall():
    assert len(TABLE) >= 71
    for pid in TABLE:
        P = pdef(pid)
        if pid != "3811":                      # baseplate: 0 plates by design
            assert P.h >= 1, pid
        if pid not in ATTACHED:
            assert P.w >= 1 and P.d >= 1, pid


def test_parts_table_studs_are_unit_directions():
    for pid, t in TABLE.items():
        for s in t["studs"]:
            d = [round(v) for v in s[3:]]
            assert sorted(abs(v) for v in d) == [0, 0, 1], (pid, d)


def test_plain_brick_geometry_matches_ldraw():
    P = pdef("3001")                           # Brick 2 x 4
    assert (P.w, P.d, P.h, P.bottom) == (4, 2, 3, False)
    assert len(P.studs) == 8


# ---------------------------------------------------------------- example specs
@pytest.mark.parametrize("name", SPEC_NAMES)
def test_example_spec_builds_with_zero_problems(name):
    _, problems, stats = run(spec(name))
    assert problems == [], problems
    assert stats["parts"] > 50


# ---------------------------------------------------------------- negative controls
BASE = "model t\nbaseplate 0 0 green\n"


def test_floating_part_is_reported_loose():
    _, problems, _ = run(BASE + "part 3001 red 4 4 9\n")
    assert any(p.startswith("LOOSE") for p in problems), problems


def test_overlapping_parts_are_reported_as_collision():
    _, problems, _ = run(BASE + "part 3001 red 4 4 0\npart 3001 blue 5 4 0\n")
    assert any(p.startswith("COLLISION") for p in problems), problems


def test_unknown_part_and_command_are_spec_errors():
    _, problems, _ = run(BASE + "part 99999 red 4 4 0\nfrobnicate 1 2\n")
    spec_errs = [p for p in problems if p.startswith("SPEC")]
    assert len(spec_errs) == 2, problems
    assert "unknown part 99999" in spec_errs[0]
    assert "unknown command 'frobnicate'" in spec_errs[1]


def test_unknown_colour_is_a_spec_error():
    _, problems, _ = run(BASE + "part 3001 plaid 4 4 0\n")
    assert any("unknown colour 'plaid'" in p for p in problems), problems


def test_connected_part_on_baseplate_is_clean():
    _, problems, stats = run(BASE + "part 3001 red 4 4 0\npart 3001 blue 5 4 3\n")
    assert problems == [] and stats["parts"] == 3


def test_oversized_model_is_reported_too_big():
    text = "model t\nbase 0..44,0..3 dark_bluish_gray\n"
    _, problems, _ = run(text)
    assert any(p.startswith("TOO BIG") for p in problems), problems


def test_part_limit_is_enforced(monkeypatch):
    monkeypatch.setitem(CONFIG, "limits", dict(CONFIG["limits"], max_parts=10))
    _, problems, _ = run(spec("pickup"))
    assert any("TOO BIG" in p and "parts" in p for p in problems), problems


# ---------------------------------------------------------------- options
def test_invalid_options_are_rejected():
    with pytest.raises(ValueError):
        build(BASE, finish="glossy")
    with pytest.raises(ValueError):
        build(BASE, sideways="lots")


@pytest.mark.parametrize("name,finish,sideways",
                         [(n, f, s) for n in ("toucan", "tudor", "pickup")
                          for f, s in itertools.product(("tiled", "studs"), ("off", "auto", "more"))])
def test_every_option_combination_builds_clean(name, finish, sideways):
    _, problems, _ = run(spec(name), finish=finish, sideways=sideways)
    assert problems == [], problems


def test_studs_finish_replaces_engine_chosen_tiles_with_plates():
    tiled, _, _ = run(spec("tudor"), finish="tiled")
    studs, _, _ = run(spec("tudor"), finish="studs")
    count = lambda D: sum(Counter(q.pid for q in D.parts)[t] for t in TILE_IDS)
    assert count(tiled) > 20
    assert count(studs) == 0                   # tudor places no tiles by hand


def test_studs_finish_keeps_slopes():
    slope = lambda D: sum(1 for q in D.parts if q.pid in ("11477", "15068", "50950", "24309", "61678", "93606"))
    tiled, _, _ = run(spec("toucan"), finish="tiled")
    studs, _, _ = run(spec("toucan"), finish="studs")
    assert slope(studs) == slope(tiled) > 0


def test_sideways_off_builds_no_snot_and_paints_the_eye():
    auto, _, _ = run(spec("toucan"), sideways="auto")
    off, problems, _ = run(spec("toucan"), sideways="off")
    snot = lambda D: sum(1 for q in D.parts if q.pid in SNOT_IDS or q.tag in ("panel", "anchor", "pupil", "eye"))
    assert snot(auto) > 0
    assert snot(off) == 0 and problems == []
    # the eye survives as studs-up cells in the ring colour
    assert any(q.color == 322 for q in off.parts)          # medium_azure ring


def test_sideways_more_is_engine_identical_to_auto():
    # "more" only changes what the designer model is told; the engine builds
    # exactly what the spec asks for either way
    a, _, _ = run(spec("toucan"), sideways="auto")
    m, _, _ = run(spec("toucan"), sideways="more")
    assert Counter((q.pid, q.color) for q in a.parts) == Counter((q.pid, q.color) for q in m.parts)


# ---------------------------------------------------------------- click-on, standing pieces, reports
ROCK = """model t
base 0..15,0..15 dark_tan
sculpt base=2 color=dark_bluish_gray hollow=2
  box 2..13 0..5 2..13
end
"""
FIGURE = """sculpt base=8 color=orange
  box 5..10 0..11 5..10
end
"""


def test_a_sculpt_built_on_another_sculpt_clicks_on():
    D, problems, stats = run(ROCK + FIGURE)
    assert problems == [], problems
    assert [p["status"] for p in stats["pieces"]] == ["main"]
    assert any(r[0] == "click-on" and r[1] > 0 for r in stats["engine_repairs"])
    # the rock keeps its smooth tiled top outside the figure's footprint
    assert any(q.tag == "top" and q.src == 3 for q in D.parts)


def test_a_big_separate_piece_resting_on_hand_placed_tiles_is_accepted_as_standing():
    tiles = "tiles 8 black 4..11,4..11\n"
    D, problems, stats = run(ROCK + tiles.replace("tiles 8", "tiles 8") + FIGURE.replace("base=8", "base=9"))
    statuses = sorted(p["status"] for p in stats["pieces"])
    assert statuses == ["main", "standing"], (statuses, problems)
    assert problems == [], problems


def test_a_tiny_group_resting_on_tiles_is_loose_and_the_report_says_why():
    text = BASE + "tiles 0 black 4..7,4..7\npart 3024 red 5 5 1\n"
    _, problems, _ = run(text)
    loose = [p for p in problems if p.startswith("LOOSE")]
    assert loose and "from line 4" in loose[0] and "only rests on tiles (line 3)" in loose[0], problems


def test_a_floating_group_report_says_it_floats():
    _, problems, _ = run(BASE + "part 3001 red 4 4 9\n")
    assert "floats" in problems[0], problems


def test_a_separate_piece_that_would_tip_over_is_loose():
    # a big slab (well over MIN_STANDING_PARTS) balanced on one 1x1 tile in its corner
    layers = "".join(f"plates {L} red 0..11,0..5 prefer={'x' if L % 2 else 'z'}\n" for L in range(1, 9))
    text = BASE + "tiles 0 black 0..0,0..0\n" + layers
    _, problems, stats = run(text)
    assert any("tip over" in p for p in problems), (problems, stats["pieces"])


def test_sculpt_overlapping_earlier_geometry_merges_instead_of_colliding():
    tail = """sculpt base=6 color=orange
  box 3..6 0..3 3..6
end
"""
    _, problems, stats = run(ROCK + tail)
    assert problems == [], problems
    assert any(r[0] == "sculpt overlap merged" for r in stats["engine_repairs"])


def test_decimal_range_ends_round_to_the_nearest_cell():
    from brickforge_designer.dsl import rng_
    assert list(rng_("0..3.5")) == [0, 1, 2, 3, 4]
    assert list(rng_("2.4..2.6")) == [2, 3]
    assert list(rng_("-2..1")) == [-2, -1, 0, 1]


def test_tiny_loose_bits_are_pruned_and_recorded_but_bigger_ones_are_not():
    big = BASE + "bricks 0 red 0..15,0..15 courses=2\n"
    D, problems, stats = run(big + "part 3024 blue 20 20 9\n")          # one floating 1x1 plate
    assert problems == [] and ("pruned tiny loose groups", 1) in stats["engine_repairs"]
    _, problems, _ = run(big + "plates 9 blue 20..23,20..23\nplates 10 blue 20..23,20..23 prefer=z\n")
    assert any(p.startswith("LOOSE") for p in problems), problems     # > 3 parts: still reported


def test_prune_never_hides_a_model_that_is_mostly_loose():
    _, problems, _ = run(BASE + "part 3001 red 4 4 9\n")               # 1 of 2 parts loose: > 2%
    assert any(p.startswith("LOOSE") for p in problems)


def test_eye_on_a_curved_head_is_painted_instead_of_failing():
    text = BASE + """sculpt base=0 color=orange hollow=2
  ball 8 8 0 4 8 3
  eye 10 12 pupil=black ring=yellow
end
"""
    D, problems, stats = run(text)
    assert not any("eye" in p for p in problems), problems
    assert any(r[0].startswith("eye painted") for r in stats["engine_repairs"]) or \
        any(q.tag == "eye" for q in D.parts)


# ---------------------------------------------------------------- wheels
CAR = """model t
base 0..11,-5..4 dark_bluish_gray
sculpt base=2 color=red
  box 1..10 0..5 -2..1
  wheels 2,7 size={size}
end
"""


@pytest.mark.parametrize("size,rim,tyre", [("small", "4624", "3641"), ("large", "6014b", "6015")])
def test_wheeled_sculpt_gets_real_wheels_and_is_its_own_piece(size, rim, tyre):
    D, problems, stats = run(CAR.format(size=size))
    assert problems == [], problems
    c = Counter(q.pid for q in D.parts)
    assert (c["4600"], c[rim], c[tyre]) == (4, 4, 4)
    assert sorted(p["assembly"] for p in stats["pieces"]) == ["main", "vehicle1"]
    # every wheel hangs off an axle plate, which clicks into the body
    for i, q in enumerate(D.parts):
        if q.pid in (rim, tyre):
            assert D.parts[q.host].pid == "4600"


@pytest.mark.parametrize("size", ["small", "large"])
def test_tyres_rest_on_the_surface_and_stand_clear_of_the_body(size):
    D, _, _ = run(CAR.format(size=size))
    base_top = min(q.box[1][0] for q in D.parts if q.asm == "main")      # LDraw y points down
    body = [q for q in D.parts if q.asm == "vehicle1" and q.host is None and q.pid != "4600"]
    for q in D.parts:
        if q.tag == "tyre":
            assert 0 <= base_top - q.box[1][1] <= 2.5, (q.box, base_top)   # touching (within 1 mm)
            assert q.box[2][1] <= -40 or q.box[2][0] >= 40                  # outside the 4-wide body


def test_wheels_need_a_flat_wide_enough_underside():
    text = CAR.format(size="small").replace("box 1..10 0..5 -2..1", "box 1..10 0..5 -1..0")   # 2 wide
    _, problems, _ = run(text)
    assert any("wheels at x=2" in p for p in problems), problems


def test_vehicle_body_is_lifted_onto_its_wheels_wherever_it_was_placed():
    low, _, _ = run(CAR.format(size="large").replace("base=2", "base=0"))
    high, _, _ = run(CAR.format(size="large").replace("base=2", "base=9"))
    pos = lambda D: sorted((q.pid, q.pos) for q in D.parts)
    assert pos(low) == pos(high)


# ---------------------------------------------------------------- hollow slope ends
@pytest.mark.parametrize("pid", ["11477", "15068", "50950", "24309", "61678", "93606"])
@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_curved_slope_hollow_end_gets_a_filler_plate_inside_it(pid, rot):
    from brickforge_designer.engine import HOLLOW_END
    D, problems, _ = run(BASE + f"part {pid} red 8 8 0 rot={rot}\n")
    assert problems == [], problems
    slope = next(q for q in D.parts if q.pid == pid)
    fillers = [q for q in D.parts if q.tag == "filler"]
    assert [q.pid for q in fillers] == [f[0] for f in HOLLOW_END[pid]]
    for f in fillers:
        assert f.color == slope.color and D.parts[f.host] is slope
        for a in (0, 2):                                   # inside the slope's own footprint
            assert slope.box[a][0] - 0.1 <= f.box[a][0] and f.box[a][1] <= slope.box[a][1] + 0.1
    # the first sits flush with the slope's underside (LDraw y points down; boxes include studs);
    # a second (4-long slopes) sits exactly one plate higher, on top of the first
    assert abs(fillers[0].box[1][1] - slope.box[1][1]) < 0.1
    if len(fillers) == 2:
        assert abs(fillers[1].box[1][1] - (slope.box[1][1] - 8)) < 0.1


# ---------------------------------------------------------------- resource limits
# A spec comes from a model the user can steer, so none of these may be able
# to tie up a worker: each must be reported quickly (a SPEC error for anything
# that would mean unbounded work; a lone far-away part is simply loose).
HOSTILE = [
    "sculpt base=0 color=red\n  ball 0 0 0 5000 5000 5000\nend\n",
    "sculpt base=0 color=red\n  box 0..200 0..200 0..200\nend\n",
    "sculpt base=0 color=red\n  cyl y 0..100 0 0 900\nend\n",
    "plates 0 red 0..100000,0..100000\n",
    "plates 0 red 0..200,0..200\n",
    "stack 3001 red 0 0 0 1000000\n",
    "row 3005 red 0 0 0 5000\n",
    "bricks 0 red 0..3,0..3 courses=100000\n",
    "building 0..10,0..10 0 floors=500\n",
    "part 3001 red 99999999 0 0\n",
    "plates 0 red " + " ".join(f"+{64 * i}..{64 * i + 63},0..63" for i in range(16)) + "\n",
]


@pytest.mark.parametrize("line", HOSTILE)
def test_oversized_specs_are_rejected_quickly(line):
    import time
    t0 = time.time()
    _, problems, _ = run(BASE + line)
    assert time.time() - t0 < 5, "a hostile spec must not take long to reject"
    assert problems, "a hostile spec must be reported, never silently built"


def test_many_sculpts_cannot_add_up_past_the_total_limit():
    one = "sculpt base=0 color=red\n  box 0..29 0..59 0..9\nend\n"            # 18,000 cells each
    _, problems, _ = run(BASE + one * 4)
    assert any("too big" in p for p in problems), problems


def test_stepped_ldr_name_stays_on_one_line():
    from brickforge_designer.instructions import build_steps, stepped_ldr
    D, _, _ = run(spec("pickup"))
    text = stepped_ldr(D, build_steps(D), "a truck\n1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n0 STEP")
    assert text.splitlines()[0] == "0 a truck 1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat 0 STEP"
    assert sum(1 for ln in text.splitlines() if ln.startswith("1 ")) == len(D.parts)


@pytest.mark.parametrize("roof", ["flat", "gable", "hip"])
def test_a_full_width_multi_storey_building_is_one_piece(roof):
    # Regression: "a whole modular building at 32 studs" failed in production.
    # Floor slabs and flat roofs over a wide hollow interior left islands of
    # plates floating in the middle of the floor (only the rim rests on walls);
    # the model could not fix that from one `building` line.
    text = ("baseplate 0 0 light_bluish_gray\n"
            f"building 0..31,4..27 0 floors=4 color=tan trim=dark_tan roof={roof} windows=dense base=dark_bluish_gray\n")
    D, problems, stats = run(text)
    assert problems == [], problems
    assert stats["components"] == 1
    assert not any(r[0] == "slab" for r in stats["engine_repairs"]), stats["engine_repairs"]  # right first time
    assert len(D.parts) <= 2500


def test_a_wide_slab_uses_big_plates():
    # the staggered lattice keeps a 32x24 floor to large plates (jittered
    # retries also connect it, but with roughly twice the parts)
    from brickforge_designer.dsl import Interp
    from brickforge_designer.engine import PLATES
    it = Interp()
    it.walls(0, 31, 4, 27, 0, 6, [15])
    n0 = len(it.D.parts)
    it.slab({(x, z) for x in range(32) for z in range(4, 28)}, 18, [15], PLATES)
    slab = it.D.parts[n0:]
    assert len(slab) <= 110 and sum(q.pid == "3024" for q in slab) == 0
    assert it.D.is_one_piece(range(len(it.D.parts)))


# ---------------------------------------------------------------- no base: the table is the ground
FREE_ELEPHANT = """model elephant
sculpt base=0 color=light_bluish_gray hollow=2
  ball 8 14 0 6 10 3.5
  cyl y 0..8 4 -2 1.3
  cyl y 0..8 4 2 1.3
  cyl y 0..8 11 -2 1.3
  cyl y 0..8 11 2 1.3
  ball 15 20 0 3 8 2.5
  cyl x 17..21 16 0 1.2 0.6
  eye 16 22 pupil=black ring=white
end
"""


def test_a_free_standing_animal_with_no_base_is_one_piece_and_steady():
    D, problems, stats = run(FREE_ELEPHANT)
    assert problems == [], problems
    assert stats["pieces"] == [{"assembly": "main", "status": "main", "parts": len(D.parts)}]
    assert not any(q.pid in ("3811",) for q in D.parts)


def test_a_free_standing_car_stands_on_its_own_wheels():
    D, problems, stats = run("model t\nsculpt base=0 color=red\n  box 1..10 0..5 -2..1\n  wheels 2,7 size=large\nend\n")
    assert problems == [], problems
    lowest = max(q.box[1][1] for q in D.parts)
    assert {q.tag for q in D.parts if abs(q.box[1][1] - lowest) <= 1} == {"tyre"}   # only the tyres touch the table


def test_a_model_that_would_fall_over_on_the_table_is_reported():
    # a long beam on a 2x2 post at one end
    text = "model t\nsculpt base=0 color=red\n  box 0..1 0..8 0..1\n  box 0..15 9..11 0..3\nend\n"
    _, problems, _ = run(text)
    assert any(p.startswith("TIPS main") for p in problems), problems
    # the same beam balanced on a post under its middle stands
    _, problems, _ = run(text.replace("box 0..1 0..8 0..1", "box 7..8 0..8 1..2"))
    assert problems == [], problems


def test_a_based_model_is_never_reported_as_tipping():
    # all the weight far out to one side, but it is on a baseplate
    _, problems, _ = run(BASE + "bricks 0 red 0..3,0..3 courses=4\n")
    assert problems == [], problems


def test_a_small_separate_bit_on_the_table_is_loose_and_says_why():
    text = FREE_ELEPHANT + "sculpt base=0 color=blue\n  box 25..27 0..5 0..2\nend\n"    # > 3 parts: not pruned
    _, problems, _ = run(text)
    assert any("stands on the table by itself" in p for p in problems), problems


def test_a_big_separate_object_on_the_table_is_its_own_standing_piece():
    text = FREE_ELEPHANT + "sculpt base=0 color=blue\n  box 25..30 0..8 -3..2\nend\n"
    _, problems, stats = run(text)
    assert problems == [], problems
    assert sorted(p["status"] for p in stats["pieces"]) == ["main", "standing"]


def test_instructions_for_a_free_standing_model_start_on_the_table():
    from brickforge_designer.instructions import build_steps
    D, _, _ = run(FREE_ELEPHANT)
    steps = build_steps(D)
    assert sorted(i for s in steps for i in s.part_indices) == list(range(len(D.parts)))
    lowest = max(q.box[1][1] for q in D.parts)
    assert all(abs(D.parts[i].box[1][1] - lowest) <= 1 for i in steps[0].part_indices)


def test_region_terms_may_be_joined_or_spaced():
    # production: "SPEC line 11: bad rect '8..8,2..6+10..10,2..6+...'" failed a modular
    # building twice -- the designer wrote the terms without spaces
    joined = BASE + "plates 0 red 6..17,2..6-8..8,2..6-10..10,2..6\ntiles 1 blue 6..7,2..6+11..11,2..6\n"
    spaced = BASE + "plates 0 red 6..17,2..6 -8..8,2..6 - 10..10,2..6\ntiles 1 blue 6..7,2..6 +11..11,2..6\n"
    Dj, pj, _ = run(joined)
    Ds, ps, _ = run(spaced)
    assert pj == [] and ps == [], (pj, ps)
    cells = lambda D: sorted(D.occ)
    assert cells(Dj) == cells(Ds) and len(Dj.occ) == 12 * 5 - 2 * 5 + 3 * 5


def test_a_bad_region_error_says_how_to_write_one():
    _, problems, _ = run(BASE + "plates 0 red 8..8,2..6/10..10,2..6\n")
    assert any("then optional +x0..x1,z0..z1" in p for p in problems), problems


# ---------------------------------------------------------------- gradients and water (TECHNIQUES.md 1-2)
def _band(D, src, lo, hi, axis=2):
    return Counter(q.color for q in D.parts if q.src == src and lo * 20 <= q.box[axis][0] < hi * 20)


def test_a_fill_gradient_runs_along_its_axis_without_extra_parts():
    grad, problems, _ = run(BASE + "plates 0 dark_green>green>bright_green 0..31,0..15 along=z\n")
    plain, _, _ = run(BASE + "plates 0 green 0..31,0..15\n")
    assert problems == []
    near, far = _band(grad, 3, 0, 4), _band(grad, 3, 12, 16)
    assert near.most_common(1)[0][0] == 288 and far.most_common(1)[0][0] == 10, (near, far)
    # tiled as any colour, then each part coloured from the gradient: no fragmentation
    assert len(grad.parts) <= len(plain.parts) + 4


def test_a_sculpt_colour_gradient_runs_bottom_to_top():
    text = BASE + "sculpt base=0 color=dark_bluish_gray>white\n  box 4..11 0..29 4..11\nend\n"
    D, problems, _ = run(text)
    assert problems == [], problems
    by_level = lambda lo, hi: Counter(q.color for q in D.parts if q.src == 3 and q.color != 0
                                      and lo <= -q.box[1][1] / 8 < hi)
    assert by_level(0, 6).most_common(1)[0][0] == 72 and by_level(24, 31).most_common(1)[0][0] == 15


def test_a_gradient_paint_only_changes_its_own_cells():
    text = BASE + ("sculpt base=0 color=red\n  box 4..11 0..11 4..11\n"
                   "  paint yellow>orange 4..11 6..11 along=y\nend\n")
    D, problems, _ = run(text)
    assert problems == [], problems
    low = {q.color for q in D.parts if q.src == 3 and q.box[1][0] > -8 * 5}
    assert low <= {4, 0}, low                              # the lower half stays red (hidden cells: any)
    assert {14, 25} & {q.color for q in D.parts}


def test_gradient_errors_are_reported():
    _, problems, _ = run(BASE + "plates 0 red>blue 0..3,0..3 along=q\n")
    assert any("gradient axis" in p for p in problems), problems
    _, problems, _ = run(BASE + "plates 0 " + ">".join(["red"] * 7) + " 0..3,0..3\n")
    assert any("at most 6" in p for p in problems), problems


POND = BASE + "water 0 8..23,8..23\n"


def test_water_is_one_piece_with_a_smooth_surface_and_foam_at_the_shore():
    D, problems, stats = run(POND)
    assert problems == [] and stats["components"] == 1, problems
    top = [q for q in D.parts if q.tag == "water" and abs(q.box[1][1] + 8) < 1]
    assert top and all(q.pid in TILE_IDS or q.pid == "4073" for q in top)
    shore = lambda q: min(q.box[0][0], q.box[2][0]) < 9 * 20 or max(q.box[0][1], q.box[2][1]) > 23 * 20
    foam = [q for q in top if q.pid == "4073" and q.color == 15]
    assert foam and all(shore(q) for q in foam)


def test_water_deepens_away_from_the_shore_and_open_edges_are_not_shore():
    # a beach: sand on z 0..9, sea z 10..31 running off the baseplate's far edge
    D, problems, _ = run(BASE + "tiles 0 tan 0..31,0..9\nwater 0 0..31,10..31\n")
    assert problems == [], problems
    bed = [q for q in D.parts if q.tag == "water" and abs(q.box[1][1]) < 1]
    near = Counter(q.color for q in bed if q.box[2][0] < 14 * 20)
    far = Counter(q.color for q in bed if q.box[2][0] >= 26 * 20)
    assert near.most_common(1)[0][0] == 322 and far.most_common(1)[0][0] == 272, (near, far)
    white = [q for q in D.parts if q.pid == "4073" and q.color == 15]
    assert white and all(q.box[2][0] < 12 * 20 for q in white)        # foam only along the beach


def test_water_options_are_bounded():
    _, problems, _ = run(BASE + "water 0 0..3,0..3 ripples=5\n")
    assert any("ripples" in p for p in problems), problems
    _, problems, _ = run(BASE + "water 0 0..70,0..70\n")
    assert any("too big" in p for p in problems), problems


# ---------------------------------------------------------------- engine repairs: below the table, loose rescue
def test_sculpt_cells_below_level_0_are_clipped_and_parts_below_are_reported():
    # a bush whose ball dips one plate under the baseplate (seen in a real spec)
    D, problems, stats = run(BASE + "sculpt base=0 color=green\n  ball 10 2 8 2.5 3 1.5\nend\n")
    assert problems == [], problems
    assert any(r[0] == "clipped below the table" for r in stats["engine_repairs"])
    assert all(q.box[1][1] <= 1 for q in D.parts)
    _, problems, _ = run(BASE + "part 3001 red 4 4 0\npart 3001 red 10 4 -3\n")
    assert any(p.startswith("BELOW") and "line 4" in p for p in problems), problems


def test_small_loose_groups_on_a_hollow_ball_are_rescued():
    # the ball's diagonal cells near its widest point used to end up as 1x1 plate
    # stacks under a cap, held by nothing
    D, problems, stats = run(BASE + "sculpt base=0 color=light_bluish_gray hollow=2\n  ball 16 12 24 6 12 5\nend\n")
    assert problems == [], problems
    assert any(r[0] == "loose rescued" for r in stats["engine_repairs"])
    assert stats["components"] == 1


# ---------------------------------------------------------------- vehicle lights (TECHNIQUES.md item 4)
CAR_BODY = """model car
sculpt base=0 color=red
  box 0..13 0..5 -2..1
  box 4..10 6..10 -2..1
  wheels 2,10 size=large{opts}
end
"""


def test_a_wheeled_sculpt_gets_headlights_a_grille_and_tail_lights():
    D, problems, stats = run(CAR_BODY.format(opts=""))
    assert problems == [], problems
    c = Counter((q.pid, q.tag, q.color) for q in D.parts)
    assert c[("4070", "light", 4)] == 8                      # 4 across each end, in the body colour
    assert c[("98138", "lamp", 47)] == 2 and c[("98138", "lamp", 36)] == 2
    assert c[("2412b", "grille", 0)] == 1
    # the front (+x) lamps are clear, the back ones red
    front = [q for q in D.parts if q.tag == "lamp" and q.pos[0] > 140]
    assert front and all(q.color == 47 for q in front)
    assert stats["components"] == 1


def test_lamps_sit_in_the_headlight_brick_recess():
    D, _, _ = run(CAR_BODY.format(opts=""))
    for q in D.parts:
        if q.tag == "lamp" and q.host is not None:
            b = D.parts[q.host]
            front = q.pos[0] > b.pos[0]
            face = b.box[0][1] if front else b.box[0][0]          # 4 LDU inside the brick's outer face
            outer = b.pos[0] + (10 if front else -10)
            lamp_back = q.box[0][0] if front else q.box[0][1]
            assert abs(face - (outer - (4 if front else -4))) < 0.1
            assert abs(lamp_back - face) < 0.1                     # its underside rests on the recessed face


def test_lights_follow_the_front_option_and_can_be_switched_off():
    D, _, _ = run(CAR_BODY.format(opts=" front=-x"))
    front = [q for q in D.parts if q.tag == "lamp" and q.color == 47]
    assert front and all(q.pos[0] < 140 for q in front)
    D, problems, _ = run(CAR_BODY.format(opts=" lights=0"))
    assert problems == [] and not any(q.pid == "4070" for q in D.parts)
    D, problems, _ = run(CAR_BODY.format(opts=""), sideways="off")
    assert problems == [] and not any(q.pid == "4070" for q in D.parts)


def test_lights_go_on_the_nose_and_tail_not_on_a_cabin_further_back():
    D, _, _ = run(CAR_BODY.format(opts=""))
    body = [q for q in D.parts if q.asm == "vehicle1" and q.host is None and q.pid != "4600"]
    lo, hi = min(q.box[0][0] for q in body), max(q.box[0][1] for q in body)
    for q in D.parts:
        if q.tag == "light":                      # by grid cell: the brick's box is recessed at its face
            cell = int(q.pos[0] // 20)
            assert cell in (lo // 20, hi // 20 - 1), (cell, lo, hi)


def test_lights_that_would_split_the_body_are_dropped_not_failed():
    # a tail whose only flat patch sits over a notch (the real spec that showed it)
    text = """model car
sculpt base=0 color=red hollow=2
  box 1..22 0..4 -4..3
  box 0..23 0..3 -4..3
  box 0..6 5..7 -4..3
  box 1..6 4..5 -4..3
  box 0..1 7..8 -4..3
  wheels 4,18 size=large
end
"""
    D, problems, stats = run(text)
    assert problems == [], problems
    assert stats["components"] == 1


# ---------------------------------------------------------------- wedge plates and poly (TECHNIQUES.md item 5)
WING = """model wing
base 4..20,-6..5 dark_bluish_gray
stack 3941 light_bluish_gray 11 -1 2 3
sculpt base=11 color=white{opts}
  cyl x 2..22 2 0 2 1
  poly 1..2 8,-0.5 12,-11 15,-11 15,11 12,11 8,0.5
end
"""


def test_poly_is_a_plan_view_polygon_extruded_over_levels():
    from brickforge_designer.dsl import shape_cells
    tri = shape_cells("poly", ["0..1", "0,0", "4,0", "0,4"])
    assert {(x, z) for (x, y, z) in tri} == {(x, z) for x in range(4) for z in range(4) if x + z <= 2}
    assert {y for (_, y, _) in tri} == {0, 1}


def test_poly_is_bounded():
    _, problems, _ = run(BASE + "sculpt base=0 color=red\n  poly 0..200 0,0 400,0 0,400\nend\n")
    assert any("too big" in p for p in problems), problems
    _, problems, _ = run(BASE + "sculpt base=0 color=red\n  poly 0..1 0,0 4,0\nend\n")
    assert any("3 to 16" in p for p in problems), problems


def test_a_swept_wing_gets_wedge_plates_along_its_diagonal_edges():
    D, problems, stats = run(WING.format(opts=""))
    assert problems == [] and stats["components"] == 1, problems
    wedges = [q for q in D.parts if q.tag == "wedge"]
    assert {q.pid for q in wedges} >= {"43722", "43723"}
    # each wedge's tapered column fills the step beside its tread: every wedge
    # covers cells the sculpt itself left empty (that is what makes the edge diagonal)
    plain, _, _ = run(WING.format(opts=" wedges=0"))
    plain_cells = set(plain.occ)
    for q in wedges:
        cells = [c for c, i in D.occ.items() if D.parts[i] is q]
        assert any(c not in plain_cells for c in cells)


def test_wedges_are_never_stacked_on_the_same_cells():
    D, _, _ = run(WING.format(opts=""))
    seen = {}
    for c, i in D.occ.items():
        if D.parts[i].tag == "wedge":
            seen.setdefault((c[0], c[2]), set()).add(c[1])
    assert all(len(levels) == 1 for levels in seen.values())


def test_wedge_orientation_comes_from_the_measured_outline():
    # the outline is data from the LDraw geometry, and it is what decides the fit
    from brickforge_designer.engine import pdef
    for pid in ("24299", "24307", "43722", "43723", "41769", "41770"):
        P = pdef(pid)
        assert P.outline and len(P.outline) >= 4
        assert len(P.recv) == P.d if P.d > 1 else True      # grips only under its studded column


# ---------------------------------------------------------------- spikes and teeth (TECHNIQUES.md item 8)
SPINE = """model t
sculpt base=0 color=green hollow=2
  box 2..17 0..8 -3..3
end
"""


def test_scatter_on_top_follows_the_surface_and_clicks_on():
    D, problems, stats = run(SPINE + "scatter 4589 dark_green 3..16,0..0 top every=2\n")
    assert problems == [], problems
    cones = [q for q in D.parts if q.pid == "4589"]
    assert len(cones) == 7
    assert stats["components"] == 1                    # every cone clicks onto the body
    assert any(r[0] == "click-on" for r in stats["engine_repairs"])


def test_teeth_with_rot_alt_point_out_to_both_sides_of_the_row():
    D, problems, _ = run(SPINE + "scatter 49668 white 3..16,-3..-3 top every=2 rot=alt\n")
    assert problems == [], problems
    teeth = [q for q in D.parts if q.pid == "49668"]
    assert teeth
    # the tooth sticks out a stud past the plate across the row (z), never along it (x)
    for q in teeth:
        assert q.box[0][1] - q.box[0][0] == 20 and q.box[2][1] - q.box[2][0] == 40, q.box


# ---------------------------------------------------------------- large eyes (TECHNIQUES.md item 7)
OWL = """model owl
sculpt base=0 color=reddish_brown hollow=2
  box 2..9 0..11 -3..2
  box 3..9 12..22 -3..2
  eye 7 17 size=large pupil=black ring=white{opts}
end
"""


def test_a_large_eye_is_a_round_plate_on_two_side_studs_with_a_pupil_looking_forward():
    D, problems, stats = run(OWL.format(opts=""))
    assert problems == [] and stats["components"] == 1, problems
    plates = [q for q in D.parts if q.pid == "4032"]
    pupils = [q for q in D.parts if q.tag == "pupil"]
    assert len(plates) == 2 and len(pupils) == 2
    assert sum(q.pid == "87087" for q in D.parts) == 4
    for plate in plates:
        pupil = min(pupils, key=lambda q: abs(q.pos[2] - plate.pos[2]))
        assert pupil.pos[0] > plate.pos[0]                  # the front (+x) column
        assert pupil.pos[1] < plate.pos[1]                  # the upper row (LDraw y is down)
        assert abs(pupil.pos[2]) > abs(plate.pos[2])        # outside, on the plate


def test_a_large_eye_can_look_back_and_falls_back_to_small_without_room():
    D, _, _ = run(OWL.format(opts=" look=-x"))
    plates = [q for q in D.parts if q.pid == "4032"]
    assert plates and all(min((q for q in D.parts if q.tag == "pupil"), key=lambda q: abs(q.pos[2] - p.pos[2])).pos[0]
                          < p.pos[0] for p in plates)
    # a ball head has no flat 2x3 patch: the eye is painted, like a small one
    D, problems, stats = run(OWL.format(opts="").replace("box 3..9 12..22 -3..2", "ball 6 17 -0.5 4 7 3.5"))
    assert problems == [] and not any(q.pid == "4032" for q in D.parts)


# ---------------------------------------------------------------- facades (TECHNIQUES.md item 6)
def _house(opts):
    return run(BASE + f"building 6..21,8..21 0 floors=2 color=light_bluish_gray trim=dark_tan roof=gable {opts}\n")


def test_textured_walls_use_embossed_or_log_bricks():
    for tex, pid in (("masonry", "98283"), ("log", "30136")):
        D, problems, _ = _house(f"texture={tex}")
        assert problems == [], problems
        assert sum(q.pid == pid for q in D.parts) > 40


def test_quoins_are_only_at_the_corners():
    D, problems, _ = _house("quoins=tan")
    assert problems == [], problems
    quoin = [q for q in D.parts if q.color == 19]
    assert quoin
    for q in quoin:
        x0, x1 = q.box[0][0] / 20, q.box[0][1] / 20
        z0, z1 = q.box[2][0] / 20, q.box[2][1] / 20
        assert (x0 <= 6 or x1 >= 22) and (z0 <= 8 or z1 >= 22), q.box


def test_window_types():
    for kind, frame, glass in (("tall", "60593", "60602"), ("small", "60592", "60601"), ("arched", "60594", "60603")):
        D, problems, _ = _house(f"wintype={kind}")
        assert problems == [], (kind, problems)
        c = Counter(q.pid for q in D.parts)
        assert c[frame] > 0 and c[frame] == c[glass], (kind, c[frame], c[glass])
        if kind == "arched":
            assert c["3659"] == c[frame]
    _, problems, _ = _house("wintype=round")
    assert any("wintype" in p for p in problems)


# ---------------------------------------------------------------- slope-brick roofs (TECHNIQUES.md item 9)
@pytest.mark.parametrize("ridge", ["x", "z"])
def test_a_slope_brick_roof_faces_out_and_closes_with_a_ridge(ridge):
    D, problems, stats = run(BASE + f"building 6..21,8..19 0 floors=1 color=white roof=gable ridge={ridge} "
                                    f"roofstyle=slope roofcolor=dark_red\n")
    assert problems == [] and stats["components"] == 1, problems
    slopes = [q for q in D.parts if q.pid in ("3039", "3040b")]
    ridge_parts = [q for q in D.parts if q.pid in ("3043", "3044b")]
    assert slopes and ridge_parts
    top = min(q.box[1][0] for q in D.parts)
    assert all(abs(q.box[1][0] - top) < 1 for q in ridge_parts)          # the ridge is the highest row
    # every slope's low (sloped) side faces away from the ridge line
    axis = 2 if ridge == "x" else 0
    mid = (min(q.box[axis][0] for q in ridge_parts) + max(q.box[axis][1] for q in ridge_parts)) / 2
    for q in slopes:
        stud = next(p for p, d in q.studs if d == (0, -1, 0))
        centre = (q.box[axis][0] + q.box[axis][1]) / 2
        assert (stud[axis] - centre) * (centre - mid) < 0, (q.pos, stud)   # the stud row is on the ridge side


# ---------------------------------------------------------------- trees (TECHNIQUES.md item 3)
@pytest.mark.parametrize("style,part", [("round", "2417"), ("bush", "2423"), ("pine", "2435")])
def test_tree_styles_build_as_one_piece(style, part):
    D, problems, stats = run(BASE + f"tree 10 10 0 dark_green|green style={style}\n")
    assert problems == [] and stats["components"] == 1, problems
    assert any(q.pid == part for q in D.parts)


def test_a_round_tree_threads_its_leaves_on_the_trunk_at_quarter_turns():
    D, problems, _ = run(BASE + "tree 10 10 0 green style=round height=2 layers=3\n")
    assert problems == [], problems
    leaves = sorted((q for q in D.parts if q.pid == "2417"), key=lambda q: -q.pos[1])
    assert len(leaves) == 3 and len({q.mat for q in leaves}) == 3
    assert sum(q.pid == "3062b" for q in D.parts) == 4          # 2 trunk + one between each leaf pair
