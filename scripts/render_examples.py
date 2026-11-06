"""Rebuild canonical examples and the light/dark release showcase."""

from __future__ import annotations

import argparse
from pathlib import Path

from nodelace import export_png, render_file
from nodelace.theme import THEMES

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--png", action="store_true", help="requires the png extra and Chromium")
    args = parser.parse_args()
    for source in sorted((ROOT / "examples").glob("*.diagram")):
        render_file(source, ROOT / "examples/rendered" / f"{source.stem}.svg", force=True)
        preview = ROOT / "examples/rendered" / f"{source.stem}.png"
        if args.png and preview.exists():
            export_png(source.read_text(encoding="utf-8"), preview, force=True)
    links = []
    for source in sorted((ROOT / "examples/styles").glob("*.diagram")):
        for name, theme in THEMES.items():
            stem = f"{source.stem}-{name}"
            target = source.parent / f"{stem}.html"
            render_file(source, target, theme=theme, force=True)
            render_file(source, target.with_suffix(".svg"), theme=theme, force=True)
            if args.png:
                export_png(
                    source.read_text(encoding="utf-8"),
                    target.with_suffix(".png"),
                    theme=theme,
                    force=True,
                )
            links.append(
                f"<article><h2>{source.stem.replace('-', ' ')} · {name}</h2>"
                f'<a href="{stem}.html"><img src="{stem}.svg" alt="{stem}"></a>'
                f'<p><a href="{source.name}">Source</a> · '
                f'<a href="{stem}.svg">SVG</a> · <a href="{stem}.html">HTML</a></p></article>'
            )
    (ROOT / "examples/styles/index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Nodelace — editorial styles</title><style>"
        "body{margin:32px;background:#ececec;color:#2d3142;font:16px system-ui}"
        "main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:24px}"
        "article{min-width:0}img{width:100%;height:auto}a{color:#2456a6}"
        "</style><h1>Nodelace: light &amp; dark</h1>"
        "<p>The same compact source, rendered locally. "
        "Open a diagram for its readable full size.</p>"
        "<main>" + "".join(links) + "</main></html>",
        encoding="utf-8",
    )
    if args.png:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.goto((ROOT / "examples/index.html").as_uri())
            page.wait_for_function("[...document.images].every(i => i.complete)")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(ROOT / "examples/gallery.png"), full_page=True)
            browser.close()


if __name__ == "__main__":
    main()
