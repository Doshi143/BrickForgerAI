"""Phase B: does the structural graph actually understand a SNOT branch,
or does it still see one as a floating island? Each test here is the kind
of measurement this project insists on before trusting a claim -- see
structure/graph.py's own module docstring for what `_add_snot_edges` is
supposed to guarantee.
"""

import networkx as nx
import pytest

from brickforge.lattice import GridPos, Rotation
from brickforge.model import Model
from brickforge.parts import PartCatalog
from brickforge.snot import SnotChild
from brickforge.structure.graph import GROUND, build_connectivity_graph
from brickforge.structure.load import propagate_gravity_load
from brickforge.structure.report import analyze
from brickforge.structure.weakpoints import find_bricks_outside_main_component, find_ungrounded_bricks

_CATALOG = PartCatalog.load_default()


def _grounded_model(part_id: str = "30414") -> Model:
    model = Model(catalog=_CATALOG)
    model.place(part_id, 4, 0, 0, 0)  # y=0 -- grounded
    return model


def test_snot_branch_is_no_longer_misclassified_as_disconnected():
    # "Before" (simulated directly, not by disabling real code, so this
    # test can't rot silently if _add_snot_edges is later refactored):
    # Phase A's graph could have a SNOT node added with no edges at all,
    # since build_connectivity_graph didn't know how to connect one --
    # that node is its own singleton component and gets flagged outside
    # the main mass.
    before = nx.Graph()
    before.add_node(GROUND)
    before.add_node(0)
    before.add_edge(GROUND, 0, studs=None)
    before.add_node(("snot", 0))
    assert ("snot", 0) in find_bricks_outside_main_component(before)

    # "After": the real thing.
    model = _grounded_model()
    plate = _CATALOG.get("3710")  # Plate 1 x 4 -- spans all 4 of 30414's side studs
    children = [SnotChild(parent_index=0, part=plate, local_pos=GridPos(0, 0, 0))]

    after = build_connectivity_graph(model, children)
    assert ("snot", 0) not in find_bricks_outside_main_component(after)
    assert nx.node_connected_component(after, ("snot", 0)) == nx.node_connected_component(after, GROUND)


def test_parent_to_child_edge_weight_matches_real_stud_overlap():
    model = _grounded_model()
    wide_plate = _CATALOG.get("3710")  # Plate 1x4, footprint [4, 1] -- spans all 4 studs
    narrow_plate = _CATALOG.get("3024")  # Plate 1x1 -- spans exactly 1 stud, at index 2
    children = [
        SnotChild(parent_index=0, part=wide_plate, local_pos=GridPos(0, 0, 0)),
        SnotChild(parent_index=0, part=narrow_plate, local_pos=GridPos(2, 0, 0)),
    ]

    graph = build_connectivity_graph(model, children)
    assert graph[0][("snot", 0)]["studs"] == 4
    assert graph[0][("snot", 1)]["studs"] == 1


def test_child_not_flush_against_parent_gets_no_parent_edge():
    # local_pos.y != 0 means this child isn't resting against the parent's
    # own molded stud(s) at all -- it should only ever connect to whatever
    # it's actually stacked on, never straight to the parent.
    model = _grounded_model("87087")
    plate = _CATALOG.get("3024")
    children = [SnotChild(parent_index=0, part=plate, local_pos=GridPos(0, 1, 0))]

    graph = build_connectivity_graph(model, children)
    assert not graph.has_edge(0, ("snot", 0))


def test_stacked_snot_children_connect_to_each_other():
    model = _grounded_model("87087")
    plate = _CATALOG.get("3024")
    children = [
        SnotChild(parent_index=0, part=plate, local_pos=GridPos(0, 0, 0)),
        SnotChild(parent_index=0, part=plate, local_pos=GridPos(0, 1, 0)),
    ]

    graph = build_connectivity_graph(model, children)
    assert graph.has_edge(0, ("snot", 0))
    assert graph.has_edge(("snot", 0), ("snot", 1))
    assert graph[("snot", 0)][("snot", 1)]["studs"] == 1
    assert not graph.has_edge(0, ("snot", 1))  # not flush against the parent itself


def test_non_overlapping_children_at_the_same_layer_do_not_connect():
    # Two children on the SAME parent+face, same local_pos.y, at DIFFERENT
    # in-plane positions that don't overlap -- side by side, not stacked.
    # No edge should appear between them (matches the ordinary top/bottom
    # grid: side-by-side parts never share a stud connection in this
    # catalog either).
    model = _grounded_model()
    plate = _CATALOG.get("3024")
    children = [
        SnotChild(parent_index=0, part=plate, local_pos=GridPos(0, 0, 0)),
        SnotChild(parent_index=0, part=plate, local_pos=GridPos(1, 0, 0)),
    ]

    graph = build_connectivity_graph(model, children)
    assert not graph.has_edge(("snot", 0), ("snot", 1))


def test_snot_child_referencing_a_non_snot_parent_raises():
    model = Model(catalog=_CATALOG)
    model.place("3005", 4, 0, 0, 0)  # ordinary 1x1 brick, no side_stud_face
    plate = _CATALOG.get("3024")
    children = [SnotChild(parent_index=0, part=plate, local_pos=GridPos(0, 0, 0))]

    with pytest.raises(ValueError):
        build_connectivity_graph(model, children)


def test_find_ungrounded_bricks_does_not_crash_with_snot_nodes_present():
    # find_ungrounded_bricks is directed and doesn't understand SNOT edges
    # (see its own docstring) -- it must skip them safely, not crash
    # indexing model.bricks by a ("snot", i) tuple.
    model = _grounded_model()
    plate = _CATALOG.get("3710")
    children = [SnotChild(parent_index=0, part=plate, local_pos=GridPos(0, 0, 0))]
    graph = build_connectivity_graph(model, children)
    result = find_ungrounded_bricks(graph, model)
    assert result == set()  # the one ordinary brick is grounded directly


def test_propagate_gravity_load_does_not_crash_with_snot_nodes_present():
    # Grounded brick0 alone would `continue` before ever reaching the
    # down_neighbors line (graph.has_edge(i, GROUND) short-circuits) --
    # that wouldn't actually exercise the isinstance(n, int) guard this
    # test is for. Stack an UNgrounded SNOT parent (brick1) on top of it
    # instead, so brick1's own down_neighbors lookup genuinely has to walk
    # past its ("snot", 0) neighbor without crashing on model.bricks[n].
    model = Model(catalog=_CATALOG)
    model.place("3005", 4, 0, 0, 0)  # grounded 1x1x3 brick
    model.place("87087", 4, 0, 3, 0)  # stacked on top, not grounded itself
    plate = _CATALOG.get("3024")
    children = [SnotChild(parent_index=1, part=plate, local_pos=GridPos(0, 0, 0))]

    graph = build_connectivity_graph(model, children)
    assert graph.has_edge(1, ("snot", 0))
    result = propagate_gravity_load(graph, model)
    assert result.floating_bricks == []  # brick1 rests on brick0, not floating


def test_analyze_end_to_end_with_a_snot_branch_reports_a_single_connected_piece():
    model = _grounded_model()
    wide_plate = _CATALOG.get("3710")
    children = [
        SnotChild(parent_index=0, part=wide_plate, local_pos=GridPos(0, 0, 0)),
        SnotChild(parent_index=0, part=wide_plate, local_pos=GridPos(0, 1, 0)),
    ]

    report = analyze(model, children)
    assert report.is_single_piece
    assert report.critical_bricks == set()

    # Omitting snot_children (the default) must remain byte-for-byte the
    # pre-Phase-B behavior -- no crash, no SNOT nodes anywhere.
    plain_report = analyze(model)
    assert plain_report.is_single_piece
    assert plain_report.critical_bricks == set()
