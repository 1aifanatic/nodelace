import { readFile, readdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { loadPyodide } from 'pyodide';

const require = createRequire(import.meta.url);
const packageRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const MAX_SOURCE_BYTES = 256 * 1024;
const SIZES = new Set(['fit', 'doc-inline', 'doc-wide', 'slide-16x9', 'social-square', 'print-a4']);
const OPTION_KEYS = new Set(['format', 'theme', 'size', 'idPrefix', 'embedFonts', 'profile']);
let runtimePromise;
let queue = Promise.resolve();

export class NodelaceError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'NodelaceError';
    this.code = details.code ?? 'INVALID_INPUT';
    this.line = details.line ?? null;
    this.column = details.column ?? null;
  }
}

// This code is constant. DSL/profile data cross the bridge as JSON, never as Python code.
const BRIDGE = `
import dataclasses, json, sys, warnings
sys.path.insert(0, "/nodelace-package")
from nodelace import parse_diagram, render, check_diagram, load_theme
from nodelace.errors import NodelaceError
from nodelace.theme import THEMES

def _nodelace_request(payload):
    request = json.loads(payload)
    try:
        options = request.get("options", {})
        theme = THEMES[options.get("theme", "light")]
        if "profile" in options:
            with open("/nodelace-profile.toml", "w", encoding="utf-8") as stream:
                stream.write(options["profile"])
            try:
                theme = load_theme("/nodelace-profile.toml")
            finally:
                import os
                os.unlink("/nodelace-profile.toml")
        diagram = parse_diagram(request["source"])
        if request["operation"] == "parse":
            value = dataclasses.asdict(diagram)
        elif request["operation"] == "check":
            value = [dataclasses.asdict(issue) for issue in check_diagram(
                diagram, theme=theme, size=options.get("size", "fit"))]
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                value = render(diagram, format=options.get("format", "svg"), theme=theme,
                    size=options.get("size", "fit"), id_prefix=options.get("idPrefix"),
                    embed_fonts=options.get("embedFonts", True))
        return json.dumps({"value": value})
    except (NodelaceError, ValueError, TypeError) as error:
        return json.dumps({"error": {"message": str(error), "code": type(error).__name__,
            "line": getattr(error, "line", None), "column": getattr(error, "column", None)}})
`;

async function initialize() {
  // An absolute local indexURL loads WASM and stdlib from the npm dependency, never a CDN.
  const pyodide = await loadPyodide({ indexURL: dirname(require.resolve('pyodide')), packages: [] });
  async function copy(source, target) {
    pyodide.FS.mkdirTree(target);
    for (const entry of await readdir(source, { withFileTypes: true })) {
      if (entry.isDirectory()) await copy(join(source, entry.name), `${target}/${entry.name}`);
      else if (entry.isFile()) pyodide.FS.writeFile(`${target}/${entry.name}`, await readFile(join(source, entry.name)));
    }
  }
  await copy(join(packageRoot, 'python/nodelace'), '/nodelace-package/nodelace');
  pyodide.runPython(BRIDGE);
  return pyodide.globals.get('_nodelace_request');
}

function validate(source, options) {
  if (typeof source !== 'string') throw new NodelaceError('source must be DSL text');
  if (Buffer.byteLength(source, 'utf8') > MAX_SOURCE_BYTES) throw new NodelaceError('source exceeds 256 KiB');
  if (!source.isWellFormed()) throw new NodelaceError('source contains an unpaired Unicode surrogate');
  if (options === null || typeof options !== 'object' || Array.isArray(options)) throw new NodelaceError('options must be an object');
  for (const key of Object.keys(options)) if (!OPTION_KEYS.has(key)) throw new NodelaceError(`unknown option: ${key}`);
  if (options.format !== undefined && !['svg', 'html'].includes(options.format)) throw new NodelaceError('format must be svg or html');
  if (options.theme !== undefined && !['light', 'dark'].includes(options.theme)) throw new NodelaceError('theme must be light or dark');
  if (options.size !== undefined && !SIZES.has(options.size)) throw new NodelaceError('unknown destination size');
  if (options.embedFonts !== undefined && typeof options.embedFonts !== 'boolean') throw new NodelaceError('embedFonts must be boolean');
  if (options.idPrefix !== undefined && (typeof options.idPrefix !== 'string' || options.idPrefix.length > 200 || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(options.idPrefix))) throw new NodelaceError('idPrefix must be up to 200 characters, start with a letter and contain only letters, digits, - or _');
  if (options.profile !== undefined) {
    if (typeof options.profile !== 'string' || Buffer.byteLength(options.profile, 'utf8') > 16384 || !options.profile.isWellFormed()) throw new NodelaceError('profile must be valid TOML text up to 16 KiB');
    if (options.theme !== undefined) throw new NodelaceError('choose theme or profile, not both');
  }
}

function request(operation, source, options = {}) {
  let payload;
  try {
    if (options === null || typeof options !== 'object' ||
        ![Object.prototype, null].includes(Object.getPrototypeOf(options))) {
      throw new NodelaceError('options must be a plain object');
    }
    // Copy own values once. Inherited toJSON and changing getters cannot bypass validation.
    const snapshot = Object.create(null);
    for (const key of Object.keys(options)) snapshot[key] = options[key];
    validate(source, snapshot);
    payload = JSON.stringify({ operation, source, options: snapshot });
  } catch (error) { return Promise.reject(error); }
  const result = queue.then(async () => {
    runtimePromise ??= initialize();
    const invoke = await runtimePromise;
    const response = JSON.parse(invoke(payload));
    if (response.error) throw new NodelaceError(response.error.message, response.error);
    return response.value;
  });
  queue = result.catch(() => {});
  return result;
}

/** Render DSL to an SVG or a self-contained HTML string. Runtime is reused after first call. */
export function render(source, options = {}) { return request('render', source, options); }
/** Return local layout/publication diagnostics. Syntax errors reject the promise. */
export function check(source, options = {}) { return request('check', source, options); }
/** Parse DSL into a serializable domain model. */
export function parse(source, options = {}) { return request('parse', source, options); }
