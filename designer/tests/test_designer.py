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
ATTACHED = {"60603", "60623", "4624", "3641"}


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
