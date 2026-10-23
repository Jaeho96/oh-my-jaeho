/** 화면에 쓰는 짧은 표기. 계산만 하고 React 를 모른다. */

export function compactNumber(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

export function relativeTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '';
  const sec = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (sec < 60) return `${Math.round(sec)}초 전`;
  if (sec < 3_600) return `${Math.round(sec / 60)}분 전`;
  if (sec < 86_400) return `${Math.round(sec / 3_600)}시간 전`;
  return `${Math.round(sec / 86_400)}일 전`;
}

export function duration(sec: number | null | undefined): string {
  if (typeof sec !== 'number') return '-';
  if (sec < 60) return `${sec}초`;
  return `${Math.floor(sec / 60)}분 ${sec % 60}초`;
}
