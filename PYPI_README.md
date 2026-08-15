# Nodelace

Nodelace renders polished architecture, flow, and sequence diagrams from a
small text language. Rendering is deterministic and entirely local: the base
package has no runtime dependencies, AI calls, network requests, telemetry,
Graphviz, browser, or Node.js requirement.

```console
python -m pip install nodelace
```

Create `system.diagram`:

```text
architecture "Small Web Service"
direction left-to-right

Browser -> API: HTTPS
API -> Database: query
highlight API
```

Then validate and render it:

```console
nodelace check system.diagram
nodelace render system.diagram
```

The default artifact is `system.svg`. Standalone HTML is also available:

```console
nodelace render system.diagram --format html -o system.html
```

The Python API accepts source text or an immutable parsed model:

```python
from nodelace import parse_diagram, render

diagram = parse_diagram('flow "Two Steps"\nStart -> Finish')
svg = render(diagram)
```

Nodelace provides:

- architecture, flow, and basic sequence diagrams;
- deterministic layered and participant-lane layout;
- orthogonal connectors, cycles, flat groups, and focal highlights;
- accessible SVG title and description metadata;
- self-contained offline SVG/HTML with bundled OFL-1.1 fonts and notices;
- a strict, non-executable UTF-8 language with bounded input limits;
- a dependency-free Python 3.11+ runtime and typed public API.

Current limits include flat groups only, Latin coverage in the bundled fonts,
no full UML sequence fragments, a 50-node safety ceiling, and SVG/HTML output
only. Other Unicode text remains valid and selectable but may use a viewer's
installed fallback font.

The source distribution contains the complete language and architecture
references under `docs/`, plus ten source examples, byte-verified SVGs, and an
offline gallery under `examples/`.

Nodelace code is MIT licensed. Instrument Serif, Geist, and Geist Mono remain
under the SIL Open Font License 1.1; their complete notices ship in the package
and in artifacts that embed the fonts.

The design goals were inspired by Kathryn Lavery's
[diagram-design](https://github.com/cathrynlavery/diagram-design) work.
Nodelace is an independent deterministic implementation and does not package
or invoke that AI-oriented skill.
