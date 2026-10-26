import { useState } from 'react';

import { type Run, useBoard } from '../../../entities/board';
import { compactNumber, duration } from '../../../shared/lib';
import styles from './ActivityLists.module.css';

export function runLabel(state: string): string {
  switch (state) {
    case 'running': return '실행 중';
    case 'done': return '실행 종료';
    case 'error': return '실행 오류';
    default: return '상태 미확인';
  }
}

function wikiLabel(state: string | null): string {
  switch (state) {
    case 'progress':
    case 'in_progress': return '진행 중';
    case 'completed':
    case 'done': return '완료';
    case 'blocked': return '보류';
    case 'error': return '오류';
    default: return '상태 미확인';
  }
}

function title(run: Run) {
  return run.meta.task?.split('\n').find((line) => line.trim())?.replace(/^[#*>\s-]+/u, '').slice(0, 120) || run.name;
}

function mode(run: Run) {
  return run.meta.mode === 'team' ? '팀 실행' : run.meta.mode === 'single' ? '단일 실행' : '방식 미확인';
}

function RunCard({ run, selected, onToggle, disabled }: {
  run: Run; selected: boolean; onToggle: () => void; disabled: boolean;
}) {
  return (
    <li className={styles.item}>
      <div className={styles.line}><h3>{title(run)}</h3><span>{runLabel(run.state)}</span></div>
      <p className={styles.meta}>
        {mode(run)} · 에이전트 {run.members + 1}명 · {[run.meta.model, run.meta.effort].filter(Boolean).join(' · ') || '모델 미확인'}
      </p>
      <div className={styles.nums}>
        <span>소요 시간 {duration(run.elapsedSec)}</span><span>총 토큰 {compactNumber(run.teamTokens.total)}</span>
        {run.meta.exitCode !== null ? <span>종료 코드 {run.meta.exitCode}{run.meta.exitCode === 0 ? ' · 정상 종료' : ''}</span> : null}
      </div>
      <p className={styles.result}>{run.resultHead || '결과 요약을 받지 못했습니다'}</p>
      {run.meta.error ? <p className={styles.error}>{run.meta.error}</p> : null}
      <div className={styles.actions}>
        <details>
          <summary>과제 원문 펼치기</summary>
          <pre>{run.meta.task || '과제 원문이 없습니다'}</pre><small>{run.name}</small>
        </details>
        <label>
          <input type="checkbox" aria-label={`${title(run)} 비교 대상으로 선택`}
            checked={selected} disabled={disabled} onChange={onToggle} /> 비교 대상으로 선택
        </label>
      </div>
    </li>
  );
}

function Comparison({ runs }: { runs: Run[] }) {
  if (runs.length !== 2) return null;
  const rows: [string, (run: Run) => string][] = [
    ['방식', mode], ['모델', (run) => run.meta.model ?? '미확인'],
    ['추론 수준', (run) => run.meta.effort ?? '미확인'],
    ['쓰기', (run) => run.meta.write === null ? '미확인' : run.meta.write ? '허용' : '읽기 전용'],
    ['인원', (run) => String(run.members + 1)], ['시간', (run) => duration(run.elapsedSec)],
    ['총 토큰', (run) => compactNumber(run.teamTokens.total)], ['종료 상태', (run) => runLabel(run.state)],
    ['오류', (run) => run.meta.error ?? '보고 없음'],
    ['결과 요약', (run) => run.resultHead || '결과 요약을 받지 못했습니다'],
  ];
  return (
    <section className={styles.comparison} aria-label="실행 비교">
      <h3>선택한 실행 비교</h3>
      <table>
        <caption>조건·사용량·결과 비교</caption>
        <thead><tr><th scope="col">항목</th>{runs.map((run, index) => (
          <th key={run.name} scope="col">{index === 0 ? 'A' : 'B'} · {title(run)}</th>
        ))}</tr></thead>
        <tbody>{rows.map(([label, value]) => (
          <tr key={label}><th scope="row">{label}</th>{runs.map((run) => <td key={run.name}>{value(run)}</td>)}</tr>
        ))}</tbody>
      </table>
    </section>
  );
}

export function ActivityLists() {
  const runs = useBoard((state) => state.snapshot?.runs ?? []);
  const wiki = useBoard((state) => state.snapshot?.wiki ?? []);
  const [selected, setSelected] = useState<string[]>([]);
  const [limit, setLimit] = useState(10);
  const comparison = runs.filter((run) => selected.includes(run.name));

  return (
    <div className={styles.grid}>
      <section aria-labelledby="runs-title" className={styles.card}>
        <h2 id="runs-title">실행</h2><Comparison runs={comparison} />
        {runs.length ? (
          <ul className={styles.list}>{runs.map((run) => (
            <RunCard key={run.name} run={run} selected={selected.includes(run.name)}
              disabled={comparison.length === 2 && !selected.includes(run.name)}
              onToggle={() => setSelected(selected.includes(run.name) ? selected.filter((id) => id !== run.name) : [...comparison.map((item) => item.name), run.name])} />
          ))}</ul>
        ) : <p>실행 기록이 없습니다.</p>}
      </section>
      <section aria-labelledby="wiki-title" className={styles.card}>
        <h2 id="wiki-title">공유 작업 기록</h2>
        {wiki.length ? (
          <ul className={styles.list}>{wiki.slice(0, limit).map((task) => (
            <li className={styles.wiki} key={task.taskId}>
              <strong>{task.title || '제목 없음'}</strong><span>{wikiLabel(task.status)} · {task.count}건</span>
              <details><summary>기록 상세</summary>
                <p>{task.taskId} · {task.authors.join(', ')} · {task.machine ?? '기기 미확인'}</p><p>{task.file}</p>
              </details>
            </li>
          ))}</ul>
        ) : <p>최근 작업 기록이 없습니다.</p>}
        {wiki.length > limit ? <button type="button" onClick={() => setLimit(limit + 10)}>더 보기</button> : null}
      </section>
    </div>
  );
}
