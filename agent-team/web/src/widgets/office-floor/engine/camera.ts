import type { Office } from '../../../entities/board';
import { TILE } from './layout';
import type { Point, Scene } from './sceneTypes';
export interface Camera {
  x: number;
  y: number;
  zoom: number;
  width: number;
  height: number;
  dpr: number;
}
export function fitZoom(worldWidth: number, worldHeight: number, width: number, height: number): number {
  return Math.max(1, Math.floor(Math.min(width / worldWidth, height / worldHeight)));
}
export function worldToScreen(p: Point, c: Camera): Point {
  return { x: (p.x - c.x) * c.zoom, y: (p.y - c.y) * c.zoom };
}
export function screenToWorld(p: Point, c: Camera): Point {
  return { x: p.x / c.zoom + c.x, y: p.y / c.zoom + c.y };
}
export function centerCamera(width: number, height: number, c: Camera): Camera {
  const x = Math.round((width - c.width / c.zoom) / 2 * c.dpr) / c.dpr;
  const y = Math.round((height - c.height / c.zoom) / 2 * c.dpr) / c.dpr;
  return { ...c, x, y };
}

/** 좁은 화면에서는 대기 인원이 가장 많은 방부터 읽을 수 있게 보여 준다. */
export function cameraTarget(scene: Scene, office: Office | null, roomId: string | null, width: number, height = Infinity, viewportWidth = width) {
  const chosen = scene.rooms.find(room => room.roomId === roomId);
  if (chosen || viewportWidth > 767 || fitZoom(scene.widthTiles * TILE, scene.heightTiles * TILE, width, height) >= 2) return chosen;
  const waiting = (id: string) => office?.rooms.find(room => room.id === id)?.teams.flatMap(team => [team.lead, ...team.members])
    .filter(agent => ['permission', 'waiting', 'stalled'].includes(agent.status)).length ?? 0;
  return [...scene.rooms].toSorted((a, b) => waiting(b.roomId) - waiting(a.roomId))[0];
}
/** 방의 절대 좌표를 기준으로 맞춤 배율과 수동 배율 모두 중앙을 유지한다. */
export function focusCamera(scene: Scene, office: Office | null, roomId: string | null, scale: number, camera: Camera, viewportWidth = camera.width): Camera {
  const room = cameraTarget(scene, office, roomId, camera.width, camera.height, viewportWidth);
  const worldWidth = (room?.w ?? scene.widthTiles) * TILE;
  const worldHeight = (room?.h ?? scene.heightTiles) * TILE;
  const minimum = viewportWidth <= 767 ? 2 : 1;
  const zoom = scale || Math.max(minimum, fitZoom(worldWidth, worldHeight, camera.width, camera.height));
  const centered = centerCamera(worldWidth, worldHeight, { ...camera, zoom });
  return { ...centered, x: centered.x + (room?.x ?? 0) * TILE, y: centered.y + (room?.y ?? 0) * TILE };
}
