import type { AgentStatus } from '../../../entities/board';
export type Pose = 'stand' | 'walk' | 'sit' | 'type' | 'read';
export interface Behavior {
  pose: Pose;
  bubble: string | null;
  frozen: boolean;
}
export function deriveBehavior(status: AgentStatus): Behavior {
  switch (status) {
    case 'typing': return { pose: 'type', bubble: null, frozen: false };
    case 'reading': return { pose: 'read', bubble: null, frozen: false };
    case 'thinking': return { pose: 'sit', bubble: '···', frozen: false };
    case 'team': return { pose: 'sit', bubble: '팀', frozen: false };
    case 'waiting': return { pose: 'sit', bubble: '?', frozen: false };
    case 'permission': return { pose: 'stand', bubble: '!', frozen: true };
    case 'stalled': return { pose: 'sit', bubble: 'Ⅱ', frozen: true };
    case 'error': return { pose: 'stand', bubble: '×', frozen: true };
    case 'idle': return { pose: 'sit', bubble: null, frozen: false };
    case 'done': return { pose: 'sit', bubble: '✓', frozen: false };
    default: {
      const unreachable: never = status;
      return unreachable;
    }
  }
}
