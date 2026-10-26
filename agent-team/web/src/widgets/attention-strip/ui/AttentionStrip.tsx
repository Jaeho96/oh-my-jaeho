import { useEffect, useState } from 'react';

import { type BoardSnapshot, agentName, attentionAgents, listAgents, newWaiting, subscribeBoard, useBoard } from '../../../entities/board';
import { selectAgent } from '../../../features/select-agent';
import { relativeTime } from '../../../shared/lib';
import styles from './AttentionStrip.module.css';

export function AttentionStrip({ onSelect }: { onSelect?: () => void }) {
  const generatedAt = useBoard((state) => state.snapshot?.generatedAt ?? null);
  const office = useBoard((state) => state.snapshot?.office ?? null);
  const agents = attentionAgents(office);
  const errors = listAgents(office).filter((agent) => agent.status === 'error');
  const [announcement, setAnnouncement] = useState({ text: '', sequence: 0 });

  // Live announcements are an external synchronization with assistive technology.
  // A recovered transport opens before its first state event. Only a fresh snapshot
  // can consume the recovery baseline; connection-only updates must not consume it.
  useEffect(() => {
    let previous = new Map<string, string>();
    let initialized = false;
    let previousSnapshot: BoardSnapshot | null = null;
    let recovering = false;
    return subscribeBoard((state) => {
      if (state.connection.kind === 'reconnecting') recovering = true;
      if (!state.snapshot || state.snapshot === previousSnapshot) return;
      const current = listAgents(state.snapshot.office);
      const names = initialized && !recovering ? newWaiting(previous, current) : [];
      previous = new Map(current.map((agent) => [agent.id, agent.status]));
      initialized = true;
      previousSnapshot = state.snapshot;
      recovering = state.connection.kind === 'reconnecting';
      if (names.length) {
        setAnnouncement((last) => ({ text: `${names.join('、')}가 확인을 기다립니다`, sequence: last.sequence + 1 }));
      }
    });
  }, []);

  const openAgent = (id: string) => {
    selectAgent(id);
    onSelect?.();
  };

  return (
    <section aria-label="나를 기다림" className={agents.length ? styles.strip : styles.quiet}>
      <div role="status" aria-label="새 대기 알림" className={styles.live} aria-live="polite" aria-atomic="true">
        <span key={announcement.sequence}>{announcement.text}</span>
      </div>
      <h2>나를 기다림 <span>{agents.filter((agent) => agent.status !== 'stalled').length}명</span></h2>
      {agents.length === 0 ? <p>나를 기다리는 에이전트가 없습니다</p> : (
        <ul>
          {agents.map((agent) => {
            const team = office?.rooms.flatMap((room) => room.teams).find(
              (item) => [item.lead, ...item.members].some((member) => member.id === agent.id),
            );
            const now = Date.parse(generatedAt ?? office?.generatedAt ?? '');
            const changedAt = Date.parse(agent.statusChangedAt ?? '');
            const duration = Number.isFinite(changedAt) && Number.isFinite(now) && agent.status !== 'stalled' ?
              `${Math.max(0, Math.floor((now - changedAt) / 60000))}분째 대기` :
              `마지막 소식 ${relativeTime(agent.lastEventAt) || '미확인'}`;
            return (
              <li key={agent.id}>
                <strong>{agentName(agent)}</strong>
                <span>{team?.label} · {agent.status === 'permission' ? '승인 대기' : agent.status === 'waiting' ? '입력 대기' : '멈춤 의심 — 확인 필요'}</span>
                <small>{duration}</small>
                <button type="button" aria-label={`${agentName(agent)} 상세 확인`} onClick={() => openAgent(agent.id)}>상세 확인</button>
              </li>
            );
          })}
        </ul>
      )}
      {errors.length ? (
        <p className={styles.error}>오류 {errors.length}명 {errors.map((agent) => (
          <button key={agent.id} type="button" onClick={() => openAgent(agent.id)}>{agentName(agent)} 확인</button>
        ))}</p>
      ) : null}
    </section>
  );
}
