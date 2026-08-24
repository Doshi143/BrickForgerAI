import pytest

from brickforge import Model, PartCatalog
from brickforge.pipeline.instructions import (
    bill_of_materials,
    build_steps,
    stepped_ldr_text,
    tally,
)

RED = 4
BLUE = 1


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_build_steps_partitions_every_brick_exactly_once_bottom_up(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)  # Plate 1x1, layer y=0
    model.place("3024", RED, 1, 0, 0)  # same layer
    model.place("3024", BLUE, 0, 1, 0)  # layer y=1
    model.place("3024", BLUE, 0, 2, 0)  # layer y=2

    steps = build_steps(model)

    assert [s.y_layer for s in steps] == [0, 1, 2]
    all_indices = [i for s in steps for i in s.brick_indices]
    assert sorted(all_indices) == [0, 1, 2, 3]
    assert set(steps[0].brick_indices) == {0, 1}
    assert steps[1].brick_indices == (2,)
    assert steps[2].brick_indices == (3,)
    assert [s.running_total for s in steps] == [2, 3, 4]
    assert steps[-1].running_total == len(model)


def test_build_steps_on_empty_model(catalog):
    model = Model(catalog=catalog)
    assert build_steps(model) == []


def test_tally_groups_by_part_and_colour(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    model.place("3024", RED, 1, 0, 0)
    model.place("3024", BLUE, 2, 0, 0)
    model.place("3005", RED, 0, 1, 0)  # Brick 1x1, different part

    rows = tally(model, range(len(model)))

    by_key = {(r.part_id, r.color_code): r.count for r in rows}
    assert by_key[("3024", RED)] == 2
    assert by_key[("3024", BLUE)] == 1
    assert by_key[("3005", RED)] == 1
    # Descending by count first -- the 2x plate/red row must lead.
    assert rows[0].part_id == "3024" and rows[0].color_code == RED


def test_tally_only_counts_the_given_indices(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    model.place("3024", RED, 1, 0, 0)

    rows = tally(model, [0])

    assert len(rows) == 1
    assert rows[0].count == 1


def test_bill_of_materials_covers_the_whole_model(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    model.place("3024", RED, 1, 0, 0)
    model.place("3005", BLUE, 0, 1, 0)

    rows = bill_of_materials(model)

    assert sum(r.count for r in rows) == len(model)


def test_stepped_ldr_text_inserts_step_between_layers_not_before_the_first(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)  # step 0
    model.place("3024", RED, 1, 0, 0)  # step 0
    model.place("3024", BLUE, 0, 1, 0)  # step 1

    steps = build_steps(model)
    text = stepped_ldr_text(model, steps, "test model")

    lines = text.splitlines()
    step_lines = [i for i, line in enumerate(lines) if line == "0 STEP"]
    part_lines = [i for i, line in enumerate(lines) if line.startswith("1 ")]

    # Exactly one STEP marker (2 steps -> 1 boundary), and it falls strictly
    # between the two layers' part lines, never before the very first part.
    assert len(step_lines) == 1
    assert part_lines[0] < step_lines[0] < part_lines[-1]
    assert len(part_lines) == 3


def test_stepped_ldr_text_reorders_lines_but_keeps_every_brick(catalog):
    model = Model(catalog=catalog)
    model.place("3024", BLUE, 0, 1, 0)  # placed first, but a HIGHER layer
    model.place("3024", RED, 0, 0, 0)  # placed second, but the ground layer

    steps = build_steps(model)
    text = stepped_ldr_text(model, steps, "test model")

    part_lines = [line for line in text.splitlines() if line.startswith("1 ")]
    assert len(part_lines) == 2
    # The ground-layer (red) brick's line must come first in the stepped
    # export, even though it was placed second in the original model.
    assert part_lines[0].startswith(f"1 {RED} ")
    assert part_lines[1].startswith(f"1 {BLUE} ")


def test_single_layer_model_has_no_step_markers(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    model.place("3024", RED, 1, 0, 0)

    steps = build_steps(model)
    text = stepped_ldr_text(model, steps, "test model")

    assert "0 STEP" not in text.splitlines()
