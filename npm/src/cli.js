#!/usr/bin/env node
import { readFile, open, lstat, link, rename, unlink, realpath } from 'node:fs/promises';
import { constants } from 'node:fs';
import { basename, dirname, extname, join, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { parseArgs } from 'node:util';
import { render, check, parse } from './index.js';

const help = `Nodelace — local diagrams, Node.js only

nodelace render INPUT [-o OUTPUT|-] [--format svg|html] [--theme light|dark]
nodelace check INPUT [--layout] [--strict] [--json]
nodelace export INPUT -o OUTPUT.png [--scale 1..4]  (optional Playwright)
nodelace init [architecture|flow|sequence] [-o FILE]

INPUT '-' reads UTF-8 from stdin. Piped renders default to stdout.
Options: --profile colors.toml, --size fit|doc-inline|doc-wide|slide-16x9|
         social-square|print-a4, --id-prefix ID, --system-fonts, --force
Explicit existing outputs require --force. No model calls or remote rendering.
`;
const templates = {
  architecture: 'architecture "My service"\nnode API role=backend\nnode Database role=store\nBrowser -> API: HTTPS\nAPI -> Database: query\nhighlight API\n',
  flow: 'flow "Release"\nnode Gate shape=decision label="Checks pass?"\nnode Done shape=terminal\nBuild -> Gate\nGate => Done: yes\nGate -> Build: retry\n',
  sequence: 'sequence "Sign in"\nBrowser -> API: credentials\nactivate API\nalt "valid"\nAPI --> Browser: session\nelse "invalid"\nAPI --> Browser: rejected\nend\ndeactivate API\n',
};
const safe = value => String(value).replace(/[\p{Cc}\p{Cf}]/gu, c => `\\u${c.codePointAt(0).toString(16).padStart(4, '0')}`);
async function readInput(path, max = 262144) {
  if (path !== '-') {
    const handle = await open(path, constants.O_RDONLY | (constants.O_NONBLOCK || 0));
    try {
      const info = await handle.stat();
      if (!info.isFile() || info.size > max) throw new Error(`input must be a regular file of at most ${max} bytes`);
      const buffer = Buffer.alloc(max + 1);
      let length = 0;
      while (length < buffer.length) {
        const { bytesRead } = await handle.read(buffer, length, buffer.length - length, null);
        if (!bytesRead) break;
        length += bytesRead;
      }
      if (length > max) throw new Error(`input exceeds ${max} bytes`);
      return new TextDecoder('utf-8', { fatal: true }).decode(buffer.subarray(0, length));
    } finally { await handle.close(); }
  }
  const chunks = []; let length = 0;
  for await (const chunk of process.stdin) {
    length += chunk.length;
    if (length > max) throw new Error(`input exceeds ${max} bytes`);
    chunks.push(chunk);
  }
  return new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks));
}
async function writeOutput(path, data, force) {
  const target = resolve(path);
  try {
    const info = await lstat(target);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error('output must be a regular file');
    if (!force) throw new Error('output already exists; pass --force');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const temporary = join(dirname(target), `.${basename(target)}.${randomUUID()}.tmp`);
  const handle = await open(temporary, 'wx');
  try {
    await handle.writeFile(data, typeof data === 'string' ? 'utf8' : undefined);
    await handle.close();
    if (force) await rename(temporary, target);
    else {
      try { await link(temporary, target); }
      catch (error) {
        if (!['EPERM', 'EACCES', 'ENOTSUP', 'EOPNOTSUPP', 'EXDEV', 'ENOSYS'].includes(error.code)) throw error;
        const exclusive = await open(target, 'wx');
        try { await exclusive.writeFile(data, typeof data === 'string' ? 'utf8' : undefined); }
        finally { await exclusive.close(); }
      }
    }
  } finally {
    await handle.close();
    await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error; });
  }
}
async function png(svg, scale) {
  if (!Number.isInteger(scale) || scale < 1 || scale > 4) throw new Error('--scale must be 1..4');
  let chromium;
  try { ({ chromium } = await import('playwright')); }
  catch { throw new Error('PNG needs npm install playwright and npx playwright install chromium'); }
  const width = Number(svg.match(/<svg[^>]*\bwidth="(\d+)"/)[1]);
  const height = Number(svg.match(/<svg[^>]*\bheight="(\d+)"/)[1]);
  if (width * height * scale * scale > 64000000) throw new Error('PNG exceeds 64 million pixels');
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: scale });
    await page.route(/^https?:/, route => route.abort());
    await page.setContent(`<html><body style="margin:0">${svg.replace(/^<\?xml[^>]+>\s*/, '')}</body></html>`);
    await page.evaluate(() => document.fonts.ready);
    return await page.locator('svg').screenshot({ type: 'png', timeout: 30000 });
  } finally { await browser.close(); }
}

let jsonMode = process.argv.includes('--json') && process.argv[2] === 'check';
let sourceName = '<options>';
try {
  const { values: args, positionals } = parseArgs({ allowPositionals: true, options: {
    output: { type: 'string', short: 'o' }, format: { type: 'string' },
    theme: { type: 'string' }, profile: { type: 'string' }, size: { type: 'string' },
    'id-prefix': { type: 'string' }, 'system-fonts': { type: 'boolean' },
    force: { type: 'boolean' }, layout: { type: 'boolean' }, strict: { type: 'boolean' },
    json: { type: 'boolean' }, scale: { type: 'string' },
    help: { type: 'boolean', short: 'h' }, version: { type: 'boolean', short: 'v' },
  } });
  jsonMode = !!args.json;
  const [command, input] = positionals;
  sourceName = input === '-' ? '<stdin>' : input || '<options>';
  const allowed = {
    render: ['output', 'format', 'theme', 'profile', 'size', 'id-prefix', 'system-fonts', 'force'],
    check: ['theme', 'profile', 'size', 'layout', 'strict', 'json'],
    export: ['output', 'theme', 'profile', 'size', 'scale', 'force'],
    init: ['output', 'force'],
  };
  if (!args.help && !args.version && allowed[command]) {
    for (const key of Object.keys(args)) if (!allowed[command].includes(key)) throw new Error(`--${key} is not supported by ${command}`);
  }
  if (args.version) console.log(`nodelace ${JSON.parse(await readFile(new URL('../package.json', import.meta.url))).version}`);
  else if (args.help || !command) console.log(help);
  else if (command === 'init') {
    if (positionals.length > 2) throw new Error('too many arguments');
    const kind = input || 'architecture';
    if (!Object.hasOwn(templates, kind)) throw new Error('choose architecture, flow or sequence');
    const output = args.output || 'diagram.diagram';
    if (output === '-') process.stdout.write(templates[kind]);
    else { await writeOutput(output, templates[kind], args.force); console.log(safe(output)); }
  } else {
    if (!['render', 'check', 'export'].includes(command) || !input || positionals.length !== 2) throw new Error('expected render, check or export and one INPUT; use --help');
    if (args.theme !== undefined && args.profile !== undefined) throw new Error('choose --theme or --profile');
    const options = {
      ...(args.theme !== undefined ? { theme: args.theme } : {}),
      ...(args.size !== undefined ? { size: args.size } : {}),
      ...(args.profile !== undefined ? { profile: await readInput(args.profile, 16384) } : {}),
      ...(args['id-prefix'] !== undefined ? { idPrefix: args['id-prefix'] } : {}),
      embedFonts: !args['system-fonts'],
    };
    const source = await readInput(input);
    if (command === 'check') {
      const diagram = await parse(source, options);
      const diagnostics = args.layout || args.strict ? await check(source, options) : [];
      const valid = !diagnostics.some(d => d.severity === 'error' || args.strict);
      if (jsonMode) console.log(JSON.stringify({ valid, kind: diagram.kind, nodes: diagram.nodes.length, edges: diagram.edges.length, diagnostics, error: null }));
      else {
        for (const d of diagnostics) console.error(`${d.severity}: ${d.code}: ${safe(d.message)}`);
        if (valid) console.log(`ok: ${safe(input)} (${diagram.kind}, ${diagram.nodes.length} nodes, ${diagram.edges.length} edges)`);
      }
      process.exitCode = valid ? 0 : 2;
    } else {
      const suffix = extname(args.output || '').toLowerCase();
      if (command === 'render' && suffix && !['.svg', '.html'].includes(suffix)) throw new Error('output suffix must be .svg or .html');
      const format = command === 'export' ? 'svg' : args.format ?? (suffix === '.html' ? 'html' : 'svg');
      if (command === 'render' && ['.svg', '.html'].includes(suffix) && suffix !== `.${format}`) throw new Error('output suffix does not match --format');
      const output = args.output || (input === '-' ? '-' : input.slice(0, input.length - extname(input).length) + `.${format}`);
      if (command === 'export' && (!args.output || extname(output).toLowerCase() !== '.png')) throw new Error('export needs -o OUTPUT.png');
      if (input !== '-' && output !== '-') {
        const sourcePath = await realpath(input);
        const outputPath = await realpath(output).catch(error => {
          if (error.code !== 'ENOENT') throw error;
          return resolve(output);
        });
        if (sourcePath === outputPath) throw new Error('refusing to replace the source file');
      }
      const content = await render(source, { ...options, format });
      const data = command === 'export' ? await png(content, Number(args.scale || 2)) : content;
      if (output === '-') process.stdout.write(data);
      else { await writeOutput(output, data, !!args.force || !args.output); console.log(safe(output)); }
    }
  }
} catch (error) {
  const code = error.code === 'DiagramSyntaxError' ? 'syntax'
    : error.code === 'DiagramValidationError' ? 'validation'
    : /^E[A-Z]+$/.test(error.code || '') ? 'io' : 'options';
  if (jsonMode) console.log(JSON.stringify({ valid: false, kind: null, nodes: 0, edges: 0,
    diagnostics: [], error: { code, message: safe(error.message),
      source: sourceName, line: error.line ?? null, column: error.column ?? null } }));
  else console.error(`error: ${safe(error.message)}`);
  process.exitCode = 2;
}
