"""Deterministic participant-lane layout for sequence diagrams."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from nodelace.text import node_text_width, text_width

from .router import edge_label_width
from .types import (
    LayoutResult,
    Point,
    PositionedNode,
    Rect,
    RoutedEdge,
    SequenceFrame,
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
        min(PARTICIPANT_MAX_WIDTH, _round_up(text_width(label) + 32)),
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
    translated_nodes = tuple(replace(node, bounds=node.bounds.translated(dx, dy)) for node in nodes)
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
        height = 80 if node.tag or node.sublabel else PARTICIPANT_HEIGHT
        width = max(
            _width(label), min(PARTICIPANT_MAX_WIDTH, _round_up(node_text_width(node) + 32))
        )
        bounds = Rect(cursor, CANVAS_PADDING, width, height)
        participant_specs.append((fallback, node, identifier, label, bounds))
        cursor = bounds.right + PARTICIPANT_GAP

    participant_height = max(
        (item[4].height for item in participant_specs), default=PARTICIPANT_HEIGHT
    )
    first_message_y = CANVAS_PADDING + participant_height + MESSAGE_TOP_GAP
    timeline = first_message_y
    message_y: list[int] = []
    frame_tops: dict[int, int] = {}
    frame_bottoms: dict[int, int] = {}
    dividers: dict[int, int] = {}
    for index in range(len(indexed_edges) + 1):
        for fi, frame in sorted(enumerate(diagram.fragments), key=lambda item: -item[1].depth):
            if frame.end == index:
                frame_bottoms[fi] = timeline - 24
                timeline += 24
        for fi, frame in sorted(enumerate(diagram.fragments), key=lambda item: item[1].depth):
            if frame.split == index:
                dividers[fi] = timeline - 16
                timeline += 64
            if frame.start == index:
                frame_tops[fi] = timeline - 16
                timeline += 80
        if index < len(indexed_edges):
            message_y.append(timeline)
            edge = indexed_edges[index][1]
            timeline += MESSAGE_GAP + (SELF_LOOP_HEIGHT if edge.source == edge.target else 0)
    lifeline_bottom = timeline + 8 if indexed_edges else first_message_y + 32
    highlighted = set(getattr(diagram, "highlights", ()))
    participants = tuple(
        SequenceParticipant(
            node=node,
            id=identifier,
            label=label,
            bounds=bounds,
            lifeline_x=bounds.center_x,
            lifeline_top=bounds.bottom,
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
        y = message_y[message_index]
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
    frames: list[SequenceFrame] = []
    for fi, frame in enumerate(diagram.fragments):
        frame_messages = messages[frame.start : frame.end]
        actors = {actor for message in frame_messages for actor in (message.source, message.target)}
        inset = 48 - frame.depth * 16
        left = min(participant_by_id[actor].lifeline_x for actor in actors) - inset
        right = max(participant_by_id[actor].lifeline_x for actor in actors) + inset
        for message in frame_messages:
            left = min(left, *(point.x - 16 for point in message.points))
            right = max(right, *(point.x + 16 for point in message.points))
            if bounds := _label_bounds(message):
                left = min(left, bounds.x - 12)
                right = max(right, bounds.right + 12)
        guard_width = (
            max(
                text_width(f"[{frame.guard}]", 11, "mono"),
                text_width(f"[{frame.else_guard or ''}]", 11, "mono"),
            )
            + 32
        )
        frame_width = max(right - left, min(640, guard_width))
        frames.append(
            SequenceFrame(
                frame,
                Rect(
                    left, frame_tops[fi], _round_up(frame_width), frame_bottoms[fi] - frame_tops[fi]
                ),
                dividers.get(fi),
            )
        )
    for index, outer in enumerate(frames):
        children = [
            inner.bounds
            for inner in frames
            if inner.fragment.depth > outer.fragment.depth
            and outer.fragment.start <= inner.fragment.start
            and inner.fragment.end <= outer.fragment.end
        ]
        if children:
            left = min(outer.bounds.x, *(child.x - 16 for child in children))
            right = max(outer.bounds.right, *(child.right + 16 for child in children))
            frames[index] = replace(
                outer, bounds=Rect(left, outer.bounds.y, right - left, outer.bounds.height)
            )
    label_bounds = tuple(
        bounds for message in message_tuple if (bounds := _label_bounds(message)) is not None
    )
    min_x = min(
        [participant.bounds.x for participant in participants]
        + [point.x for message in message_tuple for point in message.points]
        + [bounds.x for bounds in label_bounds]
        + [frame.bounds.x for frame in frames]
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
        + [frame.bounds.right for frame in frames]
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
        frames=tuple(
            replace(
                frame,
                bounds=frame.bounds.translated(dx, dy),
                divider_y=frame.divider_y + dy if frame.divider_y is not None else None,
            )
            for frame in frames
        ),
    )


__all__ = ["layout_sequence"]
