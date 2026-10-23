/**
 * 사무실 자동 배치. 방(기기) 안에 팀 묶음(리더 책상 + 팀원 책상)을 왼쪽부터 채우고, 넘치면 다음 줄로 내린다.
 * 단위는 타일이다(1타일 = TILE 픽셀). 그리기와 클릭 판정이 같은 결과를 쓴다. React 를 모른다.
 */
import type { Office } from '../../../entities/board';

export const TILE = 16;
export const SEAT_W = 3; // 책상 하나가 차지하는 칸(가로)
export const SEAT_H = 4; // 말풍선·캐릭터·책상·이름표(세로)
const ROOM_HEADER = 2; // 벽과 방 이름
const ROOM_PAD = 1;
const POD_GAP = 1;

export interface Seat {
  agentId: string;
  teamId: string;
  isLead: boolean;
  x: number; // 자리 왼쪽 위(타일)
  y: number;
}

export interface Pod {
  teamId: string;
  label: string;
  provider: string | null;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface RoomBox {
  roomId: string;
  label: string;
  hidden: number;
  error: string | null;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Scene {
  widthTiles: number;
  heightTiles: number;
  rooms: RoomBox[];
  pods: Pod[];
  seats: Seat[];
}

export function computeLayout(office: Office | null, widthTiles: number): Scene {
  const width = Math.max(widthTiles, SEAT_W * 2 + ROOM_PAD * 2);
  const inner = width - ROOM_PAD * 2;
  const perRow = Math.max(1, Math.floor(inner / SEAT_W));
  const rooms: RoomBox[] = [];
  const pods: Pod[] = [];
  const seats: Seat[] = [];
  let top = 0;

  for (const room of office?.rooms ?? []) {
    let cursorX = ROOM_PAD;
    let cursorY = top + ROOM_HEADER;
    let rowHeight = 0;

    for (const team of room.teams) {
      const ids = [team.lead.id, ...team.members.map((m) => m.id)];
      const cols = Math.min(ids.length, perRow);
      const rows = Math.ceil(ids.length / cols);
      const podW = cols * SEAT_W;
      const podH = rows * SEAT_H;
      if (cursorX > ROOM_PAD && cursorX + podW > ROOM_PAD + inner) {
        cursorX = ROOM_PAD;
        cursorY += rowHeight + POD_GAP;
        rowHeight = 0;
      }
      pods.push({ teamId: team.id, label: team.label, provider: team.provider, x: cursorX, y: cursorY, w: podW, h: podH });
      ids.forEach((agentId, i) => {
        seats.push({
          agentId,
          teamId: team.id,
          isLead: i === 0,
          x: cursorX + (i % cols) * SEAT_W,
          y: cursorY + Math.floor(i / cols) * SEAT_H,
        });
      });
      cursorX += podW + POD_GAP;
      rowHeight = Math.max(rowHeight, podH);
    }

    const bodyH = Math.max(rowHeight, SEAT_H);
    const h = cursorY - top + bodyH + ROOM_PAD;
    rooms.push({ roomId: room.id, label: room.label, hidden: room.hidden, error: room.error, x: 0, y: top, w: width, h });
    top += h;
  }

  return { widthTiles: width, heightTiles: Math.max(top, SEAT_H + ROOM_HEADER), rooms, pods, seats };
}

/** 화면 좌표(CSS 픽셀) → 그 자리의 에이전트 id. */
export function hitTest(scene: Scene, cssX: number, cssY: number, scale: number): string | null {
  const tx = cssX / (TILE * scale);
  const ty = cssY / (TILE * scale);
  const seat = scene.seats.find((s) => tx >= s.x && tx < s.x + SEAT_W && ty >= s.y && ty < s.y + SEAT_H);
  return seat?.agentId ?? null;
}
