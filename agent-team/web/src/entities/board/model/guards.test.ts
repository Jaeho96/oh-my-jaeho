import { describe, expect, it } from 'vitest';

import { parseSnapshot } from './guards';

const agent = (over: Record<string, unknown> = {}) => ({ id: 'a', kind: 'lead', status: 'typing', ...over });

describe('parseSnapshot', () => {
  it('서버 스냅샷을 방·팀·에이전트로 좁힌다', () => {
    const raw = JSON.stringify({
      generatedAt: '2026-10-23T21:00:00+09:00',
      office: { rooms: [{ id: 'local', label: '내 맥', teams: [{ id: 't', label: '팀', lead: agent(), members: [agent({ id: 'b', kind: 'subagent' })] }] }], counts: { typing: 2 } },
      runs: [{ name: 'r', state: 'done', elapsed_sec: 483, members: 3, team_tokens: { total_tokens: 3193660 }, meta: { mode: 'team' } }],
      wiki: [{ task_id: 'k', latest: { status: 'completed', title: 'T', file: 'f.md' }, count: 2, authors: ['claude-code'] }],
      slots: { office: { error: null } },
    });
    const result = parseSnapshot(raw);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const team = result.snapshot.office?.rooms[0].teams[0];
    expect(team?.members[0].kind).toBe('subagent');
    expect(result.snapshot.runs[0].teamTokens.total).toBe(3193660);
    expect(result.snapshot.wiki[0].taskId).toBe('k');
  });

  it('모르는 상태 이름은 idle 로 그리고 따로 알린다', () => {
    const raw = JSON.stringify({ office: { rooms: [{ id: 'local', teams: [{ id: 't', lead: agent({ status: 'dancing' }) }] }] } });
    const result = parseSnapshot(raw);
    expect(result.ok && result.snapshot.office?.rooms[0].teams[0].lead.status).toBe('idle');
    expect(result.ok && result.unknownStatuses).toEqual(['dancing']);
  });

  it('JSON 이 아니면 실패로 돌려준다', () => {
    expect(parseSnapshot('<html>')).toEqual({ ok: false, reason: 'JSON 이 아니다' });
  });

  it('필드가 비거나 모양이 틀린 항목은 건너뛴다', () => {
    const raw = JSON.stringify({ office: { rooms: [null, { id: 'r', teams: [{ id: 't' }, 'x'] }] }, runs: 'nope' });
    const result = parseSnapshot(raw);
    expect(result.ok && result.snapshot.office?.rooms).toEqual([{ id: 'r', label: 'r', teams: [], hidden: 0, error: null }]);
    expect(result.ok && result.snapshot.runs).toEqual([]);
  });
});

it('잘못된 대기 시각은 버리고 공백 결과 요약은 없는 값으로 처리한다',()=>{
 const result=parseSnapshot(JSON.stringify({office:{rooms:[{id:'r',teams:[{id:'t',lead:{id:'a',status:'waiting',statusChangedAt:'invalid'}}]}]},runs:[{name:'r',resultHead:'  '}]}));
 if(!result.ok)throw new Error('fixture');
 expect(result.snapshot.office?.rooms[0]?.teams[0]?.lead.statusChangedAt).toBeNull();
 expect(result.snapshot.runs[0]?.resultHead).toBeNull();
});
