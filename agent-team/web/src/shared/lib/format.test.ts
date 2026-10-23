import { describe, expect, it } from 'vitest';

import { compactNumber, duration, relativeTime } from './format';

describe('compactNumber', () => {
  it('천·백만 단위를 줄여 쓴다', () => {
    expect(compactNumber(950)).toBe('950');
    expect(compactNumber(47_500)).toBe('47.5k');
    expect(compactNumber(3_193_660)).toBe('3.19M');
  });

  it('숫자가 아니면 줄표를 쓴다', () => {
    expect(compactNumber(null)).toBe('-');
  });
});

describe('relativeTime', () => {
  it('지금과의 차이를 초·분·시간으로 쓴다', () => {
    const now = Date.parse('2026-10-23T12:00:00Z');
    expect(relativeTime('2026-10-23T11:59:30Z', now)).toBe('30초 전');
    expect(relativeTime('2026-10-23T11:00:00Z', now)).toBe('1시간 전');
  });
});

describe('duration', () => {
  it('초를 분·초로 쓴다', () => {
    expect(duration(483)).toBe('8분 3초');
  });
});
