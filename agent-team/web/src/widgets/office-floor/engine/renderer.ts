/**
 * 장면 그리기. 바닥·벽·방 이름 → 팀 깔개 → 자리마다 의자·캐릭터·책상·말풍선·게이지·이름표 순서로 그린다.
 * 픽셀은 논리 좌표로 그리고 scale 로 키운다(뭉개지지 않게 smoothing 을 끈다). 글자는 화면 좌표로 쓴다.
 */
import { agentName, statusVisual, type Agent } from '../../../entities/board';
import { type Scene, SEAT_H, SEAT_W, TILE } from './layout';
import { characterColors, type OfficeTheme } from './palette';
import { drawBubble, drawCharacter, drawChair, drawDesk, drawGauge, type ScreenMode } from './sprites';

export interface DrawInput {
  scene: Scene;
  agents: Map<string, Agent>;
  selectedId: string | null;
  hoverId: string | null;
  theme: OfficeTheme;
  scale: number;
  t: number; // ms
}

function screenFor(agent: Agent): ScreenMode {
  switch (statusVisual(agent.status).pose) {
    case 'type':
      return 'type';
    case 'read':
      return 'read';
    case 'sit':
      return 'idle';
    case 'lean':
      return 'off';
  }
}

function drawRooms(ctx: CanvasRenderingContext2D, { scene, theme }: DrawInput) {
  for (const room of scene.rooms) {
    for (let y = room.y; y < room.y + room.h; y += 1) {
      for (let x = room.x; x < room.x + room.w; x += 1) {
        ctx.fillStyle = (x + y) % 2 === 0 ? theme.floorA : theme.floorB;
        ctx.fillRect(x * TILE, y * TILE, TILE, TILE);
      }
    }
    ctx.fillStyle = theme.wall;
    ctx.fillRect(room.x * TILE, room.y * TILE, room.w * TILE, TILE + 6);
    ctx.fillStyle = theme.wallTrim;
    ctx.fillRect(room.x * TILE, room.y * TILE + TILE + 6, room.w * TILE, 2);
    // 화분 두 개
    for (const px of [room.x * TILE + 4, (room.x + room.w) * TILE - 14]) {
      ctx.fillStyle = '#8b5a2b';
      ctx.fillRect(px + 2, (room.y + room.h) * TILE - 12, 8, 8);
      ctx.fillStyle = '#16a34a';
      ctx.fillRect(px, (room.y + room.h) * TILE - 20, 12, 9);
    }
  }
}

function drawPods(ctx: CanvasRenderingContext2D, { scene, theme }: DrawInput) {
  for (const pod of scene.pods) {
    ctx.fillStyle = pod.provider === 'claude' ? theme.rugClaude : pod.provider === 'codex' ? theme.rugCodex : theme.rugOther;
    ctx.fillRect(pod.x * TILE + 2, pod.y * TILE + 2, pod.w * TILE - 4, pod.h * TILE - 4);
  }
}

function drawSeats(ctx: CanvasRenderingContext2D, input: DrawInput) {
  const { scene, agents, theme, t } = input;
  const frame = Math.floor(t / 280) % 2;
  for (const seat of scene.seats) {
    const agent = agents.get(seat.agentId);
    if (!agent) continue;
    const ox = seat.x * TILE;
    const oy = seat.y * TILE;
    const visual = statusVisual(agent.status);
    drawChair(ctx, ox, oy, theme);
    drawCharacter(ctx, ox, oy, characterColors(agent), visual.pose, frame);
    drawDesk(ctx, ox, oy, theme, screenFor(agent), frame);
    drawGauge(ctx, ox, oy, agent.context?.pct ?? null);
    drawBubble(ctx, ox, oy, visual.bubble, frame, t);
    if (seat.agentId === input.selectedId || seat.agentId === input.hoverId) {
      ctx.strokeStyle = theme.select;
      ctx.lineWidth = seat.agentId === input.selectedId ? 2 : 1;
      ctx.strokeRect(ox + 1, oy + 1, SEAT_W * TILE - 2, SEAT_H * TILE - 2);
    }
  }
}

/** 글자는 scale 을 풀고 화면 좌표로 쓴다(작은 글씨가 흐려지지 않게). */
function drawLabels(ctx: CanvasRenderingContext2D, { scene, agents, theme, scale }: DrawInput) {
  ctx.textBaseline = 'top';
  ctx.fillStyle = theme.text;
  ctx.font = `600 ${Math.max(11, Math.round(scale * 4))}px -apple-system, "Apple SD Gothic Neo", sans-serif`;
  for (const room of scene.rooms) {
    const extra = room.hidden > 0 ? `  · 자동 리뷰 ${room.hidden}개 숨김` : room.error ? `  · ${room.error}` : '';
    ctx.fillText(`${room.label}${extra}`, (room.x + 0.6) * TILE * scale, (room.y * TILE + 4) * scale);
  }
  ctx.font = `${Math.max(10, Math.round(scale * 3.4))}px -apple-system, "Apple SD Gothic Neo", sans-serif`;
  const maxWidth = SEAT_W * TILE * scale - 6;
  for (const seat of scene.seats) {
    const agent = agents.get(seat.agentId);
    if (!agent) continue;
    let name = agentName(agent);
    while (name.length > 1 && ctx.measureText(name).width > maxWidth) name = `${name.slice(0, -2)}…`;
    ctx.fillStyle = seat.isLead ? theme.text : `${theme.text}cc`;
    ctx.fillText(name, (seat.x * TILE + 3) * scale, (seat.y * TILE + 54) * scale);
  }
}

export function drawScene(ctx: CanvasRenderingContext2D, input: DrawInput) {
  const { scene, scale } = input;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, scene.widthTiles * TILE * scale, scene.heightTiles * TILE * scale);
  ctx.imageSmoothingEnabled = false;
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  drawRooms(ctx, input);
  drawPods(ctx, input);
  drawSeats(ctx, input);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  drawLabels(ctx, input);
}
