import { advanceSimulation, createSimulation, officeAgents } from './simulation';
import { describe, expect, it, vi } from 'vitest';
import { startOfficeLoop } from './loop';
import { LIGHT } from './palette';
import { makeOffice } from './testFixtures';
import { SpriteCache } from './spriteCache';
import { createRenderCache, drawScene, rasterizeFloor } from './renderer';
import { computeLayout, TILE } from './layout';
describe('사무실 외부 동기화', () => {
  it('같은 구성의 SSE 60회에도 캔버스 크기를 다시 설정하지 않고 RAF를 해제한다', () => {
    let callback: FrameRequestCallback | undefined;
    const request = vi.spyOn(window, 'requestAnimationFrame').mockImplementation(cb => { callback = cb; return 1; });
    const cancel = vi.spyOn(window, 'cancelAnimationFrame');
    const canvas = document.createElement('canvas');
    const resize = vi.spyOn(canvas, 'width', 'set');
    const loop = startOfficeLoop(canvas, { office: makeOffice(2), selectedId: null, hoverId: null, theme: LIGHT, scale: 3, widthPx: 800, heightPx: 500, reduced: false, roomId: null });
    callback?.(1);
    expect(resize).toHaveBeenCalledTimes(1);
    for (let i = 1; i <= 60; i += 1) {
      loop.update({ office: makeOffice(2) });
      callback?.(i * 17);
    }
    expect(resize).toHaveBeenCalledTimes(1);
    loop.stop();
    expect(cancel).toHaveBeenCalledWith(1);
    request.mockRestore();
    cancel.mockRestore();
    resize.mockRestore();
  });
  it('컨텍스트를 만들지 못하면 캐시를 비워 둔다', () => {
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    const cache = new SpriteCache(4096);
    expect(cache.get('a', 16, 32, () => { })).toBeNull();
    expect(cache.byteLength).toBe(0);
    cache.clear();
    getContext.mockRestore();
  });
  it('숨긴 탭에서는 크기 설정과 시뮬레이션을 멈추고 복귀한다', () => {
    let callback:FrameRequestCallback|undefined;
    const request=vi.spyOn(window,'requestAnimationFrame').mockImplementation(cb=>{callback=cb;return 1;});
    const hidden=vi.spyOn(document,'hidden','get').mockReturnValue(true);
    const canvas=document.createElement('canvas');const resize=vi.spyOn(canvas,'width','set');
    const loop=startOfficeLoop(canvas,{office:makeOffice(2),selectedId:null,hoverId:null,theme:LIGHT,scale:3,widthPx:800,heightPx:500,reduced:false,roomId:null});
    callback?.(1);callback?.(20000);expect(resize).not.toHaveBeenCalled();
    hidden.mockReturnValue(false);callback?.(20016);expect(resize).toHaveBeenCalledTimes(1);
    loop.stop();request.mockRestore();hidden.mockRestore();resize.mockRestore();
  });

  it.each([[0,32],[-1,32],[1.5,32],[NaN,32],[Infinity,32],[1e308,32],[16,32]])('예산 초과나 잘못된 크기 %s×%s는 스프라이트 캔버스를 생성하지 않는다', (width,height) => {
    const create = vi.spyOn(document,'createElement');
    const context = vi.spyOn(HTMLCanvasElement.prototype,'getContext');
    const paint = vi.fn();
    const cache = new SpriteCache(128);
    expect(cache.get('rejected',width,height,paint)).toBeNull();
    expect(create).not.toHaveBeenCalled();
    expect(context).not.toHaveBeenCalled();
    expect(paint).not.toHaveBeenCalled();
    expect(cache.byteLength).toBe(0);
    create.mockRestore();context.mockRestore();
  });
  it('16MiB를 넘는 바닥은 캔버스와 컨텍스트를 만들지 않고 직접 그리기로 넘긴다', () => {
    const create = vi.spyOn(document,'createElement');
    const context = vi.spyOn(HTMLCanvasElement.prototype,'getContext');
    const scene = {...computeLayout(null),widthTiles:256,heightTiles:256};
    expect(rasterizeFloor(scene,LIGHT)).toBeNull();
    expect(create).not.toHaveBeenCalled();
    expect(context).not.toHaveBeenCalled();
    create.mockRestore();context.mockRestore();
  });

});

it('실제 바닥에 문틀 대신 통로와 낮은 매트를 그린다', () => {
  const ctx = { fillRect: vi.fn(), drawImage: vi.fn() } as unknown as CanvasRenderingContext2D;
  const context = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx);
  const sprites = new SpriteCache();
  const get = vi.spyOn(sprites, 'get');
  const scene = computeLayout(makeOffice(8, 2));
  rasterizeFloor(scene, LIGHT, sprites);
  expect(get.mock.calls.some(([key]) => key.startsWith('furniture/door/'))).toBe(false);
  for (const room of scene.rooms) {
    for (const door of room.doors) {
      expect(ctx.fillRect).toHaveBeenCalledWith(door.x * TILE, door.y * TILE, TILE, TILE);
      expect(ctx.fillRect).toHaveBeenCalledWith(door.x * TILE + 2, door.y * TILE + TILE - 5, TILE - 4, 3);
    }
  }
  context.mockRestore();
});

it('실제 선택 이름표에 글자 없는 얇은 막대를 그리고 함께 충돌 판정한다', () => {
  const ctx = {
    fillRect: vi.fn(), drawImage: vi.fn(), setTransform: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(),
    moveTo: vi.fn(), arcTo: vi.fn(), fill: vi.fn(), fillText: vi.fn(), measureText: () => ({ width: 60 }),
  } as unknown as CanvasRenderingContext2D;
  const context = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx);
  const office = makeOffice(2);
  office.rooms[0].teams[0].lead.context = { used: 24000, window: 100000, pct: 24 };
  const scene = computeLayout(office);
  const agents = officeAgents(office);
  const simulation = createSimulation();
  advanceSimulation(simulation, scene, agents, 0, 0, null, true);
  const cache = createRenderCache();
  drawScene(ctx, { scene, agents, simulation, selectedId: '0-0', hoverId: null, theme: LIGHT,
    camera: { x: 0, y: 0, zoom: 3, width: 800, height: 500, dpr: 1 }, t: 0, reduced: true }, cache);
  const selected = cache.labels.find(box => box.id === '0-0');
  expect(selected?.h).toBe(26);
  expect(ctx.fillText).not.toHaveBeenCalledWith(expect.stringContaining('컨텍스트'), expect.anything(), expect.anything());
  expect(ctx.fillRect).toHaveBeenCalledWith(expect.any(Number), expect.any(Number), expect.any(Number), 3);
  context.mockRestore();
});
