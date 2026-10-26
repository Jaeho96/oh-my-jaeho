import { describe, expect, it } from 'vitest';
import { availableHeight, contentHeight } from './viewport';

describe('사무실 내용 높이', () => {
  it('1680×843 에서 대기 띠 아래에 놓여도 두 방을 세 배로 그린다', () => {
    // 칸 위치(약 400px) 아래 남은 화면으로 잡으면 429px 이라 두 배로 떨어진다
    expect(contentHeight(336, 160, 1124, availableHeight(843))).toBe(480);
  });
  it('두 방이 세 배로 들어가는 높이에서 빈 띠를 제거한다', () => {
    expect(contentHeight(336, 128, 1124, 428)).toBe(384);
  });
  it('내용과 가용 높이가 늘면 고정 높이를 넘어 확장한다', () => {
    expect(contentHeight(336, 160, 1124, 620)).toBe(480);
    expect(contentHeight(336, 200, 1124, 900)).toBe(600);
  });
  it('좁은 화면과 매우 큰 방에서도 설계 높이 범위를 유지한다', () => {
    expect(contentHeight(224, 240, 354, 200)).toBe(480);
    expect(contentHeight(800, 900, 1124, 1000)).toBe(680);
  });
});
