import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { connectBoard, receiveSnapshot } from '../../../entities/board';
import { BoardPage } from './BoardPage';

const SNAPSHOT = JSON.stringify({
  generatedAt: '2026-10-23T21:30:00+09:00',
  office: { rooms: [{ id: 'local', label: '내 맥', teams: [{ id: 't', lead: { id: 'a', kind: 'lead', status: 'waiting', nickname: '총괄' } }] }], counts: { waiting: 1 } },
  runs: [{ name: 'poc', state: 'done', elapsed_sec: 483, members: 3, team_tokens: { total_tokens: 3193660 }, meta: { mode: 'team' } }],
});

/** 실제 연결 경로(connectBoard → openEventStream → 파싱)를 그대로 타되, 네트워크만 가짜로 바꾼다. */
function connectWith(status: number, text = SNAPSHOT) {
  return connectBoard({
    token: 'tok',
    deps: {
      fetchText: () => Promise.resolve({ status, text }),
      createEventSource: () => ({ readyState: 0, addEventListener: () => {}, close: () => {} }),
    },
  });
}

const noop = () => {};

describe('BoardPage', () => {
  it('처음 연결하는 동안에만 바쁨으로 표시한다', () => {
    render(<BoardPage />);
    expect(screen.getByRole('main')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('보드 서버에 연결하는 중…')).toBeInTheDocument();
  });

  it('토큰이 틀리면 다시 여는 법을 알린다', async () => {
    render(<BoardPage />);
    let stop: () => void = noop;
    await act(async () => {
      stop = connectWith(401);
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('토큰이 맞지 않습니다');
    stop();
  });

  it('스냅샷을 받으면 상태별 인원과 사람 목록을 보여 준다', async () => {
    render(<BoardPage />);
    let stop: () => void = noop;
    await act(async () => {
      stop = connectWith(200);
    });
    expect(screen.getByRole('main')).toHaveAttribute('aria-busy', 'false');
    expect(screen.getByRole('list', { name: '상태별 인원' })).toHaveTextContent('입력 기다림 1');
    expect(screen.getByRole('button', { name: /총괄/ })).toBeInTheDocument();
    stop();
  });

  it('실행·기록 탭에서 팀 실행 결과를 본다', async () => {
    receiveSnapshot(SNAPSHOT);
    render(<BoardPage />);
    await userEvent.click(screen.getByRole('button', { name: '실행·기록' }));
    expect(screen.getByRole('region', { name: '팀 실행' })).toHaveTextContent('3.19M');
  });
});
