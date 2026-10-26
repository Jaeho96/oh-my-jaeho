/** 스냅샷에서 계산되는 값. 상태로 저장하지 않고 필요할 때 계산한다. */
import { STATUS_PRIORITY, statusVisual } from '../lib/status';
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

/** 사람이 먼저 봐야 하는 에이전트부터. 같은 상태면 안정된 id 순. */
export function sortByAttention(agents: Agent[]): Agent[] {
  return agents.toSorted(
    (a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id),
  );
}

export function agentName(agent: Agent): string {
  if (agent.nickname && agent.role) return `${agent.nickname} · ${agent.role}`;
  return agent.nickname ?? agent.title ?? agent.role ?? agent.id.slice(0, 8);
}

export function isWaiting(agent: Agent): boolean {
  return agent.status === 'permission' || agent.status === 'waiting';
}
export function attentionAgents(office: Office | null): Agent[] {
  return sortByAttention(listAgents(office).filter((a) => isWaiting(a) || a.status === 'stalled'));
}
export function activityText(agent: Agent): string | null {
  const text = agent.activity?.trim();
  return !text || text === agent.status || text === statusVisual(agent.status).label ? null : text;
}
export function newWaiting(previous: Map<string, string>, agents: Agent[]): string[] {
  return agents.filter((a) => previous.has(a.id) && previous.get(a.id) !== a.status && isWaiting(a)).map(agentName);
}
const priority = (agents: Agent[]) => Math.min(99, ...agents.map(rank));
export function groupedRooms(office: Office | null) {
  return (office?.rooms ?? []).map((room) => ({ ...room, teams: room.teams.toSorted((a, b) =>
    priority([a.lead, ...a.members]) - priority([b.lead, ...b.members]) || a.id.localeCompare(b.id))
  })).toSorted((a, b) => priority(a.teams.flatMap((t) => [t.lead, ...t.members])) - priority(b.teams.flatMap((t) => [t.lead, ...t.members])) || a.id.localeCompare(b.id));
}
