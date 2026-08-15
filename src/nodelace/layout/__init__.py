"""Public deterministic layout API."""

from __future__ import annotations

from typing import Any

from .layered import layout_layered, normalise_kind
from .sequence import layout_sequence
from .types import (
    LayoutResult,
    Point,
    PositionedGroup,
    PositionedNode,
    Rect,
    RoutedEdge,
    SequenceMessage,
    SequenceParticipant,
)


def layout_diagram(diagram: Any) -> LayoutResult:
    """Lay out a validated Nodelace diagram without randomness or I/O."""

    kind = normalise_kind(diagram.kind)
    if kind in {"architecture", "flow"}:
        return layout_layered(diagram)
    if kind == "sequence":
        return layout_sequence(diagram)
    raise ValueError(f"unsupported diagram kind: {kind}")


# A concise alias is convenient for the Python API while keeping the explicit
# command-shaped name for discoverability.
layout = layout_diagram

__all__ = [
    "LayoutResult",
    "Point",
    "PositionedGroup",
    "PositionedNode",
    "Rect",
    "RoutedEdge",
    "SequenceMessage",
    "SequenceParticipant",
    "layout",
    "layout_diagram",
]
