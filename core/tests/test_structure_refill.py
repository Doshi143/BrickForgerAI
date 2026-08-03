import pytest

from brickforge import Model, PartCatalog
from brickforge.structure import analyze
from brickforge.structure.refill import refill_enclosed_holes

RED = 4
BLUE = 1


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_cell_with_grounded_support_below_is_refilled(catalog):
    # A 1x1 plate at y=0 (grounded) with a gap directly above it at y=1 --
    # refilling the gap gives it a genuine stud connection straight down
    # to grounded material.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    removed_brick = model.place("3024", RED, 0, 1, 0)  # placeholder to build the "removed" list

    trimmed = Model(catalog=catalog)
    trimmed.place("3024", RED, 0, 0, 0)

    result = refill_enclosed_holes(trimmed, removed=[removed_brick])

    assert result.refilled == [(0, 1, 0)]
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_cell_with_nothing_below_is_not_refilled_even_if_surrounded_laterally(catalog):
    # A gap at y=1 with nothing at all beneath it (y=0 is empty at this
    # x,z), but fully boxed in on all 4 lateral sides at y=1. The old
    # enclosure-based rule would have refilled this; the new rule must not,
    # since there's no stud connection holding it up -- pure lateral
    # friction doesn't count.
    model = Model(catalog=catalog)
    for x, z in [(0, 1), (2, 1), (1, 0), (1, 2)]:
        model.place("3024", RED, x, 1, z)  # ring around (1,1) at y=1, itself floating (nothing at y=0)
    removed_brick = model.place("3024", RED, 1, 1, 1)

    trimmed = Model(catalog=catalog)
    for x, z in [(0, 1), (2, 1), (1, 0), (1, 2)]:
        trimmed.place("3024", RED, x, 1, z)

    result = refill_enclosed_holes(trimmed, removed=[removed_brick])

    assert result.refilled == []
    assert len(result.model) == len(trimmed)


def test_refill_cascades_upward_through_a_removed_stack(catalog):
    # Two removed cells stacked at (0,1,0) and (0,2,0), above a grounded
    # base at (0,0,0). Refilling (0,1,0) first must unlock (0,2,0) in the
    # same call, even though at the start of the pass (0,2,0) had nothing
    # grounded beneath it yet.
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    removed_1 = model.place("3024", RED, 0, 1, 0)
    removed_2 = model.place("3024", RED, 0, 2, 0)

    trimmed = Model(catalog=catalog)
    trimmed.place("3024", RED, 0, 0, 0)

    result = refill_enclosed_holes(trimmed, removed=[removed_1, removed_2])

    assert set(result.refilled) == {(0, 1, 0), (0, 2, 0)}
    report = analyze(result.model)
    assert report.ungrounded_bricks == set()


def test_no_removed_bricks_is_a_no_op(catalog):
    model = Model(catalog=catalog)
    model.place("3024", RED, 0, 0, 0)
    result = refill_enclosed_holes(model, removed=[])
    assert result.refilled == []
    assert result.model is model


def test_refill_color_matches_a_present_neighbor_not_the_removed_brick(catalog):
    model = Model(catalog=catalog)
    model.place("3024", BLUE, 0, 0, 0)
    removed_brick_wrong_color = model.place("3024", RED, 0, 1, 0)

    trimmed = Model(catalog=catalog)
    trimmed.place("3024", BLUE, 0, 0, 0)

    result = refill_enclosed_holes(trimmed, removed=[removed_brick_wrong_color])

    refilled_brick = next(b for b in result.model if b.pos == removed_brick_wrong_color.pos)
    assert refilled_brick.color == BLUE
