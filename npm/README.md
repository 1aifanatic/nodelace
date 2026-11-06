# Nodelace for Node.js

Generate architecture, flow and sequence diagrams locally from compact text.
**Node.js 22+ is the only required system runtime.** SVG/HTML need no Python
installation, browser, API key or rendering server.

## Quick start

Install from npm:

```sh
npm install nodelace
npx nodelace init architecture -o system.diagram
npx nodelace check system.diagram --layout --strict
npx nodelace render system.diagram --theme dark --format html
```

Global installation with `npm install -g nodelace` provides the `nodelace` command.
`init architecture|flow|sequence` creates a
starter. Example source:

```text
architecture "Order service"
node API role=backend tag=SERVICE sublabel="Order orchestration"
node Orders role=store
Browser -> API: HTTPS
API => Orders: commit
highlight API
```

`render` defaults to a sibling SVG, replaced on reruns. Explicit `-o OUTPUT` paths
require `--force` to replace an existing file. Input `-` reads UTF-8 from stdin;
`-o -` writes SVG/HTML to stdout. Rendering from stdin defaults to stdout.
`check --json` emits structured results; `--layout` enables visual diagnostics;
`--strict` fails on warnings too.

```sh
echo "Browser -> API" | npx nodelace render - --system-fonts > system.svg
npx nodelace check system.diagram --layout --json
```

Themes: `--theme light|dark`, or `--profile colors.toml` with `[theme]`,
`base = "light"` and hex color overrides. Sizes: `fit`, `doc-inline`, `doc-wide`,
`slide-16x9`, `social-square`, `print-a4`. Fixed canvases may shrink crowded layouts;
check with the same theme/size before publication. Repeated inline SVGs need unique
`--id-prefix` values. Fonts embed by default; `--system-fonts` omits them.

## JavaScript / TypeScript

```js
import { render, check, parse } from 'nodelace';
import { writeFile } from 'node:fs/promises';
const source = 'architecture "Service"\nBrowser -> API: HTTPS';
const diagnostics = await check(source, { theme: 'dark' });
const svg = await render(source, { theme: 'dark', idPrefix: 'service-map' });
await writeFile('service.svg', svg);
const model = await parse(source);
```

Options: `format` (`svg` or `html`), `theme`, `size`, `idPrefix`, `embedFonts`,
and `profile` (TOML **text**, not a path). Methods return promises. `NodelaceError`
has `code`, `line`, `column`. Type declarations are included. CommonJS callers
can use `await import('nodelace')`.

## Optional PNG

```sh
npm install playwright
npx playwright install chromium
npx nodelace export system.diagram -o system.png --theme dark --scale 2
```

Browser installation downloads Chromium. Export blocks HTTP(S) and waits for
fonts. PNG is a CLI feature; the JS API produces SVG/HTML.

## Shared engine and tradeoffs

The same Python renderer runs inside **Pyodide WebAssembly**, loaded from the
installed npm dependency. This is not a separate JS layout engine or a wrapper
around system Python. Byte-parity tests cover the shipped SVG examples.

The runtime adds about 14 MB and cold startup overhead. First render measured
about 1.8 seconds on the development machine; your timing will vary. The runtime
is reused. Rendering is CPU-bound and serialized in-process; use your own worker
thread for server workloads.

Installation needs registry access or a populated cache. Once installed, rendering
needs no network, subprocesses, model calls or telemetry. This package targets
Node.js; a browser editing SDK is not provided. Source limit:256 KiB; profile:16 KiB.
Diagnostics cannot guarantee perfect composition for every graph.

[DSL guide](https://github.com/1aifanatic/nodelace/blob/main/docs/DSL.md) ·
[Agent guide](https://github.com/1aifanatic/nodelace/blob/main/docs/AGENT-REFERENCE.md)

## Development

From `npm/`: `npm ci`, `npm test`, `npm pack`. Tests use repository examples.
`npm run sync` copies allowlisted Python sources/assets and license notices;
version checks prevent mismatched releases. There are no install-time scripts.
MIT; fonts retain their OFL notices. Pyodide retains its own license.
