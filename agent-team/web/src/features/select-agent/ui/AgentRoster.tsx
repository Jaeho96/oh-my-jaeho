import { activityText, agentName, groupedRooms, isWaiting, sortByAttention, StatusBadge, useBoard } from '../../../entities/board';
import { selectAgent, useSelectedId } from '../model/selection';
import styles from './AgentRoster.module.css';

export function AgentRoster() {
  const office = useBoard((state) => state.snapshot?.office ?? null);
  const selectedId = useSelectedId();
  const rooms = groupedRooms(office);
  if (!rooms.length) return <p className={styles.empty}>지금 사무실에 아무도 없습니다.</p>;

  return (
    <div>
      {rooms.map((room) => (
        <section key={room.id} aria-label={room.label} className={styles.room}>
          <h3>{room.label} {room.hidden > 0 ? <small>자동 리뷰 {room.hidden}개 숨김</small> : null}</h3>
          {room.error ? <p role="alert">방 수집 오류: {room.error}</p> : null}
          {room.teams.map((team) => (
            <section key={team.id} aria-label={`${team.label} 팀`}>
            <details open className={styles.team}>
              <summary>
                {team.label} · {team.provider ?? '공급자 미확인'}{' '}
                <small>{team.members.length + 1}명 · 대기 {[team.lead, ...team.members].filter(isWaiting).length}명</small>
              </summary>
              <ul aria-label={`${team.label} 에이전트 목록`} className={styles.list}>
                {sortByAttention([team.lead, ...team.members]).map((agent) => (
                  <li key={agent.id}>
                    <button data-agent-id={agent.id} type="button" className={styles.item}
                      aria-pressed={agent.id === selectedId}
                      onClick={() => selectAgent(agent.id === selectedId ? null : agent.id)}>
                      <span className={styles.name}>{agentName(agent)}</span>
                      {agent.unknownStatus ? <span>상태 미확인</span> : <StatusBadge status={agent.status} />}
                      <span className={styles.activity}>
                        {agent.kind === 'lead' ? '총괄' : agent.role ?? '팀원'}
                        {activityText(agent) ? ` · ${activityText(agent)}` : ''}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </details>
            </section>
          ))}
        </section>
      ))}
    </div>
  );
}
