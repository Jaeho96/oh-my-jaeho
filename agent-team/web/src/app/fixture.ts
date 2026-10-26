import { connectBoard, type AgentStatus } from '../entities/board';
import type { EventSourceLike } from '../shared/api';

/** Generic development-only data; App's DEV branch excludes this module from production. */
export function loadBusyFixture(): () => void {
  const now = Date.now();
  const stamp = (minutes: number) => new Date(now - minutes * 60000).toISOString();
  const statuses: AgentStatus[] = [
    'permission', 'waiting', 'stalled', 'error', 'typing', 'reading',
    'thinking', 'team', 'idle', 'done', 'typing', 'reading',
  ];
  const names = [
    '화면 리드', '검토자', '구현 담당', '검증 담당', '자료 조사', '문서 담당',
    '설계 담당', '테스트 담당', '분석 담당', '완료 담당', '화면 담당', '품질 담당',
  ];
  const agents = names.map((nickname, index) => ({
    id: `demo-${index}`, nickname, provider: index < 8 ? 'codex' : 'claude',
    kind: index % 4 === 0 ? 'lead' : 'subagent',
    parent: index % 4 === 0 ? null : `demo-${Math.floor(index / 4) * 4}`,
    role: index % 4 === 0 ? '총괄' : '팀원', machine: index < 8 ? 'room-a' : 'room-b',
    status: statuses[index], statusChangedAt: stamp(8), lastEventAt: stamp(12),
    activity: index === 4 ? '화면 구성 구현' : statuses[index],
    model: '개발 예시 모델', effort: 'high', context: { used: 48000, window: 200000, pct: 24 },
    tokens: { total: 68000, output: 12000 },
    lastMessage: index === 9 ? '완료 — 결과와 검증 내용을 정리했습니다.' : null,
  }));
  const counts: Partial<Record<AgentStatus, number>> = {};
  for (const status of statuses) counts[status] = (counts[status] ?? 0) + 1;
  const teams = [0, 1, 2].map((index) => ({
    id: `team-${index}`, label: ['화면 팀', '엔진 팀', '검증 팀'][index],
    provider: index === 2 ? 'claude' : 'codex', lead: agents[index * 4],
    members: agents.slice(index * 4 + 1, index * 4 + 4),
  }));
  const raw = JSON.stringify({
    generatedAt: stamp(0),
    office: {
      generatedAt: stamp(0), stallSec: 600, counts,
      rooms: [
        { id: 'room-a', label: '작업실', teams: teams.slice(0, 2), hidden: 0, error: null },
        { id: 'room-b', label: '검토실', teams: teams.slice(2), hidden: 0, error: null },
      ],
    },
    runs: [0, 1, 2].map((index) => ({
      name: `demo-run-${index}`, state: index === 2 ? 'running' : 'done',
      elapsed_sec: 360 + index * 60, members: index === 0 ? 3 : 0,
      team_tokens: { total_tokens: 180000 + index * 10000 },
      resultHead: index === 2 ? '검증을 진행하고 있습니다.' : '완료 — 구현과 기본 검증을 마쳤습니다.',
      meta: {
        mode: index === 0 ? 'team' : 'single', model: '개발 예시 모델', effort: 'high', write: index === 0,
        task: ['화면 접근성 검토', '사무실 구현', '결과 검증'][index] + '\n세부 과제 원문은 기본적으로 접혀 있습니다.',
        exit_code: index === 2 ? null : 0,
      },
    })),
    wiki: [0, 1, 2, 3, 4, 5].map((index) => ({
      task_id: `demo-task-${index}`, count: index + 1, authors: ['작성자'],
      latest: {
        title: [
          '대기 알림 검증을 완료했습니다', '방 배치를 구현했습니다', '접근성을 점검했습니다',
          '실행 비교를 검토했습니다', '모바일 화면을 조정했습니다', '결과 보고를 정리했습니다',
        ][index],
        status: index < 4 ? 'completed' : 'progress', file: 'example.md', machine: '개발 예시',
      },
    })),
    slots: {},
  });
  // Exercise the normal store/parser path with an in-memory transport and no network.
  const source: EventSourceLike = {
    readyState: 1,
    addEventListener(type, listener) { if (type === 'open') queueMicrotask(() => listener(new MessageEvent('open'))); },
    close() {},
  };
  return connectBoard({
    token: 'fixture',
    deps: { fetchText: () => Promise.resolve({ status: 200, text: raw }), createEventSource: () => source },
  });
}
