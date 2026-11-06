from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace
from itertools import pairwise

import pytest

from nodelace import Activation, DiagramValidationError, check_diagram, parse_diagram, render
from nodelace.layout import layout_diagram
from nodelace.layout.router import label_bounds, segment_hits_rect

SVG = "{http://www.w3.org/2000/svg}"
SELF_CALL = (
    "sequence\nA -> A: first\n"
    "A -> B: a medium length label that needs two lines but is not truncated"
)


def test_two_line_message_label_cannot_erase_previous_self_call():
    diagram = parse_diagram(SELF_CALL)
    layout = layout_diagram(diagram)
    first, second = layout.messages
    bounds = label_bounds(second.label, second.label_position)
    assert bounds.height > 20
    assert min(bounds.y - point.y for point in first.points) >= 8
    assert not any(segment_hits_rect(a, b, bounds) for a, b in pairwise(first.points))
    assert check_diagram(diagram) == ()


def test_diagnostics_detect_message_labels_covering_other_messages(monkeypatch):
    import nodelace.diagnostics

    diagram = parse_diagram(SELF_CALL)
    layout = layout_diagram(diagram)
    first, second = layout.edges
    broken = replace(second, label_position=first.points[-1])
    monkeypatch.setattr(
        nodelace.diagnostics, "layout_diagram", lambda _: replace(layout, edges=(first, broken))
    )
    assert any(
        issue.code == "label-edge" and issue.severity == "error" for issue in check_diagram(diagram)
    )


@pytest.mark.parametrize("label", ["", ": a label extending beyond a participant lane"])
def test_nested_frames_enclose_self_calls_and_message_labels(label):
    diagram = parse_diagram(f'sequence\nopt "a"\nloop "b"\nA -> A{label}\nend\nend')
    layout = layout_diagram(diagram)
    message = layout.messages[0]
    for frame in layout.frames:
        assert all(frame.bounds.x < p.x < frame.bounds.right for p in message.points)
        assert all(frame.bounds.y < p.y < frame.bounds.bottom for p in message.points)
        if message.label:
            bounds = label_bounds(message.label, message.label_position)
            assert frame.bounds.x < bounds.x and bounds.right < frame.bounds.right
            assert frame.bounds.y < bounds.y and bounds.bottom < frame.bounds.bottom


def test_lifelines_connect_to_each_participant_with_mixed_header_heights():
    layout = layout_diagram(parse_diagram("sequence\nnode A tag=CLIENT\nA -> B: request"))
    assert len({participant.bounds.height for participant in layout.participants}) == 2
    assert all(p.lifeline_top == p.bounds.bottom for p in layout.participants)


def test_crossing_overlays_preserve_primary_and_return_semantics():
    root = ET.fromstring(render("architecture\nA => C\nB --> D\nA => D\nB --> C"))
    paths = list(root.iter(f"{SVG}path"))
    # Crossing overlays have no arrow marker, unlike the complete routes and legend entries.
    overlays = [
        p
        for p in paths
        if p.attrib.get("class", "").startswith("edge") and "marker-end" not in p.attrib
    ]
    assert overlays
    assert all(
        "kind-primary" in p.attrib["class"] or "kind-return" in p.attrib["class"] for p in overlays
    )
    assert {"kind-primary", "kind-return"} <= {
        token for p in overlays for token in p.attrib["class"].split()
    }


def test_duplicate_activation_ranges_fail_clearly():
    with pytest.raises(DiagramValidationError, match="duplicate activation"):
        parse_diagram("sequence\nactivate A\nactivate A\nA -> B\ndeactivate A\ndeactivate A")


def test_nested_activations_with_same_start_have_distinct_depths():
    source = "sequence\nactivate A\nactivate A\nA -> B\ndeactivate A\nB -> A\ndeactivate A"
    root = ET.fromstring(render(source))
    bars = [e for e in root.iter(f"{SVG}rect") if e.attrib.get("class") == "activation"]
    assert len(bars) == 2
    assert len({bar.attrib["x"] for bar in bars}) == 2


def test_direct_model_rejects_crossing_activation_ranges():
    diagram = parse_diagram("sequence\nA -> B\nB -> A\nA -> B")
    with pytest.raises(DiagramValidationError, match="nested or disjoint"):
        replace(diagram, activations=(Activation("A", 0, 2), Activation("A", 1, 3)))
    assert replace(diagram, activations=(Activation("A", 0, 2), Activation("B", 1, 3)))


def test_activation_extends_past_final_self_call_return():
    diagram = parse_diagram("sequence\nactivate A\nA -> A: work\ndeactivate A")
    layout = layout_diagram(diagram)
    root = ET.fromstring(render(diagram))
    bar = next(e for e in root.iter(f"{SVG}rect") if e.attrib.get("class") == "activation")
    assert int(bar.attrib["y"]) + int(bar.attrib["height"]) > max(
        point.y for point in layout.messages[-1].points
    )
