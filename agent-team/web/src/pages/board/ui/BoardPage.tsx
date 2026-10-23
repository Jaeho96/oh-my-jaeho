/**
 * 보드 화면. 연결 상태는 겹치지 않게 가른다 — 처음 연결 중 / 토큰 문제 / 실패 / 재연결 중(마지막 화면 유지) / 연결됨.
 */
import { useState } from 'react';

import { STATUS_PRIORITY, StatusBadge, useBoard } from '../../../entities/board';
import { AgentRoster } from '../../../features/select-agent';
import { ActivityLists } from '../../../widgets/activity-lists';
import { AgentDetail } from '../../../widgets/agent-detail';
import { OfficeFloor } from '../../../widgets/office-floor';
import styles from './BoardPage.module.css';

type Tab = 'office' | 'activity';

function ConnectionNotice() {
  const connection = useBoard((s) => s.connection);
  const hasSnapshot = useBoard((s) => s.snapshot !== null);
  const parseError = useBoard((s) => s.parseError);
  const unknownStatuses = useBoard((s) => s.unknownStatuses);

  switch (connection.kind) {
    case 'unauthorized':
      return (
        <p role="alert" className={styles.alert}>
          토큰이 맞지 않습니다. 보드 서버를 띄울 때 찍힌 주소(…/?t=토큰)로 다시 열어 주세요.
        </p>
      );
    case 'failed':
      return (
        <p role="alert" className={styles.alert}>
          보드 서버에 닿지 않습니다: {connection.message}. 잠시 뒤 다시 시도합니다.
        </p>
      );
    case 'reconnecting':
      return hasSnapshot ? (
        <p role="status" className={styles.notice}>
          다시 연결하는 중입니다. 마지막으로 받은 화면을 보여 주고 있습니다.
        </p>
      ) : null;
    case 'connecting':
    case 'open':
      break;
    default: {
      const unreachable: never = connection;
      return unreachable;
    }
  }
  if (parseError) return <p className={styles.notice}>받은 데이터를 읽지 못했습니다: {parseError}</p>;
  if (unknownStatuses.length > 0) return <p className={styles.notice}>모르는 상태: {unknownStatuses.join(', ')}</p>;
  return null;
}

function StatusSummary() {
  const counts = useBoard((s) => s.snapshot?.office?.counts ?? null);
  if (!counts) return null;
  return (
    <ul className={styles.summary} aria-label="상태별 인원">
      {STATUS_PRIORITY.filter((s) => counts[s]).map((s) => (
        <li key={s}>
          <StatusBadge status={s} /> {counts[s]}
        </li>
      ))}
    </ul>
  );
}

export function BoardPage() {
  const [tab, setTab] = useState<Tab>('office');
  const firstLoad = useBoard((s) => s.snapshot === null && (s.connection.kind === 'connecting' || s.connection.kind === 'reconnecting'));
  const generatedAt = useBoard((s) => s.snapshot?.generatedAt ?? null);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>에이전트 팀 보드</h1>
        <nav className={styles.tabs} aria-label="보기">
          <button type="button" aria-pressed={tab === 'office'} onClick={() => setTab('office')}>
            사무실
          </button>
          <button type="button" aria-pressed={tab === 'activity'} onClick={() => setTab('activity')}>
            실행·기록
          </button>
        </nav>
        <StatusSummary />
        {generatedAt ? <span className={styles.meta}>갱신 {generatedAt.slice(11, 19)}</span> : null}
      </header>
      <ConnectionNotice />
      <main className={styles.main} aria-busy={firstLoad}>
        {firstLoad ? <p className={styles.loading}>보드 서버에 연결하는 중…</p> : null}
        {!firstLoad && tab === 'office' ? (
          <div className={styles.office}>
            <section className={styles.floor} aria-label="사무실">
              <OfficeFloor />
            </section>
            <aside className={styles.side}>
              <AgentDetail />
              <h2 className={styles.sideHeading}>모두</h2>
              <AgentRoster />
            </aside>
          </div>
        ) : null}
        {!firstLoad && tab === 'activity' ? <ActivityLists /> : null}
      </main>
    </div>
  );
}
