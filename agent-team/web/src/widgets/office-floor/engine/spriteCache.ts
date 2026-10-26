/** 논리 해상도 캔버스 캐시. 확대와 DPR에 독립적이며 최대 32 MiB다. */
export class SpriteCache {
  private entries = new Map<string, HTMLCanvasElement>();
  private bytes = 0;
  private budget: number;
  constructor(budget = 32 * 1024 * 1024) {
    this.budget = budget;
  }
  get(key: string, width: number, height: number, paint: (ctx: CanvasRenderingContext2D) => void): HTMLCanvasElement | null {
    const cost = width * height * 4;
    if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width <= 0 || height <= 0 || !Number.isSafeInteger(cost) || cost > this.budget) {
      return null;
    }
    const found = this.entries.get(key);
    if (found) {
      return found;
    }
    // 새 캔버스를 만들기 전에 비워 순간 할당도 예산 안에 둔다.
    while (this.bytes + cost > this.budget) {
      const first = this.entries.keys().next().value;
      if (first === undefined) {
        break;
      }
      const old = this.entries.get(first);
      if (old) {
        this.bytes -= old.width * old.height * 4;
        old.width = 0;
        old.height = 0;
      }
      this.entries.delete(first);
    }
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      canvas.width = 0;
      canvas.height = 0;
      return null;
    }
    paint(ctx);
    this.entries.set(key, canvas);
    this.bytes += cost;
    return canvas;
  }
  clear(): void {
    for (const canvas of this.entries.values()) {
      canvas.width = 0;
      canvas.height = 0;
    }
    this.entries.clear();
    this.bytes = 0;
  }
  get byteLength(): number {
    return this.bytes;
  }
}
