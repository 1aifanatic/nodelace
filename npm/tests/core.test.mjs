import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, readdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { syncBuiltinESMExports } from 'node:module';
import childProcess from 'node:child_process';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '../..');
let api;
const digest = value => createHash('sha256').update(value).digest('hex');

test('first render loads local WASM and assets without fetch or child processes', async () => {
  const savedFetch = globalThis.fetch;
  const methods = ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork'];
  const saved = Object.fromEntries(methods.map(name => [name, childProcess[name]]));
  const blocked = () => { throw new Error('Network or process use during local rendering'); };
  globalThis.fetch = blocked;
  for (const name of methods) childProcess[name] = blocked;
  syncBuiltinESMExports();
  try {
    api = await import('../src/index.js');
    const svg = await api.render('A -> B');
    assert.match(svg, /^<\?xml/);
    assert.match(svg, /@font-face/);
    assert.match(svg, /data:font\/woff2;base64/);
  } finally {
    globalThis.fetch = savedFetch;
    for (const name of methods) childProcess[name] = saved[name];
    syncBuiltinESMExports();
  }
});

test('all shipped SVG fixtures are byte-identical to the Python renderer', async () => {
  api ??= await import('../src/index.js');
  for (const name of (await readdir(join(root, 'examples'))).filter(n => n.endsWith('.diagram'))) {
    const source = await readFile(join(root, 'examples', name), 'utf8');
    const expected = await readFile(join(root, 'examples/rendered', name.replace('.diagram', '.svg')), 'utf8');
    assert.equal(digest(await api.render(source)), digest(expected), name);
  }
  for (const name of (await readdir(join(root, 'examples/styles'))).filter(n => n.endsWith('.diagram'))) {
    const source = await readFile(join(root, 'examples/styles', name), 'utf8');
    for (const theme of ['light', 'dark']) {
      const expected = await readFile(join(root, 'examples/styles', name.replace('.diagram', `-${theme}.svg`)), 'utf8');
      assert.equal(digest(await api.render(source, { theme })), digest(expected), `${name} ${theme}`);
      assert.deepEqual(await api.check(source, { theme }), []);
    }
  }
});

test('parse and diagnostics are structured, errors do not poison later requests', async () => {
  const diagram = await api.parse('sequence\ncall A -> B: request\nB --> A: response');
  assert.equal(diagram.kind, 'sequence');
  assert.deepEqual(diagram.edges.map(e => e.kind), ['call', 'return']);
  await assert.rejects(api.parse('node A role=garbage'), error => error instanceof api.NodelaceError && error.code === 'DiagramValidationError');
  const diagnostics = await api.check('');
  assert.ok(diagnostics.some(d => d.code === 'empty' && d.severity === 'warning'));
  assert.deepEqual(await api.check('A -> B'), []);
  await assert.rejects(api.parse('A -> B', { theme: 'invalid' }), /theme must/);
  await assert.rejects(api.parse('A -> B', { profile: '[theme]\nbase="invalid"' }), /theme base/);
  await assert.rejects(api.parse('A -> B', { profile: '[theme]\naccent="bad"' }), /hexadecimal/);
  assert.equal((await api.parse('A -> B', { theme: 'dark', size: 'doc-wide' })).nodes.length, 2);
});

test('concurrent calls stay independent and deterministic', async () => {
  const sources = Array.from({ length: 8 }, (_, i) => `flow "Request ${i}"\nA -> B`);
  const results = await Promise.all(sources.map((source, i) => api.render(source, { theme: i % 2 ? 'dark' : 'light', idPrefix: `instance-${i}` })));
  for (let i = 0; i < results.length; i++) {
    assert.ok(results[i].includes(`id="instance-${i}"`));
    assert.equal(results[i], await api.render(sources[i], { theme: i % 2 ? 'dark' : 'light', idPrefix: `instance-${i}` }));
  }
});

test('profiles, sizes and HTML preserve local output behavior', async () => {
  const svg = await api.render('A -> B', { profile: '[theme]\nbase="dark"\naccent="#ff8844"', size: 'social-square', embedFonts: false });
  assert.ok(svg.includes('width="1080"'));
  assert.ok(svg.includes('#ff8844'));
  assert.ok(!svg.includes('@font-face'));
  const html = await api.render('A -> B', { format: 'html' });
  assert.ok(html.includes('Content-Security-Policy'));
  assert.ok(html.includes('overflow-x:auto'));
  await assert.rejects(api.render('A -> B', { profile: '[theme]\nbase="invalid"' }), /theme base/);
  await assert.rejects(api.render('A -> B', { profile: '[theme]\naccent="url(https:\/\/evil)"' }), /hexadecimal/);
});

test('inputs and options are bounded and validated before execution', async () => {
  await assert.rejects(api.render('x'.repeat(262145)), /256 KiB/);
  await assert.rejects(api.render('\uD800'), /surrogate/);
  await assert.rejects(api.render(null), /DSL text/);
  await assert.rejects(api.render('A -> B', { idPrefix: 'x'.repeat(201) }), /200 characters/);
  for (const options of [null, [], { unknown: 1 }, { format: 'png' }, { theme: 'bad' }, { size: 'bad' }, { idPrefix: 'x" onload=' }, { embedFonts: 'yes' }, { profile: 'x'.repeat(16385) }, { profile: '[theme]', theme: 'light' }]) {
    await assert.rejects(api.render('A -> B', options), api.NodelaceError);
  }
  const options = { theme: 'dark' };
  const pending = api.render('A -> B', options);
  options.theme = 'light';
  assert.equal(await pending, await api.render('A -> B', { theme: 'dark' }));
});

test('option getters are read once and inherited serialization cannot bypass validation', async () => {
  let reads = 0;
  const options = { get theme() { reads++; return reads === 1 ? 'dark' : 'invalid'; } };
  assert.equal(await api.render('A -> B', options), await api.render('A -> B', { theme: 'dark' }));
  assert.equal(reads, 1);
  const inherited = Object.create({ toJSON() { return { theme: 'invalid' }; } });
  await assert.rejects(api.render('A -> B', inherited), /plain object/);
  const clean = Object.create(null);
  clean.theme = 'dark';
  assert.equal(await api.render('A -> B', clean), await api.render('A -> B', { theme: 'dark' }));
});
