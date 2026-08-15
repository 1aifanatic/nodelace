"""Immutable public domain model for a parsed Nodelace diagram."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from unicodedata import category

from nodelace.errors import DiagramValidationError

MAX_NODES = 50
MAX_EDGES = 200
MAX_GROUPS = 20
MAX_EDGE_LABEL_LENGTH = 500
MAX_NAME_LENGTH = 200
MAX_TITLE_LENGTH = 200


def _model_error(message: str) -> DiagramValidationError:
    return DiagramValidationError(message, source_name="<model>")


def _validate_text(value: object, *, role: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise _model_error(f"{role} must be a string")
    if not value:
        raise _model_error(f"{role} cannot be empty")
    if len(value) > max_length:
        raise _model_error(f"{role} is longer than {max_length} characters")
    unsafe = next((character for character in value if _is_unsafe_character(character)), None)
    if unsafe is not None:
        reason = "a control character" if category(unsafe) == "Cc" else "an XML-unsafe character"
        raise _model_error(f"{role} contains {reason}")
    return value


def _is_unsafe_character(character: str) -> bool:
    """Return whether a character is unsafe in deterministic XML output."""

    codepoint = ord(character)
    is_xml_character = (
        codepoint in {0x09, 0x0A, 0x0D}
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )
    return not is_xml_character or category(character) == "Cc"


def _tuple(value: object, *, role: str) -> tuple[object, ...]:
    if isinstance(value, str):
        raise _model_error(f"{role} must be a collection, not a string")
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise _model_error(f"{role} must be a collection") from error


class DiagramKind(StrEnum):
    """Diagram families supported by the 0.1 language."""

    ARCHITECTURE = "architecture"
    FLOW = "flow"
    SEQUENCE = "sequence"


class Direction(StrEnum):
    """Optional layout direction requested by the author."""

    LEFT_TO_RIGHT = "left-to-right"
    TOP_TO_BOTTOM = "top-to-bottom"


@dataclass(frozen=True, slots=True)
class Node:
    """A uniquely named diagram node."""

    id: str
    label: str | None = None

    def __post_init__(self) -> None:
        node_id = _validate_text(self.id, role="node id", max_length=MAX_NAME_LENGTH)
        label = (
            node_id
            if self.label is None
            else _validate_text(self.label, role="node label", max_length=MAX_NAME_LENGTH)
        )
        object.__setattr__(self, "id", node_id)
        object.__setattr__(self, "label", label)

    @property
    def name(self) -> str:
        """Alias for ``id`` for callers that use display-name terminology."""

        return self.id


@dataclass(frozen=True, slots=True)
class Edge:
    """A directed relationship between two node ids."""

    source: str
    target: str
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source",
            _validate_text(self.source, role="edge source", max_length=MAX_NAME_LENGTH),
        )
        object.__setattr__(
            self,
            "target",
            _validate_text(self.target, role="edge target", max_length=MAX_NAME_LENGTH),
        )
        if self.label is not None:
            object.__setattr__(
                self,
                "label",
                _validate_text(
                    self.label,
                    role="edge label",
                    max_length=MAX_EDGE_LABEL_LENGTH,
                ),
            )


@dataclass(frozen=True, slots=True)
class Group:
    """A flat, ordered collection of node ids."""

    name: str
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        name = _validate_text(self.name, role="group name", max_length=MAX_NAME_LENGTH)
        raw_members = _tuple(self.members, role="group members")
        if not raw_members:
            raise _model_error("group must contain at least one member")
        members = tuple(
            _validate_text(member, role="group member", max_length=MAX_NAME_LENGTH)
            for member in raw_members
        )
        seen: set[str] = set()
        for member in members:
            if member in seen:
                raise _model_error(f"group {name!r} lists node {member!r} more than once")
            seen.add(member)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "members", members)


@dataclass(frozen=True, slots=True)
class Diagram:
    """A complete deterministic diagram document."""

    kind: DiagramKind = DiagramKind.FLOW
    title: str | None = None
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    groups: tuple[Group, ...] = ()
    highlights: tuple[str, ...] = ()
    direction: Direction | None = None

    def __post_init__(self) -> None:
        try:
            kind = DiagramKind(self.kind)
        except (TypeError, ValueError) as error:
            raise _model_error(
                "diagram kind must be 'architecture', 'flow', or 'sequence'"
            ) from error
        object.__setattr__(self, "kind", kind)

        if self.title is not None:
            object.__setattr__(
                self,
                "title",
                _validate_text(
                    self.title,
                    role="diagram title",
                    max_length=MAX_TITLE_LENGTH,
                ),
            )

        if self.direction is None:
            direction = None
        else:
            try:
                direction = Direction(self.direction)
            except (TypeError, ValueError) as error:
                raise _model_error(
                    "direction must be 'left-to-right' or 'top-to-bottom'"
                ) from error
        object.__setattr__(self, "direction", direction)

        raw_nodes = _tuple(self.nodes, role="nodes")
        raw_edges = _tuple(self.edges, role="edges")
        raw_groups = _tuple(self.groups, role="groups")
        raw_highlights = _tuple(self.highlights, role="highlights")
        if not all(isinstance(node, Node) for node in raw_nodes):
            raise _model_error("nodes must contain only Node values")
        if not all(isinstance(edge, Edge) for edge in raw_edges):
            raise _model_error("edges must contain only Edge values")
        if not all(isinstance(group, Group) for group in raw_groups):
            raise _model_error("groups must contain only Group values")

        nodes = tuple(raw_nodes)
        edges = tuple(raw_edges)
        groups = tuple(raw_groups)
        highlights = tuple(
            _validate_text(value, role="highlight", max_length=MAX_NAME_LENGTH)
            for value in raw_highlights
        )
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "groups", groups)
        object.__setattr__(self, "highlights", highlights)

        if len(nodes) > MAX_NODES:
            raise _model_error(f"diagram has more than {MAX_NODES} nodes")
        if len(edges) > MAX_EDGES:
            raise _model_error(f"diagram has more than {MAX_EDGES} edges")
        if len(groups) > MAX_GROUPS:
            raise _model_error(f"diagram has more than {MAX_GROUPS} groups")
        if kind is DiagramKind.SEQUENCE and direction is not None:
            raise _model_error("direction is not supported for sequence diagrams")
        if kind is DiagramKind.SEQUENCE and groups:
            raise _model_error("groups are not supported for sequence diagrams")

        node_ids: set[str] = set()
        for node in nodes:
            if node.id in node_ids:
                raise _model_error(f"node id {node.id!r} is defined more than once")
            node_ids.add(node.id)

        for edge in edges:
            if edge.source not in node_ids:
                raise _model_error(f"edge source {edge.source!r} is not a defined node")
            if edge.target not in node_ids:
                raise _model_error(f"edge target {edge.target!r} is not a defined node")

        group_names: set[str] = set()
        membership: dict[str, str] = {}
        for group in groups:
            if group.name in group_names:
                raise _model_error(f"group {group.name!r} is defined more than once")
            group_names.add(group.name)
            for member in group.members:
                if member not in node_ids:
                    raise _model_error(
                        f"group {group.name!r} references undefined node {member!r}"
                    )
                previous = membership.get(member)
                if previous is not None:
                    raise _model_error(
                        f"node {member!r} cannot belong to both "
                        f"{previous!r} and {group.name!r}"
                    )
                membership[member] = group.name

        highlighted: set[str] = set()
        for node_id in highlights:
            if node_id not in node_ids:
                raise _model_error(f"highlight references undefined node {node_id!r}")
            if node_id in highlighted:
                raise _model_error(f"node {node_id!r} is highlighted more than once")
            highlighted.add(node_id)

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Node ids in their stable first-mention order."""

        return tuple(node.id for node in self.nodes)


__all__ = [
    "MAX_EDGES",
    "MAX_EDGE_LABEL_LENGTH",
    "MAX_GROUPS",
    "MAX_NAME_LENGTH",
    "MAX_NODES",
    "MAX_TITLE_LENGTH",
    "Diagram",
    "DiagramKind",
    "Direction",
    "Edge",
    "Group",
    "Node",
]
