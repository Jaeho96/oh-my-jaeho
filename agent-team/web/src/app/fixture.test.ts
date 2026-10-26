import { describe, expect, it } from 'vitest';
import { listAgents, subscribeBoard, type BoardState } from '../entities/board';
import { loadBusyFixture } from './fixture';

describe('개발 예시', () => {
  it('서버 없이 정상 연결 상태로 두 방 세 팀 열두 명과 실행 기록을 제공한다', async () => {
    let state: BoardState | null = null;
    const unsubscribe = subscribeBoard((value) => { state = value; });
    const stop = loadBusyFixture();
    await Promise.resolve();
    await Promise.resolve();
    function current(): BoardState {
      if (!state) throw new Error('스냅샷 없음');
      return state;
    }
    const office = current().snapshot?.office ?? null;
    expect(current().connection.kind).toBe('open');
    expect(office?.rooms).toHaveLength(2);
    expect(office?.rooms.flatMap((room) => room.teams)).toHaveLength(3);
    expect(listAgents(office)).toHaveLength(12);
    expect(office?.counts.permission).toBe(1);
    expect(office?.counts.done).toBe(1);
    expect(current().snapshot?.runs).toHaveLength(3);
    expect(current().snapshot?.wiki).toHaveLength(6);
    stop();
    unsubscribe();
  });
});
