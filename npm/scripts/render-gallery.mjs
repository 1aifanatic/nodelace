// Rebuild the ten-example gallery using the public Node API and local Chromium.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { render, check } from '../src/index.js';

const { chromium } = createRequire(import.meta.url)('playwright');

const folder = fileURLToPath(new URL('../../examples/showcase/', import.meta.url));
const catalog = JSON.parse(await readFile(join(folder, 'catalog.json'), 'utf8'));
if (catalog.length !== 10) throw new Error('Expected ten curated examples');
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
await mkdir(join(folder, 'rendered'), { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ deviceScaleFactor: 2 });
const page = await context.newPage();
await page.route(/^https?:/, route => route.abort());
const evidence = [];
try {
  for (const item of catalog) {
    const source = await readFile(join(folder, 'sources', `${item.id}.diagram`), 'utf8');
    for (const theme of ['light', 'dark']) {
      const diagnostics = await check(source, { theme });
      if (diagnostics.length) throw new Error(`${item.id}/${theme}: ${JSON.stringify(diagnostics)}`);
      const stem = `${item.id}-${theme}`;
      const html = await render(source, { format: 'html', theme });
      const svg = await render(source, { theme });
      await writeFile(join(folder, 'rendered', `${stem}.html`), html);
      await writeFile(join(folder, 'rendered', `${stem}.svg`), svg);
      const width = Number(svg.match(/<svg[^>]*\bwidth="(\d+)"/)[1]);
      const height = Number(svg.match(/<svg[^>]*\bheight="(\d+)"/)[1]);
      await page.setViewportSize({ width: width + 48, height: height + 48 });
      await page.setContent(html);
      await page.evaluate(() => document.fonts.ready);
      const overflow = await page.evaluate(() => [...document.querySelectorAll('.node-label')].flatMap(text => {
        const shape = text.parentElement.querySelector('.node-box');
        if (!shape) return [];
        const a = text.getBBox(), b = shape.getBBox();
        return a.x < b.x - 1 || a.x + a.width > b.x + b.width + 1 || a.y < b.y - 1 || a.y + a.height > b.y + b.height + 1 ? [text.textContent] : [];
      }));
      if (overflow.length) throw new Error(`${stem} text overflow: ${overflow}`);
      await page.locator('svg').screenshot({ path: join(folder, 'rendered', `${stem}.png`) });
      evidence.push({ id: item.id, theme, width, height, pngWidth: width * 2, pngHeight: height * 2, diagnostics, textOverflow: overflow });
      console.log(`${stem}: HTML, SVG, PNG (${width * 2} × ${height * 2})`);
    }
  }
  const cards = catalog.map((item, index) => `<article><header><span>${String(index + 1).padStart(2, '0')} / ${escape(item.kind)}</span><h2>${escape(item.title)}</h2><p>${escape(item.description)}</p></header><a class="preview light" href="rendered/${item.id}-light.html"><img src="rendered/${item.id}-light.png" alt="${escape(item.title)} in light theme"></a><a class="preview dark" href="rendered/${item.id}-dark.html"><img src="rendered/${item.id}-dark.png" alt="${escape(item.title)} in dark theme"></a><footer><div>Light <a href="rendered/${item.id}-light.html">HTML</a> <a href="rendered/${item.id}-light.png">PNG</a></div><div>Dark <a href="rendered/${item.id}-dark.html">HTML</a> <a href="rendered/${item.id}-dark.png">PNG</a></div><a href="sources/${item.id}.diagram">Editable source</a></footer></article>`).join('\n');
  const gallery = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nodelace — ten local diagrams</title><style>
  *{box-sizing:border-box}body{margin:0;background:#e9ebed;color:#2d3142;font:15px/1.5 system-ui,sans-serif}main{max-width:1480px;margin:auto;padding:40px}h1{font:52px/1.1 Georgia,serif;margin:12px 0}h2{font-size:21px;margin:6px 0}p{margin:4px 0 14px;color:#4f5d75}.intro{max-width:850px;margin-bottom:28px}.intro>span,article header>span{font:12px monospace;text-transform:uppercase;letter-spacing:.08em}nav{display:flex;gap:8px;margin:20px 0}button{background:#fff;border:1px solid #4f5d75;border-radius:5px;color:#2d3142;padding:10px 18px;font:inherit;cursor:pointer}button[aria-pressed=true]{background:#2d3142;color:#fff}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}article{min-width:0;background:white;border:1px solid #bfc0c0;border-radius:9px;overflow:hidden}article header{padding:20px 22px 0;min-height:130px}.preview{display:flex;align-items:center;justify-content:center;height:310px;background:#f5f5f5}.preview img{width:100%;height:100%;object-fit:contain}.dark{display:none;background:#2d3142}body[data-theme=dark] .dark{display:flex}body[data-theme=dark] .light{display:none}footer{padding:16px 22px;display:flex;gap:18px;flex-wrap:wrap;align-items:center}a{color:#2456a6}footer div a{margin-left:8px}footer>a{margin-left:auto}button:focus-visible,a:focus-visible{outline:3px solid #bf4520;outline-offset:3px}@media(max-width:720px){main{padding:20px}.grid{grid-template-columns:1fr}h1{font-size:38px}}@media print{nav{display:none}article{break-inside:avoid}.preview{height:230px}}
  </style></head><body data-theme="light"><main><div class="intro"><span>Nodelace 0.3.0 / generated locally with Node.js</span><h1>Ten diagrams. Two styles.</h1><p>Architecture, workflows and conversations. Each example includes standalone HTML, a high-resolution PNG and editable source. Click a preview for its readable full-size diagram.</p><nav aria-label="Preview theme"><button type="button" data-theme="light" aria-pressed="true">Light editorial</button><button type="button" data-theme="dark" aria-pressed="false">Dark editorial</button></nav></div><section class="grid" aria-label="Sample diagrams">${cards}</section></main><script>document.querySelectorAll('button[data-theme]').forEach(button=>button.addEventListener('click',()=>{document.body.dataset.theme=button.dataset.theme;document.querySelectorAll('button[data-theme]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)))}))</script></body></html>`;
  await writeFile(join(folder, 'index.html'), gallery);
  await writeFile(join(folder, 'verification.json'), JSON.stringify({ generator: 'nodelace npm 0.3.0 / local Pyodide + Chromium', samples: evidence }, null, 2));
  const overview = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await overview.goto(new URL('../../examples/showcase/index.html', import.meta.url).href);
  await overview.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth > 0));
  await overview.screenshot({ path: join(folder, 'overview-light.png'), fullPage: true });
  await overview.getByRole('button', { name: 'Dark editorial' }).click();
  await overview.screenshot({ path: join(folder, 'overview-dark.png'), fullPage: true });
  await overview.setViewportSize({ width: 390, height: 844 });
  if (!await overview.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error('Mobile gallery overflow');
} finally { await browser.close(); }
