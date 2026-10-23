/**
 * FSD 계층 규칙을 시험으로 지킨다.
 * 1. 아래 계층은 위 계층을 가져오지 않는다(app > pages > widgets > features > entities > shared).
 * 2. 같은 계층의 다른 조각을 가져오지 않는다(shared·app 은 예외).
 * 3. 다른 조각은 그 조각의 index.ts 로만 가져온다(깊은 경로 금지).
 * 4. index.ts 는 `export *` 를 쓰지 않는다.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../src');
const LAYERS = ['shared', 'entities', 'features', 'widgets', 'pages', 'app'] as const;
type Layer = (typeof LAYERS)[number];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return walk(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

function locate(file: string): { layer: Layer; slice: string; rest: string[] } {
  const parts = relative(SRC, file).split(sep);
  const layer = parts[0] as Layer;
  return { layer, slice: (parts[1] ?? '').replace(/\.tsx?$/, ''), rest: parts.slice(2) };
}

const IMPORT = /^\s*(?:import|export)\s[^'"]*?from\s+['"](\.[^'"]+)['"]/gm;

function violations(): string[] {
  const found: string[] = [];
  for (const file of walk(SRC)) {
    if (/\.test\.tsx?$/.test(file)) continue;
    const from = locate(file);
    const text = readFileSync(file, 'utf8');
    if (file.endsWith(`${sep}index.ts`) && /export\s+\*/.test(text)) found.push(`${relative(SRC, file)}: export * 금지`);
    for (const m of text.matchAll(IMPORT)) {
      const target = resolve(dirname(file), m[1]);
      if (!target.startsWith(SRC)) continue;
      const to = locate(target);
      const where = `${relative(SRC, file)} → ${m[1]}`;
      if (LAYERS.indexOf(to.layer) > LAYERS.indexOf(from.layer)) found.push(`${where}: 위 계층(${to.layer})을 가져옴`);
      const sameSlice = to.layer === from.layer && to.slice === from.slice;
      if (!sameSlice && to.layer === from.layer && from.layer !== 'shared' && from.layer !== 'app') {
        found.push(`${where}: 같은 계층의 다른 조각`);
      }
      const viaIndex = to.rest.length === 0 || (to.rest.length === 1 && /^index(\.tsx?)?$/.test(to.rest[0]));
      if (!sameSlice && to.layer !== 'app' && !viaIndex) found.push(`${where}: 깊은 경로 — index 로 가져와야 함`);
    }
  }
  return found;
}

describe('FSD 계층 규칙', () => {
  it('어긋난 가져오기가 없다', () => {
    expect(violations()).toEqual([]);
  });
});
