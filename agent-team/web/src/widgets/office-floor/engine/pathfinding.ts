import { cellKey, type Point, type Scene } from './sceneTypes';
export type PathResult = {
  kind: 'arrived';
  path: Point[];
} | {
  kind: 'unreachable';
  path: Point[];
} | {
  kind: 'path';
  path: Point[];
};
export function findPath(scene: Scene, start: Point, target: Point, reservations = new Set<string>()): PathResult {
  if (cellKey(start) === cellKey(target)) {
    return { kind: 'arrived', path: [] };
  }
  const room = scene.rooms.find(r => start.x >= r.x && start.x < r.x + r.w && start.y >= r.y && start.y < r.y + r.h);
  if (!room) {
    return { kind: 'unreachable', path: [] };
  }
  const queue: Point[] = [start];
  const parents = new Map<string, Point>();
  const seen = new Set([cellKey(start)]);
  for (let i = 0; i < queue.length; i += 1) {
    const p = queue[i];
    for (const next of [{ x: p.x + 1, y: p.y }, { x: p.x, y: p.y + 1 }, { x: p.x - 1, y: p.y }, { x: p.x, y: p.y - 1 }]) {
      const key = cellKey(next);
      const inside = scene.rooms.some(r =>
        next.x >= r.x && next.x < r.x + r.w &&
        next.y >= r.y + 1 && next.y < r.y + r.h);
      if (seen.has(key) || !inside || (scene.blocked.has(key) && key !== cellKey(target)) || reservations.has(key)) {
        continue;
      }
      seen.add(key);
      parents.set(key, p);
      if (key === cellKey(target)) {
        const path = [next];
        let cursor = p;
        while (cellKey(cursor) !== cellKey(start)) {
          path.unshift(cursor);
          const prev = parents.get(cellKey(cursor));
          if (!prev) {
            break;
          }
          cursor = prev;
        }
        return { kind: 'path', path };
      }
      queue.push(next);
    }
  }
  return { kind: 'unreachable', path: [] };
}
