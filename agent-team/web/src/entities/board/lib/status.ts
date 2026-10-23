/**
 * 상태 → 말과 그림. 모든 상태를 switch 로 다루고 never 로 닫는다 — 서버에 상태가 늘면 여기서 타입 오류가 난다.
 */
import type { AgentStatus } from '../model/types';

export type Pose = 'type' | 'read' | 'sit' | 'lean';
export type Bubble = 'dots' | 'question' | 'team' | 'alert' | 'check' | 'zzz' | 'cross' | null;
export type Tone = 'busy' | 'calm' | 'attention' | 'good' | 'bad';

export interface StatusVisual {
  label: string;
  pose: Pose;
  bubble: Bubble;
  tone: Tone;
}

export function statusVisual(status: AgentStatus): StatusVisual {
  switch (status) {
    case 'typing':
      return { label: '작업 중', pose: 'type', bubble: null, tone: 'busy' };
    case 'reading':
      return { label: '읽는 중', pose: 'read', bubble: null, tone: 'busy' };
    case 'thinking':
      return { label: '생각 중', pose: 'sit', bubble: 'dots', tone: 'busy' };
    case 'team':
      return { label: '팀 기다림', pose: 'sit', bubble: 'team', tone: 'busy' };
    case 'waiting':
      return { label: '입력 기다림', pose: 'sit', bubble: 'question', tone: 'attention' };
    case 'permission':
      return { label: '승인 기다림', pose: 'sit', bubble: 'alert', tone: 'attention' };
    case 'stalled':
      return { label: '멈춤 의심', pose: 'lean', bubble: 'zzz', tone: 'attention' };
    case 'done':
      return { label: '끝', pose: 'lean', bubble: 'check', tone: 'good' };
    case 'error':
      return { label: '오류', pose: 'sit', bubble: 'cross', tone: 'bad' };
    case 'idle':
      return { label: '쉬는 중', pose: 'lean', bubble: null, tone: 'calm' };
    default: {
      const unreachable: never = status;
      return unreachable;
    }
  }
}

/** 사람이 먼저 봐야 하는 순서. 목록 정렬에 쓴다. */
export const STATUS_PRIORITY: readonly AgentStatus[] = [
  'permission',
  'waiting',
  'stalled',
  'error',
  'typing',
  'reading',
  'thinking',
  'team',
  'done',
  'idle',
];
