export interface LabelBox {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  priority: number;
}
export function visibleLabels(boxes: LabelBox[]): LabelBox[] {
  const kept: LabelBox[] = [];
  for (const box of [...boxes].toSorted((a, b) => b.priority - a.priority || a.id.localeCompare(b.id))) {
    if (!kept.some(b => box.x < b.x + b.w && box.x + box.w > b.x && box.y < b.y + b.h && box.y + box.h > b.y)) {
      kept.push(box);
    }
  }
  return kept;
}
/** 기본 이름표는 리더와 확인이 필요한 사람에게만 붙인다. */
export function labelPriority(status: string, selected: boolean, hovered: boolean, lead: boolean, zoom = 2): number {
  if (zoom < 2 && !selected) return 0;
  if (selected) {
    return 4;
  }
  if (['permission', 'waiting', 'stalled', 'error'].includes(status)) {
    return 3;
  }
  if (hovered) {
    return 2;
  }
  return lead ? 1 : 0;
}

/** 이름표와 막대 전체를 한 충돌 영역으로 취급한다. */
export function labelHeight(gauge: boolean): number {
  return gauge ? 26 : 20;
}
