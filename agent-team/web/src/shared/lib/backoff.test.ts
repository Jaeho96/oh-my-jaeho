import { describe, expect, it } from 'vitest';

import { nextDelayMs } from './backoff';

describe('nextDelayMs', () => {
  it('첫 시도는 기본값의 절반에서 기본값 사이로 기다린다', () => {
    expect(nextDelayMs(0, { random: () => 0 })).toBe(500);
    expect(nextDelayMs(0, { random: () => 1 })).toBe(1_000);
  });

  it('시도할수록 두 배씩 늘지만 최대값을 넘지 않는다', () => {
    expect(nextDelayMs(3, { random: () => 1 })).toBe(8_000);
    expect(nextDelayMs(20, { random: () => 1 })).toBe(30_000);
  });
});
