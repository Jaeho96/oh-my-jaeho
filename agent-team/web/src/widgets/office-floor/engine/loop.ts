/**
 * 그리기 루프. React 렌더와 따로 돈다 — 스냅샷이 바뀌어도 컴포넌트를 다시 그리지 않고 다음 프레임에 반영한다.
 * 애니메이션이 느린 도트라 초당 fps 번만 그린다(CPU 를 아낀다). 배치는 입력(스냅샷·폭)이 바뀔 때만 다시 계산한다.
 */
import type { Agent, Office } from '../../../entities/board';
import { computeLayout, hitTest, type Scene, TILE } from './layout';
import type { OfficeTheme } from './palette';
import { drawScene } from './renderer';

export interface LoopInput {
  office: Office | null;
  selectedId: string | null;
  hoverId: string | null;
  theme: OfficeTheme;
  scale: number;
  widthPx: number;
}

export interface OfficeLoop {
  update(patch: Partial<LoopInput>): void;
  hit(cssX: number, cssY: number): string | null;
  stop(): void;
}

export function startOfficeLoop(canvas: HTMLCanvasElement, initial: LoopInput, fps = 8): OfficeLoop {
  const ctx = canvas.getContext('2d');
  let input = initial;
  let scene: Scene = computeLayout(null, 1);
  let agents = new Map<string, Agent>();
  let laidOut: { office: Office | null; widthPx: number; scale: number } | null = null;
  let raf = 0;
  let last = 0;
  const dpr = typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1;

  const relayout = () => {
    if (laidOut && laidOut.office === input.office && laidOut.widthPx === input.widthPx && laidOut.scale === input.scale) return;
    const widthTiles = Math.floor(input.widthPx / (TILE * input.scale));
    scene = computeLayout(input.office, widthTiles);
    agents = new Map(
      (input.office?.rooms ?? []).flatMap((r) => r.teams.flatMap((t) => [t.lead, ...t.members])).map((a) => [a.id, a]),
    );
    const cssW = scene.widthTiles * TILE * input.scale;
    const cssH = scene.heightTiles * TILE * input.scale;
    canvas.style.width = `${cssW}px`;
    canvas.style.height = `${cssH}px`;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    laidOut = { office: input.office, widthPx: input.widthPx, scale: input.scale };
  };

  const frame = (now: number) => {
    raf = requestAnimationFrame(frame);
    if (now - last < 1000 / fps) return;
    last = now;
    if (!ctx) return;
    relayout();
    drawScene(ctx, {
      scene,
      agents,
      selectedId: input.selectedId,
      hoverId: input.hoverId,
      theme: input.theme,
      scale: input.scale * dpr,
      t: now,
    });
  };
  raf = requestAnimationFrame(frame);

  return {
    update(patch) {
      input = { ...input, ...patch };
    },
    hit(cssX, cssY) {
      return hitTest(scene, cssX, cssY, input.scale);
    },
    stop() {
      cancelAnimationFrame(raf);
    },
  };
}
