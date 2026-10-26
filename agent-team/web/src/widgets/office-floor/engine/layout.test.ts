import { describe, expect, it } from 'vitest';
import { computeLayout, roomDimensions, seatFoot, TILE } from './layout';
import { findPath } from './pathfinding';
import { makeOffice } from './testFixtures';
describe('인원 기반 배치', () => {
  it.each([0, 1, 2, 3, 6, 12, 50])('%i명에게 겹치지 않는 자리를 배치한다', n => {
    const scene = computeLayout(makeOffice(n));
    expect(scene.seats).toHaveLength(n);
    for (const [i, a] of scene.seats.entries()) {
      for (const b of scene.seats.slice(i + 1)) {
        expect(Math.abs(a.x - b.x) >= 3 || Math.abs(a.y - b.y) >= 2.5).toBe(true);
      }
    }
    const room = scene.rooms[0];
    expect(room.w).toBe(roomDimensions(n).w);
    expect(room.h).toBe(Math.ceil(roomDimensions(n).h));
    for (const s of scene.seats) {
      expect(s.x + 3).toBeLessThan(room.x + room.w);
      expect(s.y + 2).toBeLessThan(room.y + room.h - 1);
    }
  });
  it('두 명씩 있는 두 방을 작은 방으로 나란히 배치한다', () => {
    const scene = computeLayout(makeOffice(2, 2), 25);
    expect(scene.rooms.map(r => [r.w, r.h])).toEqual([[8, 10], [8, 10]]);
    expect(scene.widthTiles).toBe(15);
    expect(scene.rooms[1].x).toBe(7);
  });
  it('좁은 폭에서는 방만 줄바꿈하고 내부 좌표를 유지한다', () => {
    const office = makeOffice(2, 2);
    const wide = computeLayout(office, 25);
    const narrow = computeLayout(office, 12, wide);
    expect(narrow.rooms[1].y).toBe(9);
    expect(narrow.seats[2].x - narrow.rooms[1].x).toBe(wide.seats[2].x - wide.rooms[1].x);
  });
  it('같은 스냅샷 순서와 상태가 바뀌어도 좌석을 유지한다', () => {
    const office = makeOffice(6);
    const scene = computeLayout(office);
    office.rooms[0].teams[0].members.reverse();
    office.rooms[0].teams[0].lead.status = 'waiting';
    expect(computeLayout(office, 25, scene).seats).toEqual(scene.seats);
  });
  it('열 수가 늘어나도 기존 사람의 좌표를 유지한다', () => {
    const initial = computeLayout(makeOffice(4));
    const grown = computeLayout(makeOffice(6), 25, initial, true);
    for (const s of initial.seats) {
      expect(grown.seats.find(a => a.agentId === s.agentId)).toMatchObject({ x: s.x, y: s.y });
    }
  });
  it('모든 작업 의자에서 휴게석과 출구에 도달한다', () => {
    const scene = computeLayout(makeOffice(50));
    const room = scene.rooms[0];
    for (const seat of scene.seats) {
      const foot = seatFoot(seat);
      const start = { x: Math.floor(foot.x / TILE), y: Math.floor(foot.y / TILE) };
      expect(findPath(scene, start, room.bench).kind).toBe('path');
      expect(findPath(scene, start, room.exit).kind).toBe('path');
    }
  });
  it('완료 하위 에이전트는 처음부터 작업 좌석을 차지하지 않는다', () => {
    const office = makeOffice(2);
    office.rooms[0].teams[0].members[0].status = 'done';
    expect(computeLayout(office).seats).toHaveLength(1);
  });
  it('안정화 중에는 빈 좌석과 방 크기를 유지한다', () => {
    const scene = computeLayout(makeOffice(12));
    const small = computeLayout(makeOffice(2), 25, scene, true);
    expect(small.rooms[0].w).toBe(scene.rooms[0].w);
    expect(small.rooms[0].h).toBe(scene.rooms[0].h);
  });
});

it('바쁜 두 방을 공유 벽과 열린 연결문으로 가로 배치한다', () => {
  const office = makeOffice(8, 2);
  office.rooms[1].teams[0].members = office.rooms[1].teams[0].members.slice(0, 3);
  const scene = computeLayout(office, 23);
  const [left, right] = scene.rooms;
  expect(right.y).toBe(left.y);
  expect(right.x).toBe(left.x + left.w - 1);
  const door = left.doors.find(d => d.x === right.x);
  expect(door).toBeDefined();
  expect(right.doors).toContainEqual(door);
  expect(scene.blocked.has(`${door?.x},${door?.y}`)).toBe(false);
  expect(scene.widthTiles * TILE).toBeLessThanOrEqual(352);
  expect(scene.heightTiles * TILE).toBe(160);
  expect(findPath(scene, left.bench, right.bench).kind).toBe('path');
});

it('열 수가 증가할 때 기존 좌표를 보존하면서 새 좌석과 겹치지 않는다', () => {
  const old = computeLayout(makeOffice(4));
  const next = computeLayout(makeOffice(6), 25, old, true);
  expect(new Set(next.seats.map(s => `${s.x},${s.y}`)).size).toBe(6);
  for (const seat of old.seats) expect(next.seats.find(s => s.agentId === seat.agentId)).toMatchObject({ x: seat.x, y: seat.y });
});

it('자리 보존으로 큰 방이 늘어나도 최종 외벽에 출구와 휴게석을 배치한다', () => {
  const old = computeLayout(makeOffice(4));
  for (const count of [12, 20]) {
    const scene = computeLayout(makeOffice(count), 25, old, true);
    const room = scene.rooms[0];
    expect(room.exit.y).toBe(room.y + room.h - 1);
    expect(room.bench.y).toBe(room.y + room.h - 3);
    expect(room.doors).toContainEqual(room.exit);
    expect(scene.blocked.has(`${room.exit.x},${room.exit.y}`)).toBe(false);
  }
});
