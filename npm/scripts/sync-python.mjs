// Only audited source/assets enter the npm distribution; no build cache or host paths.
import { cp, mkdir, readFile, readdir, rm } from 'node:fs/promises';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const target = join(root, 'npm/python/nodelace');
const allowed = new Set(['.py', '.json', '.woff2', '.txt']);
if (target !== join(root, 'npm', 'python', 'nodelace')) throw new Error('Unsafe build path');
await rm(target, { recursive: true, force: true });
async function copy(source, destination) {
  await mkdir(destination, { recursive: true });
  for (const entry of await readdir(source, { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.name.startsWith('__')) {
      await copy(join(source, entry.name), join(destination, entry.name));
    } else if (entry.isFile() && (allowed.has(extname(entry.name)) || entry.name === 'py.typed')) {
      await cp(join(source, entry.name), join(destination, entry.name));
    }
  }
}
await copy(join(root, 'src/nodelace'), target);
for (const name of ['LICENSE', 'THIRD_PARTY_NOTICES.md']) {
  await cp(join(root, name), join(root, 'npm', name));
}
const manifest = JSON.parse(await readFile(join(root, 'npm/package.json'), 'utf8'));
const source = await readFile(join(target, '__init__.py'), 'utf8');
const version = source.match(/__version__ = "([^"]+)"/)[1];
if (version !== manifest.version) throw new Error(`Version mismatch: npm ${manifest.version}, Python ${version}`);
console.log(`Bundled Nodelace ${version} Python source, fonts, metrics and licenses.`);
