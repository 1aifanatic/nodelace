from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from nodelace.theme import EDITORIAL_LIGHT, Theme, embedded_font_css, svg_css


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]

    def linearize(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(value) for value in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(left: str, right: str) -> float:
    brightest, darkest = sorted(
        (_relative_luminance(left), _relative_luminance(right)), reverse=True
    )
    return (brightest + 0.05) / (darkest + 0.05)


def test_embedded_fonts_are_self_contained_and_complete() -> None:
    css = embedded_font_css()

    assert css.count("@font-face") == 4
    assert "Instrument Serif" in css
    assert "Geist Mono" in css
    assert "data:font/woff2;base64," in css
    assert "http://" not in css
    assert "https://" not in css


def test_system_font_mode_omits_font_payloads() -> None:
    css = svg_css(embed_fonts=False)

    assert "@font-face" not in css
    assert "base64," not in css
    assert "Instrument Serif" in css


def test_generated_stylesheet_has_balanced_rule_braces() -> None:
    css = svg_css(embed_fonts=False)

    assert css.count("{") == css.count("}")
    assert "}}" not in css
    assert ".edge{" in css
    assert ".message{" in css


def test_bundled_assets_and_licenses_exist() -> None:
    package = Path(__file__).parents[1] / "src" / "nodelace" / "assets"
    fonts = sorted(path.name for path in (package / "fonts").glob("*.woff2"))
    licenses = sorted(path.name for path in (package / "licenses").glob("*.txt"))

    assert fonts == [
        "Geist-Variable.woff2",
        "GeistMono-Variable.woff2",
        "InstrumentSerif-Italic.woff2",
        "InstrumentSerif-Regular.woff2",
    ]
    assert licenses == ["Geist-OFL.txt", "InstrumentSerif-OFL.txt"]
    assert all((package / "fonts" / name).stat().st_size > 20_000 for name in fonts)


def test_bundled_fonts_match_the_pinned_unmodified_upstream_files() -> None:
    font_dir = Path(__file__).parents[1] / "src" / "nodelace" / "assets" / "fonts"
    expected = {
        "Geist-Variable.woff2": "2ffebe993e969069a9789d15164b7715d42491b5835516c5e3b935d5f81b05f1",
        "GeistMono-Variable.woff2": (
            "afaacc4c5fbba89d2ebf7a02dc4070208540874592a5504d57175782fe893101"
        ),
        "InstrumentSerif-Italic.woff2": (
            "4f7aacc18d491dea8778bbc591db87b9455625899ed5f913957e7fd82604c294"
        ),
        "InstrumentSerif-Regular.woff2": (
            "ca21b99b0d6b88a0dc34cebfe48104611e5c7f8f92746bed26c37aa470174322"
        ),
    }

    actual = {path.name: sha256(path.read_bytes()).hexdigest() for path in font_dir.glob("*.woff2")}

    assert actual == expected


def test_text_tokens_meet_wcag_aa_contrast() -> None:
    theme = EDITORIAL_LIGHT

    assert _contrast(theme.ink, theme.paper) >= 7.0
    assert _contrast(theme.muted, theme.paper) >= 4.5
    assert _contrast(theme.ink, theme.accent_soft) >= 7.0


@pytest.mark.parametrize(
    "unsafe_color",
    ("red", "#fff", "#12345678", "url(https://example.test/font)", "#fff;}svg{display:none"),
)
def test_theme_rejects_values_that_could_inject_css_or_network_urls(
    unsafe_color: str,
) -> None:
    with pytest.raises(ValueError, match="six-digit hexadecimal"):
        Theme(ink=unsafe_color)


def test_theme_accepts_case_insensitive_six_digit_hex_colors() -> None:
    assert Theme(accent="#Aa12fF").accent == "#Aa12fF"
