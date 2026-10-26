import { FURNITURE } from './furnitureData';
import { computeLayout, TILE } from './layout';
import { makeOffice } from './testFixtures';
import { expect, it } from 'vitest';
import { labelPriority, labelHeight, visibleLabels } from './overlays';
import { loungeFurniture, occludesActor } from './renderer';

it('선택과 호버와 주의 상태와 리더에게만 이름표를 표시한다', () => {
  expect(labelPriority('typing', false, false, false)).toBe(0);
  expect(labelPriority('typing', false, false, true)).toBe(1);
  expect(labelPriority('typing', false, true, false)).toBe(2);
  for (const status of ['permission', 'waiting', 'stalled', 'error']) expect(labelPriority(status, false, false, false)).toBe(3);
  expect(labelPriority('error', true, false, false)).toBe(4);
  expect(visibleLabels([{ id: 'lead', x: 0, y: 0, w: 70, h: 20, priority: 1 }, { id: 'selected', x: 1, y: 1, w: 70, h: 20, priority: 4 }]).map(b => b.id)).toEqual(['selected']);
});

it('책상 뒤의 사람을 가리고 앞의 사람과 겹치지 않는 사람을 보인다', () => {
  const desk = { x: 10, y: 20, w: 32, h: 24, depth: 44 };
  expect(occludesActor(desk, { x: 25, y: 40 })).toBe(true);
  expect(occludesActor(desk, { x: 25, y: 58 })).toBe(false);
  expect(occludesActor(desk, { x: 90, y: 40 })).toBe(false);
  const chair = { x: 20, y: 45, w: 12, h: 16, depth: 61 };
  expect(occludesActor(chair, { x: 25, y: 58 })).toBe(true);
});

it('휴게 가구와 아래 벽 사이에 한 타일의 통로를 확보한다', () => {
  const scene = computeLayout(makeOffice(8, 2));
  for (const room of scene.rooms) {
    for (const item of loungeFurniture(room)) {
      expect(item.y + FURNITURE[item.id].height).toBeLessThanOrEqual((room.y + room.h) * TILE - 5 - TILE);
      expect(item.x).toBeGreaterThan(room.x * TILE + 7);
      expect(item.x + FURNITURE[item.id].width).toBeLessThanOrEqual((room.x + room.w - 1) * TILE);
    }
  }
});

it('두 배 미만에서는 선택한 사람의 이름표만 표시한다', () => {
  expect(labelPriority('permission', false, true, true, 1)).toBe(0);
  expect(labelPriority('typing', true, false, false, 1)).toBe(4);
});

it('선택 막대까지 이름표 충돌 영역에 포함한다', () => {
  const boxes = [
    { id: 'selected', x: 10, y: 10, w: 90, h: labelHeight(true), priority: 4 },
    { id: 'neighbor', x: 20, y: 32, w: 80, h: labelHeight(false), priority: 3 },
  ];
  expect(visibleLabels(boxes).map(box => box.id)).toEqual(['selected']);
  expect(labelHeight(true)).toBe(26);
});
