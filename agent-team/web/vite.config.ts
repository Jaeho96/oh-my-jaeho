import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// 개발 서버는 데이터 길(/api, /events)을 보드 서버(board.py)로 넘긴다. 토큰은 주소창 ?t= 로 같이 간다.
const BOARD = process.env.BOARD_URL ?? 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': BOARD,
      '/events': BOARD,
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    // 셋업 범위로 나눈다 — DOM 이 필요한 *.dom.test.tsx 만 jsdom 에서 돈다
    projects: [
      {
        extends: true,
        test: { name: 'unit', environment: 'node', include: ['src/**/*.test.ts', 'tests/**/*.test.ts'] },
      },
      {
        extends: true,
        test: {
          name: 'dom',
          environment: 'jsdom',
          include: ['src/**/*.dom.test.tsx'],
          setupFiles: ['./tests/setup-dom.ts'],
        },
      },
    ],
  },
});
