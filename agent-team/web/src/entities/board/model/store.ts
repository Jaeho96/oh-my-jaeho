/**
 * 보드 상태의 원본은 SSE 하나다. 그것을 받는 스토어를 React 밖에 하나 둔다 —
 * 캔버스 엔진은 React 렌더 없이 subscribe 로 읽고, 컴포넌트는 좁은 selector 로 구독한다.
 * raw 스토어는 밖으로 내보내지 않는다(index.ts 는 훅과 읽기 함수만 내보낸다).
 */
import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import { openEventStream, type StreamDeps, type StreamStatus } from '../../../shared/api';
import { parseSnapshot } from './guards';
import type { BoardSnapshot } from './types';

export interface BoardState {
  snapshot: BoardSnapshot | null;
  connection: StreamStatus;
  parseError: string | null;
  unknownStatuses: string[];
}

const initial: BoardState = { snapshot: null, connection: { kind: 'connecting' }, parseError: null, unknownStatuses: [] };

const boardStore = createStore<BoardState>(() => initial);

export function useBoard<T>(selector: (state: BoardState) => T): T {
  return useStore(boardStore, selector);
}

/** React 밖(캔버스 루프)에서 읽기. 바뀔 때마다 listener 를 부른다. 해제 함수를 돌려준다. */
export function subscribeBoard(listener: (state: BoardState) => void): () => void {
  listener(boardStore.getState());
  return boardStore.subscribe(listener);
}

export function receiveSnapshot(raw: string): void {
  const result = parseSnapshot(raw);
  if (result.ok) {
    boardStore.setState({ snapshot: result.snapshot, parseError: null, unknownStatuses: result.unknownStatuses });
  } else {
    boardStore.setState({ parseError: result.reason });
  }
}

export interface ConnectOptions {
  token: string;
  baseUrl?: string;
  deps?: Partial<StreamDeps>;
}

/** 연결을 연다. 해제 함수를 돌려준다. 토큰이 없으면 조용히 기본값으로 가지 않고 호출 쪽에서 막는다. */
export function connectBoard({ token, baseUrl = '', deps }: ConnectOptions): () => void {
  const q = `t=${encodeURIComponent(token)}`;
  return openEventStream({
    snapshotUrl: `${baseUrl}/api/state?${q}`,
    streamUrl: `${baseUrl}/events?${q}`,
    eventName: 'state',
    onMessage: receiveSnapshot,
    onStatus: (connection) => boardStore.setState({ connection }),
    deps,
  });
}

/** 시험에서만 쓴다. */
export function resetBoardForTest(): void {
  boardStore.setState(initial, true);
}
