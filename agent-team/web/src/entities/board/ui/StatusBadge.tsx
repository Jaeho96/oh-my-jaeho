import { statusVisual } from '../lib/status';
import type { AgentStatus } from '../model/types';
import styles from './StatusBadge.module.css';

export function StatusBadge({ status }: { status: AgentStatus }) {
  const visual = statusVisual(status);
  return <span className={`${styles.badge} ${styles[visual.tone]}`}>{visual.label}</span>;
}
