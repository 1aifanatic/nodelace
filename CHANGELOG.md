# Changelog

## 0.3.0 — 2026-11-06

- Add the npm distribution: Node.js 22+, local Pyodide runtime, no system Python.
  One shared renderer keeps SVG output identical across Python and npm.
- Ship typed async JavaScript render/check/parse APIs and local CLI with starter
  templates, themes, profiles, sizes, safe output writes and optional PNG export.
- Both CLIs now support stdin/stdout and structured JSON diagnostics.
- Fix self-call spacing, nested frame containment, mixed-height participant
  lifelines, nested activation ranges and activation ends after self-calls.
- Preserve primary/return/feedback styling in crossing marks; diagnose sequence
  labels that overlap other message paths.
- Add Node matrix CI, packed-package smoke tests and offline/parity regressions.

Tradeoff: npm bundles a WebAssembly runtime dependency (about 14 MB installed).
Core Python still has no runtime dependencies. Neither distribution makes model
calls. Version 0.3.0 was published to npm on 2026-11-06. Python 0.3.0 artifacts
are prepared locally; PyPI publication remains pending.

## 0.2.0 — 2026-11-06

- Measured bundled-font advances replace character-count widths. Shared wrapping, Unicode fallback estimates, obstacle routing, crossing marks and scoped SVG styles address the audit regressions.
- Add layout diagnostics and strict CLI checks for collisions, shortening, contrast, density, focus and destination sizing.
- Add editorial light/dark themes, bounded TOML color profiles and five target-size presets. HTML preserves readable text with local horizontal scrolling.
- Add node roles, decision/terminal/merge shapes, tags, sublabels and semantic legends.
- Add explicit call/return/async/primary edges, sequence activations, ALT/OPT/LOOP frames and one nested level.
- Add optional local PNG export through Playwright. The base SVG/HTML package still has zero runtime dependencies.
- Ship refreshed examples, a compact agent reference and a pinned upstream design contract.

Compatibility: old DSL remains accepted. Layout, default accent contrast, SVG IDs and output bytes intentionally change. Repeated inline instances should specify unique `id_prefix` values. Full UML, all upstream diagram families and pixel-identical emulation are not claimed.

## 0.1.0

Initial deterministic architecture, flow and sequence renderer.
