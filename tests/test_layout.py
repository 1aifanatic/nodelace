from __future__ import annotations

from itertools import pairwise

from nodelace import parse_diagram
from nodelace.layout import Rect, layout_diagram
from nodelace.model import Diagram, Direction, Edge, Group, Node


def diagram(
    *nodes: str,
    edges: tuple[tuple[str, str, str], ...] = (),
    kind: str = "architecture",
    groups: tuple[Group, ...] = (),
    direction: Direction | None = None,
) -> Diagram:
    return Diagram(
        kind=kind,
        title="Test",
        nodes=tuple(Node(node_id, node_id.title()) for node_id in nodes),
        edges=tuple(Edge(source, target, label) for source, target, label in edges),
        groups=groups,
        direction=direction,
    )


def test_horizontal_chain_uses_stable_layers_and_routed_endpoints() -> None:
    source = diagram(
        "client",
        "api",
        "store",
        edges=(("client", "api", "request"), ("api", "store", "write")),
        direction=Direction.LEFT_TO_RIGHT,
    )

    result = layout_diagram(source)

    nodes = result.node_map
    assert nodes["client"].bounds.x < nodes["api"].bounds.x < nodes["store"].bounds.x
    assert nodes["client"].bounds.y == nodes["api"].bounds.y == nodes["store"].bounds.y
    assert result.edges[0].points[0].x == nodes["client"].bounds.right
    assert result.edges[0].points[-1].x == nodes["api"].bounds.x
    assert result.edges[0].points[0].y == result.edges[0].points[-1].y
    assert all(isinstance(value, int) for point in result.edges[0].points for value in point)


def test_branch_nodes_do_not_overlap_and_connectors_fan_orthogonally() -> None:
    source = diagram(
        "start",
        "left",
        "right",
        "finish",
        edges=(
            ("start", "left", "one"),
            ("start", "right", "two"),
            ("left", "finish", "three"),
            ("right", "finish", "four"),
        ),
        direction=Direction.LEFT_TO_RIGHT,
    )

    result = layout_diagram(source)
    nodes = result.node_map

    assert nodes["left"].rank == nodes["right"].rank == 1
    assert nodes["left"].bounds.bottom < nodes["right"].bounds.y
    assert result.edges[0].points[0] != result.edges[1].points[0]
    assert result.edges[2].points[-1] != result.edges[3].points[-1]
    assert all(
        first.x == second.x or first.y == second.y
        for edge in result.edges
        for first, second in pairwise(edge.points)
    )


def test_vertical_chain_aligns_centers_and_uses_top_bottom_ports() -> None:
    source = Diagram(
        kind="flow",
        nodes=(Node("short", "S"), Node("wide", "A much wider action"), Node("end", "End")),
        edges=(Edge("short", "wide"), Edge("wide", "end")),
        direction=Direction.TOP_TO_BOTTOM,
    )

    result = layout_diagram(source)
    nodes = result.node_map

    assert result.direction == "top-to-bottom"
    assert nodes["short"].bounds.center_x == nodes["wide"].bounds.center_x
    assert nodes["wide"].bounds.center_x == nodes["end"].bounds.center_x
    assert result.edges[0].points[0].y == nodes["short"].bounds.bottom
    assert result.edges[0].points[-1].y == nodes["wide"].bounds.y


def test_flat_group_bounds_contain_members_and_preserve_source_object() -> None:
    source = diagram(
        "client",
        "api",
        "store",
        edges=(("client", "api", "request"), ("api", "store", "write")),
        groups=(Group("Core services", ("api", "store")),),
        direction=Direction.LEFT_TO_RIGHT,
    )

    result = layout_diagram(source)
    group = result.group_for("Core services")

    assert group.group is source.groups[0]
    assert group.members == ("api", "store")
    for member_id in group.members:
        member = result.node_for(member_id).bounds
        assert group.bounds.x <= member.x
        assert group.bounds.y <= member.y
        assert group.bounds.right >= member.right
        assert group.bounds.bottom >= member.bottom
    assert result.canvas.right >= group.bounds.right + 24
    assert result.canvas.bottom >= group.bounds.bottom + 24


def test_cycle_uses_a_stable_outer_feedback_lane() -> None:
    source = diagram(
        "alpha",
        "beta",
        "gamma",
        edges=(
            ("alpha", "beta", "next"),
            ("beta", "gamma", "next"),
            ("gamma", "alpha", "retry"),
        ),
        direction=Direction.LEFT_TO_RIGHT,
    )

    result = layout_diagram(source)
    feedback = [edge for edge in result.edges if edge.feedback]

    assert [result.node_for(node_id).rank for node_id in ("alpha", "beta", "gamma")] == [
        0,
        1,
        2,
    ]
    assert len(feedback) == 1
    assert feedback[0].edge is source.edges[2]
    assert min(point.y for point in feedback[0].points) < min(
        node.bounds.y for node in result.nodes
    )
    assert feedback[0].points[0].y == result.node_for("gamma").bounds.y
    assert feedback[0].points[-1].y == result.node_for("alpha").bounds.y


def test_cycle_ranking_is_independent_of_edge_declaration_order() -> None:
    nodes = (Node("alpha"), Node("beta"), Node("gamma"))
    ordered = Diagram(
        kind="architecture",
        nodes=nodes,
        edges=(Edge("alpha", "beta"), Edge("beta", "gamma"), Edge("gamma", "alpha")),
        direction=Direction.LEFT_TO_RIGHT,
    )
    permuted = Diagram(
        kind="architecture",
        nodes=nodes,
        edges=(Edge("gamma", "alpha"), Edge("beta", "gamma"), Edge("alpha", "beta")),
        direction=Direction.LEFT_TO_RIGHT,
    )

    first = layout_diagram(ordered)
    second = layout_diagram(permuted)

    assert tuple(node.rank for node in first.nodes) == tuple(node.rank for node in second.nodes)
    assert tuple(node.bounds for node in first.nodes) == tuple(node.bounds for node in second.nodes)


def test_multiple_feedback_lanes_expand_canvas_without_negative_geometry() -> None:
    source = diagram(
        "alpha",
        "beta",
        "gamma",
        edges=(
            ("alpha", "alpha", "retry a"),
            ("beta", "beta", "retry b"),
            ("gamma", "gamma", "retry c"),
        ),
        direction=Direction.LEFT_TO_RIGHT,
    )

    result = layout_diagram(source)
    lane_levels = {min(point.y for point in edge.points) for edge in result.edges}
    all_points = [point for edge in result.edges for point in edge.points]

    assert len(lane_levels) == 3
    assert min(point.x for point in all_points) >= result.canvas.x
    assert min(point.y for point in all_points) >= result.canvas.y
    assert max(point.x for point in all_points) <= result.canvas.right
    assert max(point.y for point in all_points) <= result.canvas.bottom


def test_sequence_participants_have_fixed_lanes_and_messages_follow_source_order() -> None:
    source = Diagram(
        kind="sequence",
        title="Checkout",
        nodes=(Node("client", "Client"), Node("api", "API"), Node("db", "Database")),
        edges=(
            Edge("client", "api", "request"),
            Edge("api", "db", "query"),
            Edge("db", "api", "row"),
            Edge("api", "client", "response"),
        ),
    )

    result = layout_diagram(source)

    assert result.kind == "sequence"
    assert [participant.id for participant in result.participants] == ["client", "api", "db"]
    assert [participant.lifeline_x for participant in result.participants] == sorted(
        participant.lifeline_x for participant in result.participants
    )
    assert [message.edge for message in result.messages] == list(source.edges)
    assert [message.y for message in result.messages] == sorted(
        message.y for message in result.messages
    )
    assert all(
        message.points[0].x == result.participant_map[message.source].lifeline_x
        and message.points[-1].x == result.participant_map[message.target].lifeline_x
        for message in result.messages
    )
    assert len({participant.lifeline_bottom for participant in result.participants}) == 1
    assert result.participants[0].lifeline_bottom > result.messages[-1].y


def test_sequence_canvas_contains_long_self_message_labels_at_both_edges() -> None:
    long_label = "x" * 500
    source = Diagram(
        kind="sequence",
        title="Self messages",
        nodes=(Node("left", "Left"), Node("middle", "Middle"), Node("right", "Right")),
        edges=(
            Edge("left", "left", long_label),
            Edge("left", "middle", "continue"),
            Edge("right", "right", long_label),
        ),
    )

    result = layout_diagram(source)

    for message in (result.messages[0], result.messages[-1]):
        width = min(300, max(36, len(message.label) * 7 + 16))
        bounds = Rect(
            message.label_position.x - width // 2,
            message.label_position.y - 21,
            width,
            34,
        )
        assert bounds.x >= result.canvas.x + 64
        assert bounds.y >= result.canvas.y + 64
        assert bounds.right <= result.canvas.right - 64
        assert bounds.bottom <= result.canvas.bottom - 64


def _overlaps(first: object, second: object) -> bool:
    a = first.bounds
    b = second.bounds
    return not (a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y)


def test_fifty_node_star_is_deterministic_non_overlapping_and_fans_every_endpoint() -> None:
    node_ids = tuple(f"node-{index:02d}" for index in range(50))
    source = Diagram(
        kind="architecture",
        nodes=tuple(Node(node_id) for node_id in node_ids),
        edges=tuple(
            Edge(node_ids[0], target, f"route {index}") for index, target in enumerate(node_ids[1:])
        ),
        direction=Direction.LEFT_TO_RIGHT,
    )

    first = layout_diagram(source)
    second = layout_diagram(source)

    assert first == second
    assert len(first.nodes) == 50
    assert len({edge.points[0] for edge in first.edges}) == 49
    assert all(
        not _overlaps(first.nodes[left], first.nodes[right])
        for left in range(len(first.nodes))
        for right in range(left + 1, len(first.nodes))
    )
    assert all(
        first.canvas.x <= point.x <= first.canvas.right
        and first.canvas.y <= point.y <= first.canvas.bottom
        for edge in first.edges
        for point in edge.points
    )


def _segment_crosses_interior(first: object, second: object, bounds: object) -> bool:
    if first.y == second.y:
        return bounds.y < first.y < bounds.bottom and max(min(first.x, second.x), bounds.x) < min(
            max(first.x, second.x), bounds.right
        )
    return bounds.x < first.x < bounds.right and max(min(first.y, second.y), bounds.y) < min(
        max(first.y, second.y), bounds.bottom
    )


def test_rank_skipping_connector_routes_around_intervening_node() -> None:
    source = diagram(
        "alpha",
        "beta",
        "gamma",
        edges=(
            ("alpha", "beta", "step one"),
            ("beta", "gamma", "step two"),
            ("alpha", "gamma", "shortcut"),
        ),
        direction=Direction.LEFT_TO_RIGHT,
    )

    result = layout_diagram(source)
    shortcut = next(edge for edge in result.edges if edge.label == "shortcut")
    intervening = result.node_for("beta").bounds

    assert not any(
        _segment_crosses_interior(first, second, intervening)
        for first, second in pairwise(shortcut.points)
    )


def _edge_label_bounds(edge: object) -> Rect:
    width = min(300, max(36, len(edge.label) * 7 + 16))
    return Rect(
        edge.label_position.x - width // 2,
        edge.label_position.y - 14,
        width,
        20,
    )


def _rectangles_overlap(first: Rect, second: Rect) -> bool:
    return not (
        first.right <= second.x
        or second.right <= first.x
        or first.bottom <= second.y
        or second.bottom <= first.y
    )


def _label_has_clear_horizontal_segment(edge: object) -> bool:
    label = _edge_label_bounds(edge)
    return any(
        min(first.x, second.x) + 8 <= label.x
        and label.right <= max(first.x, second.x) - 8
        and (label.bottom <= first.y - 8 or label.y >= first.y + 8)
        for first, second in pairwise(edge.points)
        if first.y == second.y
    )


def _segments_share_stroke(
    first_start: object,
    first_end: object,
    second_start: object,
    second_end: object,
) -> bool:
    if first_start.y == first_end.y == second_start.y == second_end.y:
        return max(min(first_start.x, first_end.x), min(second_start.x, second_end.x)) < min(
            max(first_start.x, first_end.x), max(second_start.x, second_end.x)
        )
    if first_start.x == first_end.x == second_start.x == second_end.x:
        return max(min(first_start.y, first_end.y), min(second_start.y, second_end.y)) < min(
            max(first_start.y, first_end.y), max(second_start.y, second_end.y)
        )
    return False


def test_commerce_fanout_labels_have_editorial_clearance() -> None:
    source = parse_diagram(
        """architecture "Commerce Platform"
direction left-to-right
Browser -> Gateway: HTTPS
Gateway -> Catalog: browse
Gateway -> Orders: checkout
Catalog -> ProductDB: read products
Orders -> OrderDB: save order
Orders -> Payments: authorize
group Edge: Browser, Gateway
group Services: Catalog, Orders, Payments
group Data: ProductDB, OrderDB
"""
    )

    result = layout_diagram(source)
    labels = [_edge_label_bounds(edge) for edge in result.edges]

    assert all(_label_has_clear_horizontal_segment(edge) for edge in result.edges)
    assert all(
        not _rectangles_overlap(label, node.bounds) for label in labels for node in result.nodes
    )
    assert all(
        not _rectangles_overlap(labels[left], labels[right])
        for left in range(len(labels))
        for right in range(left + 1, len(labels))
    )
    gateway_labels = [_edge_label_bounds(edge) for edge in result.edges if edge.source == "Gateway"]
    assert gateway_labels[1].y - gateway_labels[0].bottom >= 8
    assert all(
        not _segments_share_stroke(first_start, first_end, second_start, second_end)
        for first_index, first in enumerate(result.edges)
        for second in result.edges[first_index + 1 :]
        for first_start, first_end in pairwise(first.points)
        for second_start, second_end in pairwise(second.points)
    )


def test_release_feedback_and_skip_routes_use_opposite_outer_sides() -> None:
    source = parse_diagram(
        """flow "Release Approval"
direction top-to-bottom
Change -> Tests: run suite
Tests -> Deploy: passing
Tests -> Fix: failing
Fix -> Tests: retry
Deploy -> Verify: smoke test
Verify -> Complete: healthy
Verify -> Rollback: unhealthy
Rollback -> Fix: investigate
"""
    )

    result = layout_diagram(source)
    left = min(node.bounds.x for node in result.nodes)
    right = max(node.bounds.right for node in result.nodes)
    feedback = [edge for edge in result.edges if edge.feedback]
    skips = [
        edge
        for edge in result.edges
        if not edge.feedback
        and result.node_for(edge.target).rank > result.node_for(edge.source).rank + 1
    ]
    outer = feedback + skips
    labels = [_edge_label_bounds(edge) for edge in outer]

    assert all(min(point.x for point in edge.points[1:-1]) < left for edge in feedback)
    assert all(max(point.x for point in edge.points[1:-1]) > right for edge in skips)
    assert len({edge.points[0] for edge in outer}) == len(outer)
    assert len({edge.points[-1] for edge in outer}) == len(outer)
    assert all(
        not _rectangles_overlap(labels[first], labels[second])
        for first in range(len(labels))
        for second in range(first + 1, len(labels))
    )
    assert all(
        not _rectangles_overlap(label, node.bounds) for label in labels for node in result.nodes
    )
    assert all(
        not _segments_share_stroke(first_start, first_end, second_start, second_end)
        for first_index, first in enumerate(outer)
        for second in outer[first_index + 1 :]
        for first_start, first_end in pairwise(first.points)
        for second_start, second_end in pairwise(second.points)
    )


def _assert_flat_group_geometry_is_unambiguous(result: object) -> None:
    assert all(
        not _rectangles_overlap(result.groups[first].bounds, result.groups[second].bounds)
        for first in range(len(result.groups))
        for second in range(first + 1, len(result.groups))
    )
    assert all(
        group.bounds.x <= result.node_for(member).bounds.x
        and group.bounds.y <= result.node_for(member).bounds.y
        and group.bounds.right >= result.node_for(member).bounds.right
        and group.bounds.bottom >= result.node_for(member).bounds.bottom
        for group in result.groups
        for member in group.members
    )
    assert all(
        not _rectangles_overlap(result.nodes[first].bounds, result.nodes[second].bounds)
        for first in range(len(result.nodes))
        for second in range(first + 1, len(result.nodes))
    )
    assert all(
        not _rectangles_overlap(_edge_label_bounds(edge), node.bounds)
        for edge in result.edges
        if edge.label
        for node in result.nodes
    )


def test_ltr_interleaved_flat_groups_receive_disjoint_horizontal_bands() -> None:
    source = Diagram(
        kind="architecture",
        nodes=tuple(Node(identifier) for identifier in ("A", "B", "C", "D")),
        edges=(Edge("A", "B", "one"), Edge("B", "C", "two"), Edge("C", "D", "three")),
        groups=(Group("Odd ranks", ("A", "C")), Group("Even ranks", ("B", "D"))),
        direction=Direction.LEFT_TO_RIGHT,
    )

    result = layout_diagram(source)

    _assert_flat_group_geometry_is_unambiguous(result)
    assert result.group_for("Odd ranks").bounds.bottom < result.group_for("Even ranks").bounds.y


def test_ttb_interleaved_flat_groups_receive_disjoint_vertical_bands() -> None:
    source = Diagram(
        kind="flow",
        nodes=tuple(Node(identifier) for identifier in ("A", "B", "C", "D")),
        edges=(Edge("A", "B", "one"), Edge("B", "C", "two"), Edge("C", "D", "three")),
        groups=(Group("Odd ranks", ("A", "C")), Group("Even ranks", ("B", "D"))),
        direction=Direction.TOP_TO_BOTTOM,
    )

    result = layout_diagram(source)

    _assert_flat_group_geometry_is_unambiguous(result)
    assert result.group_for("Odd ranks").bounds.right < result.group_for("Even ranks").bounds.x
