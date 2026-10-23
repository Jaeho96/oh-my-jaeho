import { describe, expect, it } from 'vitest';

import { readConnectionConfig } from './config';

describe('readConnectionConfig', () => {
  it('주소창의 t 값을 토큰으로 읽는다', () => {
    expect(readConnectionConfig('?t=abc')).toEqual({ ok: true, token: 'abc' });
  });

  it('토큰이 없거나 비면 없다고 알린다', () => {
    expect(readConnectionConfig('')).toEqual({ ok: false, reason: 'missing-token' });
    expect(readConnectionConfig('?t=%20')).toEqual({ ok: false, reason: 'missing-token' });
  });
});
