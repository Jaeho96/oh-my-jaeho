import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

import { resetBoardForTest } from '../src/entities/board';
import { resetSelectionForTest } from '../src/features/select-agent';

// jsdom 에 없는 브라우저 기능. 캔버스는 그리지 않는다(그림은 엔진 단위 시험이 본다).
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', NoopResizeObserver);
vi.stubGlobal('matchMedia', (query: string) => ({
  matches: false,
  media: query,
  addEventListener: () => {},
  removeEventListener: () => {},
}));
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext'];

afterEach(() => {
  cleanup();
  resetBoardForTest();
  resetSelectionForTest();
});
