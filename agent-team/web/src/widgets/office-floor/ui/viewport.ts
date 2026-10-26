/**
 * 사무실 칸이 쓸 수 있는 높이. 설계값 clamp(360px, 100dvh - 220px, 680px) 의 가운데 항이다.
 * 칸 위치 아래로 남은 화면으로 잡으면 대기 띠가 길어질수록 배율이 떨어진다(1680×843 에서 3배 → 2배).
 */
export function availableHeight(innerHeight: number): number {
  return innerHeight - 220;
}

/** 전체 보기의 정수 배율에 맞춰 높이를 정하고 설계 범위 안에 둔다. */
export function contentHeight(worldWidth: number, worldHeight: number, width: number, available: number, viewportWidth = width): number {
  const ceiling = Math.max(360, Math.min(680, available));
  if (worldWidth <= 0 || worldHeight <= 0 || width <= 0) return 384;
  const zoom = Math.max(1, Math.floor(Math.min(width / worldWidth, ceiling / worldHeight)));
  if (viewportWidth <= 767) return worldHeight * Math.max(2, zoom);
  return Math.min(ceiling, worldHeight * zoom);
}
