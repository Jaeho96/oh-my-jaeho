/**
 * 「실행·기록」 탭 — run_team 실행 기록과 공유 위키의 작업 기록. 사무실과 같은 스냅샷을 읽는다.
 */
import { type Run, useBoard, type WikiTask } from '../../../entities/board';
import { compactNumber, duration } from '../../../shared/lib';
import styles from './ActivityLists.module.css';

function RunRow({ run }: { run: Run }) {
  const { meta } = run;
  return (
    <li className={styles.item}>
      <div className={styles.line}>
        <span className={`${styles.state} ${styles[run.state] ?? ''}`}>{run.state}</span>
        <strong className={styles.name}>{run.name}</strong>
      </div>
      <div className={styles.nums}>
        <span>{meta.mode ?? '-'}</span>
        <span>{[meta.model, meta.effort].filter(Boolean).join(' · ')}</span>
        <span>걸린 시간 {duration(run.elapsedSec)}</span>
        <span>에이전트 {run.members + 1}</span>
        <span>토큰 {compactNumber(run.teamTokens.total)}</span>
        {meta.exitCode !== null ? <span>종료 코드 {meta.exitCode}</span> : null}
      </div>
      {meta.error ? <p className={styles.error}>{meta.error}</p> : null}
      {meta.task ? <p className={styles.task}>{meta.task}</p> : null}
    </li>
  );
}

function WikiRow({ task }: { task: WikiTask }) {
  return (
    <li className={styles.item}>
      <div className={styles.line}>
        <span className={`${styles.state} ${styles[task.status ?? ''] ?? ''}`}>{task.status ?? '?'}</span>
        <strong className={styles.name}>{task.taskId}</strong>
        <span className={styles.meta}>
          {task.count}건 · {task.authors.join(', ')}
          {task.machine ? ` · ${task.machine}` : ''}
        </span>
      </div>
      <p className={styles.task}>{task.title}</p>
    </li>
  );
}

export function ActivityLists() {
  const runs = useBoard((s) => s.snapshot?.runs ?? null);
  const wiki = useBoard((s) => s.snapshot?.wiki ?? null);

  return (
    <div className={styles.grid}>
      <section aria-labelledby="runs-title" className={styles.card}>
        <h2 id="runs-title" className={styles.heading}>
          팀 실행
        </h2>
        {runs && runs.length > 0 ? (
          <ul className={styles.list}>
            {runs.map((r) => (
              <RunRow key={r.name} run={r} />
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>실행 기록이 없습니다. run_team.py 로 시작하면 여기 쌓입니다.</p>
        )}
      </section>
      <section aria-labelledby="wiki-title" className={styles.card}>
        <h2 id="wiki-title" className={styles.heading}>
          공유 작업 기록
        </h2>
        {wiki && wiki.length > 0 ? (
          <ul className={styles.list}>
            {wiki.map((t) => (
              <WikiRow key={t.taskId} task={t} />
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>최근 작업 기록이 없습니다.</p>
        )}
      </section>
    </div>
  );
}
