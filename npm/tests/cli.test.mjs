import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.js', import.meta.url));
const run = (args, input) => spawnSync(process.execPath, [cli, ...args], {
  input, encoding: 'utf8', timeout: 60000, maxBuffer: 2 * 1024 * 1024,
});
test('help and version work without initializing the renderer', () => {
  assert.match(run(['--version']).stdout, /0\.3\.0/);
  assert.match(run(['--help']).stdout, /Node.js only/);
});
test('stdin to stdout supports SVG and dark HTML without status text', () => {
  const svg = run(['render', '-', '--system-fonts'], 'A -> B');
  assert.equal(svg.status, 0, svg.stderr);
  assert.match(svg.stdout, /^<\?xml/);
  assert.equal(svg.stderr, '');
  const html = run(['render', '-', '--format', 'html', '--theme', 'dark'], 'A -> B');
  assert.equal(html.status, 0, html.stderr);
  assert.match(html.stdout, /^<!doctype html>/);
  assert.match(html.stdout, /#2d3142/);
});
test('JSON checks include structured errors and strict failures', () => {
  const valid = run(['check', '-', '--json', '--strict'], 'A -> B');
  assert.equal(valid.status, 0, valid.stderr);
  assert.equal(JSON.parse(valid.stdout).valid, true);
  const invalid = run(['check', '-', '--json'], 'node A role=wrong');
  assert.equal(invalid.status, 2);
  assert.equal(invalid.stderr, '');
  assert.match(JSON.parse(invalid.stdout).error.message, /role/);
  assert.equal(JSON.parse(invalid.stdout).error.source, '<stdin>');
  const missing = run(['check', '/does-not-exist/nodelace.diagram', '--json']);
  assert.equal(JSON.parse(missing.stdout).error.code, 'io');
  const warning = run(['check', '-', '--json', '--strict'], 'flow "Empty"');
  assert.equal(warning.status, 2);
  assert.equal(JSON.parse(warning.stdout).diagnostics[0].code, 'empty');
});
test('templates, derived output refresh and explicit no-clobber', () => {
  const dir = mkdtempSync(join(tmpdir(), 'nodelace-cli-'));
  try {
    const source = join(dir, 'source with spaces.diagram');
    assert.equal(run(['init', 'sequence', '-o', source]).status, 0);
    assert.equal(run(['render', source]).status, 0);
    assert.equal(run(['render', source]).status, 0);
    const output = join(dir, 'source with spaces.svg');
    writeFileSync(output, 'user content');
    assert.equal(run(['render', source, '-o', output]).status, 2);
    assert.equal(readFileSync(output, 'utf8'), 'user content');
    assert.equal(run(['render', source, '-o', output, '--force']).status, 0);
    assert.match(readFileSync(output, 'utf8'), /^<\?xml/);
    assert.equal(run(['render', source, '-o', source, '--force']).status, 2);
    assert.match(readFileSync(source, 'utf8'), /^sequence/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
test('input limits, malformed UTF-8, unknown options and unsupported formats fail', () => {
  for (const [args, input] of [
    [['render', '-'], 'x'.repeat(262145)],
    [['render', '-'], Buffer.from([0xff])],
    [['render', '-', '--format', 'pdf'], 'A -> B'],
    [['render', '-', '--theme', 'dark', '--profile', 'missing'], 'A -> B'],
    [['render', '-', '--unknown'], 'A -> B'],
    [['render', '-', '-o', 'bad.png'], 'A -> B'],
    [['render', '-', '-o', 'bad.html', '--format', 'svg'], 'A -> B'],
    [['render', '-', '--id-prefix', ''], 'A -> B'],
    [['check', '-', '--theme', 'rainbow'], 'A -> B'],
    [['check', '-', '--size', 'unknown'], 'A -> B'],
  ]) assert.equal(run(args, input).status, 2);
});

test('source aliases cannot overwrite their real source target', t => {
  const dir = mkdtempSync(join(tmpdir(), 'nodelace-alias-'));
  try {
    const source = join(dir, 'original.svg');
    const alias = join(dir, 'alias.diagram');
    writeFileSync(source, 'A -> B');
    try { symlinkSync(source, alias); }
    catch (error) { if (error.code === 'EPERM') return t.skip('symlink permission unavailable'); throw error; }
    const result = run(['render', alias, '-o', source, '--force']);
    assert.equal(result.status, 2, result.stdout);
    assert.equal(readFileSync(source, 'utf8'), 'A -> B');
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
