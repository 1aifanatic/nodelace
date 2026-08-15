"""Immutable geometry returned by Nodelace layout engines.

The renderer consumes these public value objects rather than depending on an
engine's internal graph representation.  All coordinates are integer SVG user
units so serialisation can remain byte-for-byte deterministic.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True, order=True)
class Point:
    x: int
    y: int

    def __iter__(self) -> Iterator[int]:
        yield self.x
        yield self.y

    def translated(self, dx: int, dy: int) -> Point:
        return Point(self.x + dx, self.y + dy)


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    @property
    def center(self) -> Point:
        return Point(self.center_x, self.center_y)

    def translated(self, dx: int, dy: int) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.width, self.height)


@dataclass(frozen=True, slots=True)
class PositionedNode:
    node: Any
    id: str
    label: str
    bounds: Rect
    rank: int
    order: int
    highlighted: bool = False

    @property
    def center(self) -> Point:
        return self.bounds.center


@dataclass(frozen=True, slots=True)
class PositionedGroup:
    group: Any
    name: str
    members: tuple[str, ...]
    bounds: Rect
    order: int


@dataclass(frozen=True, slots=True)
class RoutedEdge:
    edge: Any
    source: str
    target: str
    label: str | None
    points: tuple[Point, ...]
    label_position: Point
    order: int
    feedback: bool = False


@dataclass(frozen=True, slots=True)
class SequenceParticipant:
    node: Any
    id: str
    label: str
    bounds: Rect
    lifeline_x: int
    lifeline_top: int
    lifeline_bottom: int
    order: int
    highlighted: bool = False


@dataclass(frozen=True, slots=True)
class SequenceMessage:
    edge: Any
    source: str
    target: str
    label: str | None
    points: tuple[Point, ...]
    label_position: Point
    y: int
    order: int
    self_message: bool = False


@dataclass(frozen=True, slots=True)
class LayoutResult:
    diagram: Any
    kind: str
    direction: str
    canvas: Rect
    nodes: tuple[PositionedNode, ...] = ()
    groups: tuple[PositionedGroup, ...] = ()
    edges: tuple[RoutedEdge, ...] = ()
    participants: tuple[SequenceParticipant, ...] = ()
    messages: tuple[SequenceMessage, ...] = ()

    @property
    def width(self) -> int:
        return self.canvas.width

    @property
    def height(self) -> int:
        return self.canvas.height

    @property
    def bounds(self) -> Rect:
        return self.canvas

    @property
    def canvas_bounds(self) -> Rect:
        return self.canvas

    @property
    def node_map(self) -> Mapping[str, PositionedNode]:
        return MappingProxyType({node.id: node for node in self.nodes})

    @property
    def group_map(self) -> Mapping[str, PositionedGroup]:
        return MappingProxyType({group.name: group for group in self.groups})

    @property
    def participant_map(self) -> Mapping[str, SequenceParticipant]:
        return MappingProxyType({participant.id: participant for participant in self.participants})

    def node_for(self, identifier: str) -> PositionedNode:
        return self.node_map[identifier]

    def group_for(self, name: str) -> PositionedGroup:
        return self.group_map[name]


__all__ = [
    "LayoutResult",
    "Point",
    "PositionedGroup",
    "PositionedNode",
    "Rect",
    "RoutedEdge",
    "SequenceMessage",
    "SequenceParticipant",
]
