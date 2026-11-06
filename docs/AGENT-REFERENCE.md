# Nodelace: compact agent reference

Write a `.diagram` file; let local Python handle geometry and SVG. Do not generate SVG, coordinates or font data in the conversation.

Node-only users can run the same commands with `npx nodelace` after installing
the npm package. `npx nodelace init architecture|flow|sequence` creates a starter.
Both CLIs accept stdin `-`, render stdout `-o -`, and `check --layout --json` for
compact structured feedback. Return the output path rather than SVG/font data.

```text
architecture "Order service"
direction left-to-right
node API role=backend tag=SERVICE sublabel="Owns order processing"
node DB role=store label="Orders"
Browser -> API: HTTPS
API => DB: persist
highlight API
```

Headers: `architecture`, `flow`, `sequence`; optional quoted title. Quote names containing punctuation. Ordinary edges: `A -> B: label`; chains allowed without labels. `-->` return, `~>` async, `=>` primary. `call A -> B` is an explicit sequence call. Roles: default/backend/store/external/input/optional. Shapes: box/decision/terminal/merge. Decision/merge cannot have tags or sublabels; sequence participants use box/terminal. Label decision exits. Groups: `group Services: API, Worker`. Highlight at most two nodes.

Sequence messages run in source order. Frame directives: `alt "condition"`, `else "other condition"`, `end`; `opt "condition"` and `loop "condition"` end with `end`. ALT requires two nonempty branches. At most one nested level. `activate API` / `deactivate API` surround messages; activation is explicit, never inferred from labels.

```console
nodelace check system.diagram --layout --strict
nodelace render system.diagram --theme dark --format html
nodelace render system.diagram --size slide-16x9
```

Themes: light/dark or `--profile colors.toml` with `[theme]`, `base="light"`, hex color overrides. Sizes: fit/doc-inline/doc-wide/slide-16x9/social-square/print-a4. Default fit preserves readable text; HTML scrolls on narrow screens. Use `--id-prefix unique-name` for repeated inline SVG instances. Explicit existing output paths require `--force`.

Keep architecture/flow under 10 nodes and 13 edges; sequence under 6 participants. Fix diagnostics or split the diagram. Inspect the image before publication. Rendering consumes no model tokens; interpreting the brief still does. Full syntax: `docs/DSL.md`.
