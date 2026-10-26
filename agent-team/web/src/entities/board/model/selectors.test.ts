import { describe, expect, it } from 'vitest';
import { parseSnapshot } from './guards';
import { activityText, attentionAgents, groupedRooms, listAgents, newWaiting } from './selectors';
function office(status = 'typing') { const parsed = parseSnapshot(JSON.stringify({ office: { rooms: [{ id: 'a', teams: [{ id: 'a', lead: { id: 'a', status, activity: status } }] }, { id: 'b', teams: [{ id: 'b', lead: { id: 'b', status: 'permission' } }, { id: 'c', lead: { id: 'c', status: 'error' } }] }] } })); if (!parsed.ok)
    {throw new Error('fixture');} return parsed.snapshot.office; }
describe('페이지 선택자', () => {
    it('대기자를 우선하되 방과 팀 관계를 보존한다', () => { const rooms = groupedRooms(office()); expect(rooms.map((r) => r.id)).toEqual(['b', 'a']); expect(rooms[0]?.teams.map((t) => t.id)).toEqual(['b', 'c']); expect(attentionAgents(office()).map((a) => a.id)).toEqual(['b']); });
    it('처음 등장한 대기자는 알리지 않고 기존 사람의 전환만 알린다', () => { const previous = new Map([['a', 'typing'], ['b', 'permission']]); expect(newWaiting(previous, listAgents(office('waiting')))).toEqual(['a']); expect(newWaiting(new Map(), listAgents(office('waiting')))).toEqual([]); expect(newWaiting(new Map([['a', 'waiting'], ['b', 'permission']]), listAgents(office('waiting')))).toEqual([]); });
    it('상태와 같은 활동은 생략한다', () => { const agent = listAgents(office())[0]; if (!agent)
        {throw new Error('fixture');} expect(activityText(agent)).toBeNull(); expect(activityText({ ...agent, activity: '파일 검사' })).toBe('파일 검사'); });
});
