import { TILE, seatFoot } from './layout';
import type { Agent, AgentStatus, Office } from '../../../entities/board';
import { deriveBehavior, type Pose } from './behavior';
import { findPath } from './pathfinding';
import { cellKey, type Point, type Scene } from './sceneTypes';
import type { Direction } from './spriteData';
export type Phase = 'work' | 'idle-rest' | 'check' | 'rest' | 'exit' | 'exited';
export interface Actor {
  id: string;
  x: number;
  y: number;
  direction: Direction;
  pose: Pose;
  status: AgentStatus;
  phase: Phase;
  since: number;
  path: Point[];
  target: string;
  roomId: string;
  phaseOffset: number;
  trips: number;
  alpha: number;
  arrivedAt: number | null;
}
export interface Simulation {
  actors: Map<string, Actor>;
  initialized: boolean;
}
export function createSimulation(): Simulation {
  return { actors: new Map(), initialized: false };
}
export function officeAgents(office: Office | null): Map<string, Agent> {
  return new Map((office?.rooms ?? []).flatMap(r => r.teams.flatMap(t => [t.lead, ...t.members])).map(a => [a.id, a]));
}
function tileOf(actor: Actor): Point {
  return { x: Math.floor(actor.x / TILE), y: Math.floor(actor.y / TILE) };
}
function move(actor: Actor, scene: Scene, target: Point, dt: number, reserved: Set<string>, reduced: boolean): boolean {
  const current = tileOf(actor);
  const key = cellKey(target);
  if (reduced) {
    actor.x = target.x * TILE + 8;
    actor.y = target.y * TILE + 15;
    actor.path = [];
    actor.target = key;
    return true;
  }
  if (actor.target !== key) {
    actor.target = key;
    actor.path = findPath(scene, current, target).path;
  }
  const next = actor.path[0];
  if (!next) {
    return cellKey(current) === key;
  }
  if (reserved.has(cellKey(next))) {
    const alternative = findPath(scene, current, target, reserved);
    if (alternative.kind === 'path') {
      actor.path = alternative.path;
    }
    return false;
  }
  reserved.add(cellKey(next));
  const dx = next.x * TILE + 8 - actor.x;
  const dy = next.y * TILE + 15 - actor.y;
  const distance = Math.hypot(dx, dy);
  const amount = Math.min(distance, 48 * dt);
  actor.direction = Math.abs(dx) > Math.abs(dy) ? dx > 0 ? 'right' : 'left' : dy > 0 ? 'down' : 'up';
  actor.pose = 'walk';
  if (distance <= amount) {
    actor.x = next.x * TILE + 8;
    actor.y = next.y * TILE + 15;
    actor.path.shift();
  }
  else {
    actor.x += dx / distance * amount;
    actor.y += dy / distance * amount;
  }
  return actor.path.length === 0;
}
export function advanceSimulation(sim: Simulation, scene: Scene, agents: Map<string, Agent>, now: number, dt: number, selectedId: string | null, reduced: boolean): void {
  const reserved = new Set<string>();
  for (const [id, actor] of sim.actors) {
    if (!agents.has(id)) {
      sim.actors.delete(id);
    }
    else if (actor.phase !== 'exited') {
      reserved.add(cellKey(tileOf(actor)));
    }
  }
  for (const [id, agent] of [...agents].toSorted(([a], [b]) => a.localeCompare(b))) {
    const seat = scene.seats.find(s => s.agentId === id);
    const room = scene.rooms.find(r => r.roomId === seat?.roomId) ?? scene.rooms.find(r => r.agentIds.includes(id));
    const fallbackRoom = room ?? scene.rooms[0];
    if (!fallbackRoom) {
      continue;
    }
    const foot = seat ? seatFoot(seat) : null;
    const work = foot ? { x: Math.floor(foot.x / TILE), y: Math.floor(foot.y / TILE) } : fallbackRoom.bench;
    let actor = sim.actors.get(id);
    if (!actor) {
      const done = agent.status === 'done' && agent.kind === 'subagent';
      const start = done ? fallbackRoom.bench : sim.initialized ? fallbackRoom.exit : work;
      actor = { id, x: start.x * TILE + 8, y: start.y * TILE + 15, direction: 'up', pose: 'sit', status: agent.status, phase: done ? 'exited' : 'work', since: now, path: [], target: '', roomId: fallbackRoom.roomId, phaseOffset: [...id].reduce((n, c) => n + c.charCodeAt(0) * 97, 0) % 4000, trips: 0, alpha: 1, arrivedAt: null };
      if (foot && !done && !sim.initialized) {
        actor.x = foot.x;
        actor.y = foot.y;
      }
      sim.actors.set(id, actor);
    }
    reserved.delete(cellKey(tileOf(actor)));
    actor.roomId = fallbackRoom.roomId;
    if (actor.status !== agent.status) {
      actor.status = agent.status;
      actor.since = now;
      actor.path = [];
      actor.target = '';
      actor.alpha = 1;
      actor.phase = agent.status === 'done' ? 'check' : 'work';
      actor.trips = 0;
      actor.arrivedAt = null;
    }
    const behavior = deriveBehavior(agent.status);
    actor.pose = behavior.pose;
    if (behavior.frozen) {
      actor.path = [];
      actor.target = '';
      continue;
    }
    if (agent.status === 'done') {
      if (actor.phase === 'work') {
        actor.phase = 'check';
      }
      if (actor.phase === 'exited') {
        if (selectedId === id) {
          actor.x = fallbackRoom.bench.x * TILE + 8;
          actor.y = fallbackRoom.bench.y * TILE + 15;
          actor.alpha = 1;
        }
        continue;
      }
      if (actor.phase === 'check' && now - actor.since >= 2000) {
        actor.phase = 'rest';
        actor.since = now;
        actor.target = '';
        actor.arrivedAt = null;
      }
      if (actor.phase === 'rest') {
        const arrived = move(actor, scene, fallbackRoom.bench, dt, reserved, reduced);
        if (arrived) {
          actor.pose = 'sit';
          if (actor.arrivedAt === null) {
            actor.arrivedAt = now;
          }
          if (now - actor.arrivedAt >= 6000 && selectedId !== id && agent.kind === 'subagent') {
            actor.phase = 'exit';
            actor.target = '';
            actor.since = now;
          }
        }
      }
      if (actor.phase === 'exit') {
        if (selectedId === id) {
          actor.phase = 'rest';
          actor.target = '';
          actor.arrivedAt = null;
          actor.alpha = 1;
          continue;
        }
        if (move(actor, scene, fallbackRoom.exit, dt, reserved, reduced)) {
          if (actor.alpha === 1) {
            actor.since = now;
            actor.alpha = .999;
          }
          else {
            actor.alpha = Math.max(0, 1 - (now - actor.since) / 300);
          }
          if (actor.alpha === 0) {
            actor.phase = 'exited';
          }
        }
      }
      continue;
    }
    if (agent.status === 'idle' && !reduced && now - actor.since >= 10000 && actor.trips < 2) {
      const moving = [...sim.actors.values()].filter(a => a.roomId === actor.roomId && a.pose === 'walk').length;
      if (actor.phase === 'work' && moving < 2) {
        actor.phase = 'idle-rest';
        actor.arrivedAt = null;
        actor.target = '';
        actor.since = now;
      }
    }
    const target = actor.phase === 'idle-rest' ? fallbackRoom.bench : work;
    const arrived = move(actor, scene, target, dt, reserved, reduced);
    if (arrived) {
      actor.pose = behavior.pose;
      actor.direction = 'up';
      if (foot && actor.phase === 'work') {
        actor.x = foot.x;
        actor.y = foot.y;
      }
      if (actor.phase === 'idle-rest' && actor.arrivedAt === null) {
        actor.arrivedAt = now;
      }
      if (actor.phase === 'idle-rest' && actor.arrivedAt !== null && now - actor.arrivedAt > 8000 + actor.phaseOffset * 2.5) {
        actor.phase = 'work';
        actor.since = now;
        actor.trips += 1;
        actor.target = '';
      }
    }
  }
  sim.initialized = sim.initialized || agents.size > 0;
}
