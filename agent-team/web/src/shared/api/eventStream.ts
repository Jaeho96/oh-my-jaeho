/**
 * 서버가 밀어 주는 이벤트(SSE)를 받는 연결. 도메인을 모른다 — 받은 문자열을 onMessage 로 넘길 뿐이다.
 *
 * - 처음에는 스냅샷을 fetch 로 한 번 받는다. 401 이면 토큰 문제로 보고 다시 붙지 않는다(EventSource 는 상태 코드를 못 준다).
 * - EventSource 가 스스로 다시 붙는 동안은 reconnecting, 끊겨서 닫히면 지수 대기 뒤 직접 다시 연다.
 * - EventSource·fetch·타이머는 바꿔 끼울 수 있다(시험에서 가짜를 넣는다).
 */
import { nextDelayMs } from '../lib';

export type StreamStatus =
  | { kind: 'connecting' }
  | { kind: 'open' }
  | { kind: 'reconnecting'; attempt: number; message?: string }
  | { kind: 'unauthorized' }
  | { kind: 'failed'; message: string };

export interface EventSourceLike {
  readyState: number;
  addEventListener(type: 'open' | 'error', listener: () => void): void;
  addEventListener(type: string, listener: (ev: MessageEvent<string>) => void): void;
  close(): void;
}

export interface StreamDeps {
  createEventSource: (url: string) => EventSourceLike;
  fetchText: (url: string) => Promise<{ status: number; text: string }>;
  setTimer: (fn: () => void, ms: number) => unknown;
  clearTimer: (handle: unknown) => void;
}

export interface StreamOptions {
  snapshotUrl: string;
  streamUrl: string;
  eventName: string;
  onMessage: (raw: string) => void;
  onStatus: (status: StreamStatus) => void;
  deps?: Partial<StreamDeps>;
}

const CLOSED = 2;

const defaultDeps: StreamDeps = {
  createEventSource: (url) => new EventSource(url),
  fetchText: async (url) => {
    const res = await fetch(url, { cache: 'no-store' });
    return { status: res.status, text: await res.text() };
  },
  setTimer: (fn, ms) => { const timer = setTimeout(fn, ms); return () => clearTimeout(timer); },
  clearTimer: (handle) => { if (typeof handle === 'function') handle(); },
};

export function openEventStream(options: StreamOptions): () => void {
  const deps: StreamDeps = { ...defaultDeps, ...options.deps };
  let source: EventSourceLike | null = null;
  let timer: unknown = null;
  let attempt = 0;
  let stopped = false;
  let lastError: string | undefined;

  const scheduleReopen = () => {
    if (stopped) return;
    options.onStatus({ kind: 'reconnecting', attempt, message: lastError });
    timer = deps.setTimer(() => {
      timer = null;
      void start();
    }, nextDelayMs(attempt));
    attempt += 1;
  };

  const listen = () => {
    const es = deps.createEventSource(options.streamUrl);
    source = es;
    es.addEventListener('open', () => {
      attempt = 0;
      lastError = undefined;
      options.onStatus({ kind: 'open' });
    });
    es.addEventListener('error', () => {
      if (stopped || source !== es) return;
      if (es.readyState === CLOSED) {
        es.close();
        source = null;
        scheduleReopen();
      } else {
        options.onStatus({ kind: 'reconnecting', attempt, message: lastError });
      }
    });
    es.addEventListener(options.eventName, (ev: MessageEvent<string>) => options.onMessage(ev.data));
  };

  const start = async () => {
    try {
      const res = await deps.fetchText(options.snapshotUrl);
      if (stopped) return;
      if (res.status === 401) {
        options.onStatus({ kind: 'unauthorized' });
        return;
      }
      if (res.status !== 200) throw new Error(`스냅샷 요청 실패: HTTP ${res.status}`);
      options.onMessage(res.text);
    } catch (error) {
      if (stopped) return;
      lastError = error instanceof Error ? error.message : String(error);
      options.onStatus({ kind: 'failed', message: lastError });
      scheduleReopen();
      return;
    }
    listen();
  };

  options.onStatus({ kind: 'connecting' });
  void start();

  return () => {
    stopped = true;
    if (timer !== null) deps.clearTimer(timer);
    source?.close();
    source = null;
  };
}
