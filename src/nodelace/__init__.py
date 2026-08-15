"""Nodelace: deterministic, offline diagrams from a tiny text language."""

from __future__ import annotations

__version__ = "0.1.0"

from nodelace.dsl import parse_diagram
from nodelace.errors import (
    DiagramSyntaxError,
    DiagramValidationError,
    NodelaceError,
)
from nodelace.model import Diagram, DiagramKind, Direction, Edge, Group, Node
from nodelace.renderer import render, render_file, render_html, render_svg
from nodelace.theme import EDITORIAL_LIGHT, Theme

__all__ = [
    "EDITORIAL_LIGHT",
    "Diagram",
    "DiagramKind",
    "DiagramSyntaxError",
    "DiagramValidationError",
    "Direction",
    "Edge",
    "Group",
    "Node",
    "NodelaceError",
    "Theme",
    "parse_diagram",
    "render",
    "render_file",
    "render_html",
    "render_svg",
]
