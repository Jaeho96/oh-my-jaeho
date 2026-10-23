/**
 * 도트 그리기. 한 자리(3×4 타일 = 48×64 논리 픽셀) 안에 위에서부터 말풍선(0–12)·게이지(12–14)·캐릭터(15–41)·책상(40–52)을 그린다.
 * 이름표(54–)는 renderer 가 글자로 쓴다.
 * 좌표는 논리 픽셀이고, ctx 에 scale 이 이미 걸려 있다고 본다.
 */
import type { Bubble, Pose } from '../../../entities/board';
import type { CharacterColors, OfficeTheme } from './palette';

type Ctx = CanvasRenderingContext2D;

const px = (ctx: Ctx, color: string, x: number, y: number, w = 1, h = 1) => {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, h);
};

/** frame 은 0·1 을 오간다(초당 몇 번 바뀌는지는 루프가 정한다). */
export function drawCharacter(ctx: Ctx, ox: number, oy: number, c: CharacterColors, pose: Pose, frame: number) {
  const lean = pose === 'lean' ? 1 : 0;
  const bob = pose === 'read' && frame === 1 ? 1 : 0;
  const hx = ox + 18 - lean;
  const hy = oy + 16 + bob;
  // 머리
  px(ctx, c.outline, hx - 1, hy - 1, 14, 13);
  px(ctx, c.skin, hx, hy, 12, 11);
  px(ctx, c.hair, hx, hy, 12, 4);
  px(ctx, c.hair, hx, hy + 4, 2, 3);
  px(ctx, c.hair, hx + 10, hy + 4, 2, 3);
  // 눈 — 쉬는 중이면 감는다
  const eyeY = hy + 6 + (pose === 'read' ? 1 : 0);
  if (pose === 'lean' && frame === 1) {
    px(ctx, c.outline, hx + 3, eyeY + 1, 2, 1);
    px(ctx, c.outline, hx + 7, eyeY + 1, 2, 1);
  } else {
    px(ctx, c.outline, hx + 3, eyeY, 2, 2);
    px(ctx, c.outline, hx + 7, eyeY, 2, 2);
  }
  // 몸
  const by = oy + 28;
  px(ctx, c.outline, ox + 14 - lean, by - 1, 20, 14);
  px(ctx, c.shirt, ox + 15 - lean, by, 18, 13);
  // 팔 — 타자 칠 때는 손이 키보드로, 읽을 때는 종이를 든다
  if (pose === 'type') {
    const up = frame === 0 ? 0 : 1;
    px(ctx, c.shirt, ox + 11, by + 6 + up, 5, 4);
    px(ctx, c.shirt, ox + 32, by + 6 + (1 - up), 5, 4);
    px(ctx, c.skin, ox + 11, by + 10 + up, 4, 2);
    px(ctx, c.skin, ox + 33, by + 10 + (1 - up), 4, 2);
  } else if (pose === 'read') {
    px(ctx, '#f8fafc', ox + 17, by + 3, 14, 9);
    px(ctx, '#94a3b8', ox + 19, by + 5 + frame, 10, 1);
    px(ctx, '#94a3b8', ox + 19, by + 8 - frame, 8, 1);
    px(ctx, c.skin, ox + 15, by + 8, 3, 3);
    px(ctx, c.skin, ox + 30, by + 8, 3, 3);
  } else {
    px(ctx, c.shirt, ox + 11 - lean, by + 2, 4, 9);
    px(ctx, c.shirt, ox + 33 - lean, by + 2, 4, 9);
  }
}

export function drawChair(ctx: Ctx, ox: number, oy: number, theme: OfficeTheme) {
  px(ctx, theme.chair, ox + 13, oy + 24, 22, 16);
}

export type ScreenMode = 'type' | 'read' | 'off' | 'idle';

export function drawDesk(ctx: Ctx, ox: number, oy: number, theme: OfficeTheme, screen: ScreenMode, frame: number) {
  const dy = oy + 40;
  px(ctx, theme.deskEdge, ox + 2, dy, 44, 12);
  px(ctx, theme.desk, ox + 2, dy, 44, 9);
  // 모니터(옆으로 돌린 화면)
  px(ctx, '#111827', ox + 33, dy - 11, 12, 10);
  const glow = screen === 'type' ? (frame === 0 ? '#22c55e' : '#16a34a') : screen === 'read' ? '#38bdf8' : screen === 'idle' ? '#334155' : '#0b1220';
  px(ctx, glow, ox + 34, dy - 10, 10, 7);
  if (screen === 'read') {
    px(ctx, '#e0f2fe', ox + 35, dy - 9 + frame, 7, 1);
    px(ctx, '#e0f2fe', ox + 35, dy - 6 + frame, 5, 1);
  }
  px(ctx, '#111827', ox + 38, dy - 1, 2, 2);
  // 키보드
  px(ctx, '#cbd5e1', ox + 12, dy + 2, 16, 3);
}

/** 말풍선. frame 으로 점이 움직이거나 깜빡인다. */
export function drawBubble(ctx: Ctx, ox: number, oy: number, bubble: Bubble, frame: number, t: number) {
  if (bubble === null) return;
  const bx = ox + 24;
  const by = oy;
  if (bubble === 'alert' && frame === 1) return; // 깜빡임
  px(ctx, '#1f2937', bx - 1, by - 1, 18, 12);
  px(ctx, '#ffffff', bx, by, 16, 10);
  px(ctx, '#ffffff', bx + 2, by + 10, 3, 2);
  switch (bubble) {
    case 'dots': {
      const n = Math.floor(t / 300) % 4;
      for (let i = 0; i < Math.min(n, 3); i += 1) px(ctx, '#475569', bx + 3 + i * 4, by + 4, 2, 2);
      break;
    }
    case 'question':
      px(ctx, '#d97706', bx + 6, by + 2, 4, 1);
      px(ctx, '#d97706', bx + 9, by + 3, 1, 2);
      px(ctx, '#d97706', bx + 7, by + 5, 2, 1);
      px(ctx, '#d97706', bx + 7, by + 7, 2, 2);
      break;
    case 'alert':
      px(ctx, '#dc2626', bx + 7, by + 2, 2, 4);
      px(ctx, '#dc2626', bx + 7, by + 7, 2, 2);
      break;
    case 'team':
      px(ctx, '#6366f1', bx + 3, by + 3, 3, 3);
      px(ctx, '#0ea5e9', bx + 7, by + 3, 3, 3);
      px(ctx, '#f59e0b', bx + 11, by + 3, 3, 3);
      px(ctx, '#94a3b8', bx + 3 + (frame === 0 ? 0 : 4), by + 7, 3, 1);
      break;
    case 'check':
      px(ctx, '#16a34a', bx + 4, by + 5, 2, 2);
      px(ctx, '#16a34a', bx + 6, by + 6, 2, 2);
      px(ctx, '#16a34a', bx + 8, by + 3, 2, 3);
      px(ctx, '#16a34a', bx + 10, by + 2, 2, 2);
      break;
    case 'zzz':
      px(ctx, '#64748b', bx + 3, by + 2 + frame, 4, 1);
      px(ctx, '#64748b', bx + 5, by + 3 + frame, 1, 1);
      px(ctx, '#64748b', bx + 3, by + 4 + frame, 4, 1);
      px(ctx, '#94a3b8', bx + 9, by + 5 - frame, 3, 1);
      px(ctx, '#94a3b8', bx + 9, by + 7 - frame, 3, 1);
      break;
    case 'cross':
      for (let i = 0; i < 5; i += 1) {
        px(ctx, '#dc2626', bx + 5 + i, by + 2 + i, 2, 1);
        px(ctx, '#dc2626', bx + 9 - i, by + 2 + i, 2, 1);
      }
      break;
    default: {
      const unreachable: never = bubble;
      return unreachable;
    }
  }
}

/** 컨텍스트 사용량 막대. pct 가 없으면 그리지 않는다. */
export function drawGauge(ctx: Ctx, ox: number, oy: number, pct: number | null) {
  if (pct === null) return;
  const w = 20;
  const filled = Math.max(1, Math.round((Math.min(pct, 100) / 100) * w));
  const color = pct >= 85 ? '#ef4444' : pct >= 60 ? '#f59e0b' : '#22c55e';
  px(ctx, '#1f2937', ox + 14, oy + 12, w + 2, 3);
  px(ctx, '#e5e7eb', ox + 15, oy + 13, w, 1);
  px(ctx, color, ox + 15, oy + 13, filled, 1);
}
