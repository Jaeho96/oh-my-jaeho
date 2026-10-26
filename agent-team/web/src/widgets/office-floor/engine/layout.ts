import type { Office } from '../../../entities/board';
import { cellKey, type Scene, type Seat, type RoomBox, type Pod, type Point } from './sceneTypes';
export type { Scene, Seat, RoomBox, Pod } from './sceneTypes';
export const TILE = 16;
export const SEAT_W = 3;
export const SEAT_H = 2.5;
export function roomDimensions(n: number): {
  columns: number;
  w: number;
  h: number;
} {
  const columns = n <= 4 ? 2 : 4;
  return { columns, w: columns * SEAT_W + 2, h: Math.max(10, Math.ceil(n / columns) * SEAT_H + 5) };
}
/** 인원으로 방 크기를 정하고, 이웃한 방은 한 타일 두께의 벽을 공유한다. */
export function computeLayout(office: Office | null, widthTiles = 24, previous?: Scene, keepSpace = false): Scene {
  const rooms: RoomBox[] = [];
  const seats: Seat[] = [];
  const pods: Pod[] = [];
  const blocked = new Set<string>();
  let x = 0;
  let y = 0;
  let rowHeight = 0;
  let width = 0;
  for (const room of [...(office?.rooms ?? [])].toSorted((a, b) => a.id.localeCompare(b.id))) {
    const teams = [...room.teams].toSorted((a, b) => a.id.localeCompare(b.id));
    const entries = teams.flatMap(team =>
      [team.lead, ...[...team.members].toSorted((a, b) => a.id.localeCompare(b.id))]
      .filter(a => a.kind === 'lead' || a.status !== 'done' || keepSpace && previous?.seats.some(s => s.agentId === a.id))
      .map(agent => ({ agent, team })));
    const oldRoom = previous?.rooms.find(r => r.roomId === room.id);
    const retained = previous?.seats.filter(s => s.roomId === room.id && entries.some(e => e.agent.id === s.agentId)) ?? [];
    const d = roomDimensions(entries.length);
    if (keepSpace && oldRoom) {
      d.w = Math.max(d.w, oldRoom.w);
      d.h = Math.max(d.h, oldRoom.h);
    }
    // 자리가 늘어도 기존 열 수와 상대 좌표를 보존한다.
    if (oldRoom && retained.length) {
      d.columns = Math.max(d.columns, Math.round((oldRoom.w - 2) / SEAT_W));
      d.w = Math.max(d.w, d.columns * SEAT_W + 2);
      d.h = Math.max(d.h, ...retained.map(s => s.y - oldRoom.y + 5));
    }
    if (x > 0 && x + d.w > widthTiles) {
      x = 0;
      y += rowHeight - 1;
      rowHeight = 0;
    }
    const box: RoomBox = {
      roomId: room.id, label: room.label, hidden: room.hidden, error: room.error,
      x, y, w: d.w, h: Math.ceil(d.h),
      agentIds: room.teams.flatMap(t => [t.lead.id, ...t.members.map(a => a.id)]),
      completed: room.teams.reduce((n, t) => n + t.members.filter(a => a.status === 'done').length, 0),
      bench: { x: x + 2, y: y + Math.ceil(d.h) - 3 },
      exit: { x: x + d.w - 3, y: y + Math.ceil(d.h) - 1 },
      doors: [{ x: x + d.w - 3, y: y + Math.ceil(d.h) - 1 }],
    };
    rooms.push(box);
    const retainedSlots = new Map(retained.map(s => [s.agentId, s.slot]));
    const used = new Set(retainedSlots.values());
    for (const { agent, team } of entries) {
      let slot = retainedSlots.get(agent.id);
      if (slot === undefined) {
        slot = 0;
        const occupied = (candidate: number) => retained.some(s =>
          oldRoom &&
          s.x - oldRoom.x === 1 + candidate % d.columns * SEAT_W &&
          s.y - oldRoom.y === 1.5 + Math.floor(candidate / d.columns) * SEAT_H);
        while (used.has(slot) || occupied(slot)) {
          slot += 1;
        }
        used.add(slot);
      }
      const retainedSeat = retained.find(s => s.agentId === agent.id);
      const sx = retainedSeat && oldRoom ? x + retainedSeat.x - oldRoom.x : x + 1 + slot % d.columns * SEAT_W;
      const sy = retainedSeat && oldRoom ? y + retainedSeat.y - oldRoom.y : y + 1.5 + Math.floor(slot / d.columns) * SEAT_H;
      box.h = Math.max(box.h, Math.ceil(sy - y + 5));
      seats.push({ agentId: agent.id, teamId: team.id, roomId: room.id, isLead: agent.id === team.lead.id, slot, x: sx, y: sy });
      pods.push({ teamId: team.id, label: team.label, provider: team.provider, x: sx, y: sy, w: 2.5, h: 2.5 });
      for (let dy = 0; dy < 2; dy += 1) {
        for (let dx = 0; dx < 2; dx += 1) {
          blocked.add(cellKey({ x: sx + dx, y: Math.floor(sy) + dy }));
        }
      }
    }
    x += box.w - 1;
    width = Math.max(width, x + 1);
    rowHeight = Math.max(rowHeight, box.h);
  }
  // 빈 슬롯을 건너뛰며 방이 커질 수 있으므로 출구와 휴게석은 최종 높이로 계산한다.
  for (const room of rooms) {
    room.bench = { x: room.x + 2, y: room.y + room.h - 3 };
    room.exit = { x: room.x + room.w - 3, y: room.y + room.h - 1 };
    room.doors = [room.exit];
  }
  for (const room of rooms) {
    const neighbor = rooms.find(r => r.y === room.y && r.x + r.w - 1 === room.x);
    if (neighbor) {
      const door = { x: room.x, y: room.y + Math.min(room.h, neighbor.h) - 2 };
      neighbor.doors.push(door);
      room.doors.push(door);
    }
  }
  for (const room of rooms) {
    for (let by = room.y; by < room.y + room.h; by += 1) {
      for (let bx = room.x; bx < room.x + room.w; bx += 1) {
        if (by <= room.y || bx === room.x || bx === room.x + room.w - 1 || by === room.y + room.h - 1) {
          blocked.add(cellKey({ x: bx, y: by }));
        }
      }
    }
  }
  // 공유 벽 양쪽에서 같은 문을 통과할 수 있게 마지막에 문 타일을 연다.
  for (const room of rooms) {
    for (const door of room.doors) {
      blocked.delete(cellKey(door));
    }
  }
  return { rooms, seats, pods, blocked, widthTiles: Math.max(width, 1), heightTiles: Math.max(y + rowHeight, 1) };
}
export function seatFoot(seat: Point): Point {
  return { x: seat.x * TILE + TILE, y: seat.y * TILE + 38 };
}
