import { describe, expect, it } from 'vitest';
import { FURNITURE, FURNITURE_PALETTE } from './furnitureData';
import { DIRECTIONS, spritePixels } from './spriteData';
import { spritePalette } from './palette';

describe('직접 그린 도트 자산', () => {
  it('모든 가구를 팔레트에 있는 키와 일정한 행 너비로 정의한다', () => {
    for (const data of Object.values(FURNITURE)) {
      expect(data.pixels.every(row => row.length === data.width)).toBe(true);
      for (const key of data.pixels.join('')) {
        expect(key === '.' || key in FURNITURE_PALETTE).toBe(true);
      }
    }
  });
  it('문을 한 타일 크기의 열린 문틀로 정의해 중앙 통로를 유지한다', () => {
    const door = FURNITURE.door;
    expect(door.width).toBe(16);
    expect(door.height).toBe(16);
    expect(door.pixels.slice(3).every(row => row.slice(3, 13) === '..........')).toBe(true);
  });
  it('인물의 모든 방향과 자세에서 발 기준 크기를 유지한다', () => {
    for (const direction of DIRECTIONS) {
      for (const pose of ['stand', 'walk', 'sit', 'type', 'read'] as const) {
        for (let frame = 0; frame < 4; frame += 1) {
          const pixels = spritePixels(direction, pose, frame);
          expect(pixels).toHaveLength(32);
          expect(pixels.every(row => row.length === 16)).toBe(true);
        }
      }
    }
  });
  it('여섯 외형의 상의와 하의를 각각 구분한다', () => {
    const palettes = Array.from({ length: 6 }, (_, i) => spritePalette(i, 'worker'));
    expect(new Set(palettes.map(p => p.c)).size).toBe(6);
    expect(new Set(palettes.map(p => p.p)).size).toBe(6);
  });
  it('앉아 타자 치는 뒷모습에 얼굴이 나타나지 않는다', () => {
    for (let frame = 0; frame < 2; frame += 1) {
      const head = spritePixels('up', 'type', frame).slice(3, 10).join('');
      expect(head).not.toMatch(/[sS]/);
    }
  });
});
