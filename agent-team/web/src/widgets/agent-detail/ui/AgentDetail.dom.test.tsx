import { act, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { receiveSnapshot } from '../../../entities/board';
import { selectAgent } from '../../../features/select-agent';
import { AgentDetail } from './AgentDetail';

const office = (lead: Record<string, unknown>) =>
  JSON.stringify({ office: { rooms: [{ id: 'local', teams: [{ id: 't', lead }] }] } });

describe('AgentDetail', () => {
  it('고르기 전에는 고르는 법을 알려 준다', () => {
    render(<AgentDetail />);
    expect(screen.getByText(/캐릭터를 누르거나/)).toBeInTheDocument();
  });

  it('고른 에이전트의 상태·하는 일·컨텍스트를 보여 준다', () => {
    receiveSnapshot(
      office({ id: 'a', kind: 'lead', status: 'reading', nickname: 'Huygens', role: 'explorer', activity: 'rg', context: { used: 47500, window: 475000, pct: 10 } }),
    );
    render(<AgentDetail />);
    act(() => selectAgent('a'));
    const panel = screen.getByRole('region', { name: '에이전트 상세' });
    expect(panel).toHaveTextContent('Huygens · explorer');
    expect(panel).toHaveTextContent('읽는 중');
    expect(panel).toHaveTextContent('47.5k (10%)');
  });

  it('고른 에이전트가 사무실에서 사라지면 없다고 말한다', () => {
    receiveSnapshot(office({ id: 'a', kind: 'lead', status: 'idle' }));
    render(<AgentDetail />);
    act(() => selectAgent('a'));
    act(() => receiveSnapshot(office({ id: 'b', kind: 'lead', status: 'idle' })));
    expect(screen.getByText('이 에이전트는 지금 사무실에 없습니다.')).toBeInTheDocument();
  });
});
