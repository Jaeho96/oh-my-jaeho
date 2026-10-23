import { describe, expect, it } from 'vitest';

import type { Agent, Office, Team } from '../../../entities/board';
import { computeLayout, hitTest, SEAT_H, SEAT_W, TILE } from './layout';

const agent = (id: string): Agent => ({
  id,
  provider: 'codex',
  kind: 'lead',
  parent: null,
  machine: 'local',
  role: null,
  nickname: null,
  title: null,
  cwd: null,
  model: null,
  effort: null,
  status: 'idle',
  activity: null,
  context: null,
  tokens: null,
  lastMessage: null,
  startedAt: null,
  lastEventAt: null,
  errors: 0,
});

const team = (id: string, members: number): Team => ({
  id,
  provider: 'codex',
  label: id,
  lead: agent(`${id}-lead`),
  members: Array.from({ length: members }, (_, i) => agent(`${id}-m${i}`)),
});

const office = (...rooms: Team[][]): Office => ({
  rooms: rooms.map((teams, i) => ({ id: `r${i}`, label: `방${i}`, teams, hidden: 0, error: null })),
  counts: {},
  generatedAt: null,
  stallSec: 600,
});

const overlaps = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.abs(a.x - b.x) < SEAT_W && Math.abs(a.y - b.y) < SEAT_H;

describe('computeLayout', () => {
  it('모든 에이전트에게 겹치지 않는 자리를 준다', () => {
    const scene = computeLayout(office([team('a', 3), team('b', 0), team('c', 5)], [team('d', 1)]), 30);
    expect(scene.seats).toHaveLength(4 + 1 + 6 + 2);
    for (const [i, s] of scene.seats.entries()) {
      for (const t of scene.seats.slice(i + 1)) expect(overlaps(s, t)).toBe(false);
    }
  });

  it('팀 리더가 팀의 첫 자리에 앉는다', () => {
    const scene = computeLayout(office([team('a', 2)]), 30);
    expect(scene.seats[0]).toMatchObject({ agentId: 'a-lead', isLead: true });
  });

  it('폭을 넘는 팀 묶음은 다음 줄로 내린다', () => {
    const scene = computeLayout(office([team('a', 3), team('b', 3)]), 4 * SEAT_W + 2);
    const [a, b] = scene.pods;
    expect(b.y).toBeGreaterThan(a.y);
    for (const s of scene.seats) expect(s.x + SEAT_W).toBeLessThanOrEqual(scene.widthTiles);
  });

  it('방은 위에서 아래로 겹치지 않게 쌓는다', () => {
    const scene = computeLayout(office([team('a', 1)], [team('b', 1)]), 30);
    expect(scene.rooms[1].y).toBe(scene.rooms[0].y + scene.rooms[0].h);
  });

  it('스냅샷이 없으면 빈 장면을 준다', () => {
    expect(computeLayout(null, 30).seats).toEqual([]);
  });
});

describe('hitTest', () => {
  it('누른 칸에 앉은 에이전트를 찾는다', () => {
    const scene = computeLayout(office([team('a', 1)]), 30);
    const seat = scene.seats[1];
    const scale = 3;
    const x = (seat.x + 1) * TILE * scale;
    const y = (seat.y + 2) * TILE * scale;
    expect(hitTest(scene, x, y, scale)).toBe('a-m0');
    expect(hitTest(scene, 0, 0, scale)).toBeNull();
  });
});
