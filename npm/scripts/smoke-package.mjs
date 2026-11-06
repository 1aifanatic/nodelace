// Install the actual tarball in isolation, with install scripts disabled.
import { mkdtempSync, writeFileSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';

const version = JSON.parse(readFileSync(new URL('../package.json', import.meta.url))).version;
const tarball = resolve(`nodelace-${version}.tgz`);
const dir = mkdtempSync(join(tmpdir(), 'nodelace-package-'));
function run(args) {
  const result = spawnSync(process.execPath, args, {
    cwd: dir, encoding: 'utf8', timeout: 120000, maxBuffer: 2 * 1024 * 1024,
    // npm 11 can forward this user setting as an unsupported install flag.
    // The smoke install still explicitly disables every lifecycle script.
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      !/^npm_config_allow[_-]?scripts$/i.test(key))),
  });
  assert.equal(result.status, 0, result.stderr || result.error?.message);
  return result.stdout;
}
try {
  writeFileSync(join(dir, 'package.json'), '{"private":true,"type":"module"}');
  // npm supplies its own JS entrypoint, avoiding shell invocation on Windows.
  const npmCli = process.env.npm_execpath;
  if (!npmCli) throw new Error('Run through npm run smoke (needs npm_execpath)');
  run([npmCli, 'install', tarball, '--ignore-scripts', '--no-audit', '--no-fund']);
  writeFileSync(join(dir, 'smoke.mjs'), `
    import assert from 'node:assert/strict';
    import { render, check } from 'nodelace';
    globalThis.fetch = () => { throw new Error('Network forbidden'); };
    const svg = await render('Browser -> API', { theme: 'dark' });
    assert.ok(svg.startsWith('<?xml'));
    assert.ok(svg.includes('@font-face'));
    assert.deepEqual(await check('Browser -> API'), []);
    console.log('Packed npm package: offline rendering, fonts and diagnostics PASS');
  `);
  console.log(run(['smoke.mjs']).trim());
  assert.match(run(['node_modules/nodelace/src/cli.js', '--version']), new RegExp(version));
} finally { rmSync(dir, { recursive: true, force: true }); }
