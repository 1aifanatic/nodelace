# 0.3.0 launch checklist

Scope: extend the project with Node-only npm distribution and fix additional sequence/crossing defects; implement the audit's six confirmed fixes and recommended next release for the existing architecture, flow and sequence families. The audit explicitly deferred all-45-type parity, website scraping, animation, GUI editing and broad imports; these are not release requirements. Prepare distributions locally; publishing is a separate action.

- [x] Shared deterministic font metrics and Unicode-aware wrapping; overflow regressions.
- [x] Obstacle-aware orthogonal routing, crossing reduction and readable crossing marks.
- [x] Scoped SVG CSS and deterministic caller-supplied instance IDs.
- [x] Layout diagnostics for intersections, labels, density, focus, contrast and destination size.
- [x] Reference-compatible light/dark presets, role-specific contrast checks and CLI selection.
- [x] Readable responsive HTML, print behavior and target-size presets.
- [x] Explicit node roles/shapes, tags, sublabels and legends.
- [x] Explicit edge roles; sequence returns, asynchronous messages, activations and simple fragments.
- [x] Lightweight TOML profiles and optional PNG export outside the base dependencies.
- [x] Compact agent reference and pinned upstream contract manifest.
- [x] Regenerated examples and at least two visually reviewed styles, with previews.
- [x] Version/changelog/readme/API/DSL documentation and package contents updated.
- [x] Tests, coverage >=90%, lint, sdist/wheel build, strict metadata checks and clean-install smoke.
- [x] Completion audit against each item above with concrete evidence.

## Verification evidence (2026-11-06)

- `tests/test_audit_regressions.py`: measured wrapping, obstacle routes in both directions, safe/scoped SVG IDs, mobile HTML and crossing marks.
- `tests/test_editorial.py`: model/DSL roles, shapes, fragments, activations, themes, profiles, destination sizes, diagnostics, CLI and snapshots. All six showcase outputs pass strict publication checks.
- `scripts/verify_visuals.py`: Chromium bounds checks on ten original examples, three new examples and wide Latin/CJK labels; loaded fonts; light/dark inline isolation; 390px local scrolling at 12px text; print fitting.
- Manual visual review: light architecture, light decision flow, dark architecture and dark ALT sequence. All six showcase previews, five legacy PNGs and the main gallery were regenerated through the real PNG/browser path.
- Python 3.12 on Windows: 242 tests passed, 6 platform-specific skips, 94% branch-aware coverage; Ruff clean. The CI matrix remains Windows/Linux/macOS and Python 3.11?3.14; remote runs are not claimed here.
- Isolated `python -m build` produced the sdist and a wheel built from that sdist. Strict Twine checks pass for both.
- Clean wheel venv outside the repository, Python `-I`: bundled fonts, metrics, licenses, dark rendering, diagnostics and zero core dependencies verified. Only nodelace and pip installed.
- Release metadata is 0.3.0. CI adds browser checks; publication checks the `v0.3.0` tag against package version and smoke-tests the installed wheel.
- Compact agent guide, pinned upstream SHA, updated API/DSL documentation, changelog and source examples are included in the source distribution.

## npm verification (0.3)

- [x] Node.js 22+ API and CLI, local Pyodide 314.0.7; no system Python required.
- [x] Shared source bundle, pinned runtime, included fonts/licenses and TypeScript declarations.
- [x] Thirteen Node tests passed: offline first render with network/child-process APIs blocked, byte parity across 16 SVG fixtures, errors, concurrent calls, profiles, options, stdin/stdout, templates and overwrite protection.
- [x] Actual tarball installed in an isolated temporary project with lifecycle scripts disabled; offline rendering, embedded fonts, diagnostics and CLI version passed.
- [x] Both CLIs support stdin/stdout and structured JSON diagnostics.
- [x] Python suite includes ten regressions for the additional geometry/activation/crossing fixes.
- [x] Local Node 22.23.4 and 25.4.0 exercised. Node 22/24 on Windows/macOS/Linux added to CI; these remote runs are pending.
- [x] Packed npm CLI exported a dark PNG using optional Playwright/Chromium; inspected the result.
- [x] Fresh review found and fixed source-symlink overwrite protection and output-format mismatches; regression coverage included.

The npm tarball is `npm/nodelace-0.3.0.tgz` (about 257 KB). Its Pyodide dependency
adds about 14 MB installed. Cold startup measured around 1.8s locally. SVG/HTML need
no browser; npm PNG export uses optional Playwright/Chromium. Distribution source
and instructions are in `npm/README.md`. Public registry installation and local
tarball installation are both verified.

## Publication status (2026-11-06)

`nodelace@0.3.0` is published publicly on npm under account `1aifanatic`, with
the `latest` tag pointing to `0.3.0`: https://www.npmjs.com/package/nodelace.
The exact tested tarball was published after browser authentication. Its registry
SHA-1 matches the local artifact: `cbebb206e9b30e8f3e087cfec5bd35e2b9b8fe0d`.
A fresh public-registry install with an isolated npm cache and lifecycle scripts
disabled passed offline rendering, embedded-font, diagnostics and CLI version checks.
No GitHub commit or push was performed as part of publication; remote CI runs
remain pending.

Local artifacts are `dist/nodelace-0.3.0-py3-none-any.whl` and
`dist/nodelace-0.3.0.tar.gz`. Python 0.3.0 has not been published to PyPI. Before publishing,
run remote CI and confirm the repository's PyPI Trusted Publisher/environment is
configured. The existing workflow publishes on a GitHub release tagged `v0.3.0`.
PyPI authorization was not exercised during this release.

The original audit records the pre-fix baseline. This checklist records what changed.
Dense arbitrary graphs and fallback glyph rendering can still require human review;
strict checks flag supported failure modes and do not promise universal layout quality.

