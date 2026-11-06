"""Regenerate offline advances from bundled fonts (development-only fontTools)."""

from __future__ import annotations

import json
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src/nodelace/assets"
FONTS = {
    "sans": "Geist-Variable.woff2",
    "mono": "GeistMono-Variable.woff2",
    "serif": "InstrumentSerif-Regular.woff2",
}


def main() -> None:
    metrics = {}
    for family, filename in FONTS.items():
        font = TTFont(ASSETS / "fonts" / filename)
        instances = (
            [instantiateVariableFont(font, {"wght": w}, inplace=False) for w in (400, 500, 600)]
            if "fvar" in font
            else [font]
        )
        cmap = font.getBestCmap()
        units = font["head"].unitsPerEm
        metrics[family] = {
            chr(code): round(max(f["hmtx"][name][0] for f in instances) / units, 5)
            for code, name in sorted(cmap.items())
        }
    (ASSETS / "font-metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
