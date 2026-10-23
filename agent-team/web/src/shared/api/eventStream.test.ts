import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { type EventSourceLike, openEventStream, type StreamStatus } from './eventStream';

class FakeEventSource implements EventSourceLike {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  listeners = new Map<string, (ev: MessageEvent<string>) => void>();
  closed = false;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (ev: MessageEvent<string>) => void) {
    this.listeners.set(type, listener);
  }
  fire(type: 'open' | 'error') {
    this.listeners.get(type)?.(new MessageEvent(type));
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  emit(type: string, data: string) {
    this.listeners.get(type)?.(new MessageEvent(type, { data }));
  }
}

function setup(fetchResult: { status: number; text: string } | Error) {
  const messages: string[] = [];
  const statuses: StreamStatus[] = [];
  const stop = openEventStream({
    snapshotUrl: '/api/state?t=x',
    streamUrl: '/events?t=x',
    eventName: 'state',
    onMessage: (raw) => messages.push(raw),
    onStatus: (s) => statuses.push(s),
    deps: {
      createEventSource: (url) => new FakeEventSource(url),
      fetchText: () => (fetchResult instanceof Error ? Promise.reject(fetchResult) : Promise.resolve(fetchResult)),
    },
  });
  return { messages, statuses, stop };
}

describe('openEventStream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('스냅샷을 먼저 넘기고 이벤트 스트림을 연다', async () => {
    const { messages, statuses } = setup({ status: 200, text: '{"a":1}' });
    await vi.runOnlyPendingTimersAsync();
    expect(messages).toEqual(['{"a":1}']);
    const es = FakeEventSource.instances[0];
    es.fire('open');
    es.emit('state', '{"a":2}');
    expect(messages).toEqual(['{"a":1}', '{"a":2}']);
    expect(statuses.map((s) => s.kind)).toEqual(['connecting', 'open']);
  });

  it('401 이면 토큰 문제로 보고 다시 붙지 않는다', async () => {
    const { statuses } = setup({ status: 401, text: '' });
    await vi.runOnlyPendingTimersAsync();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(statuses.at(-1)).toEqual({ kind: 'unauthorized' });
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('스트림이 닫히면 기다렸다가 다시 연다', async () => {
    setup({ status: 200, text: '{}' });
    await vi.runOnlyPendingTimersAsync();
    const first = FakeEventSource.instances[0];
    first.readyState = 2;
    first.fire('error');
    expect(first.closed).toBe(true);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it('멈추면 예약된 재연결도 취소해 서버에 다시 묻지 않는다', async () => {
    let calls = 0;
    const stop = openEventStream({
      snapshotUrl: '/api/state?t=x',
      streamUrl: '/events?t=x',
      eventName: 'state',
      onMessage: () => {},
      onStatus: () => {},
      deps: {
        createEventSource: (url) => new FakeEventSource(url),
        fetchText: () => {
          calls += 1;
          return Promise.reject(new Error('network'));
        },
      },
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(calls).toBe(1);
    stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(calls).toBe(1);
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
