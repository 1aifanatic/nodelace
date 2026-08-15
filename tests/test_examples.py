from __future__ import annotations

import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pytest

from nodelace import parse_diagram
from nodelace.model import DiagramKind
from nodelace.renderer import render_svg

ROOT = Path(__file__).parents[1]
EXAMPLE_PATHS = tuple(sorted((ROOT / "examples").glob("*.diagram")))
RENDERED_PATHS = tuple(sorted((ROOT / "examples" / "rendered").glob("*.svg")))


class _GalleryReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "img" and values.get("src"):
            self.images.append(values["src"] or "")
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")


@pytest.mark.parametrize("path", EXAMPLE_PATHS, ids=lambda path: path.stem)
def test_every_example_parses_and_renders_valid_deterministic_svg(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    diagram = parse_diagram(source, source_name=str(path))

    first = render_svg(diagram, embed_fonts=False)
    second = render_svg(diagram, embed_fonts=False)

    assert first == second
    assert ET.fromstring(first).tag == "{http://www.w3.org/2000/svg}svg"
    assert "<script" not in first.lower()
    assert "NaN" not in first
    assert "Infinity" not in first
    assert len(diagram.nodes) <= 50

    golden = ROOT / "examples" / "rendered" / f"{path.stem}.svg"
    assert golden.read_bytes() == render_svg(diagram).encode("utf-8")


def test_examples_cover_the_three_public_diagram_kinds() -> None:
    kinds = [
        parse_diagram(path.read_text(encoding="utf-8"), source_name=str(path)).kind
        for path in EXAMPLE_PATHS
    ]

    assert kinds.count(DiagramKind.ARCHITECTURE) == 4
    assert kinds.count(DiagramKind.FLOW) == 3
    assert kinds.count(DiagramKind.SEQUENCE) == 3
    assert len(RENDERED_PATHS) == len(EXAMPLE_PATHS) == 10


def test_examples_cover_groups_highlights_labels_cycles_and_unicode() -> None:
    diagrams = [
        parse_diagram(path.read_text(encoding="utf-8"), source_name=str(path))
        for path in EXAMPLE_PATHS
    ]
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in EXAMPLE_PATHS)

    assert any(diagram.groups for diagram in diagrams)
    assert all(diagram.highlights for diagram in diagrams)
    assert any(edge.label for diagram in diagrams for edge in diagram.edges)
    assert "left-to-right" in all_text
    assert "top-to-bottom" in all_text
    assert "東京" in all_text
    assert "Café" in all_text


def test_example_gallery_links_all_sources_and_rendered_outputs() -> None:
    gallery = ROOT / "examples" / "index.html"
    references = _GalleryReferences()
    references.feed(gallery.read_text(encoding="utf-8"))

    assert len(references.images) == 10
    assert len(references.links) == 10
    assert all((gallery.parent / reference).is_file() for reference in references.images)
    assert all((gallery.parent / reference).is_file() for reference in references.links)
