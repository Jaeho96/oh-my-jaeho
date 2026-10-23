/**
 * 고른 에이전트는 id 하나만 기억한다. 에이전트 객체는 스냅샷에서 그때그때 찾는다(사본을 두지 않는다).
 * 고른 에이전트가 사무실에서 사라지면 상세 패널은 「지금 사무실에 없음」을 보여 준다 — id 를 지우지는 않는다.
 */
import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

interface SelectionState {
  selectedId: string | null;
}

const selectionStore = createStore<SelectionState>(() => ({ selectedId: null }));

export function useSelectedId(): string | null {
  return useStore(selectionStore, (s) => s.selectedId);
}

export function selectAgent(id: string | null): void {
  selectionStore.setState({ selectedId: id });
}

export function subscribeSelection(listener: (id: string | null) => void): () => void {
  listener(selectionStore.getState().selectedId);
  return selectionStore.subscribe((s) => listener(s.selectedId));
}

export function resetSelectionForTest(): void {
  selectionStore.setState({ selectedId: null }, true);
}
