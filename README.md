# Nodelace

Nodelace turns a small, readable text format into polished architecture, flow,
and sequence diagrams. It is deterministic, works entirely on your machine,
and produces SVG by default. HTML output is available when a self-contained
page is more convenient.

Nodelace does not call an AI model, access the network, send telemetry, or
upload your diagram text. The base package has no runtime dependencies and
requires Python 3.11 or newer.

## Quick start

Install it from PyPI:

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

Check it, then render it:

```console
nodelace check system.diagram
nodelace render system.diagram
```

The render command writes `system.svg` when no output path or format is given.
That derived sibling is treated as a build artifact and is atomically replaced
on later renders. Use `-o` to choose an explicit path, `--format html` for a
standalone HTML page, and `--force` to replace an existing explicit output:

```console
nodelace render system.diagram -o docs/system.svg
nodelace render system.diagram --format html -o docs/system.html
```

## Language at a glance

A document normally starts with a diagram kind and a quoted title:

```text
architecture "Service Map"
flow "Release Decision"
sequence "Sign-In Request"
```

The header is optional for tiny flow diagrams; omission means `flow` with no
title. Explicit headers are recommended in saved project files.

The rest of the language is intentionally small:

```text
direction left-to-right
A -> B -> C
C -> D: stores result
group Services: B, C
highlight C
```

- `architecture` shows components and their connections.
- `flow` shows steps, branches, and feedback paths.
- `sequence` treats edges as messages in source order, with time flowing down.
- `direction left-to-right|top-to-bottom` controls architecture and flow layout.
- A chain is shorthand for consecutive edges.
- A label follows the final colon on a single edge.
- Groups are flat visual regions. Highlights mark focal nodes.

See [the DSL reference](docs/DSL.md) for the complete syntax and validation
rules.

## Command line

```text
nodelace render INPUT [-o OUTPUT] [--format svg|html] [--force] [--system-fonts]
nodelace check INPUT
nodelace --version
```

`render` uses SVG unless the format is selected explicitly or inferred from an
`.html` output path. With no `-o`, it atomically replaces the derived sibling
output. An explicitly named output is protected and requires `--force` when it
already exists. `check` parses and validates a source file without creating
output. Syntax and validation errors include source locations and return a
nonzero exit status.

Outputs embed Nodelace's bundled fonts by default. `--system-fonts` omits that
data for a smaller file, at the cost of portable typography.

The module entry point is equivalent to the installed command:

```console
python -m nodelace render system.diagram
```

## Python API

`render` accepts DSL text or a parsed `Diagram`. A string is always treated as
source text, never guessed to be a path.

```python
from nodelace import parse_diagram, render, render_file

source = '''architecture "Job Runner"
direction left-to-right
Queue -> Worker -> Store
highlight Worker
'''

svg = render(source)
html = render(source, format="html")

diagram = parse_diagram(source)
same_svg = render(diagram)

output = render_file("system.diagram")
html_output = render_file(
    "system.diagram",
    "system.html",
    format="html",
    force=True,
)
```

`render_file` follows the CLI's output policy: its derived sibling output is
atomically replaceable, while an existing explicit `output_path` requires
`force=True`. Nodelace refuses to replace directories, links, devices, and
other non-regular filesystem entries. On a filesystem without hard-link
support, the first write to an explicit output remains no-clobber but may be
observable while its final bytes are copied into place.

Lower-level renderers are also public:

```python
from nodelace import parse_diagram, render_html, render_svg

diagram = parse_diagram('flow "Two Steps"\nStart -> Finish')
svg = render_svg(diagram)
html = render_html(diagram)
```

The public signatures are:

```text
parse_diagram(source, *, source_name="<string>") -> Diagram
render(source, *, format="svg", embed_fonts=True, theme=EDITORIAL_LIGHT) -> str
render_svg(diagram, *, embed_fonts=True, theme=EDITORIAL_LIGHT) -> str
render_html(diagram, *, embed_fonts=True, theme=EDITORIAL_LIGHT) -> str
render_file(input_path, output_path=None, *, format=None, force=False,
            embed_fonts=True, theme=EDITORIAL_LIGHT) -> Path
```

The deterministic geometry seam is also public for integrations that want to
inspect positions without serializing SVG:

```python
from nodelace.layout import LayoutResult, layout_diagram

layout: LayoutResult = layout_diagram(diagram)
```

`nodelace.layout` exports immutable point, rectangle, positioned-node/group,
routed-edge, participant, and message value objects.

## Examples

The repository contains exactly ten hand-written sources and their
byte-verified rendered SVGs in [`examples/rendered`](examples/rendered). Open
the [offline HTML gallery](examples/index.html) or view the
[single-image gallery](examples/gallery.png) to scan all ten together.

1. [Hello, Nodelace](examples/01-hello-world.diagram) · [SVG](examples/rendered/01-hello-world.svg) — minimal architecture.
2. [Commerce Platform](examples/02-commerce-platform.diagram) · [SVG](examples/rendered/02-commerce-platform.svg) — branching,
   labels, and groups.
3. [Warehouse Feedback Control](examples/03-feedback-control.diagram) · [SVG](examples/rendered/03-feedback-control.svg) — a
   top-to-bottom cycle.
4. [Global Café Routing](examples/04-global-routing.diagram) · [SVG](examples/rendered/04-global-routing.svg) — Unicode names
   and converging regional paths.
5. [Release Approval](examples/05-release-approval.diagram) · [SVG](examples/rendered/05-release-approval.svg) — branching flow
   with retry and rollback.
6. [Incident Response](examples/06-incident-response.diagram) · [SVG](examples/rendered/06-incident-response.svg) —
   left-to-right business feedback loop.
7. [Invoice Processing](examples/07-invoice-processing.diagram) · [SVG](examples/rendered/07-invoice-processing.svg) — grouped
   business process.
8. [User Sign-In](examples/08-user-sign-in.diagram) · [SVG](examples/rendered/08-user-sign-in.svg) — basic request/response
   sequence.
9. [Checkout](examples/09-checkout-sequence.diagram) · [SVG](examples/rendered/09-checkout-sequence.svg) — realistic commerce
   sequence.
10. [Regional Sync](examples/10-regional-sync.diagram) · [SVG](examples/rendered/10-regional-sync.svg) — Unicode participants
    in a multi-region sequence.

Render all examples from PowerShell:

```powershell
Get-ChildItem examples\*.diagram | ForEach-Object {
    $destination = Join-Path $_.DirectoryName ("rendered\" + $_.BaseName + ".svg")
    nodelace render $_.FullName -o $destination --force
}
```

## Determinism, privacy, and accessibility

- Rendering is local and offline: no model calls, network requests, telemetry,
  remote fonts, or external rendering services.
- Stable source ordering and deterministic layout tie-breaks make the same
  input, options, and Nodelace version produce the same output.
- SVG is text, scales without pixelation, and is the canonical output. HTML is
  a self-contained wrapper around that SVG.
- Rendered diagrams include a title and description for assistive technology.
  Text remains real SVG text rather than being converted to paths.
- Color is not the only carrier of structure: labels, grouping, position, and
  connector direction remain visible without the accent color.

Complex diagrams still need human judgment. Review reading order, edge labels,
and color contrast in the context where the output will be published.

## Current limitations

- Only architecture, flow, and basic sequence diagrams are supported.
- Groups are flat; nested groups and swimlanes are not available.
- The language has one built-in editorial theme and no arbitrary SVG/CSS
  injection.
- Sequence diagrams support ordered messages, not the full UML sequence
  notation such as activation control, `alt`, `loop`, or participant lifetime.
- Dense graphs, many cycles, and long labels can produce a less compact layout.
  Split large systems into an overview and focused detail diagrams.
- A source is limited to 50 nodes so accidental or generated input cannot turn
  a documentation render into an unbounded layout job.
- The bundled fonts cover Latin text. Other Unicode text remains valid and
  selectable, but a viewer may use an installed fallback font for unsupported
  glyphs, so its pixels can vary even though the SVG bytes and geometry do not.
- SVG and HTML are the only outputs. PNG and PDF conversion are deliberately
  outside the dependency-free core.

## Development

Create and activate a virtual environment, then install the project with its
development tools:

```console
python -m venv .venv
python -m pip install -e ".[dev]"
```

Run the quality checks:

```console
python -m pytest
python -m coverage run -m pytest
python -m coverage report
python -m ruff check .
python -m build
python -m twine check dist/*
```

The implementation architecture and determinism rules are described in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License and attribution

Nodelace code is released under the [MIT License](LICENSE). Bundled fonts have
their own notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The project's design goals were inspired by Kathryn Lavery's
[diagram-design](https://github.com/cathrynlavery/diagram-design) work. Nodelace
is an independent, deterministic implementation; it does not package or invoke
that AI-oriented skill.
