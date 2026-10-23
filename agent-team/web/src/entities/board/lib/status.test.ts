import { describe, expect, it } from 'vitest';

import { AGENT_STATUSES } from '../model/types';
import { STATUS_PRIORITY, statusVisual } from './status';

describe('statusVisual', () => {
  it('사람이 봐야 하는 상태는 주의 색으로 그린다', () => {
    expect(statusVisual('permission').tone).toBe('attention');
    expect(statusVisual('waiting').bubble).toBe('question');
    expect(statusVisual('stalled').bubble).toBe('zzz');
  });

  it('읽기와 쓰기를 다른 자세로 그린다', () => {
    expect(statusVisual('reading').pose).toBe('read');
    expect(statusVisual('typing').pose).toBe('type');
  });

  it('모든 상태가 우선순위 목록에 한 번씩 있다', () => {
    expect(STATUS_PRIORITY.toSorted()).toEqual(AGENT_STATUSES.toSorted());
  });
});
