export interface DepthItem {
  id: string;
  y: number;
  layer: number;
}
export function depthOrder<T extends DepthItem>(items: T[]): T[] {
  return [...items].toSorted((a, b) => a.y - b.y || a.layer - b.layer || a.id.localeCompare(b.id));
}
