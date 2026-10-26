import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { receiveSnapshot } from '../../../entities/board';
import { ActivityLists } from './ActivityLists';
describe('실행 카드', () => {
    it('결과와 종료를 구별하고 원문을 접고 두 실행만 비교한다', async () => { receiveSnapshot(JSON.stringify({ runs: [0, 1, 2].map((i) => ({ name: `r${i}`, state: 'done', elapsed_sec: i === 0 ? null : 60, members: 0, team_tokens: { total_tokens: 100 }, meta: { task: `과제 ${i}\n긴 원문`, exit_code: 0, write: i === 0 } })) })); render(<ActivityLists />); expect(screen.getAllByText('결과 요약을 받지 못했습니다')).toHaveLength(3); expect(screen.queryByText('과제 성공')).not.toBeInTheDocument(); const boxes = screen.getAllByRole('checkbox'); if (!boxes[0] || !boxes[1] || !boxes[2])
        {throw new Error('fixture');} await userEvent.click(boxes[0]); await userEvent.click(boxes[1]); expect(boxes[2]).toBeDisabled(); const table = screen.getByRole('table'); expect(within(table).getByRole('row', { name: '시간 - 1분 0초' })).toBeInTheDocument(); const summaries = screen.getAllByText('과제 원문 펼치기'); expect(summaries[0]?.closest('details')).not.toHaveAttribute('open'); });
});
