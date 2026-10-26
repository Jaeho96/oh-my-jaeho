import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { receiveSnapshot } from '../../../entities/board';
import { selectAgent, useSelectedId } from '../../../features/select-agent';
import { makeOffice } from '../engine/testFixtures';
import { OfficeFloor } from './OfficeFloor';
const update = vi.fn();
const stop = vi.fn();
vi.mock('../engine/loop', () => ({ startOfficeLoop: () => ({ update, stop, pan: vi.fn(), hit: () => null }) }));
function Selection() { return <output aria-label="선택한 사람">{useSelectedId() ?? '없음'}</output>; }
describe('사무실 도구줄', () => {
  it('방 인원과 완료 수를 캔버스 밖에 표시하고 카메라 선택을 동기화한다', () => {
    const office = makeOffice(2, 2);
    office.rooms[1].teams[0].members[0].status = 'done';
    receiveSnapshot(JSON.stringify({ generatedAt: null, office, runs: [], wiki: [], slots: {} }));
    render(<OfficeFloor />);
    expect(screen.getByRole('toolbar', { name: '사무실 보기' })).toBeVisible();
    expect(screen.getByLabelText('사무실 방 현황')).toHaveTextContent('방 1 · 2명 · 완료 1명');
    expect(screen.getByRole('combobox', { name: '사무실 확대' })).toHaveValue('0');
    fireEvent.change(screen.getByRole('combobox', { name: '사무실 방 선택' }), { target: { value: 'r1' } });
    fireEvent.change(screen.getByRole('combobox', { name: '사무실 확대' }), { target: { value: '4' } });
    expect(update).toHaveBeenCalledWith({ roomId: 'r1', scale: 0 });
    fireEvent.click(screen.getByRole('button', { name: '전체 보기' }));
    expect(screen.getByRole('combobox', { name: '사무실 확대' })).toHaveValue('0');
    expect(screen.getByRole('combobox', { name: '사무실 방 선택' })).toHaveValue('');
    expect(update).toHaveBeenCalledWith({ scale: 0, roomId: null });
  });
  it('Escape와 빈 바닥 클릭으로 선택을 해제하고 해제 시 루프를 종료한다', () => {
    const view = render(<><OfficeFloor /><Selection /></>);
    selectAgent('reviewer');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByLabelText('선택한 사람')).toHaveTextContent('없음');
    selectAgent('worker');
    fireEvent.click(screen.getByRole('img'));
    expect(screen.getByLabelText('선택한 사람')).toHaveTextContent('없음');
    view.unmount();
    expect(stop).toHaveBeenCalled();
  });
});
