/**
 * 캐릭터와 사무실의 색. 그림 파일 없이 코드로 그린다(외부 에셋 라이선스를 피한다).
 * 머리색은 공급자(Claude·Codex), 셔츠색은 역할로 고른다.
 */
import type { Agent, Tone } from '../../../entities/board';

export interface CharacterColors {
  hair: string;
  skin: string;
  shirt: string;
  outline: string;
}

const HAIR: Record<string, string> = { claude: '#c96442', codex: '#0f8f6e' };
const SHIRT: Record<string, string> = {
  lead: '#6366f1',
  explorer: '#0ea5e9',
  Explore: '#0ea5e9',
  worker: '#f59e0b',
  reviewer: '#ef4444',
  'general-purpose': '#a855f7',
  Plan: '#14b8a6',
};

export function characterColors(agent: Agent): CharacterColors {
  const roleKey = agent.kind === 'lead' ? 'lead' : (agent.role ?? '');
  return {
    hair: HAIR[agent.provider ?? ''] ?? '#475569',
    skin: '#f2c9a0',
    shirt: SHIRT[roleKey] ?? '#94a3b8',
    outline: '#1f2937',
  };
}

export const TONE_COLOR: Record<Tone, string> = {
  busy: '#3b82f6',
  calm: '#94a3b8',
  attention: '#f59e0b',
  good: '#22c55e',
  bad: '#ef4444',
};

export interface OfficeTheme {
  floorA: string;
  floorB: string;
  wall: string;
  wallTrim: string;
  desk: string;
  deskEdge: string;
  chair: string;
  rugClaude: string;
  rugCodex: string;
  rugOther: string;
  text: string;
  plate: string;
  select: string;
}

export const LIGHT: OfficeTheme = {
  floorA: '#e9e4da',
  floorB: '#e1dbcf',
  wall: '#b9c3d1',
  wallTrim: '#8f9bad',
  desk: '#a0743f',
  deskEdge: '#7a5428',
  chair: '#4b5563',
  rugClaude: 'rgba(201,100,66,0.14)',
  rugCodex: 'rgba(15,143,110,0.14)',
  rugOther: 'rgba(100,116,139,0.14)',
  text: '#1f2937',
  plate: '#f8fafc',
  select: '#6366f1',
};

export const DARK: OfficeTheme = {
  floorA: '#23262e',
  floorB: '#1f2229',
  wall: '#343b48',
  wallTrim: '#4a5466',
  desk: '#6b4c2a',
  deskEdge: '#4d3519',
  chair: '#111827',
  rugClaude: 'rgba(201,100,66,0.18)',
  rugCodex: 'rgba(15,143,110,0.2)',
  rugOther: 'rgba(148,163,184,0.12)',
  text: '#e5e7eb',
  plate: '#1f2937',
  select: '#a5b4fc',
};
