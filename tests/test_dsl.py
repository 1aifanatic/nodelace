from __future__ import annotations

from pathlib import Path

import pytest

from nodelace.dsl import parse_diagram
from nodelace.errors import DiagramSyntaxError, DiagramValidationError
from nodelace.model import Diagram, DiagramKind, Direction, Edge, Group, Node


def test_parses_titled_architecture_chain_in_source_order() -> None:
    result = parse_diagram(
        '''architecture "Order system"
direction left-to-right

Browser -> API -> Database
''',
        source_name="order.diagram",
    )

    assert result.kind is DiagramKind.ARCHITECTURE
    assert result.title == "Order system"
    assert result.direction is Direction.LEFT_TO_RIGHT
    assert result.nodes == (Node("Browser"), Node("API"), Node("Database"))
    assert result.edges == (Edge("Browser", "API"), Edge("API", "Database"))


def test_parses_comments_labels_groups_and_highlights() -> None:
    result = parse_diagram(
        '''# commerce overview
architecture "Global Café"

Browser -> API: HTTPS  # transport
API -> München: replicate
group Edge: Browser, API
group Regions: München
highlight API, München
'''
    )

    assert result.nodes == (Node("Browser"), Node("API"), Node("München"))
    assert result.edges == (
        Edge("Browser", "API", "HTTPS"),
        Edge("API", "München", "replicate"),
    )
    assert result.groups == (
        Group("Edge", ("Browser", "API")),
        Group("Regions", ("München",)),
    )
    assert result.highlights == ("API", "München")


def test_quoted_names_preserve_syntax_unicode_and_supported_escapes() -> None:
    result = parse_diagram(
        r'''flow "Say \"hello\" \\ café"
"Web -> client" -> "API: v2": "call #1 // local"
group "Core, tier": "Web -> client", "API: v2"
highlight "API: v2"
'''
    )

    assert result.kind is DiagramKind.FLOW
    assert result.title == 'Say "hello" \\ café'
    assert result.nodes == (Node("Web -> client"), Node("API: v2"))
    assert result.edges == (Edge("Web -> client", "API: v2", "call #1 // local"),)
    assert result.groups == (Group("Core, tier", ("Web -> client", "API: v2")),)
    assert result.highlights == ("API: v2",)


def test_duplicate_direction_reports_the_exact_source_line() -> None:
    with pytest.raises(DiagramValidationError) as caught:
        parse_diagram(
            "A -> B\ndirection left-to-right\ndirection top-to-bottom\n",
            source_name="duplicate.diagram",
        )

    error = caught.value
    assert error.source_name == "duplicate.diagram"
    assert error.line == 3
    assert error.line_text == "direction top-to-bottom"
    assert error.message == "direction may only be specified once"
    assert str(error).startswith("duplicate.diagram:3: direction may only be specified once")


@pytest.mark.parametrize(
    ("source", "line", "message"),
    [
        (
            "group Services: API\ngroup Services: Worker\n",
            2,
            "group 'Services' is already defined",
        ),
        (
            "group Services: API, API\n",
            1,
            "group 'Services' lists node 'API' more than once",
        ),
        (
            "group Frontend: API\ngroup Backend: API\n",
            2,
            "node 'API' cannot belong to both 'Frontend' and 'Backend'",
        ),
        (
            "highlight API\nhighlight Worker, API\n",
            2,
            "node 'API' is already highlighted",
        ),
    ],
)
def test_rejects_ambiguous_duplicate_grouping_and_highlights(
    source: str, line: int, message: str
) -> None:
    with pytest.raises(DiagramValidationError) as caught:
        parse_diagram(source)

    assert caught.value.line == line
    assert caught.value.message == message


def test_accepts_50_nodes_and_rejects_the_51st_at_its_line() -> None:
    fifty_nodes = "\n".join(f"N{index} -> N{index + 1}" for index in range(49))
    assert len(parse_diagram(fifty_nodes).nodes) == 50

    fifty_one_nodes = "\n".join(f"N{index} -> N{index + 1}" for index in range(50))
    with pytest.raises(DiagramValidationError) as caught:
        parse_diagram(fifty_one_nodes, source_name="crowded.diagram")

    assert caught.value.line == 50
    assert caught.value.message == (
        "diagram has more than 50 nodes (first extra node is 'N50')"
    )


@pytest.mark.parametrize(
    ("accepted", "rejected", "line", "message"),
    [
        (
            "\n".join(["A -> B"] * 200),
            "\n".join(["A -> B"] * 201),
            201,
            "diagram has more than 200 edges",
        ),
        (
            "\n".join(f"group G{i}: N{i}" for i in range(20)),
            "\n".join(f"group G{i}: N{i}" for i in range(21)),
            21,
            "diagram has more than 20 groups",
        ),
        (
            f"A -> B: {'x' * 500}",
            f"A -> B: {'x' * 501}",
            1,
            "edge label is longer than 500 characters",
        ),
    ],
)
def test_resource_limits_are_inclusive_and_line_specific(
    accepted: str, rejected: str, line: int, message: str
) -> None:
    parse_diagram(accepted)

    with pytest.raises(DiagramValidationError) as caught:
        parse_diagram(rejected)

    assert caught.value.line == line
    assert caught.value.message == message


def test_omitted_header_defaults_to_flow_and_chain_label_applies_only_to_final_edge() -> None:
    result = parse_diagram("Draft order -> Validate order -> Submit order: accepted")

    assert result.kind is DiagramKind.FLOW
    assert result.title is None
    assert result.edges == (
        Edge("Draft order", "Validate order"),
        Edge("Validate order", "Submit order", "accepted"),
    )


@pytest.mark.parametrize(
    ("source", "kind", "node_ids"),
    [
        ('\ufeffflow "BOM header"\nA -> B', DiagramKind.FLOW, ("A", "B")),
        ("\ufeffA -> B", DiagramKind.FLOW, ("A", "B")),
    ],
)
def test_accepts_one_leading_utf8_bom_without_polluting_the_model(
    source: str, kind: DiagramKind, node_ids: tuple[str, ...]
) -> None:
    result = parse_diagram(source)

    assert result.kind is kind
    assert result.node_ids == node_ids


@pytest.mark.parametrize(
    ("source", "line", "message"),
    [
        ("A ->\n", 1, "node name cannot be empty"),
        ("A -> B:\n", 1, "edge label cannot be empty"),
        ("group Backend\n", 1, "a group needs ':' followed by one or more members"),
        ("group Backend:\n", 1, "group member cannot be empty"),
        ("highlight\n", 1, "highlight needs one or more comma-separated node names"),
        (
            "direction diagonal\nA -> B\n",
            1,
            "direction must be 'left-to-right' or 'top-to-bottom'",
        ),
        ("architecture Order system\nA -> B\n", 1, "diagram title must be enclosed"),
        (r'A -> "bad\n"' "\n", 1, "unsupported escape"),
        ('A -> "unterminated\n', 1, "unterminated quoted"),
        (
            'flow "One"\nsequence "Two"\nA -> B\n',
            2,
            "diagram type header must be the first statement",
        ),
        ('state "Unsupported"\nA -> B\n', 1, "unsupported diagram type 'state'"),
    ],
)
def test_malformed_input_has_a_friendly_line_specific_syntax_error(
    source: str, line: int, message: str
) -> None:
    with pytest.raises(DiagramSyntaxError) as caught:
        parse_diagram(source, source_name="broken.diagram")

    assert caught.value.source_name == "broken.diagram"
    assert caught.value.line == line
    assert message in caught.value.message
    assert caught.value.line_text == source.splitlines()[line - 1]


@pytest.mark.parametrize(
    ("accepted", "rejected", "message"),
    [
        (
            f'architecture "{"t" * 200}"\nA -> B',
            f'architecture "{"t" * 201}"\nA -> B',
            "diagram title is longer than 200 characters",
        ),
        (
            f'{"n" * 200} -> B',
            f'{"n" * 201} -> B',
            "node name is longer than 200 characters",
        ),
    ],
)
def test_text_length_limits_count_unicode_characters(
    accepted: str, rejected: str, message: str
) -> None:
    parse_diagram(accepted)

    with pytest.raises(DiagramValidationError) as caught:
        parse_diagram(rejected)

    assert caught.value.line == 1
    assert caught.value.message == message


def test_rejects_control_characters_but_accepts_non_ascii_unicode() -> None:
    unicode_diagram = parse_diagram('München -> 東京: café 🚀')
    assert unicode_diagram.node_ids == ("München", "東京")
    assert unicode_diagram.edges[0].label == "café 🚀"

    with pytest.raises(DiagramValidationError) as caught:
        parse_diagram('A -> "bad\x00name"')

    assert caught.value.line == 1
    assert caught.value.message == "node name contains a control character"


def test_xml_noncharacter_keeps_source_aware_parser_diagnostic() -> None:
    with pytest.raises(DiagramValidationError) as caught:
        parse_diagram("A -> B\ufffe", source_name="unsafe.diagram")

    assert caught.value.source_name == "unsafe.diagram"
    assert caught.value.line == 1
    assert caught.value.message == "node name contains an XML-unsafe character"
    assert r"\ufffe" in str(caught.value)


@pytest.mark.parametrize(
    ("directive", "message"),
    [
        ("direction left-to-right", "direction is not supported for sequence diagrams"),
        ("group Services: API", "groups are not supported for sequence diagrams"),
    ],
)
def test_sequence_rejects_directives_with_no_sequence_semantics(
    directive: str, message: str
) -> None:
    with pytest.raises(DiagramValidationError) as caught:
        parse_diagram(f'sequence "Request"\n{directive}\nBrowser -> API: request')

    assert caught.value.line == 2
    assert caught.value.message == message


def test_direct_model_construction_is_immutable_and_normalizes_public_values() -> None:
    result = Diagram(
        kind="architecture",  # type: ignore[arg-type]
        nodes=[Node("API"), Node("DB")],  # type: ignore[arg-type]
        edges=[Edge("API", "DB", "query")],  # type: ignore[arg-type]
        groups=[Group("Backend", ("API", "DB"))],  # type: ignore[arg-type]
        highlights=["API"],  # type: ignore[arg-type]
        direction="left-to-right",  # type: ignore[arg-type]
    )

    assert result.kind is DiagramKind.ARCHITECTURE
    assert result.direction is Direction.LEFT_TO_RIGHT
    assert isinstance(result.nodes, tuple)
    assert isinstance(result.edges, tuple)
    assert isinstance(result.groups, tuple)
    assert isinstance(result.highlights, tuple)
    with pytest.raises((AttributeError, TypeError)):
        result.title = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: Node("bad\x00id"), "node id contains a control character"),
        (lambda: Edge("A", "B", ""), "edge label cannot be empty"),
        (
            lambda: Diagram(title="bad\x00title", nodes=(Node("A"),)),
            "diagram title contains a control character",
        ),
        (
            lambda: Diagram(nodes=(Node("A"), Node("A"))),
            "node id 'A' is defined more than once",
        ),
        (
            lambda: Diagram(nodes=(Node("A"),), edges=(Edge("A", "Missing"),)),
            "edge target 'Missing' is not a defined node",
        ),
        (
            lambda: Diagram(
                nodes=(Node("A"),), groups=(Group("Unknown", ("Missing",)),)
            ),
            "group 'Unknown' references undefined node 'Missing'",
        ),
        (
            lambda: Diagram(nodes=(Node("A"),), highlights=("Missing",)),
            "highlight references undefined node 'Missing'",
        ),
        (
            lambda: Diagram(nodes=tuple(Node(f"N{i}") for i in range(51))),
            "diagram has more than 50 nodes",
        ),
        (
            lambda: Diagram(
                kind=DiagramKind.SEQUENCE,
                nodes=(Node("A"),),
                direction=Direction.LEFT_TO_RIGHT,
            ),
            "direction is not supported for sequence diagrams",
        ),
    ],
)
def test_direct_model_construction_enforces_rendering_invariants(
    build: object, message: str
) -> None:
    with pytest.raises(DiagramValidationError) as caught:
        build()  # type: ignore[operator]

    assert caught.value.source_name == "<model>"
    assert caught.value.message == message


def test_first_mention_order_is_stable_across_all_node_bearing_statements() -> None:
    source = """highlight Gamma
group Backend: Beta, Delta
Alpha -> Beta
Gamma -> Alpha
"""

    first = parse_diagram(source)
    second = parse_diagram(source)

    assert first.node_ids == ("Gamma", "Beta", "Delta", "Alpha")
    assert first.edges == (Edge("Alpha", "Beta"), Edge("Gamma", "Alpha"))
    assert first == second
    assert hash(first) == hash(second)


@pytest.mark.parametrize(
    ("filename", "kind", "node_count", "edge_count", "group_count"),
    [
        ("01-hello-world.diagram", DiagramKind.ARCHITECTURE, 3, 2, 0),
        ("02-commerce-platform.diagram", DiagramKind.ARCHITECTURE, 7, 6, 3),
        ("03-feedback-control.diagram", DiagramKind.ARCHITECTURE, 5, 5, 2),
        ("04-global-routing.diagram", DiagramKind.ARCHITECTURE, 5, 5, 2),
        ("05-release-approval.diagram", DiagramKind.FLOW, 7, 8, 0),
        ("06-incident-response.diagram", DiagramKind.FLOW, 5, 6, 2),
        ("07-invoice-processing.diagram", DiagramKind.FLOW, 7, 7, 3),
        ("08-user-sign-in.diagram", DiagramKind.SEQUENCE, 4, 6, 0),
        ("09-checkout-sequence.diagram", DiagramKind.SEQUENCE, 5, 8, 0),
        ("10-regional-sync.diagram", DiagramKind.SEQUENCE, 4, 6, 0),
    ],
)
def test_shipped_examples_parse_as_their_documented_diagram_type(
    filename: str,
    kind: DiagramKind,
    node_count: int,
    edge_count: int,
    group_count: int,
) -> None:
    path = Path(__file__).parents[1] / "examples" / filename
    result = parse_diagram(path.read_text(encoding="utf-8"), source_name=str(path))

    assert result.kind is kind
    assert len(result.nodes) == node_count
    assert len(result.edges) == edge_count
    assert len(result.groups) == group_count
