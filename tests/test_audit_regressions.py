from __future__ import annotations

import xml.etree.ElementTree as ET
from itertools import pairwise

import pytest

from nodelace import Theme, parse_diagram, render
from nodelace.layout import layout_diagram
from nodelace.layout.router import segment_hits_rect
from nodelace.text import text_width, wrap_text
from nodelace.theme import EDITORIAL_DARK, EDITORIAL_LIGHT

ROUTING = (
    'architecture "Routing probe"\nE -> A\nA -> E\nA -> B\nE -> D\nB -> E\nB -> D\nE -> F\nA -> F'
)


@pytest.mark.parametrize("label", ["W" * 30, "東京" * 15, "e\u0301" * 30, "SHIPPING_ORDER_ID" * 8])
def test_measured_labels_fit_and_preserve_identifiers(label: str) -> None:
    layout = layout_diagram(parse_diagram(f'architecture "Width"\n"{label}" -> API'))
    node = layout.nodes[0]
    lines = wrap_text(label, node.bounds.width - 28)
    assert all(text_width(line) <= node.bounds.width - 28 for line in lines)
    assert all(not line.startswith("\u0301") for line in lines)
    if "_" in label:
        assert "_" in "".join(lines)


@pytest.mark.parametrize("direction", ["left-to-right", "top-to-bottom"])
def test_routes_do_not_cross_unrelated_nodes(direction: str) -> None:
    source = ROUTING.replace("\nE -> A", f"\ndirection {direction}\nE -> A", 1)
    layout = layout_diagram(parse_diagram(source))
    for edge in layout.edges:
        for node in layout.nodes:
            assert not any(segment_hits_rect(a, b, node.bounds) for a, b in pairwise(edge.points))
    assert render(source, embed_fonts=False) == render(source, embed_fonts=False)


def test_inline_svgs_have_scoped_css_and_explicit_unique_ids() -> None:
    first = render("A -> B", embed_fonts=False, id_prefix="first")
    second = render("A -> B", theme=Theme(paper="#000000"), embed_fonts=False, id_prefix="second")
    assert "#first .canvas{" in first
    assert "#second .canvas{" in second
    ids = [
        {e.attrib["id"] for e in ET.fromstring(svg).iter() if "id" in e.attrib}
        for svg in (first, second)
    ]
    assert ids[0].isdisjoint(ids[1])
    assert (
        ET.fromstring(render("A -> B", theme=EDITORIAL_LIGHT)).attrib["id"]
        != (ET.fromstring(render("A -> B", theme=EDITORIAL_DARK)).attrib["id"])
    )


@pytest.mark.parametrize("prefix", ["", "1bad", "x y", "x{color:red}", 'x"onload'])
def test_invalid_instance_prefix_is_rejected(prefix: str) -> None:
    with pytest.raises(ValueError, match="id_prefix"):
        render("A -> B", id_prefix=prefix)


def test_html_preserves_canvas_width_and_scrolls_locally() -> None:
    html = render("A -> B", format="html", embed_fonts=False)
    assert "overflow-x:auto" in html
    assert "min-width:640px" in html
    assert "@media print" in html
    assert 'tabindex="0"' in html


def test_crossings_have_visible_hops() -> None:
    svg = render('architecture "Crossing"\nA -> C\nB -> D\nA -> D\nB -> C')
    assert 'class="crossing-halo"' in svg
