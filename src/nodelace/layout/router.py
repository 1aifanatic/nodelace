"""Deterministic orthogonal connector routing."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Literal

from .types import Point, PositionedNode, RoutedEdge

RouteKind = Literal["forward", "feedback", "skip"]

CHANNEL_TAIL = 32
LABEL_GAP = 8
OUTER_LANE_GAP = 32
OUTER_LANE_OFFSET = 48
PORT_SEPARATION = 32


def _order(item: Any, fallback: int) -> tuple[int, int]:
    return (int(getattr(item, "order", fallback)), fallback)


def edge_label_width(label: str | None) -> int:
    """Return the renderer's deterministic edge-label mask width."""

    if not label:
        return 0
    return min(300, max(36, len(label) * 7 + 16))


def _grid(value: float) -> int:
    return round(value / 4.0) * 4


def _grid_floor(value: int) -> int:
    return value // 4 * 4


def _grid_ceil(value: int) -> int:
    return (value + 3) // 4 * 4


def _fan(start: int, length: int, index: int, count: int) -> int:
    offset = (2 * index - count + 1) * PORT_SEPARATION / 2
    return _grid(start + length / 2 + offset)


def _deduplicate(points: tuple[Point, ...]) -> tuple[Point, ...]:
    result: list[Point] = []
    for point in points:
        if not result or result[-1] != point:
            result.append(point)
    return tuple(result)


def _kind(source: PositionedNode, target: PositionedNode) -> RouteKind:
    if target.rank <= source.rank:
        return "feedback"
    if target.rank > source.rank + 1:
        return "skip"
    return "forward"


def _above(first: Point, second: Point) -> Point:
    return Point(_grid((first.x + second.x) / 2), first.y - 16)


def _below(first: Point, second: Point) -> Point:
    return Point(_grid((first.x + second.x) / 2), first.y + 24)


def _beside(
    first: Point,
    second: Point,
    label: str | None,
    *,
    side: Literal["left", "right"],
) -> Point:
    width = edge_label_width(label)
    left_half = width // 2
    right_half = width - left_half
    if side == "left":
        x = _grid_floor(first.x - right_half - LABEL_GAP)
    else:
        x = _grid_ceil(first.x + left_half + LABEL_GAP)
    return Point(x, _grid((first.y + second.y) / 2))


def _label_position(
    kind: RouteKind,
    direction: str,
    points: tuple[Point, ...],
    label: str | None,
    source: PositionedNode,
    target: PositionedNode,
) -> Point:
    if kind == "forward" and direction == "left-to-right":
        return _above(points[0], points[1])
    if kind == "forward":
        side: Literal["left", "right"] = (
            "left" if target.bounds.center_x < source.bounds.center_x else "right"
        )
        return _beside(points[0], points[1], label, side=side)
    if direction == "left-to-right":
        if kind == "feedback":
            return _above(points[1], points[2])
        return _below(points[1], points[2])
    if kind == "feedback":
        return _beside(points[1], points[2], label, side="left")
    return _beside(points[1], points[2], label, side="right")


def _outer_port(
    node: PositionedNode,
    *,
    kind: RouteKind,
    direction: str,
    index: int,
    count: int,
) -> Point:
    if direction == "left-to-right":
        x = _fan(node.bounds.x, node.bounds.width, index, count)
        y = node.bounds.y if kind == "feedback" else node.bounds.bottom
        return Point(x, y)
    x = node.bounds.x if kind == "feedback" else node.bounds.right
    y = _fan(node.bounds.y, node.bounds.height, index, count)
    return Point(x, y)


def route_edges(
    edges: Iterable[Any],
    nodes: tuple[PositionedNode, ...],
    *,
    direction: str,
) -> tuple[RoutedEdge, ...]:
    """Route model edges on distinct orthogonal channels.

    Adjacent-rank edges use the primary gap. Feedback edges use the outer
    top/left side, while forward edges that skip ranks use the opposite
    bottom/right side. Splitting those route families prevents cyclic flow
    labels from tangling with long happy-path shortcuts.
    """

    by_id = {node.id: node for node in nodes}
    ordered = sorted(enumerate(edges), key=lambda pair: _order(pair[1], pair[0]))
    kinds: list[RouteKind] = []
    outgoing: dict[tuple[RouteKind, str], list[int]] = defaultdict(list)
    incoming: dict[tuple[RouteKind, str], list[int]] = defaultdict(list)
    outer_ports: dict[tuple[RouteKind, str], list[int]] = defaultdict(list)
    lane_indexes: dict[RouteKind, list[int]] = {
        "forward": [],
        "feedback": [],
        "skip": [],
    }
    forward_channels: dict[tuple[int, int], list[int]] = defaultdict(list)
    for route_index, (_, edge) in enumerate(ordered):
        source = by_id[str(edge.source)]
        target = by_id[str(edge.target)]
        kind = _kind(source, target)
        kinds.append(kind)
        outgoing[(kind, source.id)].append(route_index)
        incoming[(kind, target.id)].append(route_index)
        lane_indexes[kind].append(route_index)
        if kind == "forward":
            forward_channels[(source.rank, target.rank)].append(route_index)
        else:
            outer_ports[(kind, source.id)].append(route_index)
            if target.id != source.id:
                outer_ports[(kind, target.id)].append(route_index)

    top = min((node.bounds.y for node in nodes), default=64)
    bottom = max((node.bounds.bottom for node in nodes), default=64)
    left = min((node.bounds.x for node in nodes), default=64)
    right = max((node.bounds.right for node in nodes), default=64)
    routed: list[RoutedEdge] = []
    for route_index, (fallback, edge) in enumerate(ordered):
        source = by_id[str(edge.source)]
        target = by_id[str(edge.target)]
        kind = kinds[route_index]
        source_edges = outgoing[(kind, source.id)]
        target_edges = incoming[(kind, target.id)]

        if kind == "forward" and direction == "left-to-right":
            start = Point(
                source.bounds.right,
                _fan(
                    source.bounds.y,
                    source.bounds.height,
                    source_edges.index(route_index),
                    len(source_edges),
                ),
            )
            end = Point(
                target.bounds.x,
                _fan(
                    target.bounds.y,
                    target.bounds.height,
                    target_edges.index(route_index),
                    len(target_edges),
                ),
            )
            channel_index = forward_channels[(source.rank, target.rank)].index(route_index)
            channel = end.x - CHANNEL_TAIL - channel_index * OUTER_LANE_GAP
            points = _deduplicate((start, Point(channel, start.y), Point(channel, end.y), end))
        elif kind == "forward":
            start = Point(
                _fan(
                    source.bounds.x,
                    source.bounds.width,
                    source_edges.index(route_index),
                    len(source_edges),
                ),
                source.bounds.bottom,
            )
            end = Point(
                _fan(
                    target.bounds.x,
                    target.bounds.width,
                    target_edges.index(route_index),
                    len(target_edges),
                ),
                target.bounds.y,
            )
            channel_index = forward_channels[(source.rank, target.rank)].index(route_index)
            channel = end.y - CHANNEL_TAIL - channel_index * OUTER_LANE_GAP
            points = _deduplicate((start, Point(start.x, channel), Point(end.x, channel), end))
        else:
            if source.id == target.id:
                if direction == "left-to-right":
                    start = Point(source.bounds.center_x - 16, source.bounds.y)
                    end = Point(source.bounds.center_x + 16, source.bounds.y)
                else:
                    start = Point(source.bounds.x, source.bounds.center_y - 16)
                    end = Point(source.bounds.x, source.bounds.center_y + 16)
            else:
                source_ports = outer_ports[(kind, source.id)]
                target_ports = outer_ports[(kind, target.id)]
                start = _outer_port(
                    source,
                    kind=kind,
                    direction=direction,
                    index=source_ports.index(route_index),
                    count=len(source_ports),
                )
                end = _outer_port(
                    target,
                    kind=kind,
                    direction=direction,
                    index=target_ports.index(route_index),
                    count=len(target_ports),
                )
            lane_index = lane_indexes[kind].index(route_index)
            if direction == "left-to-right":
                if kind == "feedback":
                    lane = top - OUTER_LANE_OFFSET - lane_index * OUTER_LANE_GAP
                else:
                    lane = bottom + OUTER_LANE_OFFSET + lane_index * OUTER_LANE_GAP
                points = _deduplicate((start, Point(start.x, lane), Point(end.x, lane), end))
            else:
                if kind == "feedback":
                    lane = left - OUTER_LANE_OFFSET - lane_index * OUTER_LANE_GAP
                else:
                    lane = right + OUTER_LANE_OFFSET + lane_index * OUTER_LANE_GAP
                points = _deduplicate((start, Point(lane, start.y), Point(lane, end.y), end))

        label = getattr(edge, "label", None)
        routed.append(
            RoutedEdge(
                edge=edge,
                source=source.id,
                target=target.id,
                label=label,
                points=points,
                label_position=_label_position(kind, direction, points, label, source, target),
                order=_order(edge, fallback)[0],
                feedback=kind == "feedback",
            )
        )
    return tuple(routed)


__all__ = ["edge_label_width", "route_edges"]
