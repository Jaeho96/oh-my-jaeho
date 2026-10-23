/**
 * 고른 에이전트의 자세한 상태. 에이전트 객체는 스냅샷과 선택 id 로 렌더 중에 찾는다(상태로 들고 있지 않는다).
 */
import { agentName, findAgent, StatusBadge, useBoard } from '../../../entities/board';
import { selectAgent, useSelectedId } from '../../../features/select-agent';
import { compactNumber, relativeTime } from '../../../shared/lib';
import styles from './AgentDetail.module.css';

export function AgentDetail() {
  const selectedId = useSelectedId();
  const agent = useBoard((s) => findAgent(s.snapshot?.office ?? null, selectedId));

  if (selectedId === null) {
    return <p className={styles.hint}>캐릭터를 누르거나 아래 목록에서 고르면 자세히 보입니다.</p>;
  }
  if (agent === null) {
    return (
      <section aria-label="에이전트 상세" className={styles.panel}>
        <p className={styles.hint}>이 에이전트는 지금 사무실에 없습니다.</p>
        <button type="button" className={styles.close} onClick={() => selectAgent(null)}>
          닫기
        </button>
      </section>
    );
  }

  const rows: [string, string][] = [
    ['하는 일', agent.activity ?? '-'],
    ['모델', [agent.model, agent.effort].filter(Boolean).join(' · ') || '-'],
    ['컨텍스트', agent.context ? `${compactNumber(agent.context.used)}${agent.context.pct === null ? '' : ` (${agent.context.pct}%)`}` : '-'],
    ['토큰 합계', compactNumber(agent.tokens?.total)],
    ['폴더', agent.cwd ?? '-'],
    ['마지막 소식', relativeTime(agent.lastEventAt) || '-'],
  ];

  return (
    <section aria-label="에이전트 상세" className={styles.panel}>
      <header className={styles.head}>
        <h2 className={styles.name}>{agentName(agent)}</h2>
        <StatusBadge status={agent.status} />
      </header>
      {agent.title && agent.title !== agentName(agent) ? <p className={styles.title}>{agent.title}</p> : null}
      <dl className={styles.rows}>
        {rows.map(([k, v]) => (
          <div key={k} className={styles.row}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {agent.lastMessage ? (
        <details className={styles.report}>
          <summary>마지막 보고</summary>
          <pre>{agent.lastMessage}</pre>
        </details>
      ) : null}
      <button type="button" className={styles.close} onClick={() => selectAgent(null)}>
        닫기
      </button>
    </section>
  );
}
