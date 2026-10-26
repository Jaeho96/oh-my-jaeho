import type { Agent, Office } from '../../../entities/board';
export const makeAgent = (id: string, status: Agent['status'] = 'typing', kind: Agent['kind'] = 'subagent'): Agent => ({
  id, provider: 'codex', kind, parent: null, machine: 'local', role: 'worker', nickname: null, title: null, cwd: null, model: null, effort: null,
  status, activity: null, context: null, tokens: null, lastMessage: null, startedAt: null, lastEventAt: null, errors: 0,
});
export const makeOffice = (n: number, rooms = 1): Office => ({
  rooms: Array.from({ length: rooms }, (_, r) => ({ id: `r${r}`, label: `방 ${r}`, hidden: 0, error: null,
    teams: n ? [{ id: `t${r}`, provider: 'codex', label: '구현 팀', lead: makeAgent(`${r}-0`, 'typing', 'lead'),
        members: Array.from({ length: n - 1 }, (_member, i) => makeAgent(`${r}-${i + 1}`)) }] : [] })),
  counts: {}, generatedAt: null, stallSec: 600,
});
