export type ThemeName = 'light' | 'dark';
export type DestinationSize = 'fit' | 'doc-inline' | 'doc-wide' | 'slide-16x9' | 'social-square' | 'print-a4';
export interface RenderOptions {
  format?: 'svg' | 'html';
  theme?: ThemeName;
  size?: DestinationSize;
  idPrefix?: string;
  embedFonts?: boolean;
  /** TOML content, not a path. Mutually exclusive with theme. */
  profile?: string;
}
export interface Diagnostic {
  code: string;
  message: string;
  severity: 'error' | 'warning';
}
export interface Node {
  id: string;
  label: string;
  role: 'default' | 'backend' | 'store' | 'external' | 'input' | 'optional';
  shape: 'box' | 'decision' | 'terminal' | 'merge';
  tag: string | null;
  sublabel: string | null;
}
export interface Edge {
  source: string;
  target: string;
  label: string | null;
  kind: 'normal' | 'call' | 'return' | 'async' | 'primary';
}
export interface Diagram {
  kind: 'architecture' | 'flow' | 'sequence';
  title: string | null;
  nodes: Node[];
  edges: Edge[];
  groups: { name: string; members: string[] }[];
  highlights: string[];
  direction: 'left-to-right' | 'top-to-bottom' | null;
  fragments: {
    operator: 'alt' | 'opt' | 'loop'; guard: string; start: number; end: number;
    split: number | null; else_guard: string | null; depth: number;
  }[];
  activations: { participant: string; start: number; end: number }[];
}
export class NodelaceError extends Error {
  code: string;
  line: number | null;
  column: number | null;
  constructor(message: string, details?: { code?: string; line?: number | null; column?: number | null });
}
export function render(source: string, options?: RenderOptions): Promise<string>;
export function check(source: string, options?: Omit<RenderOptions, 'format' | 'idPrefix' | 'embedFonts'>): Promise<Diagnostic[]>;
export function parse(source: string, options?: RenderOptions): Promise<Diagram>;
