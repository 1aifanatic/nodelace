"""Command-line interface for Nodelace."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from nodelace import __version__
from nodelace.dsl import parse_diagram
from nodelace.errors import NodelaceError, _safe_display
from nodelace.renderer import _read_source_file, render_file


class _SafeArgumentParser(argparse.ArgumentParser):
    """Argument parser that never echoes terminal controls from argv."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"{_safe_display(self.prog)}: error: {_safe_display(message)}\n")


def build_parser() -> argparse.ArgumentParser:
    """Create the public CLI parser."""

    parser = _SafeArgumentParser(
        prog="nodelace",
        description="Render deterministic, offline diagrams from simple text.",
    )
    parser.add_argument("--version", action="version", version=f"nodelace {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    render_parser = commands.add_parser("render", help="render a .diagram file")
    render_parser.add_argument("input", type=Path, help="source .diagram file")
    render_parser.add_argument("-o", "--output", type=Path, help="output .svg or .html path")
    render_parser.add_argument(
        "--format",
        choices=("svg", "html"),
        help="output format; inferred from --output or defaults to svg",
    )
    render_parser.add_argument(
        "--force",
        action="store_true",
        help="replace an explicitly named existing output file",
    )
    render_parser.add_argument(
        "--system-fonts",
        action="store_true",
        help="omit bundled font data for a smaller, non-portable output",
    )

    check_parser = commands.add_parser("check", help="validate a .diagram file")
    check_parser.add_argument("input", type=Path, help="source .diagram file")
    return parser


def _read_checked(path: Path) -> str:
    return _read_source_file(path)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Nodelace CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            source = _read_checked(args.input)
            diagram = parse_diagram(source, source_name=str(args.input))
            kind = str(getattr(diagram.kind, "value", diagram.kind))
            print(
                f"ok: {_safe_display(args.input)} ({kind}, "
                f"{len(diagram.nodes)} nodes, {len(diagram.edges)} edges)"
            )
            return 0

        output = render_file(
            args.input,
            args.output,
            format=args.format,
            force=args.force,
            embed_fonts=not args.system_fonts,
        )
        print(_safe_display(output))
        return 0
    except NodelaceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as exc:
        print(f"error: {_safe_display(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised via python -m
    raise SystemExit(main())
