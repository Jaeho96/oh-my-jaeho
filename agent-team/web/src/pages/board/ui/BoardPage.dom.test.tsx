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
            createEventSource: () => ({ readyState: 0, addEventListener: () => { }, close: () => { } }),
        },
    });
}
const noop = () => { };
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
        expect(screen.getByRole('region', { name: '나를 기다림' })).toHaveTextContent('입력 대기');
        expect(screen.getByRole('button', { name: /총괄입력/ })).toBeInTheDocument();
        stop();
    });
    it('실행·기록 탭에서 팀 실행 결과를 본다', async () => {
        receiveSnapshot(SNAPSHOT);
        render(<BoardPage />);
        await userEvent.click(screen.getByRole('tab', { name: '실행·기록' }));
        expect(screen.getByRole('region', { name: '실행' })).toHaveTextContent('3.19M');
    });
});
describe('페이지 접근성', () => {
    it('탭 방향키와 Home End로 선택과 초점을 함께 이동한다', async () => { receiveSnapshot(SNAPSHOT); render(<BoardPage />); const office = screen.getByRole('tab', { name: '사무실' }); office.focus(); await userEvent.keyboard('{ArrowRight}'); expect(screen.getByRole('tab', { name: '실행·기록' })).toHaveFocus(); expect(screen.getByRole('tabpanel', { name: '실행·기록' })).toBeInTheDocument(); await userEvent.keyboard('{Home}'); expect(office).toHaveFocus(); await userEvent.keyboard('{End}'); expect(screen.getByRole('tab', { name: '실행·기록' })).toHaveAttribute('aria-selected', 'true'); });
    it('상세를 닫으면 목록의 같은 행으로 초점을 돌려준다', async () => { receiveSnapshot(SNAPSHOT); render(<BoardPage />); const row = screen.getByRole('button', { name: /총괄입력/ }); await userEvent.click(row); expect(screen.getByRole('region', { name: '에이전트 상세' })).toBeInTheDocument(); expect(screen.getByRole('button', { name: '목록으로' })).toHaveFocus(); await userEvent.click(screen.getByRole('button', { name: '목록으로' })); expect(row).toHaveFocus(); });
    it('최초 요청 실패 뒤 재연결에도 오류 이유를 유지한다', async () => { render(<BoardPage />); let stop: () => void = noop; await act(async () => { stop = connectWith(503); }); expect(screen.getByRole('alert')).toHaveTextContent('서버에 연결하지 못했습니다'); expect(screen.getByRole('alert')).toHaveTextContent('HTTP 503'); expect(screen.getByRole('main')).toHaveAttribute('aria-busy', 'false'); stop(); });
});
describe('모바일 상세', () => {
    it('다이얼로그의 초점을 가두고 Escape로 닫은 뒤 원래 행으로 돌아간다', async () => {
        const original = window.matchMedia;
        Object.defineProperty(window, 'matchMedia', { configurable: true, value: () => ({ matches: true, addEventListener: () => { }, removeEventListener: () => { } }) });
        const show = HTMLDialogElement.prototype.showModal;
        const close = HTMLDialogElement.prototype.close;
        HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); this.querySelector('button')?.focus(); };
        HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
        try {
            receiveSnapshot(SNAPSHOT);
            render(<BoardPage />);
            const row = screen.getByRole('button', { name: /총괄입력/ });
            await userEvent.click(row);
            const modal = screen.getByRole('dialog', { name: '에이전트 상세' });
            const back = screen.getByRole('button', { name: '목록으로' });
            expect(back).toHaveFocus();
            await userEvent.keyboard('{Tab}');
            expect(back).toHaveFocus();
            await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
            expect(back).toHaveFocus();
            expect(modal).toHaveAttribute('open');
            await userEvent.keyboard('{Escape}');
            expect(modal).not.toHaveAttribute('open');
            expect(row).toHaveFocus();
        }
        finally {
            Object.defineProperty(window, 'matchMedia', { configurable: true, value: original });
            HTMLDialogElement.prototype.showModal = show;
            HTMLDialogElement.prototype.close = close;
        }
    });
});
