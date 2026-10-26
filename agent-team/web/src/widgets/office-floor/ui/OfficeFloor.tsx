import { useEffect, useRef, useState } from 'react';
import { STATUS_PRIORITY, statusVisual, subscribeBoard, useBoard } from '../../../entities/board';
import { selectAgent, subscribeSelection } from '../../../features/select-agent';
import { type OfficeLoop, startOfficeLoop } from '../engine/loop';
import { DARK, LIGHT } from '../engine/palette';
import { availableHeight, contentHeight } from './viewport';
import styles from './OfficeFloor.module.css';
export function OfficeFloor({ className = '' }: {
  className?: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const loopRef = useRef<OfficeLoop | null>(null);
  const dragRef = useRef<{
    x: number;
    y: number;
    moved: boolean;
  } | null>(null);
  const [zoom, setZoom] = useState(0);
  const [roomId, setRoomId] = useState('');
  const office = useBoard(s => s.snapshot?.office ?? null);
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) {
      return;
    }
    const dark = window.matchMedia('(prefers-color-scheme: dark)');
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let bounds: { width: number; height: number } | null = null;
    const syncHeight = () => {
      if (!bounds || !wrap.clientWidth) return;
      const height = contentHeight(bounds.width, bounds.height, wrap.clientWidth, availableHeight(window.innerHeight), window.innerWidth);
      wrap.style.height = `${height}px`;
    };
    const loop = startOfficeLoop(canvas, { office: null, selectedId: null, hoverId: null, theme: dark.matches ? DARK : LIGHT,
      scale: 0, viewportWidth: window.innerWidth, widthPx: wrap.clientWidth, heightPx: wrap.clientHeight, reduced: motion.matches, roomId: null,
      onLayout: (width, height) => { bounds = { width, height }; syncHeight(); },
    });
    loopRef.current = loop;
    const offBoard = subscribeBoard(s => loop.update({ office: s.snapshot?.office ?? null }));
    const offSelection = subscribeSelection(id => loop.update({ selectedId: id }));
    const onTheme = () => loop.update({ theme: dark.matches ? DARK : LIGHT });
    const onMotion = () => loop.update({ reduced: motion.matches });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        selectAgent(null);
      }
    };
    dark.addEventListener('change', onTheme);
    motion.addEventListener('change', onMotion);
    window.addEventListener('keydown', onKey);
    window.addEventListener('resize', syncHeight);
    const resize = new ResizeObserver(([entry]) => {
      if (entry) {
        loop.update({ viewportWidth: window.innerWidth, widthPx: entry.contentRect.width, heightPx: entry.contentRect.height });
        syncHeight();
      }
    });
    resize.observe(wrap);
    return () => {
      resize.disconnect();
      dark.removeEventListener('change', onTheme);
      motion.removeEventListener('change', onMotion);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', syncHeight);
      offSelection();
      offBoard();
      loop.stop();
      loopRef.current = null;
    };
  }, []);
  const pointAt = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return loopRef.current?.hit(event.clientX - rect.left, event.clientY - rect.top) ?? null;
  };
  const summary = STATUS_PRIORITY.filter(s => office?.counts[s]).map(s => `${statusVisual(s).label} ${office?.counts[s]}`).join(', ');
  const showAll = () => {
    setZoom(0);
    setRoomId('');
    loopRef.current?.update({ scale: 0, roomId: null });
  };
  const changeRoom = (value: string) => {
    setRoomId(value);
    setZoom(0);
    loopRef.current?.update({ roomId: value || null, scale: 0 });
  };
  const changeZoom = (value: string) => {
    const scale = Number(value);
    setZoom(scale);
    loopRef.current?.update({ scale });
  };
  return (
    <section className={`${styles.office} ${className}`} aria-label="도트 사무실">
      <div className={styles.toolbar} role="toolbar" aria-label="사무실 보기">
        <label>
          방
          <select aria-label="사무실 방 선택" value={roomId} onChange={e => changeRoom(e.target.value)}>
            <option value="">모든 방</option>
            {office?.rooms.map(room => (
              <option key={room.id} value={room.id}>
                {room.label} · {room.teams.reduce((n, team) => n + 1 + team.members.length, 0)}명
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={showAll}>전체 보기</button>
        <label>
          확대
          <select aria-label="사무실 확대" value={zoom} onChange={e => changeZoom(e.target.value)}>
            <option value="0">자동</option>
            {[1, 2, 3, 4].map(scale => <option key={scale} value={scale}>{scale}배</option>)}
          </select>
        </label>
        <span className={styles.hint}>드래그하여 이동</span>
      </div>
      <div className={styles.roomSummary} aria-label="사무실 방 현황">
        {office?.rooms.filter(room => !roomId || room.id === roomId).map(room => (
          <span key={room.id}>
            {room.label} · {room.teams.reduce((n, team) => n + 1 + team.members.length, 0)}명
            {' · 완료 '}{room.teams.reduce((n, team) => n + team.members.filter(agent => agent.status === 'done').length, 0)}명
            {room.error ? ` · 방 오류: ${room.error}` : room.teams.length === 0 ? ' · 활동 없음' : ''}
          </span>
        ))}
      </div>
      <div ref={wrapRef} className={styles.wrap}>
        <canvas
          ref={canvasRef}
          className={styles.canvas}
          role="img"
          aria-label={summary ? `사무실: ${summary}` : '사무실이 비어 있습니다'}
          onPointerDown={event => {
            dragRef.current = { x: event.clientX, y: event.clientY, moved: false };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={event => {
            const drag = dragRef.current;
            if (!drag) return;
            const dx = event.clientX - drag.x;
            const dy = event.clientY - drag.y;
            if (Math.abs(dx) + Math.abs(dy) > 2) drag.moved = true;
            if (drag.moved) loopRef.current?.pan(dx, dy);
            drag.x = event.clientX;
            drag.y = event.clientY;
          }}
          onPointerUp={() => {
            if (dragRef.current?.moved) {
              setTimeout(() => { dragRef.current = null; }, 0);
            } else {
              dragRef.current = null;
            }
          }}
          onClick={event => {
            if (!dragRef.current?.moved) selectAgent(pointAt(event));
          }}
          onMouseMove={event => {
            const id = pointAt(event);
            loopRef.current?.update({ hoverId: id });
            event.currentTarget.style.cursor = id ? 'pointer' : 'grab';
          }}
          onMouseLeave={() => loopRef.current?.update({ hoverId: null })}
        />
      </div>
    </section>
  );
}
