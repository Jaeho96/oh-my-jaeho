import type { Office } from '../../../entities/board';
import { cameraTarget, focusCamera, type Camera } from './camera';
import { hitActor } from './hitTest';
import { TILE, computeLayout } from './layout';
import type { OfficeTheme } from './palette';
import { createRenderCache, drawScene } from './renderer';
import type { Point } from './sceneTypes';
import { advanceSimulation, createSimulation, officeAgents } from './simulation';
export interface LoopInput {
  office: Office | null;
  selectedId: string | null;
  hoverId: string | null;
  theme: OfficeTheme;
  scale: number;
  widthPx: number;
  viewportWidth?: number;
  heightPx: number;
  reduced: boolean;
  roomId: string | null;
  onLayout?: (worldWidth: number, worldHeight: number) => void;
}
export interface OfficeLoop {
  update(patch: Partial<LoopInput>): void;
  hit(x: number, y: number): string | null;
  pan(x: number, y: number): void;
  stop(): void;
}
export function compositionKey(office: Office | null): string {
  return (office?.rooms ?? []).flatMap(r => r.teams.flatMap(t => [t.lead, ...t.members].map(a => `${r.id}/${t.id}/${a.id}/${a.status === 'done'}`))).toSorted().join('|');
}
export function startOfficeLoop(canvas: HTMLCanvasElement, initial: LoopInput): OfficeLoop {
  const ctx = canvas.getContext('2d');
  let input = initial;
  let scene = computeLayout(initial.office);
  let agents = officeAgents(initial.office);
  const sim = createSimulation();
  const cache = createRenderCache();
  let key = compositionKey(initial.office);
  let width = 0;
  let height = 0;
  let last = 0;
  let elapsed = 0;
  let raf = 0;
  let shrinkAt = 0;
  let camera: Camera = { x: 0, y: 0, zoom: 3, width: initial.widthPx, height: initial.heightPx, dpr: window.devicePixelRatio || 1 };
  let cameraDirty = true;
  let previousSelected: string | null = null;
  let selectedAnchor: Point | null = null;
  const relayout = (keepSpace: boolean) => {
    const selected = input.selectedId ? sim.actors.get(input.selectedId) : null;
    if (selected) {
      selectedAnchor = { x: (selected.x - camera.x) * camera.zoom, y: (selected.y - camera.y) * camera.zoom };
    }
    const previous = scene;
    scene = computeLayout(input.office, Math.max(24, Math.floor(width / (TILE * 3))), previous, keepSpace);
    for (const actor of sim.actors.values()) {
      const oldRoom = previous.rooms.find(r => r.roomId === actor.roomId);
      const newRoom = scene.rooms.find(r => r.roomId === actor.roomId);
      if (oldRoom && newRoom) {
        actor.x += (newRoom.x - oldRoom.x) * TILE;
        actor.y += (newRoom.y - oldRoom.y) * TILE;
        actor.path = [];
        actor.target = '';
      }
    }
    cameraDirty = true;
  };
  const frame = (now: number) => {
    raf = requestAnimationFrame(frame);
    if (document.hidden) {
      last = now;
      return;
    }
    const dt = last ? Math.min(.05, (now - last) / 1000) : 0;
    last = now;
    elapsed += dt * 1000;
    const dpr = window.devicePixelRatio || 1;
    if (width !== input.widthPx || height !== input.heightPx || camera.dpr !== dpr) {
      const reflow = width !== input.widthPx;
      width = Math.max(1, input.widthPx);
      height = Math.max(1, input.heightPx);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      camera = { ...camera, width, height, dpr };
      cameraDirty = true;
      if (reflow) {
        relayout(true);
      }
    }
    const nextKey = compositionKey(input.office);
    if (key !== nextKey) {
      relayout(true);
      key = nextKey;
      shrinkAt = elapsed + 30000;
      cameraDirty = true;
    }
    if (shrinkAt && elapsed >= shrinkAt && ![...sim.actors.values()].some(a => a.pose === 'walk')) {
      relayout(false);
      shrinkAt = 0;
      cameraDirty = true;
    }
    if (cameraDirty) {
      const room = cameraTarget(scene, input.office, input.roomId, width, height, input.viewportWidth ?? width);
      const worldWidth = (room?.w ?? scene.widthTiles) * TILE;
      const worldHeight = (room?.h ?? scene.heightTiles) * TILE;
      input.onLayout?.(worldWidth, worldHeight);
      camera = focusCamera(scene, input.office, input.roomId, input.scale, camera, input.viewportWidth ?? width);
      if (selectedAnchor && input.selectedId && input.scale !== 0) {
        const selected = sim.actors.get(input.selectedId);
        if (selected) {
          camera.x = selected.x - selectedAnchor.x / camera.zoom;
          camera.y = selected.y - selectedAnchor.y / camera.zoom;
        }
        selectedAnchor = null;
      }
      cameraDirty = false;
    }
    advanceSimulation(sim, scene, agents, elapsed, dt, input.selectedId, input.reduced);
    if (input.selectedId !== previousSelected) {
      previousSelected = input.selectedId;
      const a = input.selectedId ? sim.actors.get(input.selectedId) : null;
      if (a && (a.x < camera.x || a.x > camera.x + width / camera.zoom || a.y < camera.y || a.y > camera.y + height / camera.zoom)) {
        camera.x = Math.round(a.x - width / camera.zoom / 2);
        camera.y = Math.round(a.y - height / camera.zoom / 2);
      }
    }
    if (ctx) {
      drawScene(ctx, { scene, agents, simulation: sim, selectedId: input.selectedId, hoverId: input.hoverId, theme: input.theme, camera, t: elapsed, reduced: input.reduced }, cache);
    }
  };
  raf = requestAnimationFrame(frame);
  return {
    update(patch) {
      if (patch.office !== undefined) {
        agents = officeAgents(patch.office);
      }
      if (patch.scale !== undefined || patch.roomId !== undefined) {
        selectedAnchor = null;
        cameraDirty = true;
      }
      if (patch.theme && patch.theme !== input.theme) {
        cache.sprites.clear();
        cache.floorKey = '';
      }
      input = { ...input, ...patch };
    },
    hit(x, y) {
      const label = cache.labels.find(b => x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + Math.max(24, b.h));
      if (label) {
        return label.id;
      }
      return hitActor([...sim.actors.values()], x, y, camera, input.selectedId);
    },
    pan(x, y) {
      camera.x -= x / camera.zoom;
      camera.y -= y / camera.zoom;
    },
    stop() {
      cancelAnimationFrame(raf);
      cache.sprites.clear();
      cache.floor = null;
    },
  };
}
