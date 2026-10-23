/**
 * 재연결 대기 시간 — 지수 증가에 전체 지터를 얹는다.
 * attempt 0 이면 base 근처, 이후 두 배씩 늘되 max 를 넘지 않는다. random 은 시험에서 바꿔 끼운다.
 */
export function nextDelayMs(
  attempt: number,
  { baseMs = 1_000, maxMs = 30_000, random = Math.random }: { baseMs?: number; maxMs?: number; random?: () => number } = {},
): number {
  const ceiling = Math.min(maxMs, baseMs * 2 ** Math.max(0, attempt));
  return Math.round(ceiling / 2 + random() * (ceiling / 2));
}
