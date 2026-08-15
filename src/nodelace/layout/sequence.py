"""Deterministic participant-lane layout for sequence diagrams."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .router import edge_label_width
from .types import (
    LayoutResult,
    Point,
    PositionedNode,
    Rect,
    RoutedEdge,
    SequenceMessage,
    SequenceParticipant,
)

CANVAS_PADDING = 64
PARTICIPANT_HEIGHT = 56
PARTICIPANT_MIN_WIDTH = 120
PARTICIPANT_MAX_WIDTH = 240
PARTICIPANT_GAP = 96
MESSAGE_TOP_GAP = 64
MESSAGE_GAP = 56
SELF_LOOP_WIDTH = 48
SELF_LOOP_HEIGHT = 24


def _round_up(value: int, grid: int = 4) -> int:
    return ((value + grid - 1) // grid) * grid


def _width(label: str) -> int:
    return max(
        PARTICIPANT_MIN_WIDTH,
        min(PARTICIPANT_MAX_WIDTH, _round_up(len(label) * 8 + 32)),
    )


def _order(item: Any, fallback: int) -> tuple[int, int]:
    return (int(getattr(item, "order", fallback)), fallback)


def _label_bounds(message: SequenceMessage) -> Rect | None:
    """Return a conservative bound for the renderer's message-label mask."""

    if not message.label:
        return None
    width = edge_label_width(str(message.label))
    # Edge labels render on at most two 14-unit lines.  Reserving the two-line
    # height for every label keeps this layout helper independent of the
    # renderer's wrapping details while remaining visually negligible.
    return Rect(
        message.label_position.x - width // 2,
        message.label_position.y - 21,
        width,
        34,
    )


def _translate_sequence(
    participants: tuple[SequenceParticipant, ...],
    nodes: tuple[PositionedNode, ...],
    messages: tuple[SequenceMessage, ...],
    edges: tuple[RoutedEdge, ...],
    dx: int,
    dy: int,
) -> tuple[
    tuple[SequenceParticipant, ...],
    tuple[PositionedNode, ...],
    tuple[SequenceMessage, ...],
    tuple[RoutedEdge, ...],
]:
    if dx == 0 and dy == 0:
        return participants, nodes, messages, edges

    translated_participants = tuple(
        replace(
            participant,
            bounds=participant.bounds.translated(dx, dy),
            lifeline_x=participant.lifeline_x + dx,
            lifeline_top=participant.lifeline_top + dy,
            lifeline_bottom=participant.lifeline_bottom + dy,
        )
        for participant in participants
    )
    translated_nodes = tuple(
        replace(node, bounds=node.bounds.translated(dx, dy)) for node in nodes
    )
    translated_messages = tuple(
        replace(
            message,
            points=tuple(point.translated(dx, dy) for point in message.points),
            label_position=message.label_position.translated(dx, dy),
            y=message.y + dy,
        )
        for message in messages
    )
    translated_edges = tuple(
        replace(
            edge,
            points=tuple(point.translated(dx, dy) for point in edge.points),
            label_position=edge.label_position.translated(dx, dy),
        )
        for edge in edges
    )
    return (
        translated_participants,
        translated_nodes,
        translated_messages,
        translated_edges,
    )


def layout_sequence(diagram: Any) -> LayoutResult:
    indexed_nodes = sorted(
        enumerate(tuple(diagram.nodes)), key=lambda pair: _order(pair[1], pair[0])
    )
    indexed_edges = sorted(
        enumerate(tuple(diagram.edges)), key=lambda pair: _order(pair[1], pair[0])
    )
    participant_specs: list[tuple[int, Any, str, str, Rect]] = []
    cursor = CANVAS_PADDING
    for fallback, node in indexed_nodes:
        identifier = str(node.id)
        label = str(getattr(node, "label", None) or identifier)
        bounds = Rect(cursor, CANVAS_PADDING, _width(label), PARTICIPANT_HEIGHT)
        participant_specs.append((fallback, node, identifier, label, bounds))
        cursor = bounds.right + PARTICIPANT_GAP

    first_message_y = CANVAS_PADDING + PARTICIPANT_HEIGHT + MESSAGE_TOP_GAP
    if indexed_edges:
        final_message_y = first_message_y + (len(indexed_edges) - 1) * MESSAGE_GAP
        lifeline_bottom = final_message_y + 64
    else:
        lifeline_bottom = first_message_y + 32
    lifeline_top = CANVAS_PADDING + PARTICIPANT_HEIGHT
    highlighted = set(getattr(diagram, "highlights", ()))
    participants = tuple(
        SequenceParticipant(
            node=node,
            id=identifier,
            label=label,
            bounds=bounds,
            lifeline_x=bounds.center_x,
            lifeline_top=lifeline_top,
            lifeline_bottom=lifeline_bottom,
            order=_order(node, fallback)[0],
            highlighted=identifier in highlighted,
        )
        for fallback, node, identifier, label, bounds in participant_specs
    )
    participant_by_id = {participant.id: participant for participant in participants}
    positioned_nodes = tuple(
        PositionedNode(
            node=participant.node,
            id=participant.id,
            label=participant.label,
            bounds=participant.bounds,
            rank=0,
            order=participant.order,
            highlighted=participant.highlighted,
        )
        for participant in participants
    )

    messages: list[SequenceMessage] = []
    routed_edges: list[RoutedEdge] = []
    for message_index, (fallback, edge) in enumerate(indexed_edges):
        source = participant_by_id[str(edge.source)]
        target = participant_by_id[str(edge.target)]
        y = first_message_y + message_index * MESSAGE_GAP
        self_message = source.id == target.id
        if self_message:
            points = (
                Point(source.lifeline_x, y),
                Point(source.lifeline_x + SELF_LOOP_WIDTH, y),
                Point(source.lifeline_x + SELF_LOOP_WIDTH, y + SELF_LOOP_HEIGHT),
                Point(source.lifeline_x, y + SELF_LOOP_HEIGHT),
            )
            label_position = Point(source.lifeline_x + SELF_LOOP_WIDTH // 2, y - 16)
        else:
            points = (Point(source.lifeline_x, y), Point(target.lifeline_x, y))
            label_position = Point((source.lifeline_x + target.lifeline_x) // 2, y - 16)
        order = _order(edge, fallback)[0]
        label = getattr(edge, "label", None)
        messages.append(
            SequenceMessage(
                edge=edge,
                source=source.id,
                target=target.id,
                label=label,
                points=points,
                label_position=label_position,
                y=y,
                order=order,
                self_message=self_message,
            )
        )
        routed_edges.append(
            RoutedEdge(
                edge=edge,
                source=source.id,
                target=target.id,
                label=label,
                points=points,
                label_position=label_position,
                order=order,
            )
        )

    message_tuple = tuple(messages)
    edge_tuple = tuple(routed_edges)
    label_bounds = tuple(
        bounds for message in message_tuple if (bounds := _label_bounds(message)) is not None
    )
    min_x = min(
        [participant.bounds.x for participant in participants]
        + [point.x for message in message_tuple for point in message.points]
        + [bounds.x for bounds in label_bounds]
        + [CANVAS_PADDING]
    )
    min_y = min(
        [participant.bounds.y for participant in participants]
        + [participant.lifeline_top for participant in participants]
        + [point.y for message in message_tuple for point in message.points]
        + [bounds.y for bounds in label_bounds]
        + [CANVAS_PADDING]
    )
    max_x = max(
        [participant.bounds.right for participant in participants]
        + [point.x for message in message_tuple for point in message.points]
        + [bounds.right for bounds in label_bounds]
        + [CANVAS_PADDING]
    )
    max_y = max(
        [participant.bounds.bottom for participant in participants]
        + [participant.lifeline_bottom for participant in participants]
        + [point.y for message in message_tuple for point in message.points]
        + [bounds.bottom for bounds in label_bounds]
        + [CANVAS_PADDING]
    )
    dx = max(0, CANVAS_PADDING - min_x)
    dy = max(0, CANVAS_PADDING - min_y)
    participants, positioned_nodes, message_tuple, edge_tuple = _translate_sequence(
        participants,
        positioned_nodes,
        message_tuple,
        edge_tuple,
        dx,
        dy,
    )
    canvas = Rect(
        0,
        0,
        _round_up(max_x + dx + CANVAS_PADDING),
        _round_up(max_y + dy + CANVAS_PADDING),
    )
    return LayoutResult(
        diagram=diagram,
        kind="sequence",
        direction="top-to-bottom",
        canvas=canvas,
        nodes=positioned_nodes,
        edges=edge_tuple,
        participants=participants,
        messages=message_tuple,
    )


__all__ = ["layout_sequence"]
