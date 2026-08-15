"""Accessible, deterministic SVG and HTML rendering for Nodelace."""

from __future__ import annotations

import hashlib
import html
import os
import secrets
import shutil
import stat
import warnings
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from nodelace import __version__
from nodelace.dsl import parse_diagram
from nodelace.errors import DiagramValidationError
from nodelace.layout import LayoutResult, Point, Rect, layout_diagram
from nodelace.model import Diagram
from nodelace.theme import EDITORIAL_LIGHT, Theme, embedded_font_license_notice, svg_css

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
MAX_SOURCE_BYTES = 256 * 1024
HEADER_HEIGHT = 104
FOOTER_HEIGHT = 40
MIN_CANVAS_WIDTH = 640


class DiagramDensityWarning(UserWarning):
    """The diagram rendered completely but exceeds the editorial density budget."""


def _tag(name: str) -> str:
    # Elements are deliberately built without Clark-notation names. The root
    # carries an explicit default namespace, so the serialized XML is proper
    # SVG while remaining independent of ElementTree's process-global
    # namespace registry.
    return name


def _add(
    parent: ET.Element,
    name: str,
    attributes: dict[str, str] | None = None,
    text: str | None = None,
) -> ET.Element:
    element = ET.SubElement(parent, _tag(name), attributes or {})
    if text is not None:
        element.text = text
    return element


def _kind_value(diagram: Diagram) -> str:
    return str(getattr(diagram.kind, "value", diagram.kind))


def _title(diagram: Diagram) -> str:
    return diagram.title or "Untitled diagram"


def _description(diagram: Diagram) -> str:
    labels = {str(node.id): str(node.label or node.id) for node in diagram.nodes}
    nodes = ", ".join(labels[str(node.id)] for node in diagram.nodes) or "none"
    relationships = "; ".join(
        f"{labels[str(edge.source)]} to {labels[str(edge.target)]}"
        + (f", {edge.label}" if edge.label else "")
        for edge in diagram.edges
    ) or "none"
    return (
        f"{_kind_value(diagram).capitalize()} diagram titled {_title(diagram)!r}. "
        f"Nodes in source order: {nodes}. Relationships in source order: {relationships}."
    )


def _fingerprint(diagram: Diagram) -> str:
    semantic = repr(
        (
            _kind_value(diagram),
            diagram.title,
            tuple((node.id, node.label) for node in diagram.nodes),
            tuple((edge.source, edge.target, edge.label) for edge in diagram.edges),
            tuple((group.name, group.members) for group in diagram.groups),
            diagram.highlights,
            str(getattr(diagram.direction, "value", diagram.direction)),
        )
    ).encode("utf-8")
    return hashlib.sha256(semantic).hexdigest()[:12]


def _rounded_path(points: Iterable[Point], radius: int = 8) -> str:
    route = tuple(points)
    if not route:
        return ""
    if len(route) < 3:
        return "M " + " L ".join(f"{point.x} {point.y}" for point in route)

    commands = [f"M {route[0].x} {route[0].y}"]
    for previous, corner, following in zip(
        route[:-2], route[1:-1], route[2:], strict=True
    ):
        before_dx = previous.x - corner.x
        before_dy = previous.y - corner.y
        after_dx = following.x - corner.x
        after_dy = following.y - corner.y
        before_length = abs(before_dx) + abs(before_dy)
        after_length = abs(after_dx) + abs(after_dy)
        bend = min(radius, before_length // 2, after_length // 2)
        if bend == 0:
            commands.append(f"L {corner.x} {corner.y}")
            continue
        approach = Point(
            corner.x + (bend if before_dx > 0 else -bend if before_dx < 0 else 0),
            corner.y + (bend if before_dy > 0 else -bend if before_dy < 0 else 0),
        )
        depart = Point(
            corner.x + (bend if after_dx > 0 else -bend if after_dx < 0 else 0),
            corner.y + (bend if after_dy > 0 else -bend if after_dy < 0 else 0),
        )
        commands.append(f"L {approach.x} {approach.y}")
        commands.append(f"Q {corner.x} {corner.y} {depart.x} {depart.y}")
    commands.append(f"L {route[-1].x} {route[-1].y}")
    return " ".join(commands)


def _label_lines(label: str, width: int) -> tuple[str, ...]:
    max_chars = max(10, (width - 28) // 8)
    if len(label) <= max_chars:
        return (label,)
    words = label.replace("_", " ").split()
    if not words:
        return (label[:max_chars], label[max_chars : max_chars * 2])
    lines: list[str] = []
    current = ""
    for word in words:
        pieces = [word[index : index + max_chars] for index in range(0, len(word), max_chars)]
        for piece in pieces:
            candidate = f"{current} {piece}".strip()
            if current and len(candidate) > max_chars:
                lines.append(current)
                current = piece
            else:
                current = candidate
    if current:
        lines.append(current)
    if len(lines) > 2:
        second = lines[1]
        lines = [lines[0], second[: max(1, max_chars - 1)] + "…"]
    return tuple(lines)


def _ellipsize(label: str, max_chars: int) -> str:
    if len(label) <= max_chars:
        return label
    return label[: max(1, max_chars - 1)] + "…"


def _text_in_box(parent: ET.Element, label: str, bounds: Rect) -> None:
    lines = _label_lines(label, bounds.width)
    first_y = bounds.center_y - ((len(lines) - 1) * 9) + 5
    text = _add(
        parent,
        "text",
        {
            "class": "node-label",
            "x": str(bounds.center_x),
            "y": str(first_y),
            "text-anchor": "middle",
        },
    )
    for index, line in enumerate(lines):
        _add(
            text,
            "tspan",
            {
                "x": str(bounds.center_x),
                "dy": "0" if index == 0 else "18",
            },
            line,
        )


def _edge_label(parent: ET.Element, label: str | None, position: Point) -> None:
    if not label:
        return
    lines = _label_lines(label, 300)
    width = max(36, max(len(line) for line in lines) * 7 + 16)
    line_height = 14
    height = 20 + (len(lines) - 1) * line_height
    top = position.y - 14 - (len(lines) - 1) * (line_height // 2)
    _add(
        parent,
        "rect",
        {
            "class": "edge-label-bg",
            "x": str(position.x - width // 2),
            "y": str(top),
            "width": str(width),
            "height": str(height),
            "rx": "3",
        },
    )
    text = _add(
        parent,
        "text",
        {
            "class": "edge-label",
            "x": str(position.x),
            "y": str(position.y - (len(lines) - 1) * (line_height // 2)),
            "text-anchor": "middle",
        },
    )
    for index, line in enumerate(lines):
        _add(
            text,
            "tspan",
            {"x": str(position.x), "dy": "0" if index == 0 else str(line_height)},
            line,
        )


def _render_layered(parent: ET.Element, layout: LayoutResult, arrow_id: str) -> None:
    labels = {node.id: node.label for node in layout.nodes}
    for group in layout.groups:
        bounds = group.bounds
        group_element = _add(parent, "g", {"aria-label": f"Group {group.name}"})
        _add(
            group_element,
            "rect",
            {
                "class": "group-box",
                "x": str(bounds.x),
                "y": str(bounds.y),
                "width": str(bounds.width),
                "height": str(bounds.height),
                "rx": "8",
            },
        )
        _add(
            group_element,
            "text",
            {"class": "group-label", "x": str(bounds.x + 12), "y": str(bounds.y + 18)},
            _ellipsize(group.name, max(6, (bounds.width - 24) // 7)),
        )

    for edge in layout.edges:
        edge_group = _add(
            parent,
            "g",
            {"aria-label": f"{labels[edge.source]} to {labels[edge.target]}"},
        )
        css_class = "edge feedback" if edge.feedback else "edge"
        _add(
            edge_group,
            "path",
            {
                "class": css_class,
                "d": _rounded_path(edge.points),
                "marker-end": f"url(#{arrow_id})",
            },
        )
        _edge_label(edge_group, edge.label, edge.label_position)

    for node in layout.nodes:
        bounds = node.bounds
        node_group = _add(parent, "g", {"aria-label": f"Node {node.label}"})
        css_class = "node-box highlight" if node.highlighted else "node-box"
        _add(
            node_group,
            "rect",
            {
                "class": css_class,
                "x": str(bounds.x),
                "y": str(bounds.y),
                "width": str(bounds.width),
                "height": str(bounds.height),
                "rx": "6",
            },
        )
        if node.highlighted:
            _add(
                node_group,
                "text",
                {
                    "class": "subtitle",
                    "x": str(bounds.x + 10),
                    "y": str(bounds.y + 14),
                },
                "FOCUS",
            )
        _text_in_box(node_group, node.label, bounds)


def _render_sequence(parent: ET.Element, layout: LayoutResult, arrow_id: str) -> None:
    labels = {participant.id: participant.label for participant in layout.participants}
    for participant in layout.participants:
        bounds = participant.bounds
        group = _add(parent, "g", {"aria-label": f"Participant {participant.label}"})
        _add(
            group,
            "line",
            {
                "class": "lifeline",
                "x1": str(participant.lifeline_x),
                "y1": str(participant.lifeline_top),
                "x2": str(participant.lifeline_x),
                "y2": str(participant.lifeline_bottom),
            },
        )
        css_class = "node-box highlight" if participant.highlighted else "node-box"
        _add(
            group,
            "rect",
            {
                "class": css_class,
                "x": str(bounds.x),
                "y": str(bounds.y),
                "width": str(bounds.width),
                "height": str(bounds.height),
                "rx": "6",
            },
        )
        if participant.highlighted:
            _add(
                group,
                "text",
                {
                    "class": "subtitle",
                    "x": str(bounds.x + 10),
                    "y": str(bounds.y + 14),
                },
                "FOCUS",
            )
        _text_in_box(group, participant.label, bounds)

    for message in layout.messages:
        group = _add(
            parent,
            "g",
            {
                "aria-label": (
                    f"Message {labels[message.source]} to {labels[message.target]}"
                )
            },
        )
        _add(
            group,
            "path",
            {
                "class": "message",
                "d": _rounded_path(message.points),
                "marker-end": f"url(#{arrow_id})",
            },
        )
        _edge_label(group, message.label, message.label_position)


def render_svg(
    diagram: Diagram,
    *,
    embed_fonts: bool = True,
    theme: Theme = EDITORIAL_LIGHT,
) -> str:
    """Render a validated diagram model to a self-contained SVG string."""

    if len(diagram.nodes) > 20 or len(diagram.edges) > 40:
        warnings.warn(
            "diagram exceeds the editorial density budget; consider splitting it",
            DiagramDensityWarning,
            stacklevel=2,
        )
    layout = layout_diagram(diagram)
    width = max(MIN_CANVAS_WIDTH, layout.width)
    height = layout.height + HEADER_HEIGHT + FOOTER_HEIGHT
    fingerprint = _fingerprint(diagram)
    title_id = f"nodelace-{fingerprint}-title"
    description_id = f"nodelace-{fingerprint}-description"
    arrow_id = f"nodelace-{fingerprint}-arrow"

    root = ET.Element(
        _tag("svg"),
        {
            "xmlns": SVG_NAMESPACE,
            "viewBox": f"0 0 {width} {height}",
            "width": str(width),
            "height": str(height),
            "role": "img",
            "aria-labelledby": f"{title_id} {description_id}",
            "data-nodelace-version": __version__,
        },
    )
    _add(root, "title", {"id": title_id}, _title(diagram))
    _add(root, "desc", {"id": description_id}, _description(diagram))
    definitions = _add(root, "defs")
    _add(definitions, "style", {"type": "text/css"}, svg_css(theme, embed_fonts=embed_fonts))
    marker = _add(
        definitions,
        "marker",
        {
            "id": arrow_id,
            "viewBox": "0 0 10 10",
            "refX": "9",
            "refY": "5",
            "markerWidth": "7",
            "markerHeight": "7",
            "orient": "auto-start-reverse",
        },
    )
    _add(marker, "path", {"d": "M 0 0 L 10 5 L 0 10 z", "fill": theme.ink})
    metadata = f"Generated by Nodelace {__version__}; no AI or network used."
    if embed_fonts:
        metadata += "\n\nBundled font notices and licenses:\n" + embedded_font_license_notice()
    _add(root, "metadata", text=metadata)
    _add(
        root,
        "rect",
        {
            "class": "canvas",
            "x": "0",
            "y": "0",
            "width": str(width),
            "height": str(height),
        },
    )
    _add(root, "text", {"class": "subtitle", "x": "48", "y": "34"}, _kind_value(diagram))
    _add(
        root,
        "text",
        {"class": "title", "x": "48", "y": "72"},
        _ellipsize(_title(diagram), max(10, (width - 96) // 14)),
    )

    content = _add(root, "g", {"transform": f"translate(0 {HEADER_HEIGHT})"})
    if layout.kind == "sequence":
        _render_sequence(content, layout, arrow_id)
    else:
        _render_layered(content, layout, arrow_id)
    _add(
        root,
        "text",
        {"class": "legend", "x": "48", "y": str(height - 18)},
        f"NODELACE  ·  {_kind_value(diagram).upper()}  ·  DETERMINISTIC / LOCAL",
    )

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode", short_empty_elements=True
    )


def render_html(
    diagram: Diagram,
    *,
    embed_fonts: bool = True,
    theme: Theme = EDITORIAL_LIGHT,
) -> str:
    """Render a diagram as a static, script-free, self-contained HTML document."""

    svg = render_svg(diagram, embed_fonts=embed_fonts, theme=theme).split("\n", 1)[1]
    title = html.escape(_title(diagram), quote=True)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; style-src \'unsafe-inline\'; font-src data:">\n'
        f"<title>{title}</title>\n"
        f"<style>html,body{{margin:0;background:{theme.paper}}}"
        "main{display:grid;min-height:100vh;"
        "place-items:center;padding:24px;box-sizing:border-box}svg{display:block;max-width:100%;"
        "height:auto}</style>\n</head>\n<body>\n<main>\n"
        f"{svg}\n</main>\n</body>\n</html>\n"
    )


def render(
    source: str | Diagram,
    *,
    format: Literal["svg", "html"] = "svg",
    embed_fonts: bool = True,
    theme: Theme = EDITORIAL_LIGHT,
) -> str:
    """Parse DSL text when needed and render it as SVG or HTML."""

    diagram = parse_diagram(source) if isinstance(source, str) else source
    if format == "svg":
        return render_svg(diagram, embed_fonts=embed_fonts, theme=theme)
    if format == "html":
        return render_html(diagram, embed_fonts=embed_fonts, theme=theme)
    raise ValueError("format must be 'svg' or 'html'")


def _resolved_format(output: Path | None, requested: str | None) -> Literal["svg", "html"]:
    error_source = str(output) if output is not None else "<options>"
    if requested is not None and requested not in {"svg", "html"}:
        raise DiagramValidationError(
            "format must be 'svg' or 'html'", source_name=error_source
        )
    suffix_format = output.suffix.lower().removeprefix(".") if output is not None else ""
    if suffix_format and suffix_format not in {"svg", "html"}:
        raise DiagramValidationError(
            "output extension must be .svg or .html", source_name=error_source
        )
    if requested and suffix_format and requested != suffix_format:
        raise DiagramValidationError(
            f"requested {requested!r} format does not match output extension .{suffix_format}",
            source_name=error_source,
        )
    return requested or (suffix_format if suffix_format else "svg")  # type: ignore[return-value]


def _read_source_file(path: Path) -> str:
    """Read one bounded regular UTF-8 file through a single open handle."""

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            file_status = os.fstat(stream.fileno())
            if not stat.S_ISREG(file_status.st_mode):
                raise DiagramValidationError(
                    "input must be a regular file", source_name=str(path)
                )
            payload = stream.read(MAX_SOURCE_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > MAX_SOURCE_BYTES:
        raise DiagramValidationError(
            f"file exceeds the {MAX_SOURCE_BYTES}-byte maximum", source_name=str(path)
        )
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DiagramValidationError(
            f"file is not valid UTF-8 ({error.reason} at byte {error.start})",
            source_name=str(path),
        ) from error


def _temporary_file(path: Path, mode: int) -> tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    for _ in range(100):
        # Keep the temporary component independent of the destination's
        # basename so a valid near-NAME_MAX output name remains renderable.
        candidate = path.parent / f".nodelace-{secrets.token_hex(8)}.tmp"
        try:
            return os.open(candidate, flags, mode), candidate
        except FileExistsError:
            continue
    raise FileExistsError(f"could not allocate a temporary output beside {path}")


def _output_conflict(path: Path) -> DiagramValidationError:
    return DiagramValidationError(
        f"refusing to replace existing output {path}; pass force=True or --force",
        source_name=str(path),
    )


def _require_regular_output(path: Path) -> os.stat_result | None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(status.st_mode):
        raise DiagramValidationError(
            f"refusing to replace non-regular output {path}",
            source_name=str(path),
        )
    return status


def _replace_existing_windows(temporary: Path, path: Path) -> None:
    """Replace a Windows file while retaining its ACLs and attributes."""

    import ctypes

    replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )
    replace_file.restype = ctypes.c_int
    if not replace_file(
        str(path.absolute()),
        str(temporary.absolute()),
        None,
        0,
        None,
        None,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _replace_output(temporary: Path, path: Path, *, existed: bool) -> None:
    if not existed:
        os.replace(temporary, path)
        return
    if os.name == "nt":
        _replace_existing_windows(temporary, path)
        return
    # copystat preserves the metadata Python can portably represent and, on
    # Linux, extended attributes (including POSIX ACL storage) before the
    # atomic inode swap. Restore the newly written file's timestamps afterward
    # so caches and build tools still observe the content change.
    written_status = temporary.stat()
    shutil.copystat(path, temporary, follow_symlinks=False)
    os.utime(
        temporary,
        ns=(written_status.st_atime_ns, written_status.st_mtime_ns),
        follow_symlinks=False,
    )
    os.replace(temporary, path)


def _exclusive_copy(temporary: Path, path: Path) -> None:
    """Portable no-clobber fallback for filesystems without hard links."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    mode = stat.S_IMODE(temporary.stat().st_mode)
    descriptor = -1
    created_status: os.stat_result | None = None
    try:
        descriptor = os.open(path, flags, mode)
        created_status = os.fstat(descriptor)
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        with temporary.open("rb") as source, os.fdopen(descriptor, "wb") as destination:
            descriptor = -1
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
    except FileExistsError as error:
        raise _output_conflict(path) from error
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        # Remove only the directory entry that still refers to the file this
        # call exclusively created; never unlink a racing replacement.
        if created_status is not None:
            try:
                current = path.lstat()
            except FileNotFoundError:
                pass
            else:
                if (current.st_dev, current.st_ino) == (
                    created_status.st_dev,
                    created_status.st_ino,
                ):
                    path.unlink()
        raise


def _publish_no_clobber(temporary: Path, path: Path) -> None:
    try:
        os.link(temporary, path)
    except FileExistsError as error:
        raise _output_conflict(path) from error
    except OSError:
        # Link failure codes vary by operating system and filesystem (notably
        # FAT/exFAT and SMB on Windows). Exclusive creation remains safe for
        # every failure: it either publishes without clobbering or reports the
        # underlying inability to create the destination.
        _exclusive_copy(temporary, path)
    temporary.unlink()


def _atomic_write(path: Path, content: str, *, replace: bool) -> None:
    path.parent.resolve(strict=True)
    existing_status = _require_regular_output(path)
    if existing_status is not None and not replace:
        raise _output_conflict(path)
    existing_mode = (
        stat.S_IMODE(existing_status.st_mode) if existing_status is not None else None
    )
    descriptor, temporary = _temporary_file(
        path, existing_mode if existing_mode is not None else 0o666
    )
    try:
        if existing_mode is not None:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, existing_mode)
            else:  # pragma: no cover - Windows lacks POSIX fchmod
                os.chmod(temporary, existing_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            # Revalidate immediately before publication.  The replace remains
            # an authorized atomic swap, but it must never target a special
            # filesystem entry such as a FIFO, socket, or device.
            current_status = _require_regular_output(path)
            _replace_output(temporary, path, existed=current_status is not None)
        else:
            _publish_no_clobber(temporary, path)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def render_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    format: Literal["svg", "html"] | None = None,
    force: bool = False,
    embed_fonts: bool = True,
    theme: Theme = EDITORIAL_LIGHT,
) -> Path:
    """Render a UTF-8 file with atomic replacement and protected publication.

    New explicit outputs use atomic no-clobber publication when the filesystem
    supports hard links, with a safe exclusive-copy fallback otherwise.
    """

    source_path = Path(input_path)
    explicit_output = Path(output_path) if output_path is not None else None
    if explicit_output is not None and source_path.resolve() == explicit_output.resolve():
        raise DiagramValidationError(
            "refusing to replace the source file", source_name=str(source_path)
        )
    selected_format = _resolved_format(explicit_output, format)
    default_output = source_path.with_suffix(f".{selected_format}")
    destination = explicit_output or default_output
    if source_path.resolve() == destination.resolve():
        raise DiagramValidationError(
            "refusing to replace the source file", source_name=str(source_path)
        )
    if explicit_output is not None and not force and os.path.lexists(destination):
        raise DiagramValidationError(
            f"refusing to replace existing output {destination}; pass force=True or --force",
            source_name=str(destination),
        )
    source = _read_source_file(source_path)
    diagram = parse_diagram(source, source_name=str(source_path))
    content = render(
        diagram,
        format=selected_format,
        embed_fonts=embed_fonts,
        theme=theme,
    )
    _atomic_write(destination, content, replace=explicit_output is None or force)
    return destination


__all__ = [
    "MAX_SOURCE_BYTES",
    "DiagramDensityWarning",
    "render",
    "render_file",
    "render_html",
    "render_svg",
]
