from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from nodelace import Diagram, Edge, Node, Theme, parse_diagram, render
from nodelace.layout import Point, layout_diagram
from nodelace.renderer import (
    DiagramDensityWarning,
    _ellipsize,
    _label_lines,
    _rounded_path,
    render_html,
    render_svg,
)

SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture
def architecture_source() -> str:
    return '''architecture "Order & Fulfilment"
direction left-to-right
Customer -> API: submits <order>
API -> Database: writes
API -> Payments: authorizes
group Backend: API, Database, Payments
highlight API
'''


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def test_svg_has_accessible_first_children_and_stable_ids(architecture_source: str) -> None:
    output = render(architecture_source)
    root = _root(output)
    children = list(root)

    assert root.tag == f"{SVG}svg"
    assert root.attrib["role"] == "img"
    assert children[0].tag == f"{SVG}title"
    assert children[1].tag == f"{SVG}desc"
    assert children[0].text == "Order & Fulfilment"
    labelled_by = root.attrib["aria-labelledby"].split()
    assert labelled_by == [children[0].attrib["id"], children[1].attrib["id"]]
    assert "Customer to API" in (children[1].text or "")


def test_svg_is_script_free_offline_and_embeds_all_fonts(architecture_source: str) -> None:
    output = render(architecture_source)

    assert output.count("@font-face") == 4
    assert "data:font/woff2;base64," in output
    assert "<script" not in output.lower()
    assert 'href="http' not in output.lower()
    assert 'src="http' not in output.lower()
    assert "url(http" not in output.lower()
    assert "@import" not in output.lower()
    assert "FOCUS" in output
    assert "SIL OPEN FONT LICENSE Version 1.1" in output
    assert "The Instrument Serif Project Authors" in output
    assert "The Geist Project Authors" in output


def test_system_font_mode_is_smaller_but_remains_valid_svg(architecture_source: str) -> None:
    diagram = parse_diagram(architecture_source)
    embedded = render_svg(diagram)
    system = render_svg(diagram, embed_fonts=False)

    assert len(system) < len(embedded) / 5
    assert "base64," not in system
    assert "SIL OPEN FONT LICENSE" not in system
    assert _root(system).attrib["role"] == "img"


def test_same_model_is_byte_identical(architecture_source: str) -> None:
    diagram = parse_diagram(architecture_source)

    assert render_svg(diagram) == render_svg(diagram)


def test_host_namespace_registration_cannot_change_svg_bytes(
    architecture_source: str,
) -> None:
    diagram = parse_diagram(architecture_source)
    before = render_svg(diagram, embed_fonts=False)
    namespace_map = ET._namespace_map.copy()  # type: ignore[attr-defined]
    try:
        ET.register_namespace("svg", "http://www.w3.org/2000/svg")
        after = render_svg(diagram, embed_fonts=False)
    finally:
        ET._namespace_map.clear()  # type: ignore[attr-defined]
        ET._namespace_map.update(namespace_map)  # type: ignore[attr-defined]

    assert after == before


def test_xml_escapes_user_controlled_text(architecture_source: str) -> None:
    output = render(architecture_source)
    root = _root(output)

    assert "Order &amp; Fulfilment" in output
    assert "submits &lt;order&gt;" in output
    assert root.find(f"{SVG}title").text == "Order & Fulfilment"


def test_html_is_static_self_contained_and_contains_svg(architecture_source: str) -> None:
    diagram = parse_diagram(architecture_source)
    output = render_html(diagram)

    assert output.startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in output
    assert "Content-Security-Policy" in output
    assert "<script" not in output.lower()
    assert 'href="http' not in output.lower()
    assert 'src="http' not in output.lower()
    assert "url(http" not in output.lower()
    assert "data:font/woff2;base64," in output
    assert "<svg " in output


def test_html_wrapper_uses_custom_theme_paper_color(architecture_source: str) -> None:
    diagram = parse_diagram(architecture_source)

    output = render_html(
        diagram,
        embed_fonts=False,
        theme=Theme(paper="#123456"),
    )

    assert "html,body{margin:0;background:#123456}" in output
    assert ".canvas{fill:#123456;}" in output


def test_format_dispatch_rejects_unknown_format(architecture_source: str) -> None:
    with pytest.raises(ValueError, match="format must be"):
        render(architecture_source, format="pdf")  # type: ignore[arg-type]


def test_sequence_renders_participants_lifelines_and_messages() -> None:
    source = '''sequence "Sign in"
Browser -> API: credentials
API -> Identity: verify
Identity -> API: accepted
API -> Browser: session
highlight API
'''

    output = render(source, embed_fonts=False)

    assert output.count('class="lifeline"') == 3
    assert output.count('class="message"') == 4
    assert "Participant Browser" in output
    assert "Message API to Identity" in output


def test_sequence_self_message_uses_a_visible_loop_and_preserves_order() -> None:
    diagram = parse_diagram('sequence "Retry"\nWorker -> Worker: retry locally')

    layout = layout_diagram(diagram)
    output = render_svg(diagram, embed_fonts=False)
    message = layout.messages[0]

    assert message.self_message is True
    assert len(message.points) == 4
    assert message.points[0].x == message.points[-1].x
    assert max(point.x for point in message.points) > message.points[0].x
    assert message.points[-1].y > message.points[0].y
    assert "retry locally" in output


def test_programmatic_node_labels_drive_accessible_relationship_text() -> None:
    diagram = Diagram(
        kind="architecture",
        title="Display labels",
        nodes=(
            Node("auth_internal", "Authentication"),
            Node("portal_internal", "Customer Portal"),
        ),
        edges=(Edge("portal_internal", "auth_internal", "signs in"),),
    )

    output = render_svg(diagram, embed_fonts=False)
    root = _root(output)
    description = root.find(f"{SVG}desc")
    relationships = [
        group.attrib["aria-label"]
        for group in root.findall(f".//{SVG}g")
        if " to " in group.attrib.get("aria-label", "")
    ]

    assert "Customer Portal to Authentication, signs in" in (description.text or "")
    assert relationships == ["Customer Portal to Authentication"]
    assert "portal_internal" not in output
    assert "auth_internal" not in output


def test_density_warning_does_not_drop_content() -> None:
    edges = "\n".join(f"N{index} -> N{index + 1}" for index in range(21))
    source = f'flow "Large but complete"\n{edges}'

    with pytest.warns(DiagramDensityWarning):
        output = render(source, embed_fonts=False)

    for index in range(22):
        assert f"N{index}" in output


def test_path_rounding_handles_empty_degenerate_and_orthogonal_routes() -> None:
    assert _rounded_path(()) == ""
    assert _rounded_path((Point(0, 0), Point(0, 0), Point(8, 0))) == (
        "M 0 0 L 0 0 L 8 0"
    )
    assert " Q " in _rounded_path((Point(0, 0), Point(20, 0), Point(20, 20)))


def test_long_labels_wrap_to_two_bounded_lines() -> None:
    lines = _label_lines("A very long node label with several separate words", 120)

    assert len(lines) == 2
    assert lines[-1].endswith("…")


def test_long_edge_label_is_visually_bounded_but_preserved_accessibly() -> None:
    label = "a detailed relationship label " * 15
    source = f'flow "Long relationship"\nStart -> Finish: "{label.strip()}"'

    output = render(source, embed_fonts=False)
    root = _root(output)
    description = root.find(f"{SVG}desc")
    label_text = root.find(f".//{SVG}text[@class='edge-label']")
    lines = list(label_text) if label_text is not None else []

    assert label.strip() in (description.text or "")
    assert len(lines) == 2
    assert (lines[-1].text or "").endswith("…")


@pytest.mark.parametrize(
    "body",
    [
        "A -> A: {label}\nA -> B\nB -> C",
        "A -> B\nB -> C\nC -> C: {label}",
    ],
)
def test_long_sequence_self_message_mask_stays_inside_viewbox(body: str) -> None:
    label = "x" * 500
    output = render(
        'sequence "Self message"\n' + body.format(label=label),
        embed_fonts=False,
    )
    root = _root(output)
    viewbox = [int(value) for value in root.attrib["viewBox"].split()]
    mask = root.find(f".//{SVG}rect[@class='edge-label-bg']")

    assert mask is not None
    left = int(mask.attrib["x"])
    top = int(mask.attrib["y"]) + 104
    right = left + int(mask.attrib["width"])
    bottom = top + int(mask.attrib["height"])
    assert viewbox[0] <= left <= right <= viewbox[2]
    assert viewbox[1] <= top <= bottom <= viewbox[3]


def test_long_title_and_group_name_are_visually_bounded_but_accessible() -> None:
    title = "A deliberately long diagram title " * 5
    group = "A deliberately long group name " * 5
    source = f'architecture "{title.strip()}"\nA -> B\ngroup "{group.strip()}": A, B'

    root = _root(render(source, embed_fonts=False))
    accessible_title = root.find(f"{SVG}title")
    visual_title = root.find(f"{SVG}text[@class='title']")
    group_element = root.find(f".//{SVG}g[@aria-label='Group {group.strip()}']")
    group_label = group_element.find(f"{SVG}text") if group_element is not None else None

    assert accessible_title is not None and accessible_title.text == title.strip()
    assert visual_title is not None and (visual_title.text or "").endswith("…")
    assert group_element is not None
    assert group_label is not None and (group_label.text or "").endswith("…")


def test_ellipsize_preserves_short_text_and_bounds_long_text() -> None:
    assert _ellipsize("short", 5) == "short"
    assert _ellipsize("longer", 5) == "long…"
