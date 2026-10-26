import { useEffect } from 'react';

import { connectBoard } from '../entities/board';
import { BoardPage } from '../pages/board';
import type { ConnectionConfig } from './config';
import styles from './App.module.css';

export function App({ config }: { config: ConnectionConfig }) {
  const fixture = import.meta.env.DEV && new URLSearchParams(window.location.search).get('fixture') === 'busy';
  useEffect(() => {
    if (fixture) {
      let stopped = false;
      let cleanup: (() => void) | undefined;
      void import('./fixture').then((module) => { if (!stopped) cleanup = module.loadBusyFixture(); });
      return () => { stopped = true; cleanup?.(); };
    }
    if (!config.ok) return undefined;
    return connectBoard({ token: config.token });
  }, [config, fixture]);

  if (!config.ok && !fixture) {
    return (
      <main className={styles.missing}>
        <h1>토큰이 필요합니다</h1>
        <p>
          보드 서버를 띄우면 <code>http://127.0.0.1:8765/?t=…</code> 주소가 찍힙니다. 그 주소로 열어 주세요. 토큰은{' '}
          <code>~/.omj/agent-team/board.token</code> 에도 있습니다.
        </p>
      </main>
    );
  }
  return <BoardPage />;
}
