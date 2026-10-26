import type { Pose } from './behavior';
import { TILE } from './layout';
import { ANCHOR, appearanceFor, spritePixels, type Direction } from './spriteData';
import { spritePalette, type OfficeTheme } from './palette';
import { FURNITURE, FURNITURE_PALETTE, type FurnitureId } from './furnitureData';
import type { SpriteCache } from './spriteCache';

export function paintPixels(ctx: CanvasRenderingContext2D, rows: string[], colors: Record<string, string>, x = 0, y = 0): void {
  rows.forEach((row, py) => {
    [...row].forEach((key, px) => {
      const color = colors[key];
      if (color) {
        ctx.fillStyle = color;
        ctx.fillRect(x + px, y + py, 1, 1);
      }
    });
  });
}

export function drawCharacter(ctx: CanvasRenderingContext2D, x: number, y: number, id: string, role: string | null, direction: Direction, pose: Pose, frame: number, cache: SpriteCache, outline: string | null, blink = false): void {
  const appearance = appearanceFor(id);
  const key = `${appearance}/${role}/${direction}/${pose}/${frame}/${blink}`;
  const pixels = spritePixels(direction, pose, frame);
  if (blink && direction === 'down') {
    pixels[7] = pixels[7].replace('osossoso', 'osssssso');
  }
  const sprite = cache.get(key, TILE, TILE * 2, c => paintPixels(c, pixels, spritePalette(appearance, role)));
  if (!sprite) {
    return;
  }
  if (outline) {
    const mask = cache.get(`${key}/${outline}`, TILE, TILE * 2, c => {
      c.drawImage(sprite, 0, 0);
      c.globalCompositeOperation = 'source-in';
      c.fillStyle = outline;
      c.fillRect(0, 0, TILE, TILE * 2);
    });
    if (mask) {
      for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
        ctx.drawImage(mask, x - ANCHOR.x + dx, y - ANCHOR.y + dy);
      }
    }
  }
  ctx.drawImage(sprite, x - ANCHOR.x, y - ANCHOR.y);
}

/** 가구는 확대와 무관한 논리 픽셀 크기로 한 번만 래스터화한다. */
export function drawFurniture(ctx: CanvasRenderingContext2D, id: FurnitureId, x: number, y: number, cache: SpriteCache, theme?: OfficeTheme, variant = ''): void {
  const data = FURNITURE[id];
  const colors = { ...FURNITURE_PALETTE };
  if (theme) {
    colors.T = theme.desk;
    colors.d = theme.deskEdge;
    colors.g = theme.chair;
  }
  if (variant === 'leader') {
    colors.G = '#b48b5c';
    colors.g = '#795339';
  }
  const key = `furniture/${id}/${theme?.desk ?? ''}/${theme?.chair ?? ''}/${variant}`;
  const sprite = cache.get(key, data.width, data.height, c => paintPixels(c, data.pixels, colors));
  if (sprite) {
    ctx.drawImage(sprite, x, y);
  }
}

const BUBBLE_SHAPE = [
  '..oooooooo..', '.owwwwwwwwo.', 'owwwwwwwwwwo', 'owwwwwwwwwwo', 'owwwwwwwwwwo', 'owwwwwwwwwwo',
  'owwwwwwwwwwo', '.owwwwwwwwo.', '..ooooowoo..', '.....owo....', '.....oo.....', '............',
];
const BUBBLE_MARKS: Record<string, string[]> = {
  '···': ['.....', '.....', 'o.o.o', '.....', '.....'],
  '팀': ['ooooo', '..o..', 'o.o.o', 'o.o.o', 'ooooo'],
  '?': ['.ooo.', 'o...o', '...o.', '..o..', '..o..'],
  '!': ['..o..', '..o..', '..o..', '.....', '..o..'],
  'Ⅱ': ['.o.o.', '.o.o.', '.o.o.', '.o.o.', '.o.o.'],
  '×': ['o...o', '.o.o.', '..o..', '.o.o.', 'o...o'],
  '✓': ['....o', '...o.', 'o.o..', '.o...', '.....'],
};

/** 작은 도트 말풍선의 좌상단을 받는다. 글꼴 렌더링을 쓰지 않는다. */
export function drawBubble(ctx: CanvasRenderingContext2D, kind: string, x: number, y: number, cache: SpriteCache, theme?: OfficeTheme): void {
  const key = `bubble/${kind}/${theme?.wall ?? ''}`;
  const sprite = cache.get(key, 12, 12, c => {
    paintPixels(c, BUBBLE_SHAPE, { o: '#28313e', w: '#eee9db' });
    paintPixels(c, BUBBLE_MARKS[kind] ?? BUBBLE_MARKS['···'], { o: kind === '×' ? '#aa4251' : '#466974' }, 3, 2);
  });
  if (sprite) {
    ctx.drawImage(sprite, x, y);
  }
}
