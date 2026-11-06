"""Shared deterministic text measurements; no font engine at runtime."""

from __future__ import annotations

import json
import math
import unicodedata
from functools import lru_cache
from importlib.resources import files

from nodelace.model import Node

NODE_SIZE = 12
EDGE_SIZE = 11
EDGE_MAX_WIDTH = 284


@lru_cache(maxsize=1)
def _advances() -> dict[str, dict[str, float]]:
    return json.loads(files("nodelace").joinpath("assets", "font-metrics.json").read_text())


def text_width(text: str, size: int = NODE_SIZE, family: str = "sans") -> int:
    """Conservative advances at weights 400-600 plus a small glyph overhang reserve.

    Unbundled wide glyphs reserve 1.1 em; unknown narrow glyphs reserve 1 em.
    Arbitrary fallback fonts cannot promise identical pixels, but never cost zero.
    """
    advances = _advances()[family]
    width = 0.0
    for char in text:
        if unicodedata.category(char) in {"Mn", "Me", "Cf"}:
            continue
        fallback = 1.1 if unicodedata.east_asian_width(char) in {"W", "F"} else 1.0
        width += advances.get(char, fallback)
    return math.ceil(width * size * 1.04 + (2 if text else 0))


def ellipsize(text: str, width: int, size: int = NODE_SIZE, family: str = "sans") -> str:
    if text_width(text, size, family) <= width:
        return text
    while text and text_width(text + "…", size, family) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap_text(
    text: str, width: int, size: int = NODE_SIZE, family: str = "sans", max_lines: int = 2
) -> tuple[str, ...]:
    """Wrap on spaces when possible, preserving printed identifiers and combining marks."""
    lines: list[str] = []
    remaining = text
    while remaining:
        if len(lines) == max_lines - 1:
            lines.append(ellipsize(remaining, width, size, family))
            break
        if text_width(remaining, size, family) <= width:
            lines.append(remaining)
            break
        end = 1
        while end < len(remaining) and text_width(remaining[: end + 1], size, family) <= width:
            end += 1
        while end < len(remaining) and unicodedata.category(remaining[end]) in {"Mn", "Me"}:
            end += 1
        space = remaining.rfind(" ", 0, end + 1)
        if space > 0:
            end = space
        lines.append(remaining[:end].rstrip())
        remaining = remaining[end:].lstrip()
    return tuple(lines) or ("",)


def edge_label_size(label: str | None) -> tuple[int, int]:
    if not label:
        return 0, 0
    lines = wrap_text(label, EDGE_MAX_WIDTH, EDGE_SIZE, "mono")
    return max(36, max(text_width(line, EDGE_SIZE, "mono") for line in lines) + 16), (
        20 + (len(lines) - 1) * 14
    )


def node_text_width(node: Node) -> int:
    return max(
        text_width(node.label or node.id),
        text_width(node.tag or "", 8, "mono"),
        text_width(node.sublabel or "", 9, "mono"),
    )
