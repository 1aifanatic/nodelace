"""Public, source-aware exceptions raised by Nodelace."""

from __future__ import annotations

from unicodedata import category


def _safe_display(value: object) -> str:
    """Return user-controlled text without terminal control sequences."""

    escaped: list[str] = []
    for character in str(value):
        codepoint = ord(character)
        if character == "\n":
            escaped.append(r"\n")
        elif character == "\r":
            escaped.append(r"\r")
        elif character == "\t":
            escaped.append(r"\t")
        elif category(character).startswith("C"):
            if codepoint <= 0xFF:
                escaped.append(f"\\x{codepoint:02x}")
            elif codepoint <= 0xFFFF:
                escaped.append(f"\\u{codepoint:04x}")
            else:
                escaped.append(f"\\U{codepoint:08x}")
        else:
            escaped.append(character)
    return "".join(escaped)


class NodelaceError(Exception):
    """Base class for expected Nodelace input errors."""


class DiagramError(NodelaceError):
    """Base class for errors tied to diagram source text."""

    def __init__(
        self,
        message: str,
        *,
        source_name: str = "<string>",
        line: int | None = None,
        column: int | None = None,
        line_text: str | None = None,
    ) -> None:
        self.message = message
        self.source_name = source_name
        self.line = line
        self.column = column
        self.line_text = line_text
        super().__init__(message)

    def __str__(self) -> str:
        location = _safe_display(self.source_name)
        if self.line is not None:
            location += f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"
        result = f"{location}: {_safe_display(self.message)}"
        if self.line_text is not None:
            safe_line = _safe_display(self.line_text)
            result += f"\n  {safe_line}"
            if self.column is not None:
                safe_prefix = _safe_display(self.line_text[: self.column - 1])
                result += f"\n  {' ' * len(safe_prefix)}^"
        return result


class DiagramSyntaxError(DiagramError):
    """The source text does not follow the Nodelace grammar."""


class DiagramValidationError(DiagramError):
    """The source is grammatical but violates a diagram invariant or limit."""


__all__ = [
    "DiagramError",
    "DiagramSyntaxError",
    "DiagramValidationError",
    "NodelaceError",
]
