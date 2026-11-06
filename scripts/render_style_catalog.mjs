// Generate examples for every built-in diagram family, theme and canvas size.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { render, check } from '../npm/src/index.js';

const { chromium } = createRequire(import.meta.url)('playwright');
const folder = fileURLToPath(new URL('../examples/style-catalog/', import.meta.url));
const catalog = [];
for (const kind of ['architecture', 'flow', 'sequence']) {
  for (const theme of ['light', 'dark', 'blueprint']) {
    catalog.push({ id: `${kind}-${theme}`, title: `${kind} / ${theme}`,
      source: `sources/${kind}.diagram`, size: 'fit',
      ...(kind === 'sequence' ? { expectedWarnings: ['fragments'] } : {}),
      ...(theme === 'blueprint' ? { profile: 'blueprint.toml' } : { theme }) });
  }
}
for (const size of ['fit', 'doc-inline', 'doc-wide', 'slide-16x9', 'social-square', 'print-a4']) {
  catalog.push({ id: `canvas-${size}`, title: `Canvas / ${size}`,
    source: 'sources/canvas.diagram', theme: 'light', size });
}
await mkdir(join(folder, 'rendered'), { recursive: true });
await writeFile(join(folder, 'catalog.json'), JSON.stringify(catalog, null, 2) + '\n');
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2 });
await page.route(/^https?:/, route => route.abort());
const results = [];
try {
  for (const item of catalog) {
    const source = await readFile(join(folder, item.source), 'utf8');
    const options = { size: item.size, ...(item.profile
      ? { profile: await readFile(join(folder, item.profile), 'utf8') }
      : { theme: item.theme }) };
    const diagnostics = await check(source, options);
    const warnings = diagnostics.filter(d => d.severity === 'warning').map(d => d.code).sort();
    if (diagnostics.some(d => d.severity === 'error') ||
        JSON.stringify(warnings) !== JSON.stringify(item.expectedWarnings || [])) {
      throw new Error(`${item.id}: ${JSON.stringify(diagnostics)}`);
    }
    const svg = await render(source, options);
    const html = await render(source, { ...options, format: 'html' });
    for (const [format, content] of [['svg', svg], ['html', html]]) {
      await writeFile(join(folder, 'rendered', `${item.id}.${format}`), content);
    }
    const width = Number(svg.match(/<svg[^>]*\bwidth="(\d+)"/)[1]);
    const height = Number(svg.match(/<svg[^>]*\bheight="(\d+)"/)[1]);
    await page.setViewportSize({ width: width + 48, height: height + 48 });
    await page.setContent(`<html><body style="margin:0">${svg.replace(/^<\?xml[^>]+>\s*/, '')}</body></html>`);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('svg').screenshot({ path: join(folder, 'rendered', `${item.id}.png`) });
    results.push({ id: item.id, width, height, diagnostics });
    console.log(`${item.id}: SVG, HTML, PNG`);
  }
} finally { await browser.close(); }
const cards = catalog.map(item => `<article><h2>${item.title}</h2><a href="rendered/${item.id}.html"><img loading="lazy" src="rendered/${item.id}.png" alt="${item.title}"></a><p><a href="${item.source}">Source</a> · <a href="rendered/${item.id}.svg">SVG</a> · <a href="rendered/${item.id}.html">HTML</a> · <a href="rendered/${item.id}.png">PNG</a></p></article>`).join('\n');
await writeFile(join(folder, 'index.html'), `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nodelace style catalog</title><style>body{font:16px/1.5 system-ui;margin:32px;background:#f5f5f5;color:#2d3142}main{max-width:1200px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:24px}article{padding:16px;background:white;border:1px solid #bfc0c0;border-radius:8px}img{width:100%;height:300px;object-fit:contain}a{color:#2456a6}h1{font-family:Georgia,serif}</style><main><h1>Every supported diagram style</h1><p>Three diagram families, two built-in themes, a custom color profile, and all six canvas presets. Click a preview to open standalone HTML.</p><section class="grid">${cards}</section></main></html>\n`);
await writeFile(join(folder, 'verification.json'), JSON.stringify({ version: '0.3.0', results }, null, 2) + '\n');
