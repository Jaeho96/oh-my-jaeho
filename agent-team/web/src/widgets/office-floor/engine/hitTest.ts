import { screenToWorld, type Camera } from './camera';
import type { Actor } from './simulation';
export function hitActor(actors: Actor[], x: number, y: number, camera: Camera, selectedId: string | null = null): string | null {
  const p = screenToWorld({ x, y }, camera);
  const half = Math.max(8, 12 / camera.zoom);
  return [...actors].toSorted((a, b) => b.y - a.y).find(a => (a.phase !== 'exited' || a.id === selectedId) && Math.abs(p.x - a.x) <= half && p.y >= a.y - 32 && p.y <= a.y + 3)?.id ?? null;
}
