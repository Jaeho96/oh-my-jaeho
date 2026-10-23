/**
 * 연결 설정은 주소창에서 한 번 읽는다. 토큰이 없으면 기본값으로 조용히 가지 않고 없다고 알린다.
 * 토큰은 화면 상태가 아니라 연결 계층으로만 넘긴다.
 */
export type ConnectionConfig = { ok: true; token: string } | { ok: false; reason: 'missing-token' };

export function readConnectionConfig(search: string): ConnectionConfig {
  const token = new URLSearchParams(search).get('t')?.trim();
  return token ? { ok: true, token } : { ok: false, reason: 'missing-token' };
}
