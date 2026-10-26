import type { Pose } from './behavior';
import { TILE } from './layout';
export type Direction = 'up' | 'down' | 'left' | 'right';
export const DIRECTIONS: Direction[] = ['up', 'down', 'left', 'right'];
export const ANCHOR = { x: TILE / 2, y: TILE * 2 - 1 };
/** 직접 그린 인물. 발 기준점은 (8, 31)이다. */
const BODY = [
  '................', '................', '......oooo......', '.....oLhHHo.....',
  '....ohhHHHHo....', '....ohHHHHho....', '....ohssSsho....', '....osossoso....',
  '....osssSSso....', '.....osSSso.....', '......osso......', '.....oCCcco.....',
  '....oCCCccco....', '...oLCCcccco....', '...oLCCcccdo....', '...oLCCcccdo....',
  '...osCCcccso....', '...osCCcccso....', '....oCCccco.....', '.....odddo......',
  '.....opPpo......', '.....opPpo......', '.....opPpo......', '.....opPpo......',
  '.....opPpo......', '.....opPpo......', '.....opPpo......', '.....opPpo......',
  '.....obobo......', '....obboobbo....', '....ooooooo.....', '................'
];
export function appearanceFor(id: string): number {
  let hash = 0;
  for (const c of id) {
    hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  }
  return hash % 6;
}
export function spritePixels(direction: Direction, pose: Pose, frame: number): string[] {
  const rows = BODY.map(row => row.split(''));
  const set = (x: number, y: number, key: string) => {
    const row = rows[y];
    if (row && x >= 0 && x < TILE) {
      row[x] = key;
    }
  };
  if (direction === 'up') {
    for (let y = 6; y <= 9; y += 1) {
      for (let x = 5; x <= 10; x += 1) {
        set(x, y, x < 8 ? 'H' : 'h');
      }
    }
  }
  else if (direction === 'right' || direction === 'left') {
    for (let y = 6; y <= 9; y += 1) {
      for (let x = 4; x <= 7; x += 1) {
        set(x, y, 'h');
      }
    }
    set(10, 7, 'o');
    set(10, 8, 's');
  }
  if (pose === 'walk') {
    const shifts = [0, 1, 0, -1];
    const shift = shifts[frame % 4] ?? 0;
    for (let y = 23; y <= 30; y += 1) {
      const original = [...(rows[y] ?? [])];
      rows[y] = Array.from({ length: TILE }, () => '.');
      for (let x = 0; x < TILE; x += 1) {
        const key = original[x];
        if (key && key !== '.') {
          set(x + (x < 8 ? shift : -shift), y, key);
        }
      }
    }
    if (frame % 4 === 2) {
      set(3, 17, 's');
      set(12, 16, 's');
    }
  }
  if (pose === 'sit' || pose === 'type' || pose === 'read') {
    for (let y = 22; y <= 30; y += 1) {
      for (let x = 0; x < TILE; x += 1) {
        set(x, y, '.');
      }
    }
    const side = direction === 'right' || direction === 'left';
    if (side) {
      for (let x = 6; x <= 12; x += 1) {
        set(x, 22, 'p');
        set(x, 23, 'P');
      }
      for (let y = 24; y <= 27; y += 1) {
        set(11, y, 'p');
        set(12, y, 'P');
      }
      for (let x = 11; x <= 14; x += 1) {
        set(x, 28, 'b');
      }
    } else {
      for (let y = 22; y <= 23; y += 1) {
        for (let x = 4; x <= 11; x += 1) {
          set(x, y, x < 8 ? 'p' : 'P');
        }
      }
      for (let y = 24; y <= 27; y += 1) {
        for (const x of [4, 5, 10, 11]) {
          set(x, y, x < 8 ? 'p' : 'P');
        }
      }
      for (const x of [3, 4, 5, 6, 9, 10, 11, 12]) {
        set(x, 28, 'b');
      }
    }
    if (pose === 'type') {
      for (const y of [17, 18, 19]) {
        set(3, y, '.');
        set(12, y, '.');
      }
      set(5, 17, 'c');
      set(10, 17, 'c');
      set(4, 16 + frame % 2, 's');
      set(11, 17 - frame % 2, 'S');
      set(4, 18, '.');
      set(11, 18, '.');
    }
    if (pose === 'read' && direction === 'up') {
      // 몸 뒤로 책이 가려지고 가장자리와 손만 보인다.
      const lift = frame % 2;
      for (let y = 13 + lift; y <= 17 + lift; y += 1) {
        set(12, y, 'w');
        set(13, y, y % 2 ? 'w' : 'g');
      }
      set(11, 17 + lift, 's');
      set(12, 18 + lift, 'S');
      set(11, 18 + lift, 'c');
      set(5, 9, lift ? 'h' : 'H');
      set(6, 10, lift ? 'h' : 'o');
    }
    if (pose === 'read' && direction !== 'up') {
      for (let y = 14 + frame % 2; y < 20 + frame % 2; y += 1) {
        for (let x = 6; x <= 10; x += 1) {
          set(x, y, y % 2 ? 'w' : 'g');
        }
      }
    }
  }
  const result = rows.map(row => row.join(''));
  return direction === 'left' ? result.map(row => row.split('').toReversed().join('')) : result;
}
