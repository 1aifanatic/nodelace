"""Compact, local publication checks over the actual computed geometry."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, pairwise
from typing import Literal

from nodelace.layout import layout_diagram
from nodelace.layout.router import label_bounds, rectangles_overlap, segment_hits_rect
from nodelace.model import Diagram
from nodelace.presentation import footer_height, frame_size
from nodelace.text import ellipsize, wrap_text
from nodelace.theme import EDITORIAL_LIGHT, Theme, contrast_ratio


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: Literal["error", "warning"] = "warning"


def check_diagram(
    diagram: Diagram, *, theme: Theme = EDITORIAL_LIGHT, size: str = "fit"
) -> tuple[Diagnostic, ...]:
    """Check geometry and editorial budgets without a browser or an AI model."""
    layout = layout_diagram(diagram)
    issues: list[Diagnostic] = []
    canvas_width, _, scale = frame_size(layout.width, layout.height, size, footer_height(diagram))
    preferred = 4 / 3 if size in {"slide-16x9", "social-square"} else 1
    title = diagram.title or "Untitled diagram"
    if ellipsize(title, canvas_width - 96, 40 if preferred > 1 else 28, "serif") != title:
        issues.append(Diagnostic("truncated-title", "title is shortened visually"))
    for frame in layout.frames:
        for guard in (frame.fragment.guard, frame.fragment.else_guard):
            if (
                guard
                and ellipsize(f"[{guard}]", frame.bounds.width - 24, 11, "mono") != f"[{guard}]"
            ):
                issues.append(Diagnostic("truncated-guard", "sequence guard is shortened visually"))
    if scale < preferred:
        issues.append(
            Diagnostic(
                "size",
                f"{size} scales node text to {12 * scale:.1f}px; split the diagram or use fit",
            )
        )
    if len(diagram.fragments) > 1:
        issues.append(Diagnostic("fragments", "prefer one sequence fragment per diagram"))
    if not diagram.nodes:
        issues.append(Diagnostic("empty", "diagram contains no nodes"))
    node_limit = 5 if layout.kind == "sequence" else 9
    if len(diagram.nodes) > node_limit or len(diagram.edges) > 12:
        issues.append(
            Diagnostic(
                "density",
                f"use at most {node_limit} nodes and 12 relationships; "
                "split into an overview and detail",
            )
        )
    if len(diagram.highlights) > 2:
        issues.append(Diagnostic("focus", "highlight at most two focal nodes"))
    if layout.width > 1280 or layout.height > 900:
        issues.append(
            Diagnostic(
                "canvas",
                f"layout is {layout.width} x {layout.height}; "
                "consider splitting it for readable publication",
            )
        )
    for node in layout.nodes:
        for field, font_size in (("tag", 8), ("sublabel", 9)):
            value = getattr(node.node, field)
            if value and ellipsize(value, node.bounds.width - 24, font_size, "mono") != value:
                issues.append(
                    Diagnostic("truncated-label", f"node {node.id!r} {field} is shortened")
                )
        width = node.bounds.width // 2 if node.node.shape == "decision" else node.bounds.width
        if node.node.shape != "merge" and wrap_text(node.label, width - 28)[-1].endswith("…"):
            issues.append(Diagnostic("truncated-label", f"node {node.id!r} is shortened visually"))
        if node.node.shape == "decision":
            exits = [e for e in diagram.edges if e.source == node.id]
            if any(not e.label for e in exits):
                issues.append(Diagnostic("decision-label", f"label every exit from {node.id!r}"))
            if len(exits) > 3:
                issues.append(
                    Diagnostic("decision-exits", f"split decision {node.id!r}: over 3 exits")
                )
    for first, second in combinations(layout.nodes, 2):
        if rectangles_overlap(first.bounds, second.bounds):
            issues.append(
                Diagnostic("node-overlap", f"{first.id!r} overlaps {second.id!r}", "error")
            )
    labels = []
    for index, edge in enumerate(layout.edges, 1):
        if layout.kind != "sequence":
            for node in layout.nodes:
                if node.id in {edge.source, edge.target}:
                    continue
                if any(segment_hits_rect(a, b, node.bounds) for a, b in pairwise(edge.points)):
                    issues.append(
                        Diagnostic("edge-node", f"edge {index} intersects {node.id!r}", "error")
                    )
        if edge.label:
            bounds = label_bounds(edge.label, edge.label_position)
            if layout.kind == "sequence":
                for other_index, other_edge in enumerate(layout.edges, 1):
                    if other_index != index and any(
                        segment_hits_rect(a, b, bounds) for a, b in pairwise(other_edge.points)
                    ):
                        issues.append(
                            Diagnostic(
                                "label-edge",
                                f"message {index} label overlaps message {other_index}",
                                "error",
                            )
                        )
            for node in layout.nodes:
                if rectangles_overlap(bounds, node.bounds):
                    issues.append(
                        Diagnostic(
                            "label-node", f"edge {index} label overlaps {node.id!r}", "error"
                        )
                    )
            for other_index, other in labels:
                if rectangles_overlap(bounds, other):
                    issues.append(
                        Diagnostic(
                            "label-overlap",
                            f"edge labels {other_index} and {index} overlap",
                            "error",
                        )
                    )
            labels.append((index, bounds))
            if wrap_text(edge.label, 284, 11, "mono")[-1].endswith("…"):
                issues.append(Diagnostic("truncated-label", f"edge {index} label is shortened"))
    for role in ("ink", "muted"):
        for surface in ("paper", "surface", "accent_soft", "group_fill"):
            ratio = contrast_ratio(getattr(theme, role), getattr(theme, surface))
            if ratio < 4.5:
                issues.append(
                    Diagnostic(
                        "contrast",
                        f"{role} on {surface}: {ratio:.2f}:1 (text needs 4.5:1)",
                        "error",
                    )
                )
    for role in ("accent", "muted"):
        ratio = contrast_ratio(getattr(theme, role), theme.paper)
        if ratio < 3:
            issues.append(
                Diagnostic(
                    "contrast",
                    f"{role} on paper: {ratio:.2f}:1 (essential marks need 3:1)",
                    "error",
                )
            )
    return tuple(issues)
