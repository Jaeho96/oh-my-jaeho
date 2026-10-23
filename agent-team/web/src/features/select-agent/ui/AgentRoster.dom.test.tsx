import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { receiveSnapshot } from '../../../entities/board';
import { AgentRoster } from './AgentRoster';

const snapshot = (agents: Record<string, unknown>[]) =>
  JSON.stringify({
    office: {
      rooms: [{ id: 'local', label: '내 맥', teams: [{ id: 't', label: '팀', lead: agents[0], members: agents.slice(1) }] }],
    },
  });

describe('AgentRoster', () => {
  it('사람이 먼저 봐야 하는 에이전트를 위에 둔다', () => {
    receiveSnapshot(
      snapshot([
        { id: 'a', kind: 'lead', status: 'typing', nickname: '작업자' },
        { id: 'b', kind: 'subagent', status: 'permission', nickname: '승인대기' },
      ]),
    );
    render(<AgentRoster />);
    const buttons = screen.getAllByRole('button');
    expect(buttons[0]).toHaveTextContent('승인대기');
    expect(buttons[1]).toHaveTextContent('작업자');
  });

  it('키보드로 골랐다가 다시 누르면 고르기를 푼다', async () => {
    receiveSnapshot(snapshot([{ id: 'a', kind: 'lead', status: 'idle', nickname: '혼자' }]));
    render(<AgentRoster />);
    const button = screen.getByRole('button', { name: /혼자/ });
    button.focus();
    await userEvent.keyboard('{Enter}');
    expect(button).toHaveAttribute('aria-pressed', 'true');
    await userEvent.keyboard('{Enter}');
    expect(button).toHaveAttribute('aria-pressed', 'false');
  });

  it('아무도 없으면 비었다고 말한다', () => {
    render(<AgentRoster />);
    expect(screen.getByText('지금 사무실에 아무도 없습니다.')).toBeInTheDocument();
  });
});
