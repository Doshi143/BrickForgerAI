import pytest

from brickforge import Model, PartCatalog
from brickforge.structure import (
    GROUND,
    analyze,
    build_connectivity_graph,
    build_heatmap_model,
    classify_bricks,
    find_articulation_points,
    find_bridges,
    find_disconnected_components,
    prune_unstable,
    propagate_gravity_load,
)
from brickforge.structure.heatmap import COLOR_CRITICAL, COLOR_OK, COLOR_WARNING
from brickforge.structure.weakpoints import find_bricks_outside_main_component, find_ungrounded_bricks

RED = 4


@pytest.fixture(scope="module")
def catalog():
    return PartCatalog.load_default()


def test_two_stacked_2x2_bricks_share_four_studs(catalog):
    model = Model(catalog=catalog)
    model.place("3003", RED, 0, 0, 0)  # 2x2 brick at y=0
    model.place("3003", RED, 0, 3, 0)  # 2x2 brick stacked directly on top
    graph = build_connectivity_graph(model)
    assert graph.has_edge(0, 1)
    assert graph[0][1]["studs"] == 4
    assert graph.has_edge(GROUND, 0)


def test_non_overlapping_bricks_are_not_connected(catalog):
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)  # 1x1 at x=0
    model.place("3005", RED, 5, 0, 0)  # 1x1 far away, same layer, no vertical relationship
    graph = build_connectivity_graph(model)
    assert not graph.has_edge(0, 1)


def test_chain_of_single_stud_bricks_are_all_articulation_points(catalog):
    # A 5-tall tower of 1x1 bricks, each connected to the next by exactly
    # one stud: every brick except the very top is a cut vertex (removing
    # any one disconnects everything above it from the ground).
    model = Model(catalog=catalog)
    for y in range(0, 15, 3):
        model.place("3005", RED, 0, y, 0)
    graph = build_connectivity_graph(model)
    points = find_articulation_points(graph)
    # indices 0..3 (all but the topmost brick) must be articulation points
    assert points == {0, 1, 2, 3}


def test_floating_brick_is_detected(catalog):
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)  # grounded
    model.place("3005", RED, 5, 4, 5)  # nothing underneath, not touching anything
    graph = build_connectivity_graph(model)
    load = propagate_gravity_load(graph, model)
    assert load.floating_bricks == [1]


def test_isolated_piece_is_its_own_component(catalog):
    # find_disconnected_components deliberately excludes GROUND itself
    # (see its own docstring) -- a real bug that used to live here: GROUND
    # connects to every y=0 brick, so brick0 and GROUND used to be
    # (falsely) counted as one 2-node component. Both bricks are single,
    # otherwise-unconnected 1x1s, so with GROUND excluded the honest
    # answer is two separate 1-node components -- neither is "more
    # connected" than the other just for one of them touching the floor.
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)  # grounded
    model.place("3005", RED, 9, 9, 9)  # far away, floating, touching nothing
    graph = build_connectivity_graph(model)
    components = find_disconnected_components(graph)
    assert len(components) == 2
    sizes = sorted(len(c) for c in components)
    assert sizes == [1, 1]


def test_grounded_single_stack_has_no_floating_bricks(catalog):
    model = Model(catalog=catalog)
    for y in range(0, 9, 3):
        model.place("3001", RED, 0, y, 0)  # 2x4 bricks stacked, well supported
    graph = build_connectivity_graph(model)
    load = propagate_gravity_load(graph, model)
    assert load.floating_bricks == []


def test_load_accumulates_upward_bricks_weight_downward(catalog):
    model = Model(catalog=catalog)
    model.place("3001", RED, 0, 0, 0)
    model.place("3001", RED, 0, 3, 0)
    graph = build_connectivity_graph(model)
    load = propagate_gravity_load(graph, model)
    # the lower brick must carry at least its own weight plus the upper one's
    assert load.cumulative_load[0] > load.own_weight[0]
    assert load.cumulative_load[0] >= load.own_weight[0] + load.own_weight[1]
    assert load.edge_load[(0, 1)] == pytest.approx(load.own_weight[1])


def test_overloaded_connection_is_flagged_with_a_tiny_capacity(catalog):
    model = Model(catalog=catalog)
    model.place("3001", RED, 0, 0, 0)
    model.place("3001", RED, 0, 3, 0)
    graph = build_connectivity_graph(model)
    load = propagate_gravity_load(graph, model, capacity_per_stud=0.0001)
    assert len(load.overloaded_edges) >= 1


def test_heatmap_classifies_floating_brick_as_critical(catalog):
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)
    model.place("3005", RED, 5, 4, 5)
    report = analyze(model)
    colors = classify_bricks(report)
    assert colors[1] == COLOR_CRITICAL
    assert colors[0] in (COLOR_OK, COLOR_WARNING)


def test_heatmap_model_preserves_geometry(catalog):
    model = Model(catalog=catalog)
    model.place("3001", RED, 0, 0, 0)
    model.place("3001", RED, 0, 3, 0)
    report = analyze(model)
    heatmap = build_heatmap_model(report)
    assert len(heatmap) == len(model)
    for original, recolored in zip(model, heatmap):
        assert original.part.id == recolored.part.id
        assert original.pos == recolored.pos
        assert original.rotation == recolored.rotation


def test_brick_resting_on_a_floating_brick_is_also_ungrounded(catalog):
    # Regression test for a real bug: the original "floating brick" check
    # only looked one hop down (does this brick have ANY neighbor below
    # it), so a brick resting on top of an unsupported brick had a
    # non-empty down_neighbors list and was wrongly treated as fine. It
    # isn't -- its entire support chain terminates at something that
    # itself isn't grounded. find_ungrounded_bricks must catch this
    # transitively, in one pass, with no iteration.
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)  # grounded
    model.place("3005", RED, 5, 4, 5)  # floating: nothing below it at all
    model.place("3005", RED, 5, 7, 5)  # rests ON the floating brick above -- also ungrounded
    graph = build_connectivity_graph(model)

    assert graph.has_edge(1, 2)  # they really are connected to each other
    ungrounded = find_ungrounded_bricks(graph, model)
    assert ungrounded == {1, 2}


def test_single_hop_floating_check_alone_would_have_missed_the_cascade(catalog):
    # Same setup as above, phrased as a direct comparison: propagate_gravity_load's
    # single-hop floating_bricks list only catches index 1, not the brick
    # resting on it (index 2) -- which is exactly why report.py and
    # repair.py use find_ungrounded_bricks instead, not this list, to
    # decide what's actually structurally sound.
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)
    model.place("3005", RED, 5, 4, 5)
    model.place("3005", RED, 5, 7, 5)
    graph = build_connectivity_graph(model)
    load = propagate_gravity_load(graph, model)
    assert load.floating_bricks == [1]  # incomplete on its own -- 2 is missing
    assert find_ungrounded_bricks(graph, model) == {1, 2}  # the correct, complete answer


def test_prune_unstable_converges_in_a_single_pass(catalog):
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)
    model.place("3005", RED, 5, 4, 5)
    model.place("3005", RED, 5, 7, 5)  # cascade case: rests on the floating brick
    model.place("3005", RED, 9, 9, 9)  # a fully isolated brick too

    result = prune_unstable(model)

    assert len(result.removed) == 3
    assert len(result.model) == 1
    # re-analyzing the pruned model must show nothing left ungrounded
    report_after = analyze(result.model)
    assert report_after.ungrounded_bricks == set()
    assert report_after.is_single_piece


def test_prune_unstable_is_a_no_op_on_a_sound_model(catalog):
    model = Model(catalog=catalog)
    model.place("3001", RED, 0, 0, 0)
    model.place("3001", RED, 0, 3, 0)
    result = prune_unstable(model)
    assert result.removed == []
    assert len(result.model) == len(model)


def test_undirected_connectivity_sees_a_keystone_the_directed_check_misses(catalog):
    # The exact case that made find_ungrounded_bricks the wrong check to
    # drive repair (see weakpoints.py's module docstring): a brick with
    # NOTHING directly below it, but braced into the main mass by a plate
    # spanning it and a separately-grounded column -- like a keystone held
    # by lateral compression, not by resting on the ground itself.
    #
    #   G1(6,0,5) -- G2(6,3,5) -- G3(6,6,5) [a separate grounded column]
    #   X(5,4,5) [floating: nothing below it at all]
    #   Y(5,7,5), footprint (2,1) spanning x=5..6 -- rests on BOTH X and G3
    #
    # X has no down-neighbor of its own, so the strict directed check
    # (correctly, by its own definition) calls it ungrounded. But X is
    # connected to Y, and Y is also grounded via G3 -- so under undirected
    # connectivity X is part of the same rigid mass as GROUND, and nothing
    # about it is actually going to fall off.
    model = Model(catalog=catalog)
    model.place("3005", RED, 6, 0, 5)  # G1: grounded
    model.place("3005", RED, 6, 3, 5)  # G2: rests on G1
    model.place("3024", RED, 6, 6, 5)  # G3: rests on G2, a 1-plate cap at top=7
    x_brick = model.place("3005", RED, 5, 4, 5)  # X: floating, nothing below
    model.place("3023", RED, 5, 7, 5)  # Y: spans x=5..6, rests on both X and G3

    x_index = model.bricks.index(x_brick)
    graph = build_connectivity_graph(model)

    assert x_index in find_ungrounded_bricks(graph, model)  # strict check still (correctly) flags it
    assert x_index not in find_bricks_outside_main_component(graph)  # but it's not actually isolated

    result = prune_unstable(model)
    assert result.removed == []  # repair must NOT remove X -- it's fine
    assert len(result.model) == len(model)


def test_bridges_include_the_only_ground_connection(catalog):
    # A single brick is the ONLY thing touching the ground under a whole
    # tower: that ground edge is a bridge by definition.
    model = Model(catalog=catalog)
    model.place("3005", RED, 0, 0, 0)
    model.place("3005", RED, 0, 3, 0)
    graph = build_connectivity_graph(model)
    bridges = find_bridges(graph)
    assert (GROUND, 0) in bridges or (0, GROUND) in bridges
