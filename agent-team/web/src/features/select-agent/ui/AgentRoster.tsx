/**
 * 사무실의 모든 에이전트를 버튼 목록으로. 캔버스는 키보드로 고를 수 없으므로 이 목록이 키보드 길이다.
 * 사람이 먼저 봐야 하는 상태(승인·입력 대기·멈춤)가 위로 온다.
 */
import { agentName, listAgents, sortByAttention, StatusBadge, useBoard } from '../../../entities/board';
import { selectAgent, useSelectedId } from '../model/selection';
import styles from './AgentRoster.module.css';

export function AgentRoster() {
  const office = useBoard((s) => s.snapshot?.office ?? null);
  const selectedId = useSelectedId();
  const agents = sortByAttention(listAgents(office));

  if (agents.length === 0) return <p className={styles.empty}>지금 사무실에 아무도 없습니다.</p>;

  return (
    <ul className={styles.list} aria-label="에이전트 목록">
      {agents.map((agent) => (
        <li key={agent.id}>
          <button
            type="button"
            className={styles.item}
            aria-pressed={agent.id === selectedId}
            onClick={() => selectAgent(agent.id === selectedId ? null : agent.id)}
          >
            <StatusBadge status={agent.status} />
            <span className={styles.name}>{agentName(agent)}</span>
            <span className={styles.activity}>{agent.activity}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
