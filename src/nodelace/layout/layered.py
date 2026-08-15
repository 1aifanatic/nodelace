"""Stable layered placement for architecture and flow diagrams."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from .router import CHANNEL_TAIL, PORT_SEPARATION, edge_label_width, route_edges
from .types import LayoutResult, PositionedGroup, PositionedNode, Rect

CANVAS_PADDING = 64
NODE_HEIGHT = 64
NODE_MIN_WIDTH = 120
NODE_MAX_WIDTH = 320
RANK_GAP = 96
NODE_GAP = 48
GROUP_SIDE_PADDING = 24
GROUP_HEADER_PADDING = 32
GROUP_BOTTOM_PADDING = 24
GROUP_BAND_GAP = 32
PORT_PADDING = 16

NodeSpec = tuple[int, Any, str, str, int, int, int]


def _value(value: Any) -> str:
    return str(getattr(value, "value", value)).lower()


def normalise_kind(kind: Any) -> str:
    value = _value(kind)
    return value.rsplit(".", 1)[-1]


def normalise_direction(direction: Any, kind: str) -> str:
    if direction is None:
        return "top-to-bottom" if kind == "flow" else "left-to-right"
    value = _value(direction).replace("_", "-").replace(" ", "-")
    aliases = {
        "right": "left-to-right",
        "horizontal": "left-to-right",
        "lr": "left-to-right",
        "left-to-right": "left-to-right",
        "down": "top-to-bottom",
        "vertical": "top-to-bottom",
        "tb": "top-to-bottom",
        "td": "top-to-bottom",
        "top-to-bottom": "top-to-bottom",
    }
    return aliases.get(value.rsplit(".", 1)[-1], value)


def _round_up(value: int, grid: int = 4) -> int:
    return ((value + grid - 1) // grid) * grid


def _node_width(label: str) -> int:
    return max(NODE_MIN_WIDTH, min(NODE_MAX_WIDTH, _round_up(len(label) * 8 + 32)))


def _order(item: Any, fallback: int) -> tuple[int, int]:
    return (int(getattr(item, "order", fallback)), fallback)


def _route_kind(source_rank: int, target_rank: int) -> str:
    if target_rank <= source_rank:
        return "feedback"
    if target_rank > source_rank + 1:
        return "skip"
    return "forward"


def _required_port_span(count: int) -> int:
    if count <= 1:
        return 0
    return PORT_PADDING * 2 + (count - 1) * PORT_SEPARATION


def _ranks(nodes: tuple[Any, ...], edges: Iterable[Any]) -> dict[str, int]:
    """Assign stable longest-path ranks after condensing graph cycles.

    Members of a strongly connected component occupy consecutive ranks in
    first-node order.  This produces a readable forward spine with one or more
    explicitly routed feedback edges and is independent of edge declaration
    order.
    """

    edge_tuple = tuple(edges)
    identifiers = [str(node.id) for node in nodes]
    known = set(identifiers)
    position = {identifier: index for index, identifier in enumerate(identifiers)}
    adjacency: dict[str, list[str]] = {identifier: [] for identifier in identifiers}
    for edge in edge_tuple:
        source = str(edge.source)
        target = str(edge.target)
        if source in known and target in known and target not in adjacency[source]:
            adjacency[source].append(target)
    for neighbors in adjacency.values():
        neighbors.sort(key=position.__getitem__)

    next_index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(identifier: str) -> None:
        nonlocal next_index
        indexes[identifier] = next_index
        lowlinks[identifier] = next_index
        next_index += 1
        stack.append(identifier)
        on_stack.add(identifier)
        for target in adjacency[identifier]:
            if target not in indexes:
                visit(target)
                lowlinks[identifier] = min(lowlinks[identifier], lowlinks[target])
            elif target in on_stack:
                lowlinks[identifier] = min(lowlinks[identifier], indexes[target])
        if lowlinks[identifier] != indexes[identifier]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == identifier:
                break
        component.sort(key=position.__getitem__)
        components.append(component)

    for identifier in identifiers:
        if identifier not in indexes:
            visit(identifier)

    component_of = {
        member: component_index
        for component_index, component in enumerate(components)
        for member in component
    }
    component_key = {
        component_index: min(position[member] for member in component)
        for component_index, component in enumerate(components)
    }
    successors: dict[int, set[int]] = {
        component_index: set() for component_index in range(len(components))
    }
    indegree = {component_index: 0 for component_index in range(len(components))}
    for edge in edge_tuple:
        source = str(edge.source)
        target = str(edge.target)
        if source not in known or target not in known:
            continue
        source_component = component_of[source]
        target_component = component_of[target]
        if (
            source_component != target_component
            and target_component not in successors[source_component]
        ):
            successors[source_component].add(target_component)
            indegree[target_component] += 1

    component_rank = {component_index: 0 for component_index in range(len(components))}
    ready = sorted(
        (component for component, degree in indegree.items() if degree == 0),
        key=component_key.__getitem__,
    )
    while ready:
        component = ready.pop(0)
        for target in sorted(successors[component], key=component_key.__getitem__):
            component_rank[target] = max(
                component_rank[target], component_rank[component] + len(components[component])
            )
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=component_key.__getitem__)

    rank: dict[str, int] = {}
    for component_index, component in enumerate(components):
        base = component_rank[component_index]
        for offset, identifier in enumerate(component):
            rank[identifier] = base + offset
    return rank


def _member_bounds(nodes: list[PositionedNode]) -> Rect:
    left = min(node.bounds.x for node in nodes) - GROUP_SIDE_PADDING
    top = min(node.bounds.y for node in nodes) - GROUP_HEADER_PADDING
    right = max(node.bounds.right for node in nodes) + GROUP_SIDE_PADDING
    bottom = max(node.bounds.bottom for node in nodes) + GROUP_BOTTOM_PADDING
    return Rect(left, top, right - left, bottom - top)


def _primary_axes_overlap(first: Rect, second: Rect, direction: str) -> bool:
    if direction == "left-to-right":
        return first.x < second.right and second.x < first.right
    return first.y < second.bottom and second.y < first.bottom


def _required_cross_shift(current: Rect, blocker: Rect, direction: str) -> int:
    if not _primary_axes_overlap(current, blocker, direction):
        return 0
    if direction == "left-to-right":
        return max(0, blocker.bottom + GROUP_BAND_GAP - current.y)
    return max(0, blocker.right + GROUP_BAND_GAP - current.x)


def _separate_group_regions(
    positioned_by_id: dict[str, PositionedNode],
    specs: list[NodeSpec],
    groups: tuple[Any, ...],
    direction: str,
) -> dict[str, PositionedNode]:
    """Shift only ambiguous later regions into a new cross-axis band.

    Regions whose primary-axis spans do not meet retain the same cross-axis
    lane. This preserves compact sequential groups while separating groups
    that actually overlap. Each ungrouped node is also a region, preventing a
    group rectangle from ambiguously enclosing a nonmember node.
    """

    node_order = {spec[2]: spec[0] for spec in specs}
    grouped_members = {str(member) for group in groups for member in group.members}
    units: list[tuple[int, int, tuple[str, ...], bool]] = []
    for group_index, group in enumerate(groups):
        members = tuple(str(member) for member in group.members)
        units.append(
            (
                min(node_order[member] for member in members),
                group_index,
                members,
                True,
            )
        )
    for identifier, order in node_order.items():
        if identifier not in grouped_members:
            units.append((order, len(groups) + order, (identifier,), False))
    units.sort(key=lambda unit: (unit[0], unit[1]))

    shifted = dict(positioned_by_id)
    occupied: list[Rect] = []
    for _, _, members, grouped in units:
        member_nodes = [shifted[member] for member in members]
        region = _member_bounds(member_nodes) if grouped else member_nodes[0].bounds
        delta = max(
            (_required_cross_shift(region, blocker, direction) for blocker in occupied),
            default=0,
        )
        delta = _round_up(delta)
        if delta:
            dx, dy = (0, delta) if direction == "left-to-right" else (delta, 0)
            for member in members:
                node = shifted[member]
                shifted[member] = replace(node, bounds=node.bounds.translated(dx, dy))
            member_nodes = [shifted[member] for member in members]
            region = _member_bounds(member_nodes) if grouped else member_nodes[0].bounds
        occupied.append(region)
    return shifted


def _normalise_geometry(
    nodes: tuple[PositionedNode, ...],
    groups: tuple[PositionedGroup, ...],
    edges: tuple[Any, ...],
) -> tuple[
    tuple[PositionedNode, ...],
    tuple[PositionedGroup, ...],
    tuple[Any, ...],
    Rect,
]:
    min_x: list[int] = []
    min_y: list[int] = []
    max_x: list[int] = []
    max_y: list[int] = []
    for item in (*nodes, *groups):
        min_x.append(item.bounds.x)
        min_y.append(item.bounds.y)
        max_x.append(item.bounds.right)
        max_y.append(item.bounds.bottom)
    for edge in edges:
        min_x.extend(point.x for point in edge.points)
        min_y.extend(point.y for point in edge.points)
        max_x.extend(point.x for point in edge.points)
        max_y.extend(point.y for point in edge.points)
        width = edge_label_width(edge.label)
        if width:
            min_x.append(edge.label_position.x - width // 2)
            min_y.append(edge.label_position.y - 14)
            max_x.append(edge.label_position.x - width // 2 + width)
            max_y.append(edge.label_position.y + 6)
    if not min_x:
        return nodes, groups, edges, Rect(0, 0, CANVAS_PADDING * 2, CANVAS_PADDING * 2)

    dx = _round_up(CANVAS_PADDING - min(min_x))
    dy = _round_up(CANVAS_PADDING - min(min_y))
    translated_nodes = tuple(replace(node, bounds=node.bounds.translated(dx, dy)) for node in nodes)
    translated_groups = tuple(
        replace(group, bounds=group.bounds.translated(dx, dy)) for group in groups
    )
    translated_edges = tuple(
        replace(
            edge,
            points=tuple(point.translated(dx, dy) for point in edge.points),
            label_position=edge.label_position.translated(dx, dy),
        )
        for edge in edges
    )
    canvas = Rect(
        0,
        0,
        _round_up(max(max_x) + dx + CANVAS_PADDING),
        _round_up(max(max_y) + dy + CANVAS_PADDING),
    )
    return translated_nodes, translated_groups, translated_edges, canvas


def layout_layered(diagram: Any) -> LayoutResult:
    kind = normalise_kind(diagram.kind)
    direction = normalise_direction(getattr(diagram, "direction", None), kind)
    indexed_nodes = sorted(
        enumerate(tuple(diagram.nodes)), key=lambda pair: _order(pair[1], pair[0])
    )
    model_nodes = tuple(node for _, node in indexed_nodes)
    model_edges = tuple(diagram.edges)
    model_groups = tuple(getattr(diagram, "groups", ()))
    rank_by_id = _ranks(model_nodes, model_edges)
    known_ids = set(rank_by_id)

    outgoing: dict[tuple[str, str], int] = defaultdict(int)
    incoming: dict[tuple[str, str], int] = defaultdict(int)
    incident: dict[tuple[str, str], int] = defaultdict(int)
    gap_after: dict[int, int] = defaultdict(lambda: RANK_GAP)
    forward_lane: dict[int, int] = defaultdict(int)
    ordered_edges = sorted(enumerate(model_edges), key=lambda pair: _order(pair[1], pair[0]))
    for _, edge in ordered_edges:
        source = str(edge.source)
        target = str(edge.target)
        if source not in known_ids or target not in known_ids:
            continue
        route_kind = _route_kind(rank_by_id[source], rank_by_id[target])
        outgoing[(route_kind, source)] += 1
        incoming[(route_kind, target)] += 1
        if route_kind != "forward":
            incident[(route_kind, source)] += 1
            incident[(route_kind, target)] += 1
        if route_kind == "forward":
            lane = forward_lane[rank_by_id[source]]
            forward_lane[rank_by_id[source]] += 1
            label_space = edge_label_width(edge.label) + 24 if direction == "left-to-right" else 40
            gap_after[rank_by_id[source]] = max(
                gap_after[rank_by_id[source]],
                _round_up(CHANNEL_TAIL + lane * PORT_SEPARATION + label_space),
            )

    specs: list[NodeSpec] = []
    for fallback, node in indexed_nodes:
        identifier = str(node.id)
        label = str(getattr(node, "label", None) or identifier)
        rank = rank_by_id[identifier]
        degree = {
            "forward": max(outgoing[("forward", identifier)], incoming[("forward", identifier)]),
            "feedback": incident[("feedback", identifier)],
            "skip": incident[("skip", identifier)],
        }
        width = _node_width(label)
        height = NODE_HEIGHT
        if direction == "left-to-right":
            height = max(height, _required_port_span(degree["forward"]))
            width = max(
                width,
                _required_port_span(degree["feedback"]),
                _required_port_span(degree["skip"]),
            )
        else:
            width = max(width, _required_port_span(degree["forward"]))
            height = max(
                height,
                _required_port_span(degree["feedback"]),
                _required_port_span(degree["skip"]),
            )
        specs.append((fallback, node, identifier, label, rank, _round_up(width), _round_up(height)))

    by_rank: dict[int, list[NodeSpec]] = {}
    for spec in specs:
        by_rank.setdefault(spec[4], []).append(spec)
    ranks = sorted(by_rank)
    rank_primary_size: dict[int, int] = {}
    rank_cross_size: dict[int, int] = {}
    for rank in ranks:
        layer = by_rank[rank]
        if direction == "left-to-right":
            rank_primary_size[rank] = max(spec[5] for spec in layer)
            rank_cross_size[rank] = sum(spec[6] for spec in layer) + NODE_GAP * (len(layer) - 1)
        else:
            rank_primary_size[rank] = max(spec[6] for spec in layer)
            rank_cross_size[rank] = sum(spec[5] for spec in layer) + NODE_GAP * (len(layer) - 1)

    primary_start: dict[int, int] = {}
    cursor = CANVAS_PADDING
    for rank in ranks:
        primary_start[rank] = cursor
        cursor += rank_primary_size[rank] + gap_after[rank]
    cross_extent = max(rank_cross_size.values(), default=0)
    positioned_by_id: dict[str, PositionedNode] = {}
    highlighted = set(getattr(diagram, "highlights", ()))
    for rank in ranks:
        layer = by_rank[rank]
        cross = CANVAS_PADDING + _round_up((cross_extent - rank_cross_size[rank]) // 2)
        for fallback, node, identifier, label, _, width, height in layer:
            if direction == "left-to-right":
                bounds = Rect(primary_start[rank], cross, width, height)
                cross += height + NODE_GAP
            else:
                bounds = Rect(cross, primary_start[rank], width, height)
                cross += width + NODE_GAP
            positioned_by_id[identifier] = PositionedNode(
                node=node,
                id=identifier,
                label=label,
                bounds=bounds,
                rank=rank,
                order=_order(node, fallback)[0],
                highlighted=identifier in highlighted,
            )

    if model_groups:
        positioned_by_id = _separate_group_regions(positioned_by_id, specs, model_groups, direction)
    nodes = tuple(positioned_by_id[spec[2]] for spec in specs)
    groups: list[PositionedGroup] = []
    for fallback, group in sorted(
        enumerate(model_groups),
        key=lambda pair: _order(pair[1], pair[0]),
    ):
        members = tuple(str(member) for member in group.members)
        member_nodes = [positioned_by_id[member] for member in members]
        if not member_nodes:
            continue
        groups.append(
            PositionedGroup(
                group=group,
                name=str(group.name),
                members=members,
                bounds=_member_bounds(member_nodes),
                order=_order(group, fallback)[0],
            )
        )

    edges = route_edges(model_edges, nodes, direction=direction)
    nodes, positioned_groups, edges, canvas = _normalise_geometry(nodes, tuple(groups), edges)
    return LayoutResult(
        diagram=diagram,
        kind=kind,
        direction=direction,
        canvas=canvas,
        nodes=nodes,
        groups=positioned_groups,
        edges=edges,
    )


__all__ = ["layout_layered", "normalise_direction", "normalise_kind"]
