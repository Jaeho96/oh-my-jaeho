export interface Point {
  x: number;
  y: number;
}
export interface Seat extends Point {
  agentId: string;
  teamId: string;
  roomId: string;
  isLead: boolean;
  slot: number;
}
export interface Pod extends Point {
  teamId: string;
  label: string;
  provider: string | null;
  w: number;
  h: number;
}
export interface RoomBox extends Point {
  roomId: string;
  label: string;
  hidden: number;
  error: string | null;
  w: number;
  h: number;
  completed: number;
  agentIds: string[];
  bench: Point;
  exit: Point;
  doors: Point[];
}
export interface Scene {
  widthTiles: number;
  heightTiles: number;
  rooms: RoomBox[];
  pods: Pod[];
  seats: Seat[];
  blocked: Set<string>;
}
export const cellKey = (p: Point): string => `${p.x},${p.y}`;
