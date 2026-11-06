"""Strict parser for Nodelace's small, non-executable text language."""

from __future__ import annotations

import shlex
from itertools import pairwise
from unicodedata import category

from nodelace.errors import DiagramSyntaxError, DiagramValidationError
from nodelace.model import (
    MAX_EDGE_LABEL_LENGTH,
    MAX_EDGES,
    MAX_GROUPS,
    MAX_NAME_LENGTH,
    MAX_NODES,
    MAX_TITLE_LENGTH,
    Activation,
    Diagram,
    DiagramKind,
    Direction,
    Edge,
    Fragment,
    Group,
    Node,
    _is_unsafe_character,
)

_KIND_WORDS = {kind.value: kind for kind in DiagramKind}


def _split_edges(text: str) -> tuple[list[str], list[str]]:
    parts: list[str] = []
    kinds: list[str] = []
    start = index = 0
    quoted = escaped = False
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted:
            arrow = next((a for a in ("-->", "->", "~>", "=>") if text.startswith(a, index)), None)
            if arrow:
                parts.append(text[start:index])
                kinds.append(
                    {"-->": "return", "->": "normal", "~>": "async", "=>": "primary"}[arrow]
                )
                index += len(arrow)
                start = index
                continue
        index += 1
    parts.append(text[start:])
    return parts, kinds


def _strip_comment(line: str) -> str:
    """Remove a comment marker outside quotes when it begins a token."""

    quoted = False
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if quoted and character == "\\":
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
            continue
        starts_token = index == 0 or line[index - 1].isspace()
        if not quoted and starts_token and character == "#":
            return line[:index].rstrip()
        if not quoted and starts_token and line.startswith("//", index):
            return line[:index].rstrip()
    return line


def _split_unquoted(text: str, separator: str, *, maxsplit: int = -1) -> list[str]:
    """Split on a literal separator, ignoring occurrences inside double quotes."""

    parts: list[str] = []
    start = 0
    index = 0
    splits = 0
    quoted = False
    escaped = False
    while index < len(text):
        character = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if quoted and character == "\\":
            escaped = True
            index += 1
            continue
        if character == '"':
            quoted = not quoted
            index += 1
            continue
        if not quoted and text.startswith(separator, index) and (maxsplit < 0 or splits < maxsplit):
            parts.append(text[start:index])
            index += len(separator)
            start = index
            splits += 1
            continue
        index += 1
    parts.append(text[start:])
    return parts


def _syntax(
    message: str,
    *,
    source_name: str,
    line_number: int,
    original: str,
    column: int | None = None,
) -> DiagramSyntaxError:
    return DiagramSyntaxError(
        message,
        source_name=source_name,
        line=line_number,
        column=column,
        line_text=original,
    )


def _validation(
    message: str,
    *,
    source_name: str,
    line_number: int,
    original: str,
) -> DiagramValidationError:
    return DiagramValidationError(
        message,
        source_name=source_name,
        line=line_number,
        line_text=original,
    )


def _decode_text(
    token: str,
    *,
    role: str,
    source_name: str,
    line_number: int,
    original: str,
    require_quoted: bool = False,
    max_length: int | None = None,
) -> str:
    """Decode one quoted or unquoted name/label token."""

    value = token.strip()
    if not value:
        raise _syntax(
            f"{role} cannot be empty",
            source_name=source_name,
            line_number=line_number,
            original=original,
        )
    if not value.startswith('"'):
        if require_quoted:
            raise _syntax(
                f"{role} must be enclosed in double quotes",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        if '"' in value:
            raise _syntax(
                f"a double quote in {role} must be escaped inside a quoted value",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        result = value
        if max_length is not None and len(result) > max_length:
            raise _validation(
                f"{role} is longer than {max_length} characters",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        unsafe = next((character for character in result if _is_unsafe_character(character)), None)
        if unsafe is not None:
            reason = (
                "a control character" if category(unsafe) == "Cc" else "an XML-unsafe character"
            )
            raise _validation(
                f"{role} contains {reason}",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        return result

    decoded: list[str] = []
    index = 1
    while index < len(value):
        character = value[index]
        if character == '"':
            if index != len(value) - 1:
                raise _syntax(
                    f"unexpected text after quoted {role}",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            result = "".join(decoded)
            if not result:
                raise _syntax(
                    f"{role} cannot be empty",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            if max_length is not None and len(result) > max_length:
                raise _validation(
                    f"{role} is longer than {max_length} characters",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            unsafe = next(
                (character for character in result if _is_unsafe_character(character)), None
            )
            if unsafe is not None:
                reason = (
                    "a control character" if category(unsafe) == "Cc" else "an XML-unsafe character"
                )
                raise _validation(
                    f"{role} contains {reason}",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            return result
        if character == "\\":
            index += 1
            if index >= len(value):
                break
            escaped = value[index]
            if escaped not in {'"', "\\"}:
                raise _syntax(
                    rf"unsupported escape '\{escaped}' in {role}; use '\\' or '\"'",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            decoded.append(escaped)
        else:
            decoded.append(character)
        index += 1
    raise _syntax(
        f"unterminated quoted {role}",
        source_name=source_name,
        line_number=line_number,
        original=original,
    )


def parse_diagram(source: str, *, source_name: str = "<string>") -> Diagram:
    """Parse *source* into an immutable :class:`~nodelace.model.Diagram`."""

    # UTF-8 editors on Windows commonly write a single signature at the start
    # of a text file.  Treat that signature as encoding metadata, not as part
    # of the first diagram keyword or node identifier.  A BOM anywhere else
    # remains ordinary source text.
    if source.startswith("\ufeff"):
        source = source[1:]

    kind = DiagramKind.FLOW
    title: str | None = None
    direction: Direction | None = None
    direction_seen = False
    node_ids: list[str] = []
    node_specs: dict[str, Node] = {}
    edges: list[Edge] = []
    groups: list[Group] = []
    group_names: set[str] = set()
    membership: dict[str, str] = {}
    highlights: list[str] = []
    highlighted: set[str] = set()
    statement_index = 0
    fragments: list[Fragment] = []
    frames: list[dict] = []
    active: dict[str, list[int]] = {}
    activations: list[Activation] = []

    def remember(name: str, *, line_number: int, original: str) -> None:
        if name not in node_ids:
            if len(node_ids) == MAX_NODES:
                raise _validation(
                    f"diagram has more than {MAX_NODES} nodes (first extra node is {name!r})",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            node_ids.append(name)

    for line_number, original in enumerate(source.splitlines(), start=1):
        line = _strip_comment(original).strip()
        if not line:
            continue
        statement_index += 1
        first_word, *header_tail = line.split(maxsplit=1)
        if statement_index == 1 and first_word in _KIND_WORDS:
            kind = _KIND_WORDS[first_word]
            if header_tail:
                title = _decode_text(
                    header_tail[0],
                    role="diagram title",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                    require_quoted=True,
                    max_length=MAX_TITLE_LENGTH,
                )
            continue
        if first_word in _KIND_WORDS:
            raise _syntax(
                "diagram type header must be the first statement",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        if first_word == "node":
            try:
                tokens = shlex.split(line)
                if len(tokens) < 2:
                    raise ValueError("node needs an identifier")
                name = tokens[1]
                if name in node_specs:
                    raise ValueError(f"node {name!r} is already declared")
                attributes: dict[str, str] = {}
                for token in tokens[2:]:
                    key, separator, value = token.partition("=")
                    if not separator or key not in {"label", "role", "shape", "tag", "sublabel"}:
                        raise ValueError(
                            "node attributes are label=, role=, shape=, tag=, sublabel="
                        )
                    if key in attributes:
                        raise ValueError(f"duplicate node attribute {key!r}")
                    attributes[key] = value
                node_specs[name] = Node(name, **attributes)
                remember(name, line_number=line_number, original=original)
            except (ValueError, DiagramValidationError) as error:
                raise _validation(
                    str(error), source_name=source_name, line_number=line_number, original=original
                ) from error
            continue
        if first_word in {"alt", "opt", "loop", "else", "end", "activate", "deactivate"}:
            try:
                if kind is not DiagramKind.SEQUENCE:
                    raise ValueError("sequence directives require a sequence diagram")
                tail = line[len(first_word) :].strip()
                if first_word == "end":
                    if tail or not frames:
                        raise ValueError("end requires an open sequence fragment and no arguments")
                    frame = frames.pop()
                    fragments.append(Fragment(**frame, end=len(edges)))
                elif first_word in {"activate", "deactivate"}:
                    name = _decode_text(
                        tail,
                        role="participant",
                        source_name=source_name,
                        line_number=line_number,
                        original=original,
                        max_length=MAX_NAME_LENGTH,
                    )
                    remember(name, line_number=line_number, original=original)
                    if first_word == "activate":
                        active.setdefault(name, []).append(len(edges))
                    elif active.get(name):
                        activations.append(Activation(name, active[name].pop(), len(edges)))
                    else:
                        raise ValueError(f"participant {name!r} is not active")
                else:
                    guard = _decode_text(
                        tail,
                        role="guard",
                        source_name=source_name,
                        line_number=line_number,
                        original=original,
                        require_quoted=True,
                        max_length=MAX_NAME_LENGTH,
                    )
                    if first_word == "else":
                        if not frames or frames[-1]["operator"] != "alt" or "split" in frames[-1]:
                            raise ValueError("else requires an alt with no previous else")
                        frames[-1].update(split=len(edges), else_guard=guard)
                    else:
                        if len(frames) >= 2:
                            raise ValueError("sequence fragments permit one nested level")
                        frames.append(
                            dict(
                                operator=first_word,
                                guard=guard,
                                start=len(edges),
                                depth=len(frames),
                            )
                        )
            except (ValueError, DiagramValidationError) as error:
                raise _validation(
                    str(error), source_name=source_name, line_number=line_number, original=original
                ) from error
            continue
        if line == "direction":
            raise _syntax(
                "direction needs 'left-to-right' or 'top-to-bottom'",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        if line.startswith("direction "):
            if kind is DiagramKind.SEQUENCE:
                raise _validation(
                    "direction is not supported for sequence diagrams",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            if direction_seen:
                raise _validation(
                    "direction may only be specified once",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            value = line.removeprefix("direction ").strip()
            try:
                direction = Direction(value)
            except ValueError as error:
                raise DiagramSyntaxError(
                    "direction must be 'left-to-right' or 'top-to-bottom'",
                    source_name=source_name,
                    line=line_number,
                    line_text=original,
                ) from error
            direction_seen = True
            continue
        if line == "group":
            raise _syntax(
                "a group needs a name, ':', and one or more members",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        if line.startswith("group "):
            if kind is DiagramKind.SEQUENCE:
                raise _validation(
                    "groups are not supported for sequence diagrams",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            body = line.removeprefix("group ")
            if ":" not in body:
                raise DiagramSyntaxError(
                    "a group needs ':' followed by one or more members",
                    source_name=source_name,
                    line=line_number,
                    line_text=original,
                )
            group_parts = _split_unquoted(body, ":", maxsplit=1)
            if len(group_parts) != 2:
                raise _syntax(
                    "a group needs ':' followed by one or more members",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            group_name = _decode_text(
                group_parts[0],
                role="group name",
                source_name=source_name,
                line_number=line_number,
                original=original,
                max_length=MAX_NAME_LENGTH,
            )
            members = tuple(
                _decode_text(
                    part,
                    role="group member",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                    max_length=MAX_NAME_LENGTH,
                )
                for part in _split_unquoted(group_parts[1], ",")
            )
            if group_name in group_names:
                raise _validation(
                    f"group {group_name!r} is already defined",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            if len(groups) == MAX_GROUPS:
                raise _validation(
                    f"diagram has more than {MAX_GROUPS} groups",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            seen_members: set[str] = set()
            for member in members:
                if member in seen_members:
                    raise _validation(
                        f"group {group_name!r} lists node {member!r} more than once",
                        source_name=source_name,
                        line_number=line_number,
                        original=original,
                    )
                seen_members.add(member)
                existing_group = membership.get(member)
                if existing_group is not None:
                    raise _validation(
                        f"node {member!r} cannot belong to both "
                        f"{existing_group!r} and {group_name!r}",
                        source_name=source_name,
                        line_number=line_number,
                        original=original,
                    )
            groups.append(Group(group_name, members))
            group_names.add(group_name)
            for member in members:
                membership[member] = group_name
                remember(member, line_number=line_number, original=original)
            continue
        if line == "highlight":
            raise _syntax(
                "highlight needs one or more comma-separated node names",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        if line.startswith("highlight "):
            names = tuple(
                _decode_text(
                    part,
                    role="highlighted node",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                    max_length=MAX_NAME_LENGTH,
                )
                for part in _split_unquoted(line.removeprefix("highlight "), ",")
            )
            for name in names:
                if name in highlighted:
                    raise _validation(
                        f"node {name!r} is already highlighted",
                        source_name=source_name,
                        line_number=line_number,
                        original=original,
                    )
                remember(name, line_number=line_number, original=original)
                highlights.append(name)
                highlighted.add(name)
            continue
        is_call = line.startswith("call ")
        edge_and_label = _split_unquoted(line[5:] if is_call else line, ":", maxsplit=1)
        edge_parts, edge_kinds = _split_edges(edge_and_label[0])
        if len(edge_parts) > 1:
            names = [
                _decode_text(
                    part,
                    role="node name",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                    max_length=MAX_NAME_LENGTH,
                )
                for part in edge_parts
            ]
            label = (
                _decode_text(
                    edge_and_label[1],
                    role="edge label",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                    max_length=MAX_EDGE_LABEL_LENGTH,
                )
                if len(edge_and_label) == 2
                else None
            )
            for name in names:
                remember(name, line_number=line_number, original=original)
            relationships = list(pairwise(names))
            if len(edges) + len(relationships) > MAX_EDGES:
                raise _validation(
                    f"diagram has more than {MAX_EDGES} edges",
                    source_name=source_name,
                    line_number=line_number,
                    original=original,
                )
            edges.extend(
                Edge(left, right, kind="call" if is_call else edge_kind)
                for (left, right), edge_kind in zip(
                    relationships[:-1], edge_kinds[:-1], strict=True
                )
            )
            final_source, final_target = relationships[-1]
            edges.append(
                Edge(final_source, final_target, label, "call" if is_call else edge_kinds[-1])
            )
            continue
        if statement_index == 1 and header_tail and header_tail[0].startswith('"'):
            raise _syntax(
                f"unsupported diagram type {first_word!r}; use architecture, flow, or sequence",
                source_name=source_name,
                line_number=line_number,
                original=original,
            )
        raise DiagramSyntaxError(
            "expected an edge or directive",
            source_name=source_name,
            line=line_number,
            line_text=original,
        )

    if frames or any(active.values()):
        raise DiagramValidationError("unclosed fragment or activation", source_name=source_name)
    return Diagram(
        kind=kind,
        title=title,
        nodes=tuple(node_specs.get(node_id) or Node(node_id) for node_id in node_ids),
        edges=tuple(edges),
        groups=tuple(groups),
        highlights=tuple(highlights),
        direction=direction,
        fragments=tuple(sorted(fragments, key=lambda f: (f.start, f.depth, -f.end))),
        activations=tuple(activations),
    )


__all__ = ["parse_diagram"]
