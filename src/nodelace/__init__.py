"""Nodelace: deterministic, offline diagrams from a tiny text language."""

from __future__ import annotations

__version__ = "0.3.0"

from nodelace.diagnostics import Diagnostic, check_diagram
from nodelace.dsl import parse_diagram
from nodelace.errors import (
    DiagramSyntaxError,
    DiagramValidationError,
    NodelaceError,
)
from nodelace.export import export_png
from nodelace.model import Activation, Diagram, DiagramKind, Direction, Edge, Fragment, Group, Node
from nodelace.renderer import render, render_file, render_html, render_svg
from nodelace.theme import EDITORIAL_DARK, EDITORIAL_LIGHT, Theme, load_theme

__all__ = [
    "EDITORIAL_DARK",
    "EDITORIAL_LIGHT",
    "Activation",
    "Diagnostic",
    "Diagram",
    "DiagramKind",
    "DiagramSyntaxError",
    "DiagramValidationError",
    "Direction",
    "Edge",
    "Fragment",
    "Group",
    "Node",
    "NodelaceError",
    "Theme",
    "check_diagram",
    "export_png",
    "load_theme",
    "parse_diagram",
    "render",
    "render_file",
    "render_html",
    "render_svg",
]
