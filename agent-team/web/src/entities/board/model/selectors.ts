/** 스냅샷에서 계산되는 값. 상태로 저장하지 않고 필요할 때 계산한다. */
import { STATUS_PRIORITY } from '../lib/status';
import type { Agent, Office } from './types';

export function listAgents(office: Office | null): Agent[] {
  if (office === null) return [];
  return office.rooms.flatMap((room) => room.teams.flatMap((team) => [team.lead, ...team.members]));
}

export function findAgent(office: Office | null, id: string | null): Agent | null {
  if (id === null) return null;
  return listAgents(office).find((a) => a.id === id) ?? null;
}

const rank = (a: Agent) => STATUS_PRIORITY.indexOf(a.status);

/** 사람이 먼저 봐야 하는 에이전트부터. 같은 상태면 최근에 움직인 순. */
export function sortByAttention(agents: Agent[]): Agent[] {
  return agents.toSorted(
    (a, b) => rank(a) - rank(b) || (b.lastEventAt ?? '').localeCompare(a.lastEventAt ?? ''),
  );
}

export function agentName(agent: Agent): string {
  if (agent.nickname && agent.role) return `${agent.nickname} · ${agent.role}`;
  return agent.nickname ?? agent.title ?? agent.role ?? agent.id.slice(0, 8);
}
