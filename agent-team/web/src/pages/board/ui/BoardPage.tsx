import { useEffect, useRef, useState, type KeyboardEvent } from 'react';

import { listAgents, useBoard } from '../../../entities/board';
import { AgentRoster, selectAgent, useSelectedId } from '../../../features/select-agent';
import { relativeTime } from '../../../shared/lib';
import { ActivityLists } from '../../../widgets/activity-lists';
import { AgentDetail } from '../../../widgets/agent-detail';
import { AttentionStrip } from '../../../widgets/attention-strip';
import { OfficeFloor } from '../../../widgets/office-floor';
import styles from './BoardPage.module.css';

type Tab = 'office' | 'activity';

function ConnectionNotice() {
  const connection = useBoard((state) => state.connection);
  const snapshot = useBoard((state) => state.snapshot);
  const parseError = useBoard((state) => state.parseError);
  if (parseError) {
    return <p role="alert" className={styles.alert}>새 데이터를 읽지 못했습니다: {parseError}</p>;
  }
  switch (connection.kind) {
    case 'unauthorized':
      return <p role="alert" className={styles.alert}>토큰이 맞지 않습니다. 접근 주소를 확인해 주세요. 보드 서버의 기존 주소로 다시 열어 주세요.</p>;
    case 'failed':
      return <p role="alert" className={styles.alert}>서버에 연결하지 못했습니다. 다시 연결하는 중입니다: {connection.message}</p>;
    case 'reconnecting':
      return (
        <p role="alert" className={styles.alert}>
          {snapshot ? `마지막 수신 ${snapshot.generatedAt ?? '미확인'} · 재연결 중` : '서버에 연결하지 못했습니다. 다시 연결하는 중입니다'}
          {connection.message ? ` · ${connection.message}` : ''}
        </p>
      );
    case 'connecting':
    case 'open':
      return null;
    default: {
      const unreachable: never = connection;
      return unreachable;
    }
  }
}

function useMobileViewport() {
  const [mobile, setMobile] = useState(() => window.matchMedia?.('(max-width: 767px)').matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 767px)');
    if (!media) return undefined;
    const update = () => setMobile(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return mobile;
}

function trapDialogFocus(event: KeyboardEvent<HTMLDialogElement>) {
  if (event.key === 'Escape') {
    event.preventDefault();
    selectAgent(null);
    return;
  }
  if (event.key !== 'Tab') return;
  const nodes = event.currentTarget.querySelectorAll('button,[href],input,summary,[tabindex="0"]');
  if (!nodes.length) return;
  const first = nodes[0];
  const last = nodes[nodes.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    if (last instanceof HTMLElement) last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    if (first instanceof HTMLElement) first.focus();
  }
}

export function BoardPage() {
  const [tab, setTab] = useState<Tab>('office');
  const mobile = useMobileViewport();
  const snapshot = useBoard((state) => state.snapshot);
  const connection = useBoard((state) => state.connection);
  const selectedId = useSelectedId();
  const dialog = useRef<HTMLDialogElement>(null);
  const panel = useRef<HTMLElement>(null);
  const origin = useRef<HTMLElement | null>(null);
  const scroll = useRef(0);
  const previousId = useRef<string | null>(null);

  // Selection synchronizes native focus and the dialog top layer, including viewport changes.
  useEffect(() => {
    if (selectedId !== null && previousId.current === null) {
      origin.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      scroll.current = panel.current?.scrollTop ?? 0;
    }
    if (selectedId !== null && mobile && !dialog.current?.open) dialog.current?.showModal();
    if (!mobile) {
      dialog.current?.close();
      if (selectedId !== null) panel.current?.querySelector('button')?.focus();
    }
    if (selectedId === null && previousId.current !== null) {
      dialog.current?.close();
      if (panel.current) panel.current.scrollTop = scroll.current;
      const target = origin.current?.isConnected ? origin.current :
        Array.from(document.querySelectorAll('button[data-agent-id]')).find(
          (node) => node instanceof HTMLElement && node.dataset.agentId === previousId.current,
        );
      if (target instanceof HTMLElement) target.focus();
    }
    previousId.current = selectedId;
  }, [selectedId, mobile]);

  const loading = snapshot === null && connection.kind === 'connecting';
  const changeTab = (next: Tab) => {
    setTab(next);
    document.getElementById(`tab-${next}`)?.focus();
  };
  const handleTabKey = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowLeft':
        event.preventDefault();
        changeTab(tab === 'office' ? 'activity' : 'office');
        break;
      case 'Home':
        event.preventDefault();
        changeTab('office');
        break;
      case 'End':
        event.preventDefault();
        changeTab('activity');
        break;
      default:
        break;
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headline}>
          <h1>에이전트 팀 보드</h1>
          <span role="status" aria-label="연결 상태" title={snapshot?.generatedAt ?? undefined}>
            {connection.kind === 'open' ? '연결됨' : connection.kind === 'connecting' ? '연결 중' : '연결 확인 필요'}
            {snapshot?.generatedAt ? ` · ${relativeTime(snapshot.generatedAt)} 수신` : ''}
          </span>
        </div>
        <div role="tablist" aria-label="보기" className={styles.tabs} onKeyDown={handleTabKey}>
          {(['office', 'activity'] satisfies Tab[]).map((value) => (
            <button key={value} type="button" id={`tab-${value}`} role="tab"
              aria-selected={tab === value} aria-controls={`panel-${value}`}
              tabIndex={tab === value ? 0 : -1} onClick={() => setTab(value)}>
              {value === 'office' ? '사무실' : '실행·기록'}
            </button>
          ))}
        </div>
      </header>
      <ConnectionNotice />
      {snapshot ? Object.entries(snapshot.slots).filter(([, value]) => value.error).map(([name, value]) => (
        <p key={name} role="alert" className={styles.alert}>{name} 수집 오류: {value.error}</p>
      )) : null}
      <main aria-busy={loading}>
        {loading ? <div className={styles.loading}><p>보드 서버에 연결하는 중…</p></div> : null}
        {snapshot ? (
          <>
            <AttentionStrip onSelect={() => setTab('office')} />
            <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
              {tab === 'office' ? (
                <div className={styles.office}>
                  <details className={styles.floor} open={!mobile}>
                    <summary>사무실 보기</summary>
                    <div className={styles.viewport}><OfficeFloor /></div>
                  </details>
                  <aside ref={panel} className={styles.side} aria-label="팀·에이전트">
                    {selectedId !== null && !mobile ? <AgentDetail /> : null}
                    <div hidden={selectedId !== null && !mobile}>
                      <h2>팀·에이전트</h2>
                      {snapshot.office === null ? <p>사무실 정보를 받지 못했습니다</p> :
                        listAgents(snapshot.office).length === 0 ? <p>연결은 정상입니다. 표시할 에이전트가 없습니다</p> : null}
                      <AgentRoster />
                    </div>
                  </aside>
                </div>
              ) : <ActivityLists />}
            </div>
          </>
        ) : null}
      </main>
      {mobile ? (
        <dialog ref={dialog} className={styles.dialog} aria-label="에이전트 상세"
          onCancel={() => selectAgent(null)} onKeyDown={trapDialogFocus}>
          <AgentDetail />
        </dialog>
      ) : null}
    </div>
  );
}
