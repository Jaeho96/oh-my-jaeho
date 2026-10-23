/**
 * 서버 응답(unknown) → 타입. `as` 로 덮지 않고 필드마다 확인한다.
 * 모르는 상태 이름은 버리지 않고 idle 로 바꿔 화면이 깨지지 않게 한다 — 대신 unknownStatuses 로 알린다.
 */
import {
  AGENT_STATUSES,
  type Agent,
  type AgentStatus,
  type BoardSnapshot,
  type ContextUsage,
  type Office,
  type Room,
  type Run,
  type Team,
  type WikiTask,
} from './types';

type Json = Record<string, unknown>;

const isObject = (v: unknown): v is Json => typeof v === 'object' && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

export const isAgentStatus = (v: unknown): v is AgentStatus =>
  typeof v === 'string' && (AGENT_STATUSES as readonly string[]).includes(v);

function parseContext(v: unknown): ContextUsage | null {
  if (!isObject(v)) return null;
  const used = num(v.used);
  return used === null ? null : { used, window: num(v.window), pct: num(v.pct) };
}

export function parseAgent(v: unknown, unknownStatuses: Set<string>): Agent | null {
  if (!isObject(v) || typeof v.id !== 'string') return null;
  let status: AgentStatus = 'idle';
  if (isAgentStatus(v.status)) status = v.status;
  else if (typeof v.status === 'string') unknownStatuses.add(v.status);
  const tokens = isObject(v.tokens) ? { total: num(v.tokens.total), output: num(v.tokens.output) } : null;
  return {
    id: v.id,
    provider: str(v.provider),
    kind: v.kind === 'subagent' ? 'subagent' : 'lead',
    parent: str(v.parent),
    machine: str(v.machine) ?? 'local',
    role: str(v.role),
    nickname: str(v.nickname),
    title: str(v.title),
    cwd: str(v.cwd),
    model: str(v.model),
    effort: str(v.effort),
    status,
    activity: str(v.activity),
    context: parseContext(v.context),
    tokens,
    lastMessage: str(v.lastMessage),
    startedAt: str(v.startedAt),
    lastEventAt: str(v.lastEventAt),
    errors: num(v.errors) ?? 0,
  };
}

function parseTeam(v: unknown, unknownStatuses: Set<string>): Team | null {
  if (!isObject(v) || typeof v.id !== 'string') return null;
  const lead = parseAgent(v.lead, unknownStatuses);
  if (lead === null) return null;
  const members = list(v.members)
    .map((m) => parseAgent(m, unknownStatuses))
    .filter((m): m is Agent => m !== null);
  return { id: v.id, provider: str(v.provider), label: str(v.label) ?? lead.id, lead, members };
}

function parseRoom(v: unknown, unknownStatuses: Set<string>): Room | null {
  if (!isObject(v) || typeof v.id !== 'string') return null;
  return {
    id: v.id,
    label: str(v.label) ?? v.id,
    teams: list(v.teams)
      .map((t) => parseTeam(t, unknownStatuses))
      .filter((t): t is Team => t !== null),
    hidden: num(v.hidden) ?? 0,
    error: str(v.error),
  };
}

export function parseOffice(v: unknown, unknownStatuses: Set<string>): Office | null {
  if (!isObject(v)) return null;
  const counts: Office['counts'] = {};
  if (isObject(v.counts)) {
    for (const [k, n] of Object.entries(v.counts)) {
      if (isAgentStatus(k) && typeof n === 'number') counts[k] = n;
    }
  }
  return {
    rooms: list(v.rooms)
      .map((r) => parseRoom(r, unknownStatuses))
      .filter((r): r is Room => r !== null),
    counts,
    generatedAt: str(v.generatedAt),
    stallSec: num(v.stallSec) ?? 600,
  };
}

function parseRun(v: unknown): Run | null {
  if (!isObject(v) || typeof v.name !== 'string') return null;
  const meta = isObject(v.meta) ? v.meta : {};
  const tt = isObject(v.team_tokens) ? v.team_tokens : {};
  return {
    name: v.name,
    state: str(v.state) ?? 'unknown',
    elapsedSec: num(v.elapsed_sec),
    members: num(v.members) ?? 0,
    teamTokens: { total: num(tt.total_tokens), output: num(tt.output_tokens) },
    meta: {
      mode: str(meta.mode),
      model: str(meta.model),
      effort: str(meta.effort),
      write: typeof meta.write === 'boolean' ? meta.write : null,
      task: str(meta.task),
      exitCode: num(meta.exit_code),
      error: str(meta.error),
    },
  };
}

function parseWikiTask(v: unknown): WikiTask | null {
  if (!isObject(v) || typeof v.task_id !== 'string' || !isObject(v.latest)) return null;
  return {
    taskId: v.task_id,
    status: str(v.latest.status),
    title: str(v.latest.title) ?? '',
    file: str(v.latest.file) ?? '',
    count: num(v.count) ?? 1,
    authors: list(v.authors).filter((a): a is string => typeof a === 'string'),
    machine: str(v.latest.machine),
  };
}

export type ParseResult =
  | { ok: true; snapshot: BoardSnapshot; unknownStatuses: string[] }
  | { ok: false; reason: string };

export function parseSnapshot(raw: string): ParseResult {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return { ok: false, reason: 'JSON 이 아니다' };
  }
  if (!isObject(data)) return { ok: false, reason: '객체가 아니다' };
  const unknownStatuses = new Set<string>();
  const slots: BoardSnapshot['slots'] = {};
  if (isObject(data.slots)) {
    for (const [k, s] of Object.entries(data.slots)) slots[k] = { error: isObject(s) ? str(s.error) : null };
  }
  return {
    ok: true,
    snapshot: {
      generatedAt: str(data.generatedAt),
      office: parseOffice(data.office, unknownStatuses),
      runs: list(data.runs)
        .map(parseRun)
        .filter((r): r is Run => r !== null),
      wiki: list(data.wiki)
        .map(parseWikiTask)
        .filter((w): w is WikiTask => w !== null),
      slots,
    },
    unknownStatuses: [...unknownStatuses],
  };
}
