"""Browser checks for packaged fonts, text bounds, mobile scroll and SVG isolation."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from nodelace import EDITORIAL_DARK, render

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("http://**/*", lambda route: route.abort())
        page.route("https://**/*", lambda route: route.abort())
        sources = sorted((ROOT / "examples").glob("*.diagram"))
        sources += sorted((ROOT / "examples/styles").glob("*.diagram"))
        sources_text = [(p.stem, p.read_text(encoding="utf-8")) for p in sources]
        sources_text.append(("wide-label", 'flow "Width regression"\n' + "W" * 40 + " -> 漢字測試"))
        for name, source in sources_text:
            page.set_content(render(source, format="html"))
            page.evaluate("document.fonts.ready")
            data = page.evaluate("""() => {
                const failures = [];
                for (const text of document.querySelectorAll('.node-label')) {
                    const shape = text.parentElement.querySelector('.node-box');
                    if (!shape) continue;
                    const a = text.getBBox(), b = shape.getBBox();
                    if (a.x < b.x - 1 || a.x+a.width > b.x+b.width+1 ||
                        a.y < b.y-1 || a.y+a.height > b.y+b.height+1)
                        failures.push(text.textContent);
                }
                return {failures, fonts: document.fonts.check('600 12px "Geist"') &&
                    document.fonts.check('500 11px "Geist Mono"')};
            }""")
            assert data["fonts"], (name, "unloaded fonts")
            assert not data["failures"], (name, data)
            results.append({"source": name, **data})
        source = sources_text[0][1]
        page.set_content(
            '<style>.outside{color:rgb(1,2,3)}</style><p class="node-label outside">Host</p>'
            + render(source, id_prefix="light-instance")
            + render(source, theme=EDITORIAL_DARK, id_prefix="dark-instance")
        )
        page.evaluate("document.fonts.ready")
        data = page.evaluate("""() => {
            const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
            const text = [...document.querySelectorAll('svg .node-label')];
            return {unique: new Set(ids).size === ids.length,
                host: getComputedStyle(document.querySelector('p')).color,
                light: getComputedStyle(text[0]).fill,
                dark: getComputedStyle(text[text.length-1]).fill};
        }""")
        assert data["unique"] and data["host"] == "rgb(1, 2, 3)", data
        assert data["light"] != data["dark"], data
        page.set_viewport_size({"width": 390, "height": 844})
        page.set_content(render(source, format="html"))
        page.evaluate("document.fonts.ready")
        mobile = page.evaluate("""() => {
            const region = document.querySelector('[role=region]');
            return {page: document.documentElement.scrollWidth, viewport: innerWidth,
                scrollable: region.scrollWidth > region.clientWidth,
                focusable: region.tabIndex === 0,
                text: getComputedStyle(document.querySelector('.node-label')).fontSize};
        }""")
        assert mobile["page"] <= mobile["viewport"], mobile
        assert mobile["scrollable"] and mobile["focusable"] and mobile["text"] == "12px", mobile
        page.emulate_media(media="print")
        assert page.locator("svg").bounding_box()["width"] <= 390
        assert (
            page.locator(".diagram-container").evaluate("e => getComputedStyle(e).overflowX")
            == "visible"
        )
        browser.close()
    print(json.dumps({"bounds": results, "inline": data, "mobile": mobile}, indent=2))


if __name__ == "__main__":
    main()
