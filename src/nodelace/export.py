"""Optional browser PNG export; the standard renderer never imports Playwright."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from nodelace.errors import NodelaceError
from nodelace.model import Diagram
from nodelace.renderer import _atomic_write, render
from nodelace.theme import EDITORIAL_LIGHT, Theme


def export_png(
    source: str | Diagram,
    output_path: str | Path,
    *,
    force: bool = False,
    theme: Theme = EDITORIAL_LIGHT,
    size: str = "fit",
    scale: int = 2,
) -> Path:
    """Render source text to PNG with local Chromium and embedded fonts, offline."""
    if type(scale) is not int or not 1 <= scale <= 4:
        raise ValueError("PNG scale must be an integer from 1 to 4")
    path = Path(output_path)
    if path.suffix.lower() != ".png":
        raise ValueError("PNG output must end in .png")
    if path.exists() and not force:
        raise ValueError("output already exists; pass force=True or --force")
    svg = render(source, theme=theme, size=size)
    root = ET.fromstring(svg)
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    if width * height * scale * scale > 64_000_000:
        raise ValueError("PNG exceeds 64 million pixels; reduce scale or split the diagram")
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as error:
        raise NodelaceError(
            "PNG export needs pip install 'nodelace[png]' and python -m playwright install chromium"
        ) from error
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    viewport={"width": width, "height": height}, device_scale_factor=scale
                )
                page.route("http://**/*", lambda route: route.abort())
                page.route("https://**/*", lambda route: route.abort())
                page.set_content(
                    '<html><body style="margin:0">' + svg.split("\n", 1)[1] + "</body></html>"
                )
                page.evaluate("document.fonts.ready")
                payload = page.locator("svg").screenshot(type="png", timeout=30_000)
            finally:
                browser.close()
    except Error as error:
        raise NodelaceError(
            "PNG browser export failed; install Chromium with "
            "python -m playwright install chromium. " + str(error)
        ) from error
    _atomic_write(path, payload, replace=force)
    return path
