"""Destination sizes shared by rendering and publication diagnostics."""

from __future__ import annotations

from nodelace.model import Diagram

SIZE_PRESETS = {
    "doc-inline": (960, 600),
    "doc-wide": (1280, 720),
    "slide-16x9": (1280, 720),
    "social-square": (1080, 1080),
    "print-a4": (1120, 792),
}


def legend_entries(diagram: Diagram) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            [
                node.shape.capitalize() if node.shape != "box" else node.role.capitalize()
                for node in diagram.nodes
                if node.shape != "box" or node.role != "default"
            ]
            + [edge.kind.capitalize() for edge in diagram.edges if edge.kind != "normal"]
            + (["Focus"] if diagram.highlights else [])
        )
    )


def footer_height(diagram: Diagram) -> int:
    return 40 + ((len(legend_entries(diagram)) + 3) // 4) * 24


def frame_size(width: int, height: int, size: str, footer: int) -> tuple[int, int, float]:
    if size == "fit":
        return max(640, width), height + 104 + footer, 1.0
    if size not in SIZE_PRESETS:
        raise ValueError(f"size must be fit or one of {', '.join(SIZE_PRESETS)}")
    target_width, target_height = SIZE_PRESETS[size]
    preferred = 4 / 3 if size in {"slide-16x9", "social-square"} else 1.0
    scale = min(preferred, target_width / width, (target_height - 104 - footer) / height)
    return target_width, target_height, scale
