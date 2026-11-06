"""Command-line interface for Nodelace."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import NoReturn

from nodelace import __version__
from nodelace.diagnostics import check_diagram
from nodelace.dsl import parse_diagram
from nodelace.errors import DiagramSyntaxError, DiagramValidationError, NodelaceError, _safe_display
from nodelace.export import export_png
from nodelace.presentation import SIZE_PRESETS
from nodelace.renderer import (
    MAX_SOURCE_BYTES,
    _atomic_write,
    _read_source_file,
    _resolved_format,
    render,
    render_file,
)
from nodelace.theme import THEMES, load_theme


class _SafeArgumentParser(argparse.ArgumentParser):
    """Argument parser that never echoes terminal controls from argv."""

    def __init__(self, *args, json_errors: bool = False, **kwargs):
        self.json_errors = json_errors
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> NoReturn:
        if self.json_errors:
            raise ValueError(message)
        self.print_usage(sys.stderr)
        self.exit(2, f"{_safe_display(self.prog)}: error: {_safe_display(message)}\n")


def build_parser(*, json_errors: bool = False) -> argparse.ArgumentParser:
    """Create the public CLI parser."""

    parser = _SafeArgumentParser(
        prog="nodelace",
        description="Render deterministic, offline diagrams from simple text.",
        json_errors=json_errors,
    )
    parser.add_argument("--version", action="version", version=f"nodelace {__version__}")
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=partial(_SafeArgumentParser, json_errors=json_errors),
    )

    render_parser = commands.add_parser("render", help="render a .diagram file")
    render_parser.add_argument("input", type=Path, help="source .diagram file, or - for stdin")
    render_parser.add_argument(
        "-o", "--output", type=Path, help="output .svg/.html, or - for stdout"
    )
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
    check_parser.add_argument(
        "--layout", action="store_true", help="check geometry and readability"
    )
    check_parser.add_argument("--strict", action="store_true", help="fail on layout warnings too")
    check_parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    export_parser = commands.add_parser("export", help="export a .diagram to PNG (optional extra)")
    export_parser.add_argument("input", type=Path)
    export_parser.add_argument("-o", "--output", type=Path, required=True)
    export_parser.add_argument("--scale", type=int, choices=range(1, 5), default=2)
    export_parser.add_argument("--force", action="store_true")
    for command in (render_parser, check_parser, export_parser):
        command.add_argument("--size", choices=("fit", *SIZE_PRESETS), default="fit")
        skin = command.add_mutually_exclusive_group()
        skin.add_argument("--theme", choices=tuple(THEMES), default="light")
        skin.add_argument("--profile", type=Path, help="TOML [theme] profile")
    render_parser.add_argument("--id-prefix", help="unique ID for inline SVG instances")
    return parser


def _read_checked(path: Path) -> str:
    if path != Path("-"):
        return _read_source_file(path)
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    payload = stream.read(MAX_SOURCE_BYTES + 1)
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if len(payload) > MAX_SOURCE_BYTES:
        raise DiagramValidationError(
            f"stdin exceeds the {MAX_SOURCE_BYTES}-byte maximum", source_name="<stdin>"
        )
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DiagramValidationError("stdin is not valid UTF-8", source_name="<stdin>") from error


def _json_error(error: Exception) -> None:
    code = (
        "syntax"
        if isinstance(error, DiagramSyntaxError)
        else "validation"
        if isinstance(error, NodelaceError)
        else "io"
        if isinstance(error, OSError)
        else "options"
    )
    print(
        json.dumps(
            {
                "valid": False,
                "kind": None,
                "nodes": 0,
                "edges": 0,
                "diagnostics": [],
                "error": {
                    "code": code,
                    "message": getattr(error, "message", str(error)),
                    "source": getattr(error, "source_name", None),
                    "line": getattr(error, "line", None),
                    "column": getattr(error, "column", None),
                },
            }
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Nodelace CLI and return a process exit code."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    json_output = bool(arguments and arguments[0] == "check" and "--json" in arguments)
    parser = build_parser(json_errors=json_output)
    try:
        args = parser.parse_args(arguments)
        theme = load_theme(args.profile) if args.profile else THEMES[args.theme]
        if args.command == "export":
            if args.input != Path("-") and args.input.resolve() == args.output.resolve():
                raise ValueError("refusing to replace the source file")
            output = export_png(
                _read_checked(args.input),
                args.output,
                force=args.force,
                theme=theme,
                size=args.size,
                scale=args.scale,
            )
            print(_safe_display(output))
            return 0
        if args.command == "check":
            source = _read_checked(args.input)
            diagram = parse_diagram(
                source, source_name="<stdin>" if args.input == Path("-") else str(args.input)
            )
            kind = str(getattr(diagram.kind, "value", diagram.kind))
            issues = (
                check_diagram(diagram, theme=theme, size=args.size)
                if args.layout or args.strict
                else ()
            )
            valid = not any(issue.severity == "error" or args.strict for issue in issues)
            if args.json:
                print(
                    json.dumps(
                        {
                            "valid": valid,
                            "kind": kind,
                            "nodes": len(diagram.nodes),
                            "edges": len(diagram.edges),
                            "diagnostics": [asdict(issue) for issue in issues],
                            "error": None,
                        }
                    )
                )
                return 0 if valid else 2
            for issue in issues:
                print(
                    f"{issue.severity}: {issue.code}: {_safe_display(issue.message)}",
                    file=sys.stderr,
                )
            if not valid:
                return 2
            print(
                f"ok: {_safe_display(args.input)} ({kind}, "
                f"{len(diagram.nodes)} nodes, {len(diagram.edges)} edges)"
            )
            return 0

        if args.input == Path("-") or args.output == Path("-"):
            destination = args.output if args.output != Path("-") else None
            content = render(
                parse_diagram(
                    _read_checked(args.input),
                    source_name=("<stdin>" if args.input == Path("-") else str(args.input)),
                ),
                format=_resolved_format(destination, args.format),
                embed_fonts=not args.system_fonts,
                theme=theme,
                id_prefix=args.id_prefix,
                size=args.size,
            )
            if destination is None:
                stream = getattr(sys.stdout, "buffer", None)
                if stream is not None:
                    stream.write(content.encode("utf-8"))
                else:
                    sys.stdout.write(content)
            else:
                _atomic_write(destination, content, replace=args.force)
                print(_safe_display(destination))
            return 0
        output = render_file(
            args.input,
            args.output,
            format=args.format,
            force=args.force,
            embed_fonts=not args.system_fonts,
            theme=theme,
            id_prefix=args.id_prefix,
            size=args.size,
        )
        print(_safe_display(output))
        return 0
    except NodelaceError as exc:
        if json_output:
            _json_error(exc)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError) as exc:
        if json_output:
            _json_error(exc)
        else:
            print(f"error: {_safe_display(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised via python -m
    raise SystemExit(main())
