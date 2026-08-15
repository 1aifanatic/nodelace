"""The built-in Nodelace editorial theme and offline font embedding."""

from __future__ import annotations

import re
from base64 import b64encode
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files


@dataclass(frozen=True, slots=True)
class Theme:
    """A compact set of semantic design tokens used by the SVG renderer."""

    paper: str = "#f7f7f4"
    surface: str = "#ffffff"
    ink: str = "#171717"
    muted: str = "#5f6b7a"
    accent: str = "#ff865e"
    accent_soft: str = "#fff0ea"
    hairline: str = "#c9cdcf"
    group_fill: str = "#f0f2f2"
    feedback: str = "#657384"

    def __post_init__(self) -> None:
        """Reject CSS-capable values so custom themes remain offline and inert."""

        for name in (
            "paper",
            "surface",
            "ink",
            "muted",
            "accent",
            "accent_soft",
            "hairline",
            "group_fill",
            "feedback",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
                raise ValueError(f"theme color {name!r} must be a six-digit hexadecimal color")


EDITORIAL_LIGHT = Theme()


_FONT_FILES: tuple[tuple[str, str, str, str], ...] = (
    ("Instrument Serif", "InstrumentSerif-Regular.woff2", "400", "normal"),
    ("Instrument Serif", "InstrumentSerif-Italic.woff2", "400", "italic"),
    ("Geist", "Geist-Variable.woff2", "100 900", "normal"),
    ("Geist Mono", "GeistMono-Variable.woff2", "100 900", "normal"),
)

_FONT_LICENSES: tuple[tuple[str, str], ...] = (
    ("Instrument Serif", "InstrumentSerif-OFL.txt"),
    ("Geist and Geist Mono", "Geist-OFL.txt"),
)


@lru_cache(maxsize=1)
def embedded_font_css() -> str:
    """Return deterministic ``@font-face`` rules with bundled WOFF2 data URLs."""

    font_dir = files("nodelace").joinpath("assets", "fonts")
    rules: list[str] = []
    for family, filename, weight, style in _FONT_FILES:
        payload = b64encode(font_dir.joinpath(filename).read_bytes()).decode("ascii")
        rules.append(
            "@font-face{"
            f"font-family:'{family}';"
            f"src:url(data:font/woff2;base64,{payload}) format('woff2');"
            f"font-weight:{weight};font-style:{style};font-display:block;"
            "}"
        )
    return "".join(rules)


@lru_cache(maxsize=1)
def embedded_font_license_notice() -> str:
    """Return complete notices that accompany extractable embedded webfonts."""

    license_dir = files("nodelace").joinpath("assets", "licenses")
    return "\n\n".join(
        f"{family}\n{license_dir.joinpath(filename).read_text(encoding='utf-8').strip()}"
        for family, filename in _FONT_LICENSES
    )


def svg_css(theme: Theme = EDITORIAL_LIGHT, *, embed_fonts: bool = True) -> str:
    """Build the complete, script-free CSS embedded in each generated SVG."""

    fonts = embedded_font_css() if embed_fonts else ""
    return fonts + "".join(
        (
            f".canvas{{fill:{theme.paper};}}",
            f".title{{font:400 30px 'Instrument Serif',Georgia,serif;fill:{theme.ink};}}",
            f".subtitle{{font:500 11px 'Geist Mono',monospace;letter-spacing:.12em;"
            f"text-transform:uppercase;fill:{theme.muted};}}",
            f".group-box{{fill:{theme.group_fill};stroke:{theme.hairline};stroke-width:1;}}",
            f".group-label{{font:600 11px 'Geist',Arial,sans-serif;fill:{theme.muted};}}",
            f".node-box{{fill:{theme.surface};stroke:{theme.ink};stroke-width:1.25;}}",
            f".node-box.highlight{{fill:{theme.accent_soft};stroke:{theme.accent};"
            "stroke-width:2.5;}",
            f".node-label{{font:550 14px 'Geist',Arial,sans-serif;fill:{theme.ink};}}",
            f".edge{{fill:none;stroke:{theme.ink};stroke-width:1.5;"
            "stroke-linejoin:round;stroke-linecap:round;}",
            f".edge.feedback{{stroke:{theme.feedback};stroke-dasharray:6 5;}}",
            f".edge-label-bg{{fill:{theme.paper};}}",
            f".edge-label{{font:500 11px 'Geist Mono',monospace;fill:{theme.muted};}}",
            f".lifeline{{fill:none;stroke:{theme.hairline};stroke-width:1.25;"
            "stroke-dasharray:4 5;}",
            f".message{{fill:none;stroke:{theme.ink};stroke-width:1.5;}}",
            f".message-label{{font:500 12px 'Geist',Arial,sans-serif;fill:{theme.ink};}}",
            f".legend{{font:500 10px 'Geist Mono',monospace;fill:{theme.muted};}}",
        )
    )
