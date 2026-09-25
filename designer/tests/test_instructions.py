"""Build steps / parts lists for designer models (the Step 5 acceptance checks)."""
import os

import pytest

from brickforge_designer.engine import COLORS
from brickforge_designer.instructions import (COLOR_TABLE, bill_of_materials, build_steps, color_info, part_name,
                                              stepped_ldr, tally)
from brickforge_designer.pipeline import build

SPECS = os.path.join(os.path.dirname(__file__), "..", "specs")
MODELS = ("house", "toucan", "tudor2", "pickup", "giraffe")


def design(name):
    with open(os.path.join(SPECS, f"{name}.bfd"), encoding="utf-8") as f:
        return build(f.read())[0]


@pytest.fixture(scope="module", params=MODELS)
def built(request):
    D = design(request.param)
    return request.param, D, build_steps(D)


def test_every_part_is_in_exactly_one_step(built):
    _, D, steps = built
    seen = [i for s in steps for i in s.part_indices]
    assert sorted(seen) == list(range(len(D.parts)))
    assert steps[-1].running_total == len(D.parts)


def test_every_part_clicks_onto_something_already_built(built):
    _, D, steps = built
    step_of = {i: s.index for s in steps for i in s.part_indices}
    adj = D.graph()
    ground = {}                  # per section: underside height of its lowest part
    for s in steps:
        for i in s.part_indices:
            ground[s.section] = min(ground.get(s.section, 1e9), -D.parts[i].box[1][1])
    for s in steps:
        for i in s.part_indices:
            q = D.parts[i]
            if q.host is not None:
                continue
            if -q.box[1][1] > ground[s.section] + 0.5:
                # not on the ground: it clicks onto something already built (earlier or same step)
                assert any(step_of[m] <= s.index for m in adj[i]), (i, q.pid, s.index)


def test_attachments_share_their_host_step(built):
    _, D, steps = built
    step_of = {i: s.index for s in steps for i in s.part_indices}
    for i, q in enumerate(D.parts):
        if q.host is not None:
            assert step_of[i] == step_of[q.host], (q.pid, D.parts[q.host].pid)


def test_steps_stay_small(built):
    _, D, steps = built
    for s in steps:
        movers = [i for i in s.part_indices if D.parts[i].host is None]
        assert 1 <= len(movers) <= 8


def test_bill_of_materials_adds_up(built):
    _, D, steps = built
    bom = bill_of_materials(D)
    assert sum(r.count for r in bom) == len(D.parts)
    assert sum(r.count for s in steps for r in tally(D, s.part_indices)) == len(D.parts)
    assert all(not r.part_name.startswith(("~", "=")) for r in bom)


def test_vehicle_is_its_own_sub_build():
    D = design("house")
    steps = build_steps(D)
    labels = [s.section for s in steps]
    assert labels[0] == "Main model" and "Vehicle 1" in labels
    first_vehicle = labels.index("Vehicle 1")
    assert all(lbl == "Vehicle 1" for lbl in labels[first_vehicle:])
    for s in steps[first_vehicle:]:
        assert all(D.parts[i].asm.startswith("vehicle") for i in s.part_indices)


def test_glass_is_listed_as_transparent_with_a_real_name():
    D = design("house")
    rows = {r.part_id: r for r in bill_of_materials(D)}
    assert rows["60603"].part_name == "Glass for Window 1 x 4 x 3"
    assert rows["60603"].transparent


def test_colour_table_covers_every_designer_colour_and_names_redirects():
    assert set(COLOR_TABLE) == set(COLORS.values())
    assert color_info(47) == ("Trans Clear", (0xFC, 0xFC, 0xFC), True)
    assert part_name("3023") == "Plate 1 x 2" and part_name("4073") == "Plate 1 x 1 Round"
    assert part_name("3001") == "Brick 2 x 4"


def test_stepped_ldr_has_every_part_and_a_step_per_step(built):
    _, D, steps = built
    text = stepped_ldr(D, steps)
    assert sum(1 for ln in text.splitlines() if ln.startswith("1 ")) == len(D.parts)
    assert text.count("0 STEP") == len(steps) - 1
