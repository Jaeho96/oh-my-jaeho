import { describe, expect, it } from 'vitest';
import { focusCamera, cameraTarget, centerCamera, screenToWorld, worldToScreen, fitZoom, type Camera } from './camera';
import { deriveBehavior } from './behavior';
import { computeLayout, TILE } from './layout';
import { makeAgent, makeOffice } from './testFixtures';
import { findPath } from './pathfinding';
import { depthOrder } from './renderOrder';
import { advanceSimulation, createSimulation, officeAgents } from './simulation';
import { ANCHOR, appearanceFor, DIRECTIONS, spritePixels } from './spriteData';
import { spritePalette } from './palette';
import { visibleLabels } from './overlays';
import { hitActor } from './hitTest';
import { compositionKey } from './loop';
describe('카메라·경로·깊이', () => {
  it.each([1, 2, 3, 4])('%i배에서 화면과 세계 좌표를 왕복한다', zoom => {
    const camera: Camera = { x: 12, y: 23, zoom, width: 800, height: 500, dpr: 2 };
    const p = { x: 125, y: 87 };
    expect(screenToWorld(worldToScreen(p, camera), camera)).toEqual(p);
    expect(Number.isInteger(centerCamera(400, 160, camera).x * 2)).toBe(true);
  });
  it('전체 보기 배율을 정수로 제한한다', () => { expect(fitZoom(400, 160, 1200, 500)).toBe(3); expect(fitZoom(400, 160, 300, 100)).toBe(1); });
  it('도착과 도달 불가를 구분하고 장애물을 돌아간다', () => {
    const scene = computeLayout(makeOffice(2));
    const start = { x: 3, y: 5 };
    const target = { x: 5, y: 6 };
    expect(findPath(scene, start, start)).toEqual({ kind: 'arrived', path: [] });
    expect(findPath(scene, start, { x: 0, y: 0 }).kind).toBe('unreachable');
    const result = findPath(scene, start, target);
    expect(result.kind).toBe('path');
    for (const step of result.path) {
      expect(scene.blocked.has(`${step.x},${step.y}`)).toBe(false);
    }
  });
  it('앞에 있는 인물과 가구부터 클릭하고 깊이 순서로 그린다', () => {
    const sim = createSimulation();
    const scene = computeLayout(makeOffice(2));
    advanceSimulation(sim, scene, officeAgents(makeOffice(2)), 0, 0, null, false);
    const a = sim.actors.get('0-0');
    const b = sim.actors.get('0-1');
    if (!a || !b) {
      throw Error('인물이 필요하다');
    }
    b.x = a.x;
    b.y = a.y + 2;
    const c: Camera = { x: 0, y: 0, zoom: 3, width: 1000, height: 500, dpr: 2 };
    expect(hitActor([a, b], a.x * 3, (a.y - 10) * 3, c)).toBe(b.id);
    expect(depthOrder([{ id: 'front', y: 10, layer: 0 }, { id: 'back', y: 1, layer: 1 }]).map(v => v.id)).toEqual(['back', 'front']);
  });
});
describe('독자 도트와 정보', () => {
  it('네 방향의 모든 프레임을 16×32와 유효 팔레트로 정의한다', () => {
    const colors = spritePalette(0, 'worker');
    expect(ANCHOR).toEqual({ x: 8, y: 31 });
    for (const direction of DIRECTIONS) {
      for (const pose of ['walk', 'type', 'read', 'sit', 'stand'].values()) {
        if (pose !== 'walk' && pose !== 'type' && pose !== 'read' && pose !== 'sit' && pose !== 'stand') {
          throw Error('자세');
        }
        for (let frame = 0; frame < 4; frame += 1) {
          const map = spritePixels(direction, pose, frame);
          expect(map).toHaveLength(32);
          for (const row of map) {
            expect(row).toHaveLength(16);
            for (const key of row) {
              expect(key === '.' || colors[key] !== undefined).toBe(true);
            }
          }
        }
      }
    }
    expect(new Set([0, 1, 2, 3].map(f => spritePixels('down', 'walk', f).join(''))).size).toBe(4);
    expect(spritePixels('down', 'read', 0)).not.toEqual(spritePixels('down', 'read', 1));
    expect(spritePixels('down', 'type', 0)).not.toEqual(spritePixels('down', 'type', 1));
  });
  it.each(DIRECTIONS)('%s 방향 읽기와 타자의 두 프레임을 서로 다른 자세로 구별한다', direction => {
    const sit = spritePixels(direction, 'sit', 0);
    const read = [spritePixels(direction, 'read', 0), spritePixels(direction, 'read', 1)];
    const type = [spritePixels(direction, 'type', 0), spritePixels(direction, 'type', 1)];
    expect(read[0]).not.toEqual(read[1]);
    expect(type[0]).not.toEqual(type[1]);
    for (const frame of read) {
      expect(frame).not.toEqual(sit);
      for (const typing of type) { expect(frame).not.toEqual(typing); }
    }
    for (const frame of type) { expect(frame).not.toEqual(sit); }
    if (direction === 'up') {
      for (const frame of read) {
        expect(frame.some(row => row.includes('w'))).toBe(true);
        expect(frame.slice(13,21).every(row => !/[wg]/.test(row.slice(5,11)))).toBe(true);
      }
    }
  });
  it('외형을 아이디 해시로 여섯 종류에 고정한다', () => { expect(appearanceFor('reviewer')).toBe(appearanceFor('reviewer')); expect(new Set(Array.from({ length: 60 }, (_, i) => appearanceFor(String(i)))).size).toBe(6); });
  it('겹친 이름표에서는 선택한 사람을 우선한다', () => {
    const boxes = [{ id: 'a', x: 0, y: 0, w: 120, h: 18, priority: 1 }, { id: 'b', x: 2, y: 2, w: 120, h: 18, priority: 4 }];
    expect(visibleLabels(boxes).map(b => b.id)).toEqual(['b']);
  });
});
describe('상태 행동과 완료 수명', () => {
  it('승인과 멈춤과 오류를 정지시키고 수면으로 표시하지 않는다', () => {
    for (const status of ['permission', 'stalled', 'error'].values()) {
      if (status !== 'permission' && status !== 'stalled' && status !== 'error') {
        throw Error('상태');
      }
      expect(deriveBehavior(status).frozen).toBe(true);
      expect(deriveBehavior(status).bubble).not.toBe('zzz');
    }
  });
  it('최초 완료는 재연출하지 않고 원래 방의 완료 영역에 둔다', () => {
    const office = makeOffice(2, 2);
    office.rooms[1].teams[0].members[0].status = 'done';
    const scene = computeLayout(office);
    const sim = createSimulation();
    advanceSimulation(sim, scene, officeAgents(office), 0, 0, null, false);
    expect(sim.actors.get('1-1')).toMatchObject({ phase: 'exited', roomId: 'r1' });
  });
  it('완료 확인과 휴게석을 거쳐 퇴장하고 다시 활성화하면 복귀한다', () => {
    const office = makeOffice(2);
    const scene = computeLayout(office);
    const sim = createSimulation();
    const agents = officeAgents(office);
    advanceSimulation(sim, scene, agents, 0, 0, null, true);
    agents.set('0-1', makeAgent('0-1', 'done'));
    advanceSimulation(sim, scene, agents, 1, 0, null, true);
    expect(sim.actors.get('0-1')?.phase).toBe('check');
    advanceSimulation(sim, scene, agents, 2002, 0, null, true);
    expect(sim.actors.get('0-1')?.phase).toBe('rest');
    advanceSimulation(sim, scene, agents, 8003, 0, null, true);
    expect(sim.actors.get('0-1')?.phase).toBe('exit');
    advanceSimulation(sim, scene, agents, 8004, 0, null, true);
    advanceSimulation(sim, scene, agents, 8400, 0, null, true);
    expect(sim.actors.get('0-1')?.phase).toBe('exited');
    agents.set('0-1', makeAgent('0-1', 'typing'));
    advanceSimulation(sim, scene, agents, 8500, 0, null, true);
    expect(sim.actors.get('0-1')).toMatchObject({ phase: 'work', pose: 'type', alpha: 1 });
  });
  it('선택된 완료자는 휴게석에서 기다린다', () => {
    const office = makeOffice(2);
    const scene = computeLayout(office);
    const sim = createSimulation();
    const agents = officeAgents(office);
    advanceSimulation(sim, scene, agents, 0, 0, null, true);
    agents.set('0-1', makeAgent('0-1', 'done'));
    advanceSimulation(sim, scene, agents, 1, 0, null, true);
    advanceSimulation(sim, scene, agents, 3000, 0, '0-1', true);
    advanceSimulation(sim, scene, agents, 30000, 0, '0-1', true);
    expect(sim.actors.get('0-1')?.phase).toBe('rest');
  });
  it('이동 중 승인은 위치를 정지하고 반복 스냅샷은 전이를 반복하지 않는다', () => {
    const office = makeOffice(2);
    const scene = computeLayout(office);
    const sim = createSimulation();
    const agents = officeAgents(office);
    advanceSimulation(sim, scene, agents, 0, 0, null, false);
    advanceSimulation(sim, scene, agents, 11000, .05, null, false);
    const before = sim.actors.get('0-1');
    if (!before) {
      throw Error('인물');
    }
    const x = before.x;
    const y = before.y;
    agents.set('0-1', makeAgent('0-1', 'permission'));
    advanceSimulation(sim, scene, agents, 12000, .05, null, false);
    advanceSimulation(sim, scene, agents, 13000, .05, null, false);
    expect(sim.actors.get('0-1')).toMatchObject({ x, y, since: 12000 });
    const reordered = makeOffice(2);
    reordered.rooms[0].teams[0].members.reverse();
    expect(compositionKey(reordered)).toBe(compositionKey(office));
  });
});

it('보간 이동으로 완료자가 실제 휴게석과 출구를 거쳐 퇴장한다', () => {
  const office=makeOffice(2);const scene=computeLayout(office);const sim=createSimulation();const agents=officeAgents(office);
  advanceSimulation(sim,scene,agents,0,0,null,false);
  agents.set('0-1',makeAgent('0-1','done'));
  let arrived: number | null = null;
  let exitTime: number | null = null;
  for (let now=50;now<=40000;now+=50) {
    advanceSimulation(sim,scene,agents,now,.05,null,false);
    const actor=sim.actors.get('0-1');
    if (actor?.phase==='rest' && actor.arrivedAt!==null && arrived===null) {arrived=now;}
    if (actor?.phase==='exited' && exitTime===null) {exitTime=now;}
  }
  expect(arrived).not.toBeNull();expect(exitTime).not.toBeNull();
  if (arrived!==null && exitTime!==null) {expect(exitTime-arrived).toBeGreaterThanOrEqual(6000);}
  expect(sim.actors.get('0-1')?.phase).toBe('exited');
});
it('20명 시뮬레이션 갱신의 p95를 8ms 안에 수행한다', () => {
  const office=makeOffice(20);const scene=computeLayout(office);const sim=createSimulation();const agents=officeAgents(office);const times:number[]=[];
  for (let i=0;i<600;i+=1) {const start=performance.now();advanceSimulation(sim,scene,agents,i*16,.016,null,false);times.push(performance.now()-start);}
  const p95=times.toSorted((a,b)=>a-b)[Math.floor(times.length*.95)]??Infinity;
  process.stdout.write(`20명 update-only p95: ${p95.toFixed(3)}ms (Node, draw 제외)\n`);
  expect(p95).toBeLessThan(8);
});

it('전체 보기에서 두 방을 담는 최대 정수 배율을 구한다', () => {
  expect(fitZoom(336, 128, 1124, 384)).toBe(3);
  expect(fitZoom(100, 50, 1100, 600)).toBe(11);
});

it('방을 선택하면 맞춤 정수 배율과 방의 절대 중앙으로 카메라를 옮긴다', () => {
  const office = makeOffice(8, 2);
  const scene = computeLayout(office, 40);
  const room = scene.rooms[1];
  const initial: Camera = { x: 0, y: 0, zoom: 4, width: 1152, height: 480, dpr: 1 };
  const camera = focusCamera(scene, office, room.roomId, 0, initial);
  expect(camera.zoom).toBe(3);
  expect(worldToScreen({ x: (room.x + room.w / 2) * 16, y: (room.y + room.h / 2) * 16 }, camera)).toEqual({ x: 576, y: 240 });
  const manual = focusCamera(scene, office, room.roomId, 4, initial);
  expect(manual.zoom).toBe(4);
  expect(worldToScreen({ x: (room.x + room.w / 2) * 16, y: (room.y + room.h / 2) * 16 }, manual)).toEqual({ x: 576, y: 240 });
});

it('좁은 화면은 대기 최다 방을 두 배 이상으로 먼저 보여 준다', () => {
  const office = makeOffice(2, 2);
  office.rooms[1].teams[0].lead.status = 'permission';
  const scene = computeLayout(office, 24);
  expect(cameraTarget(scene, office, null, 354)?.roomId).toBe('r1');
  const camera = focusCamera(scene, office, null, 0, { x: 0, y: 0, zoom: 1, width: 354, height: 320, dpr: 1 });
  expect(camera.zoom).toBe(2);
  expect(cameraTarget(scene, office, null, 1000)).toBeUndefined();
});

it('좁은 화면에서 대기 최다 방의 맞춤 배율이 한 배여도 기본 두 배를 적용한다', () => {
  const office = makeOffice(8, 2);
  office.rooms[1].teams[0].lead.status = 'permission';
  office.rooms[1].teams[0].members[0].status = 'waiting';
  const scene = computeLayout(office, 40);
  const room = scene.rooms[1];
  const viewport: Camera = { x: 0, y: 0, zoom: 1, width: 370, height: 320, dpr: 1 };
  expect(room.w * TILE).toBe(224);
  expect(fitZoom(room.w * TILE, room.h * TILE, viewport.width, viewport.height)).toBe(1);
  expect(cameraTarget(scene, office, null, viewport.width, viewport.height, 420)?.roomId).toBe(room.roomId);
  expect(focusCamera(scene, office, null, 0, viewport, 420).zoom).toBe(2);
});
