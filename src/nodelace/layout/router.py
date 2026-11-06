"""Deterministic orthogonal connector routing."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from heapq import heappop, heappush
from itertools import pairwise
from typing import Any, Literal

from nodelace.text import edge_label_size

from .types import Point, PositionedNode, Rect, RoutedEdge

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

    return edge_label_size(label)[0]


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


def segment_hits_rect(first: Point, second: Point, rect: Rect) -> bool:
    """Whether an orthogonal segment crosses the open interior of a rectangle."""
    if first.x == second.x:
        return rect.x < first.x < rect.right and (
            max(min(first.y, second.y), rect.y) < min(max(first.y, second.y), rect.bottom)
        )
    if first.y == second.y:
        return rect.y < first.y < rect.bottom and (
            max(min(first.x, second.x), rect.x) < min(max(first.x, second.x), rect.right)
        )
    return False


def _lead(port: Point, bounds: Rect) -> Point:
    if port.x == bounds.x:
        return Point(port.x - 16, port.y)
    if port.x == bounds.right:
        return Point(port.x + 16, port.y)
    if port.y == bounds.y:
        return Point(port.x, port.y - 16)
    return Point(port.x, port.y + 16)


def _shape_endpoint(port: Point, neighbor: Point, node: PositionedNode) -> tuple[Point, Point]:
    b = node.bounds
    if node.node.shape == "decision":
        if port.y in {b.y, b.bottom}:
            offset = round(abs(port.x - b.center_x) * b.height / b.width)
            return Point(port.x, port.y + offset if port.y == b.y else port.y - offset), neighbor
        offset = round(abs(port.y - b.center_y) * b.width / b.height)
        return Point(port.x + offset if port.x == b.x else port.x - offset, port.y), neighbor
    if node.node.shape == "merge":
        if port.y in {b.y, b.bottom}:
            point = Point(b.center_x, b.center_y + (-8 if port.y == b.y else 8))
            return point, Point(point.x, neighbor.y)
        point = Point(b.center_x + (-8 if port.x == b.x else 8), b.center_y)
        return point, Point(neighbor.x, point.y)
    return port, neighbor


def _avoid_obstacles(
    points: tuple[Point, ...],
    nodes: tuple[PositionedNode, ...],
    source: PositionedNode,
    target: PositionedNode,
) -> tuple[Point, ...]:
    """Retain clear routes; repair blocked routes on a deterministic visibility grid."""
    if not any(segment_hits_rect(a, b, n.bounds) for a, b in pairwise(points) for n in nodes):
        return points
    start = _lead(points[0], source.bounds)
    end = _lead(points[-1], target.bounds)
    obstacles = tuple(
        Rect(n.bounds.x - 12, n.bounds.y - 12, n.bounds.width + 24, n.bounds.height + 24)
        for n in nodes
    )
    xs = sorted({start.x, end.x, *(x for r in obstacles for x in (r.x, r.right))})
    ys = sorted({start.y, end.y, *(y for r in obstacles for y in (r.y, r.bottom))})
    origin = (xs.index(start.x), ys.index(start.y), 0)
    costs = {origin: 0}
    previous: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    queue = [(0, 0, origin)]
    final = None
    while queue:
        _, cost, state = heappop(queue)
        if cost != costs[state]:
            continue
        x, y, axis = state
        here = Point(xs[x], ys[y])
        if here == end:
            final = state
            break
        for dx, dy, next_axis in ((-1, 0, 1), (1, 0, 1), (0, -1, 2), (0, 1, 2)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            there = Point(xs[nx], ys[ny])
            if any(segment_hits_rect(here, there, r) for r in obstacles):
                continue
            next_state = (nx, ny, next_axis)
            distance = abs(there.x - here.x) + abs(there.y - here.y)
            next_cost = cost + distance + (24 if axis and axis != next_axis else 0)
            if next_cost >= costs.get(next_state, float("inf")):
                continue
            costs[next_state] = next_cost
            previous[next_state] = state
            estimate = next_cost + abs(there.x - end.x) + abs(there.y - end.y)
            heappush(queue, (estimate, next_cost, next_state))
    if final is None:
        # A diagnostic will fail closed instead of hiding an unrouteable relationship.
        return points
    reverse = []
    while final != origin:
        reverse.append(Point(xs[final[0]], ys[final[1]]))
        final = previous[final]
    path = [points[0], start, *reversed(reverse), points[-1]]
    simplified: list[Point] = []
    for point in _deduplicate(tuple(path)):
        while len(simplified) >= 2 and (
            simplified[-2].x == simplified[-1].x == point.x
            or simplified[-2].y == simplified[-1].y == point.y
        ):
            simplified.pop()
        simplified.append(point)
    return tuple(simplified)


def label_bounds(label: str | None, position: Point) -> Rect:
    width, height = edge_label_size(label)
    return Rect(position.x - width // 2, position.y - 14 - (height - 20) // 2, width, height)


def rectangles_overlap(first: Rect, second: Rect, padding: int = 0) -> bool:
    return (
        first.x < second.right + padding
        and second.x < first.right + padding
        and first.y < second.bottom + padding
        and second.y < first.bottom + padding
    )


def _clear_label(
    label: str | None,
    preferred: Point,
    points: tuple[Point, ...],
    nodes: tuple[PositionedNode, ...],
    occupied: list[Rect],
) -> Point:
    if not label:
        return preferred
    candidates = [preferred]
    for a, b in sorted(
        pairwise(points), key=lambda ab: -(abs(ab[0].x - ab[1].x) + abs(ab[0].y - ab[1].y))
    ):
        if a.y == b.y:
            candidates.extend((_above(a, b), _below(a, b)))
        else:
            candidates.extend(
                (_beside(a, b, label, side="left"), _beside(a, b, label, side="right"))
            )
    for point in candidates:
        bounds = label_bounds(label, point)
        if not any(
            rectangles_overlap(bounds, r, 4) for r in (*(n.bounds for n in nodes), *occupied)
        ):
            occupied.append(bounds)
            return point
    occupied.append(label_bounds(label, preferred))
    return preferred


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
    occupied_labels: list[Rect] = []
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

        points = _avoid_obstacles(points, nodes, source, target)
        route = list(points)
        route[0], route[1] = _shape_endpoint(route[0], route[1], source)
        route[-1], route[-2] = _shape_endpoint(route[-1], route[-2], target)
        points = tuple(route)
        label = getattr(edge, "label", None)
        preferred = _label_position(kind, direction, points, label, source, target)
        label_position = _clear_label(label, preferred, points, nodes, occupied_labels)
        routed.append(
            RoutedEdge(
                edge=edge,
                source=source.id,
                target=target.id,
                label=label,
                points=points,
                label_position=label_position,
                order=_order(edge, fallback)[0],
                feedback=kind == "feedback",
            )
        )
    return tuple(routed)


__all__ = ["edge_label_width", "route_edges"]
