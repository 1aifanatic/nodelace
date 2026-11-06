from __future__ import annotations

import builtins
import json
import xml.etree.ElementTree as ET
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from nodelace import (
    Activation,
    Diagram,
    DiagramValidationError,
    Edge,
    Fragment,
    Node,
    Theme,
    check_diagram,
    export_png,
    load_theme,
    parse_diagram,
    render,
)
from nodelace.cli import main
from nodelace.errors import NodelaceError
from nodelace.layout import Point, Rect, layout_diagram
from nodelace.presentation import SIZE_PRESETS
from nodelace.theme import THEMES, contrast_ratio

ROOT = Path(__file__).parents[1]
SVG = "{http://www.w3.org/2000/svg}"


def test_rejects_silent_shape_attribute_loss():
    for shape in ("decision", "merge"):
        with pytest.raises(DiagramValidationError, match="tags or sublabels"):
            Node("A", shape=shape, sublabel="Important")
        with pytest.raises(DiagramValidationError, match="participants"):
            Diagram(kind="sequence", nodes=(Node("A", shape=shape),))


def test_rejects_overlapping_sibling_frames_and_cross_branch_nesting():
    nodes = (Node("A"), Node("B"))
    edges = (Edge("A", "B"),) * 4
    for frames in (
        (Fragment("opt", "outer", 0, 4), Fragment("opt", "inner", 1, 3)),
        (Fragment("alt", "yes", 0, 4, 2, "no"), Fragment("opt", "inner", 1, 3, depth=1)),
    ):
        with pytest.raises(DiagramValidationError):
            Diagram(kind="sequence", nodes=nodes, edges=edges, fragments=frames)


def test_target_sizes_have_distinct_default_scopes():
    a = ET.fromstring(render("A -> B"))
    b = ET.fromstring(render("A -> B", size="slide-16x9"))
    assert a.attrib["id"] != b.attrib["id"]


def test_shortening_is_reported_and_full_guards_are_accessible():
    diagram = parse_diagram('sequence "' + "W" * 200 + '"\nopt "' + "W" * 200 + '"\nA -> B\nend')
    codes = {issue.code for issue in check_diagram(diagram)}
    assert {"truncated-title", "truncated-guard"} <= codes
    root = ET.fromstring(render(diagram))
    assert "W" * 200 in root.find(f"{SVG}desc").text


@pytest.mark.parametrize("source", sorted((ROOT / "examples/styles").glob("*.diagram")))
@pytest.mark.parametrize("skin", THEMES)
def test_showcase_is_complete_deterministic_and_passes_publication_check(source, skin):
    diagram = parse_diagram(source.read_text(encoding="utf-8"))
    theme = THEMES[skin]
    assert check_diagram(diagram, theme=theme) == ()
    output = render(diagram, theme=theme)
    assert output == render(diagram, theme=theme)
    assert (source.parent / f"{source.stem}-{skin}.svg").read_bytes() == output.encode()
    root = ET.fromstring(output)
    assert root.find(f"{SVG}title").text == diagram.title
    assert len(root.findall(f".//{SVG}g[@aria-label]")) >= len(diagram.nodes)


def test_semantic_arrows_preserve_labels_and_quoted_syntax():
    diagram = parse_diagram("""architecture "Roles"
node "A -> B" label="A label" role=external tag=WEB sublabel="Printed: ID_1"
"A -> B" -> C --> D ~> E => F: "keep -> and ~> literally"
call F -> G: sync
""")
    assert diagram.nodes[0].id == "A -> B"
    assert diagram.nodes[0].sublabel == "Printed: ID_1"
    assert [e.kind for e in diagram.edges] == ["normal", "return", "async", "primary", "call"]
    assert diagram.edges[3].label == "keep -> and ~> literally"
    assert "role-external" in render(diagram)


def test_merge_and_decision_shapes_attach_to_visible_perimeters():
    diagram = parse_diagram("""flow "Shapes"
node A shape=decision label="Accept?"
node B shape=merge
node C shape=terminal
A -> B: yes
B -> C
""")
    layout = layout_diagram(diagram)
    assert check_diagram(diagram) == ()
    assert "<polygon" in render(diagram)
    assert 'class="merge"' in render(diagram)
    assert 'rx="20"' in render(diagram)
    for edge in layout.edges:
        assert all(a.x == b.x or a.y == b.y for a, b in pairwise(edge.points))


def test_nested_sequence_frames_and_self_messages_reserve_guard_space():
    source = """sequence "Nested"
node A tag=CLIENT
node B tag=SERVER
activate B
opt "request present"
A -> B: request
loop "three retries"
B -> B: retry
end
B --> A: result
end
deactivate B
"""
    diagram = parse_diagram(source)
    layout = layout_diagram(diagram)
    outer, inner = layout.frames
    assert outer.bounds.y < inner.bounds.y < inner.bounds.bottom < outer.bounds.bottom
    assert outer.bounds.x <= inner.bounds.x < inner.bounds.right <= outer.bounds.right
    assert layout.messages[1].y > inner.bounds.y + 60
    output = render(diagram, embed_fonts=False)
    assert "[three retries]" in output and "[request present]" in output
    assert 'class="activation"' in output
    assert len(diagram.activations) == 1


def test_alt_has_two_visible_guards_and_an_internal_divider():
    diagram = parse_diagram(
        'sequence\nalt "ok"\nA => B: accepted\nelse "failed"\nA --> B: denied\nend'
    )
    frame = layout_diagram(diagram).frames[0]
    assert frame.bounds.y < frame.divider_y < frame.bounds.bottom
    svg = render(diagram)
    assert "[ok]" in svg and "[failed]" in svg
    assert "kind-return" in svg and "kind-primary" in svg
    root = ET.fromstring(svg)
    guards = [e for e in root.iter() if "fragment-guard" in e.attrib.get("class", "")]
    assert len(guards) == 2
    assert "paint-order:stroke" in svg


@pytest.mark.parametrize(
    "body",
    [
        "node",
        "node A role=rainbow",
        "node A color=red",
        "node A role=store role=input",
        "node A\nnode A",
        "node A shape=cloud",
        'node A tag=""',
        'alt "guard"\nA -> B',
        'else "no"',
        "end",
        "end extra",
        "deactivate A",
        "activate A\nA -> B",
        "activate A\ndeactivate A",
        'alt "a"\nA -> B\nend',
        'alt "a"\nA -> B\nelse "b"\nelse "c"',
        'opt "a"\nelse "b"',
        'opt "a"\nopt "b"\nopt "c"',
        'alt "a"\nelse "b"\nA -> B\nend',
    ],
)
def test_new_syntax_rejects_ambiguous_or_unclosed_input(body):
    with pytest.raises(NodelaceError):
        parse_diagram("sequence\n" + body)


def test_sequence_directives_are_not_silently_flattened_into_flows():
    with pytest.raises(DiagramValidationError, match="sequence"):
        parse_diagram('flow\nopt "x"\nA -> B\nend')


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Node("A", role=[]),
        lambda: Node("A", shape=[]),
        lambda: Edge("A", "B", kind=[]),
        lambda: Fragment("parallel", "x", 0, 1),
        lambda: Fragment("opt", "x", 1, 1),
        lambda: Fragment("alt", "x", 0, 1),
        lambda: Fragment("opt", "x", 0, 1, split=1),
        lambda: Fragment("opt", "x", 0, 1, depth=2),
        lambda: Activation("A", 1, 1),
        lambda: Diagram(fragments=("bad",)),
        lambda: Diagram(activations=("bad",)),
        lambda: Diagram(fragments=(Fragment("opt", "x", 0, 1),)),
    ],
)
def test_new_public_model_values_validate_at_construction(factory):
    with pytest.raises(DiagramValidationError):
        factory()


def test_sequence_model_rejects_out_of_range_and_crossing_frames():
    base = dict(
        kind="sequence", nodes=(Node("A"), Node("B")), edges=tuple(Edge("A", "B") for _ in range(4))
    )
    for additions in (
        dict(fragments=(Fragment("opt", "x", 0, 5),)),
        dict(fragments=(Fragment("opt", "x", 0, 3), Fragment("opt", "y", 2, 4))),
        dict(fragments=(Fragment("opt", "x", 0, 1, depth=1),)),
        dict(activations=(Activation("missing", 0, 1),)),
        dict(activations=(Activation("A", 0, 5),)),
        dict(fragments=tuple(Fragment("opt", "x", 0, 1) for _ in range(13))),
    ):
        with pytest.raises(DiagramValidationError):
            Diagram(**base, **additions)


@pytest.mark.parametrize("skin", THEMES)
def test_each_theme_passes_text_and_essential_mark_contrast(skin):
    theme = THEMES[skin]
    for role in ("ink", "muted"):
        for surface in ("paper", "surface", "accent_soft", "group_fill"):
            assert contrast_ratio(getattr(theme, role), getattr(theme, surface)) >= 4.5
    for surface in ("paper", "surface", "accent_soft"):
        assert contrast_ratio(theme.accent, getattr(theme, surface)) >= 3


def test_toml_profiles_support_named_base_and_safe_overrides(tmp_path):
    path = tmp_path / "brand.toml"
    path.write_text('[theme]\nbase="dark"\naccent="#abcdef"')
    assert load_theme(path) == replace(THEMES["dark"], accent="#abcdef")
    assert load_theme(ROOT / "examples/styles/blueprint.toml").accent == "#2456a6"


@pytest.mark.parametrize(
    "data",
    [
        "",
        "[other]\nx=1",
        '[theme]\nbase="wrong"',
        "[theme]\nbase=[]",
        '[theme]\nfont="remote"',
        '[theme]\nink="url(http://bad)"',
        "[theme]\nink=12",
        "[theme]\n" + "#comment\n" * 3000,
    ],
)
def test_profiles_fail_closed(tmp_path, data):
    path = tmp_path / "invalid.toml"
    path.write_text(data)
    with pytest.raises(ValueError):
        load_theme(path)


def test_layout_checks_surface_density_truncation_focus_and_contrast():
    diagram = parse_diagram('node A label="' + "W" * 200 + '"\nA -> B -> C\nhighlight A,B,C')
    codes = {i.code for i in check_diagram(diagram, theme=Theme(ink="#ffffff"))}
    assert {"focus", "truncated-label", "contrast"} <= codes
    huge = parse_diagram(" -> ".join(f"N{i}" for i in range(15)))
    assert {"density", "canvas", "size"} <= {i.code for i in check_diagram(huge, size="doc-inline")}
    assert check_diagram(Diagram())[0].code == "empty"
    decision = parse_diagram("node A shape=decision\nA -> B\nA -> C\nA -> D\nA -> E")
    assert {"decision-exits", "decision-label"} <= {i.code for i in check_diagram(decision)}


def test_checker_detects_known_bad_geometry_independently(monkeypatch):
    import nodelace.diagnostics as module

    diagram = parse_diagram("A -> B: one\nB -> C: two")
    layout = layout_diagram(diagram)
    nodes = tuple(replace(n, bounds=Rect(100, 100, 80, 60)) for n in layout.nodes)
    edges = tuple(
        replace(e, points=(Point(80, 120), Point(200, 120)), label_position=Point(120, 120))
        for e in layout.edges
    )
    monkeypatch.setattr(
        module, "layout_diagram", lambda _: replace(layout, nodes=nodes, edges=edges)
    )
    assert {"node-overlap", "edge-node", "label-node", "label-overlap"} <= {
        i.code for i in check_diagram(diagram)
    }


@pytest.mark.parametrize("size,dimensions", SIZE_PRESETS.items())
def test_destination_presets_preserve_requested_size(size, dimensions):
    root = ET.fromstring(render("A -> B", size=size, embed_fonts=False))
    assert (int(root.attrib["width"]), int(root.attrib["height"])) == dimensions
    assert root.attrib["viewBox"] == f"0 0 {dimensions[0]} {dimensions[1]}"
    assert check_diagram(parse_diagram("A -> B"), size=size) == ()


def test_cli_theme_size_profile_and_layout_failures(tmp_path, capsys):
    source = tmp_path / "test.diagram"
    source.write_text("A -> B")
    target = tmp_path / "test.html"
    assert (
        main(["render", str(source), "-o", str(target), "--theme", "dark", "--size", "doc-inline"])
        == 0
    )
    assert "#2d3142" in target.read_text()
    assert (
        main(
            [
                "check",
                str(source),
                "--strict",
                "--profile",
                str(ROOT / "examples/styles/blueprint.toml"),
            ]
        )
        == 0
    )
    source.write_text("A -> B -> C\nhighlight A,B,C")
    assert main(["check", str(source), "--layout"]) == 0
    assert main(["check", str(source), "--strict"]) == 2
    assert "focus" in capsys.readouterr().err
    bad = tmp_path / "bad.toml"
    bad.write_text('[theme]\nink="#ffffff"')
    assert main(["check", str(source), "--layout", "--profile", str(bad)]) == 2
    assert main(["render", str(source), "--id-prefix", "bad prefix"]) == 2
    assert main(["export", str(source), "-o", str(source)]) == 2


def test_png_export_validation_and_missing_optional_extra(tmp_path, monkeypatch):
    for path, options in (
        (tmp_path / "a.svg", {}),
        (tmp_path / "a.png", {"scale": 0}),
        (tmp_path / "a.png", {"scale": True}),
    ):
        with pytest.raises(ValueError):
            export_png("A -> B", path, **options)
    path = tmp_path / "existing.png"
    path.write_bytes(b"keep")
    with pytest.raises(ValueError, match="already exists"):
        export_png("A -> B", path)
    original = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("not installed")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    with pytest.raises(NodelaceError, match=r"nodelace\[png\]"):
        export_png("A -> B", tmp_path / "new.png")
    assert not (tmp_path / "new.png").exists()


def test_font_metrics_are_bundled_and_derive_from_real_font_advances():
    data = json.loads((ROOT / "src/nodelace/assets/font-metrics.json").read_text())
    assert set(data) == {"sans", "serif", "mono"}
    assert data["sans"]["W"] > data["sans"]["i"]
    assert data["mono"]["W"] == data["mono"]["i"]
