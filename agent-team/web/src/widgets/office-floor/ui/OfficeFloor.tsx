/**
 * 픽셀 사무실. 캔버스와 그리기 루프는 외부 시스템이라 Effect 로 붙이고, 스냅샷·선택은 스토어를 직접 구독해 루프에 넘긴다 —
 * 스냅샷이 1초마다 와도 이 컴포넌트는 다시 렌더되지 않는다. 키보드로 고르는 길은 AgentRoster 가 맡는다.
 */
import { useEffect, useRef } from 'react';

import { STATUS_PRIORITY, statusVisual, subscribeBoard, useBoard } from '../../../entities/board';
import { selectAgent, subscribeSelection } from '../../../features/select-agent';
import { type OfficeLoop, startOfficeLoop } from '../engine/loop';
import { DARK, LIGHT } from '../engine/palette';
import styles from './OfficeFloor.module.css';

const scaleFor = (width: number) => (width >= 1100 ? 3 : 2);

export function OfficeFloor() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const loopRef = useRef<OfficeLoop | null>(null);
  const counts = useBoard((s) => s.snapshot?.office?.counts ?? null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const dark = window.matchMedia('(prefers-color-scheme: dark)');
    const width = wrap.clientWidth;
    const loop = startOfficeLoop(canvas, {
      office: null,
      selectedId: null,
      hoverId: null,
      theme: dark.matches ? DARK : LIGHT,
      scale: scaleFor(width),
      widthPx: width,
    });
    loopRef.current = loop;

    const offBoard = subscribeBoard((s) => loop.update({ office: s.snapshot?.office ?? null }));
    const offSelection = subscribeSelection((id) => loop.update({ selectedId: id }));
    const onTheme = () => loop.update({ theme: dark.matches ? DARK : LIGHT });
    dark.addEventListener('change', onTheme);
    const resize = new ResizeObserver(([entry]) => {
      const w = entry.contentRect.width;
      loop.update({ widthPx: w, scale: scaleFor(w) });
    });
    resize.observe(wrap);

    return () => {
      resize.disconnect();
      dark.removeEventListener('change', onTheme);
      offSelection();
      offBoard();
      loop.stop();
      loopRef.current = null;
    };
  }, []);

  const pointAt = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return loopRef.current?.hit(e.clientX - rect.left, e.clientY - rect.top) ?? null;
  };

  const summary = STATUS_PRIORITY.filter((s) => counts?.[s])
    .map((s) => `${statusVisual(s).label} ${counts?.[s]}`)
    .join(', ');

  return (
    <div ref={wrapRef} className={styles.wrap}>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        role="img"
        aria-label={summary ? `사무실: ${summary}` : '사무실이 비어 있습니다'}
        onClick={(e) => selectAgent(pointAt(e))}
        onMouseMove={(e) => {
          const id = pointAt(e);
          loopRef.current?.update({ hoverId: id });
          e.currentTarget.style.cursor = id ? 'pointer' : 'default';
        }}
        onMouseLeave={() => loopRef.current?.update({ hoverId: null })}
      />
    </div>
  );
}
