import { agentName, type Agent } from '../../../entities/board';
import { worldToScreen, type Camera } from './camera';
import { deriveBehavior } from './behavior';
import { FURNITURE } from './furnitureData';
import { TILE } from './layout';
import { labelPriority, labelHeight, visibleLabels, type LabelBox } from './overlays';
import type { OfficeTheme } from './palette';
import { depthOrder } from './renderOrder';
import type { RoomBox, Scene } from './sceneTypes';
import type { Simulation } from './simulation';
import { SpriteCache } from './spriteCache';
import { drawBubble, drawCharacter, drawFurniture } from './sprites';
export interface DrawInput {
  scene: Scene;
  agents: Map<string, Agent>;
  simulation: Simulation;
  selectedId: string | null;
  hoverId: string | null;
  theme: OfficeTheme;
  camera: Camera;
  t: number;
  reduced: boolean;
}
export interface RenderCache {
  sprites: SpriteCache;
  floor: HTMLCanvasElement | null;
  floorKey: string;
  labels: LabelBox[];
  occluders: Occluder[];
}
export function createRenderCache(): RenderCache {
  return { sprites: new SpriteCache(16 * 1024 * 1024), floor: null, floorKey: '', labels: [], occluders: [] };
}
interface Occluder {
  x: number;
  y: number;
  w: number;
  h: number;
  depth: number;
  mask: Path2D;
}
/** 가구의 아래쪽에도 벽까지 한 타일의 통로를 남긴다. */
export function loungeFurniture(room: RoomBox): { id: keyof typeof FURNITURE; x: number; y: number }[] {
  const x = room.x * TILE;
  const bottom = (room.y + room.h) * TILE - 5 - TILE;
  return [
    { id: 'rug', x: x + 12, y: bottom - 24 },
    { id: 'sofa', x: x + 12, y: bottom - 24 },
    { id: 'coffeeTable', x: x + 49, y: bottom - 16 },
    { id: 'coffeeMachine', x: (room.x + room.w) * TILE - 36, y: bottom - 16 },
    { id: 'plantTall', x: (room.x + room.w) * TILE - 32, y: bottom - 20 },
    { id: 'bin', x: (room.x + room.w) * TILE - 48, y: bottom - 10 },
  ];
}
/** 장식과 모든 가구까지 한 번 그린 정적 장면을 재사용한다. */
function drawFloor(ctx: CanvasRenderingContext2D, scene: Scene, theme: OfficeTheme, sprites: SpriteCache, occluders: Occluder[] = []): void {
  const furniture = (id: keyof typeof FURNITURE, x: number, y: number, variant?: string) => {
    drawFurniture(ctx, id, x, y, sprites, theme, variant);
    if (id === 'rug' || typeof Path2D === 'undefined') {
      return;
    }
    const data = FURNITURE[id];
    const mask = new Path2D();
    data.pixels.forEach((row, py) => {
      [...row].forEach((pixel, px) => {
        if (pixel !== '.') {
          mask.rect(x + px, y + py, 1, 1);
        }
      });
    });
    occluders.push({ x, y, w: data.width, h: data.height, depth: y + data.height, mask });
  };
  for (const r of scene.rooms) {
    const x = r.x * TILE;
    const y = r.y * TILE;
    const w = r.w * TILE;
    const h = r.h * TILE;
    ctx.fillStyle = theme.floorA;
    ctx.fillRect(x, y, w, h);
    // 짧은 널판을 엇갈리게 놓고 한 픽셀의 결만 더한다.
    for (let row = 0; row < h / 8; row += 1) {
      for (let col = -1; col < w / 32; col += 1) {
        const px = x + col * 32 + row % 2 * TILE;
        ctx.fillStyle = (row * 7 + col * 3) % 5 === 0 ? theme.floorB : theme.floorA;
        ctx.fillRect(Math.max(x, px), y + row * 8, Math.min(32, x + w - Math.max(x, px)), 8);
        ctx.fillStyle = 'rgba(58,35,24,.12)';
        ctx.fillRect(Math.max(x, px), y + row * 8 + 7, Math.min(32, x + w - Math.max(x, px)), 1);
        if (px >= x) {
          ctx.fillRect(px, y + row * 8, 1, 8);
        }
      }
    }
    ctx.fillStyle = theme.wall;
    ctx.fillRect(x, y, w, 22);
    ctx.fillRect(x, y, 7, h);
    ctx.fillRect(x + w - TILE, y, TILE, h);
    ctx.fillRect(x, y + h - 5, w, 5);
    ctx.fillStyle = theme.wallTrim;
    ctx.fillRect(x, y, w, 3);
    ctx.fillRect(x, y + 20, w, 3);
    ctx.fillRect(x + w - TILE, y, 3, h);
    ctx.fillRect(x, y + h - 5, w, 2);
    furniture('bookcase', x + 12, y + 3);
    furniture('clock', x + w / 2 - 6, y + 4);
    furniture('window', x + w - 48, y + 3);
    if (r.w > 8) {
      furniture('picture', x + w / 2 + 12, y + 5);
    }
    // 아래 벽의 타일 통로를 비워 두고 휴게 가구를 바닥 안에 놓는다.
    for (const item of loungeFurniture(r)) furniture(item.id, item.x, item.y);
    furniture('plant', x + w - 29, y + 20);

  }
  // 공유 벽은 마지막에 문을 뚫어 어느 방을 먼저 그려도 통로를 유지한다.
  for (const room of scene.rooms) {
    for (const door of room.doors) {
      const x = door.x * TILE;
      const y = door.y * TILE;
      ctx.fillStyle = theme.floorB;
      ctx.fillRect(x, y, TILE, TILE);
      // 벽을 지운 통로 바닥에 낮은 매트만 놓아 세워 둔 문틀처럼 보이지 않게 한다.
      ctx.fillStyle = theme.wallTrim;
      ctx.fillRect(x + 2, y + TILE - 5, TILE - 4, 3);
      ctx.fillStyle = theme.floorA;
      ctx.fillRect(x + 3, y + TILE - 4, TILE - 6, 1);
    }
  }
  for (const seat of scene.seats) {
    const x = seat.x * TILE;
    const y = seat.y * TILE;
    furniture('chairBack', x + 10, y + 25, seat.isLead ? 'leader' : undefined);
    furniture(seat.isLead ? 'deskLead' : 'desk', x, y);
    furniture('monitorFront', x + 10, y - 2);
    furniture('keyboard', x + 10, y + 12);
  }
}
/** 잘못된 크기나 과도한 버퍼는 할당 전에 거절한다. */
export function rasterizeFloor(scene: Scene, theme: OfficeTheme, sprites = new SpriteCache(16 * 1024 * 1024), occluders: Occluder[] = []): HTMLCanvasElement | null {
  const width = scene.widthTiles * TILE;
  const height = scene.heightTiles * TILE;
  const cost = width * height * 4;
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width <= 0 || height <= 0 || !Number.isSafeInteger(cost) || cost > 16 * 1024 * 1024) {
    return null;
  }
  const floor = document.createElement('canvas');
  floor.width = width;
  floor.height = height;
  const ctx = floor.getContext('2d');
  if (!ctx) {
    floor.width = 0;
    floor.height = 0;
    return null;
  }
  drawFloor(ctx, scene, theme, sprites, occluders);
  return floor;
}
export function drawScene(ctx: CanvasRenderingContext2D, input: DrawInput, cache: RenderCache): void {
  const { scene, camera: c, theme, agents, simulation, selectedId, hoverId, t, reduced } = input;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, c.width * c.dpr, c.height * c.dpr);
  ctx.imageSmoothingEnabled = false;
  ctx.setTransform(c.zoom * c.dpr, 0, 0, c.zoom * c.dpr, Math.round(-c.x * c.zoom * c.dpr), Math.round(-c.y * c.zoom * c.dpr));
  const floorKey = `${JSON.stringify(theme)}/${scene.rooms.map(r => `${r.roomId}:${r.x},${r.y},${r.w},${r.h},${r.doors.map(d => `${d.x}:${d.y}`).join(';')}`).join('/')}/${scene.seats.map(s => `${s.agentId}:${s.x},${s.y},${s.isLead}`).join('/')}`;
  if (cache.floorKey !== floorKey) {
    cache.floorKey = floorKey;
    if (cache.floor) {
      cache.floor.width = 0;
      cache.floor.height = 0;
    }
    cache.occluders = [];
    cache.floor = rasterizeFloor(scene, theme, cache.sprites, cache.occluders);
  }
  if (cache.floor) {
    ctx.drawImage(cache.floor, 0, 0);
  }
  else {
    drawFloor(ctx, scene, theme, cache.sprites);
  }
  const actors = [...simulation.actors.values()].filter(a => a.phase !== 'exited' || a.id === selectedId);
  // 의자와 책상은 뒤쪽 정적 층, 사람은 그 앞쪽에서 발 좌표로 정렬한다.
  for (const a of depthOrder(actors.map(actor => ({ ...actor, layer: 1 })))) {
    const agent = agents.get(a.id);
    if (!agent) {
      continue;
    }
    const frozen = deriveBehavior(agent.status).frozen;
    const frame = reduced || frozen ? 0 : Math.floor((t + a.phaseOffset) / (a.pose === 'walk' ? 150 : a.pose === 'read' ? 600 : 240)) % (a.pose === 'walk' ? 4 : 2);
    const blink = !reduced && !frozen && (t + a.phaseOffset) % 4700 < 120;
    ctx.globalAlpha = a.alpha;
    drawCharacter(ctx, Math.round(a.x), Math.round(a.y), a.id, agent.role, a.direction, a.pose, frame, cache.sprites, a.id === selectedId ? theme.select : a.id === hoverId ? theme.wallTrim : null, blink);
    ctx.globalAlpha = 1;
    // 캐시된 가구의 불투명 도트만 복원해 뒤에서 지나가는 인물을 가린다.
    for (const item of cache.occluders) {
      if (cache.floor && occludesActor(item, a)) {
        ctx.save();
        ctx.clip(item.mask);
        ctx.drawImage(cache.floor, 0, 0);
        ctx.restore();
      }
    }
    if (a.id === selectedId) {
      ctx.fillStyle = theme.select;
      ctx.fillRect(Math.round(a.x) - 7, Math.round(a.y) + 1, 14, 1);
    }
    const bubble = deriveBehavior(agent.status).bubble;
    if (bubble && (agent.status !== 'done' || a.phase === 'check' || a.id === selectedId)) {
      drawBubble(ctx, bubble, Math.round(a.x) + 5, Math.round(a.y) - 38, cache.sprites, theme);
    }
  }
  ctx.setTransform(c.dpr, 0, 0, c.dpr, 0, 0);
  ctx.textBaseline = 'top';
  ctx.font = '12px -apple-system,"Apple SD Gothic Neo",sans-serif';
  const labels: LabelBox[] = [];
  for (const a of actors) {
    const agent = agents.get(a.id);
    if (!agent) {
      continue;
    }
    const priority = labelPriority(agent.status, a.id === selectedId, a.id === hoverId, agent.kind === 'lead', c.zoom);
    if (!priority) {
      continue;
    }
    const p = worldToScreen({ x: a.x, y: a.y + 2 }, c);
    if (p.x < 0 || p.x > c.width || p.y < 0 || p.y > c.height) continue;
    const w = Math.min(132, ctx.measureText(agentName(agent)).width + 14);
    const h = labelHeight(a.id === selectedId && typeof agent.context?.pct === 'number');
    labels.push({ id: a.id, x: Math.max(2, Math.min(c.width - w - 2, p.x - w / 2)), y: Math.max(2, Math.min(c.height - h - 1, p.y)), w, h, priority });
  }
  cache.labels = visibleLabels(labels);
  for (const box of cache.labels) {
    const agent = agents.get(box.id);
    if (!agent) {
      continue;
    }
    let name = agentName(agent);
    while (ctx.measureText(name).width > box.w - 12 && name.length > 1)
      {name = name.slice(0, -2) + '…';}
    const nameHeight = 20;
    ctx.fillStyle = 'rgba(19,27,38,.86)';
    ctx.beginPath();
    ctx.moveTo(box.x + 9, box.y);
    ctx.arcTo(box.x + box.w, box.y, box.x + box.w, box.y + nameHeight, 9);
    ctx.arcTo(box.x + box.w, box.y + nameHeight, box.x, box.y + nameHeight, 9);
    ctx.arcTo(box.x, box.y + nameHeight, box.x, box.y, 9);
    ctx.arcTo(box.x, box.y, box.x + box.w, box.y, 9);
    ctx.fill();
    ctx.fillStyle = '#f4f1e9';
    ctx.fillText(name, box.x + 7, box.y + 3);
    if (box.id === selectedId && typeof agent.context?.pct === 'number') {
      const y = box.y + 22;
      ctx.fillStyle = 'rgba(19,27,38,.9)';
      ctx.fillRect(box.x + 4, y, box.w - 8, 3);
      ctx.fillStyle = theme.select;
      ctx.fillRect(box.x + 4, y, (box.w - 8) * Math.max(0, Math.min(100, agent.context.pct)) / 100, 3);
    }
  }
}
/** 가구의 발 위치보다 뒤에 있고 화면상 도트가 겹치는 인물만 가린다. */
export function occludesActor(item: {
  x: number;
  y: number;
  w: number;
  h: number;
  depth: number;
}, actor: {
  x: number;
  y: number;
}): boolean {
  return item.depth > actor.y && actor.x + 8 > item.x && actor.x - 8 < item.x + item.w && actor.y >= item.y && actor.y - 31 < item.y + item.h;
}
