# Nodelace architecture

This document describes the internal boundaries and invariants that keep
Nodelace small, deterministic, and safe to run offline.

## Goals

Nodelace is designed around five constraints:

1. Rendering never requires AI, a network connection, Graphviz, a browser, or
   another system executable.
2. The base installation has no third-party Python runtime dependencies.
3. SVG is the canonical output; HTML is a self-contained wrapper.
4. The same source, options, and Nodelace version produce the same bytes.
5. Public objects remain useful independently of the command-line interface.

Nodelace deliberately optimizes for clear diagrams with tens of nodes, not
general-purpose graph drawing at arbitrary scale.

## Processing pipeline

```text
.diagram text
      |
      v
  DSL parser  ---> diagnostics
      |
      v
 domain model
      |
      v
layout selection ---> routing ---> scene geometry
      |                              |
      +------------------------------+
                     |
                     v
               SVG renderer
                     |
                     +----> SVG text
                     |
                     +----> standalone HTML
```

Each stage consumes explicit data and returns new data. Parsing does not draw,
layout does not serialize XML, and rendering does not reinterpret the source
language. This separation makes each stage testable without invoking the CLI
or touching the filesystem.

## Package boundaries

The source package uses these responsibilities:

- `model.py` defines the immutable public model: `Diagram`, `Node`, `Edge`,
  `Group`, `DiagramKind`, and `Direction`.
- `dsl.py` tokenizes, parses, and validates UTF-8 source into that model.
- `errors.py` defines syntax and validation exceptions with source context.
- `layout/` exposes immutable geometry value objects and turns a model into
  positioned nodes, groups, labels, and connector paths. Layout code has no
  output-format concerns.
- `theme.py` contains named visual tokens and bundled-font embedding; layout
  modules own geometry constants.
- `renderer.py` escapes content, serializes canonical SVG, embeds bundled fonts,
  and optionally wraps SVG in HTML.
- `cli.py` is a thin adapter for filesystem input, overwrite policy, diagnostic
  printing, and process exit codes.
- `__init__.py` and the documented exports from `nodelace.layout` are the
  supported Python API surface. Helper functions inside layout engines remain
  implementation details.

Dependencies point inward toward the model. In particular, the parser and
layout engine do not import the CLI, and no library entry point reads a path
unless the caller explicitly chooses `render_file`.

## Domain model

The parsed model preserves source order:

```text
Diagram
  kind: DiagramKind
  title: str | None
  nodes: tuple[Node, ...]
  edges: tuple[Edge, ...]
  groups: tuple[Group, ...]
  highlights: tuple[str, ...]
  direction: Direction | None
```

Nodes are interned by their exact Unicode name and ordered by first mention.
Edges remain in source order. Groups are flat and ordered. Frozen dataclasses
and tuples prevent later stages from mutating parse results accidentally.

That ordering is semantic for sequence diagrams and is the final tie-breaker
for equally good architecture or flow layouts.

## Layout strategies

Architecture and flow diagrams share a small layered layout pipeline:

1. Build adjacency and identify strongly connected regions.
2. Assign stable ranks along the requested direction.
3. Order each rank by stable first-mention order.
4. Size and position nodes using fixed spacing and deterministic text metrics.
5. Reserve group bounds around their members.
6. Select distinct perimeter ports and route orthogonal connectors.
7. Route feedback and rank-skipping edges through separate exterior channels.

Cycles are expected. They do not change the source ordering, and no random
seed or hash iteration order may influence placement.

Sequence diagrams use a dedicated layout because graph ranking would erase
their meaning. Participants occupy stable columns in first-mention order;
messages occupy monotonically increasing rows in source order. Reverse messages
travel back across columns while time continues downward.

Layout is intentionally bounded rather than mathematically optimal. Crossing
reduction and compaction are stable heuristics, so a dense or highly connected
graph may benefit from being split into overview and detail diagrams.

## Rendering and portability

The renderer consumes only model and layout data. It produces valid,
namespace-qualified SVG using a fixed element order, attribute order, numeric
format, and escaping policy. It never incorporates wall-clock timestamps,
random identifiers, absolute input paths, host names, or platform-specific font
measurements.

Fonts used by the default theme are bundled and embedded. Layout uses fixed
text metrics, so line breaks and box geometry do not depend on a viewer's
installed fonts. The bundled families cover Latin text; unsupported Unicode
glyphs can use a viewer fallback and therefore vary visually without changing
the SVG bytes or geometry. The CLI may omit embedded font data with
`--system-fonts` when smaller output matters more than portable appearance.

Standalone HTML contains its SVG and CSS inline. It has no JavaScript, remote
stylesheets, remote font requests, external images, or tracking pixels. Both
formats are safe to open without network access.

SVG accessibility is part of rendering rather than a post-processing step:
the diagram title and textual description accompany the image semantics, while
node and edge labels remain selectable text. Visual grouping and connector
direction do not rely on color alone.

## Determinism contract

For a fixed Nodelace version, source text, and render options, output is
byte-for-byte deterministic. Contributors must preserve these rules:

- Never rely on unordered set or mapping iteration for emitted order.
- Use source order as the final tie-breaker.
- Do not use randomized or force-directed layout.
- Normalize numeric values before serialization.
- Derive generated SVG identifiers from a stable semantic fingerprint.
- Exclude timestamps, machine paths, and environment details from output.
- Treat a change to geometry, whitespace, or serialization as an observable
  output change and cover it with deterministic tests.

Determinism is scoped to a Nodelace release. An intentional layout improvement
may change output in a later version and should be called out in release notes.

## Privacy and security boundary

Library rendering reads only immutable font/license assets bundled inside the
installed package, then operates in memory. `render_file` and the CLI add
explicit caller-selected local file reads and writes. There are no network
clients, subprocess calls, plugins, template evaluation, or arbitrary code
execution in the render path.

The DSL is data, not Python. Labels are escaped before entering SVG or HTML.
An explicitly named output is protected unless `--force` is supplied. A
derived sibling output is a repeatable build target and is replaced atomically.
Replacement refuses non-regular filesystem entries. On Windows, replacement
uses the native metadata-preserving file operation; on other platforms,
Nodelace copies the metadata supported by Python before the atomic swap. A new
explicit output is normally published atomically with a no-clobber hard link.
Filesystems without hard-link support use exclusive creation instead: the
operation still cannot overwrite a competing file, but readers may observe it
while the final bytes are copied.
The CLI reports invalid UTF-8, I/O failures, syntax failures, and validation
failures without a partial successful result.

Any future feature that introduces a dependency, subprocess, network access,
script execution, or unescaped markup belongs behind an explicit optional
boundary and must not weaken the offline default.

## Public API stability

The supported public surface is exported by `nodelace`:

```text
parse_diagram(source, *, source_name="<string>") -> Diagram
render(source, *, format="svg", embed_fonts=True, theme=EDITORIAL_LIGHT) -> str
render_svg(diagram, *, embed_fonts=True, theme=EDITORIAL_LIGHT) -> str
render_html(diagram, *, embed_fonts=True, theme=EDITORIAL_LIGHT) -> str
render_file(input_path, output_path=None, *, format=None, force=False,
            embed_fonts=True, theme=EDITORIAL_LIGHT) -> Path
layout_diagram(diagram) -> LayoutResult  # from nodelace.layout
```

`render` treats strings as DSL source. It never guesses whether a string might
be a filename; callers opt into file access with `render_file`.

New syntax should normally map into the existing model or an explicitly
versioned extension. New output backends should consume scene/layout data and
must not duplicate parsing or layout logic.

## Testing strategy

Tests are organized around observable contracts:

- parser tests cover valid syntax, Unicode, quoting, comments, diagnostics, and
  semantic validation;
- layout tests cover stable placement, requested direction, groups, cycles,
  connector endpoints, and collision invariants;
- renderer tests cover escaping, accessibility metadata, embedded assets,
  deterministic snapshots, and self-contained HTML;
- CLI tests cover default paths, format inference, overwrite refusal, exit
  codes, and `python -m nodelace` parity;
- an example test parses and renders every file under `examples/`.

Bug fixes should include the smallest failing source as a regression test. A
rendering test should assert semantic invariants where possible; reserve full
snapshots for output stability that is intentionally part of the contract.
