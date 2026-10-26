import { act, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { connectBoard, receiveSnapshot } from '../../../entities/board';
import { AttentionStrip } from './AttentionStrip';
const snapshot = (status: string) => JSON.stringify({ generatedAt: '2026-01-01T00:10:00Z', office: { rooms: [{ id: 'r', teams: [{ id: 't', label: '화면 팀', lead: { id: 'a', nickname: '검토자', status, statusChangedAt: '2026-01-01T00:02:00Z' } }] }] } });
describe('대기 띠', () => {
    it('실제 전환만 한 번 알리고 같은 사람의 다음 전환도 알린다', () => { receiveSnapshot(snapshot('typing')); render(<AttentionStrip />); const region = screen.getByRole('region', { name: '나를 기다림' }); const live = within(region).getByRole('status', { name: '새 대기 알림' }); expect(live.textContent).toBe(''); act(() => receiveSnapshot(snapshot('waiting'))); expect(live).toHaveTextContent('검토자가 확인을 기다립니다'); const first = live?.firstChild; act(() => receiveSnapshot(snapshot('waiting'))); expect(live?.firstChild).toBe(first); act(() => receiveSnapshot(snapshot('typing'))); act(() => receiveSnapshot(snapshot('waiting'))); expect(live?.firstChild).not.toBe(first); expect(region).toHaveTextContent('8분째 대기'); expect(within(region).getByRole('button', { name: '검토자 상세 확인' })).toBeInTheDocument(); });
});

it('시각 근거가 없으면 대기 경과를 지어내지 않는다',()=>{
 receiveSnapshot(JSON.stringify({office:{rooms:[{id:'r',teams:[{id:'t',lead:{id:'a',nickname:'검토자',status:'waiting',statusChangedAt:'invalid',lastEventAt:'2026-01-01T00:00:00Z'}}]}]}}));
 render(<AttentionStrip/>);
 const region=screen.getByRole('region',{name:'나를 기다림'});
 expect(region).toHaveTextContent('마지막 소식');
 expect(region).not.toHaveTextContent('분째 대기');
 expect(region).not.toHaveTextContent('NaN');
});


it('재연결 중 생긴 대기자는 복구 때 다시 알리지 않는다', async () => {
  const listeners = new Map<string, (event: MessageEvent<string>) => void>();
  const source = {
    readyState: 0,
    addEventListener(type: string, listener: (event: MessageEvent<string>) => void) { listeners.set(type, listener); },
    close() {},
  };
  receiveSnapshot(snapshot('typing'));
  render(<AttentionStrip />);
  const live = screen.getByRole('status', { name: '새 대기 알림' });
  let stop: (() => void) | undefined;
  await act(async () => {
    stop = connectBoard({ token: 'test', deps: {
      fetchText: () => Promise.resolve({ status: 200, text: snapshot('typing') }),
      createEventSource: () => source,
    } });
  });
  act(() => listeners.get('open')?.(new MessageEvent('open')));
  act(() => listeners.get('error')?.(new MessageEvent('error')));
  act(() => listeners.get('open')?.(new MessageEvent('open')));
  act(() => listeners.get('state')?.(new MessageEvent('state', { data: snapshot('waiting') })));
  expect(live.textContent).toBe('');
  act(() => receiveSnapshot(snapshot('typing')));
  act(() => receiveSnapshot(snapshot('waiting')));
  expect(live).toHaveTextContent('검토자가 확인을 기다립니다');
  stop?.();
});
