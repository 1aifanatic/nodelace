"""The built-in Nodelace editorial theme and offline font embedding."""

from __future__ import annotations

import re
import tomllib
from base64 import b64encode
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib.resources import files
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Theme:
    """A compact set of semantic design tokens used by the SVG renderer."""

    paper: str = "#f5f5f5"
    surface: str = "#ffffff"
    ink: str = "#2d3142"
    muted: str = "#4f5d75"
    accent: str = "#bf4520"
    accent_soft: str = "#f1e7e4"
    hairline: str = "#bfc0c0"
    group_fill: str = "#ececec"
    feedback: str = "#4f5d75"

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
EDITORIAL_DARK = Theme(
    paper="#2d3142",
    surface="#393e53",
    ink="#f5f5f5",
    muted="#bfc0c0",
    accent="#f08a59",
    accent_soft="#413a44",
    hairline="#686b77",
    group_fill="#34394c",
    feedback="#bfc0c0",
)
THEMES = {"light": EDITORIAL_LIGHT, "dark": EDITORIAL_DARK}


def contrast_ratio(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        values = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def load_theme(path: str | Path) -> Theme:
    """Read a bounded TOML [theme] table, based on light or dark; reject unknown keys."""
    with Path(path).open("rb") as stream:
        data = stream.read(16385)
    if len(data) > 16384:
        raise ValueError("theme profile exceeds 16 KiB")
    document = tomllib.loads(data.decode("utf-8"))
    if set(document) != {"theme"} or not isinstance(document["theme"], dict):
        raise ValueError("profile must contain exactly one [theme] table")
    values = dict(document["theme"])
    base = values.pop("base", "light")
    if not isinstance(base, str) or base not in THEMES:
        raise ValueError("theme base must be light or dark")
    try:
        return replace(THEMES[base], **values)
    except TypeError as error:
        raise ValueError(f"unknown theme setting: {error}") from error


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


def svg_css(
    theme: Theme = EDITORIAL_LIGHT, *, embed_fonts: bool = True, scope: str | None = None
) -> str:
    """Build the complete, script-free CSS embedded in each generated SVG."""

    fonts = embedded_font_css() if embed_fonts else ""
    styles = "".join(
        (
            f".canvas{{fill:{theme.paper};}}",
            f".title{{font:400 28px 'Instrument Serif',Georgia,serif;fill:{theme.ink};}}",
            f".subtitle{{font:500 11px 'Geist Mono',monospace;letter-spacing:.12em;"
            f"text-transform:uppercase;fill:{theme.muted};}}",
            f".group-box{{fill:{theme.group_fill};stroke:{theme.hairline};stroke-width:1;}}",
            f".group-label{{font:600 11px 'Geist',Arial,sans-serif;fill:{theme.muted};}}",
            f".node-box{{fill:{theme.surface};stroke:{theme.ink};stroke-width:1;}}",
            f".node-box.role-store{{fill:{theme.group_fill};stroke:{theme.muted};}}",
            f".node-box.role-external{{fill:{theme.group_fill};stroke:{theme.muted};}}",
            f".node-box.role-input{{fill:{theme.group_fill};stroke:{theme.muted};}}",
            f".node-box.role-optional{{fill:{theme.paper};stroke:{theme.muted};"
            "stroke-dasharray:4 3;}",
            f".merge{{fill:{theme.ink};}}",
            f".fragment{{fill:none;stroke:{theme.muted};stroke-width:1;}}",
            f".activation{{fill:{theme.group_fill};stroke:{theme.muted};stroke-width:.8;}}",
            f".node-tag{{font:500 8px 'Geist Mono',monospace;fill:{theme.muted};}}",
            f".node-sublabel{{font:400 9px 'Geist Mono',monospace;fill:{theme.muted};}}",
            f".node-box.highlight{{fill:{theme.accent_soft};stroke:{theme.accent};"
            "stroke-width:1.2;}",
            f".node-label{{font:600 12px 'Geist',Arial,sans-serif;fill:{theme.ink};}}",
            f".edge{{fill:none;stroke:{theme.muted};stroke-width:1;"
            "stroke-linejoin:round;stroke-linecap:round;}",
            f".edge.feedback{{stroke:{theme.feedback};stroke-dasharray:6 5;}}",
            f".crossing-halo{{fill:none;stroke:{theme.paper};stroke-width:5;}}",
            f".edge-label-bg{{fill:{theme.paper};}}",
            f".fragment-guard{{paint-order:stroke;stroke:{theme.paper};stroke-width:4;}}",
            f".edge-label{{font:500 11px 'Geist Mono',monospace;fill:{theme.muted};}}",
            f".lifeline{{fill:none;stroke:{theme.muted};stroke-width:1;stroke-dasharray:4 5;}}",
            f".message{{fill:none;stroke:{theme.muted};stroke-width:1;}}",
            ".kind-return{stroke-dasharray:4 3;}",
            ".kind-async{stroke-dasharray:4 3;}",
            f".kind-primary{{stroke:{theme.accent};stroke-width:1.2;}}",
            f".message-label{{font:500 12px 'Geist',Arial,sans-serif;fill:{theme.ink};}}",
            f".legend{{font:500 10px 'Geist Mono',monospace;fill:{theme.muted};}}",
        )
    )
    if scope is not None:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", scope) is None:
            raise ValueError("SVG scope must be a safe identifier")
        styles = re.sub(r"(\.[^{}]+\{)", lambda match: f"#{scope} {match[1]}", styles)
        styles += f"#{scope} text{{font-kerning:none;font-variant-ligatures:none;}}"
    return fonts + styles
