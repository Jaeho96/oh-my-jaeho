/**
 * 보드 서버(board.py · office.py)가 주는 데이터의 모양. 서버와 이름이 같아야 한다.
 * 외부 입력이므로 guards.ts 로 좁힌 뒤에만 이 타입이 된다.
 */

export const AGENT_STATUSES = [
  'typing',
  'reading',
  'thinking',
  'team',
  'waiting',
  'idle',
  'done',
  'stalled',
  'permission',
  'error',
] as const;
export type AgentStatus = (typeof AGENT_STATUSES)[number];

export interface ContextUsage {
  used: number;
  window: number | null;
  pct: number | null;
}

export interface Agent {
  id: string;
  provider: string | null;
  kind: 'lead' | 'subagent';
  parent: string | null;
  machine: string;
  role: string | null;
  nickname: string | null;
  title: string | null;
  cwd: string | null;
  model: string | null;
  effort: string | null;
  status: AgentStatus;
  activity: string | null;
  context: ContextUsage | null;
  tokens: { total: number | null; output: number | null } | null;
  lastMessage: string | null;
  startedAt: string | null;
  lastEventAt: string | null;
  errors: number;
}

export interface Team {
  id: string;
  provider: string | null;
  label: string;
  lead: Agent;
  members: Agent[];
}

export interface Room {
  id: string;
  label: string;
  teams: Team[];
  hidden: number;
  error: string | null;
}

export interface Office {
  rooms: Room[];
  counts: Partial<Record<AgentStatus, number>>;
  generatedAt: string | null;
  stallSec: number;
}

export interface RunMeta {
  mode: string | null;
  model: string | null;
  effort: string | null;
  write: boolean | null;
  task: string | null;
  exitCode: number | null;
  error: string | null;
}

export interface Run {
  name: string;
  state: string;
  elapsedSec: number | null;
  members: number;
  teamTokens: { total: number | null; output: number | null };
  meta: RunMeta;
}

export interface WikiTask {
  taskId: string;
  status: string | null;
  title: string;
  file: string;
  count: number;
  authors: string[];
  machine: string | null;
}

export interface SlotStatus {
  error: string | null;
}

export interface BoardSnapshot {
  generatedAt: string | null;
  office: Office | null;
  runs: Run[];
  wiki: WikiTask[];
  slots: Record<string, SlotStatus>;
}
