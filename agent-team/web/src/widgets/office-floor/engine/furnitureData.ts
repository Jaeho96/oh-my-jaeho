/** 직접 그린 가구 픽셀맵. 좌상단이 배치 기준이며 점은 투명하다. */
export const FURNITURE_PALETTE: Record<string, string> = {
  o: '#26303c', s: '#384352', t: '#e0b880', T: '#bd8e59', d: '#93613e', D: '#694830',
  h: '#7595a4', H: '#b6d1d2', b: '#435e70', B: '#667e8e', w: '#eee6cf',
  l: '#315546', L: '#638265', v: '#8aa36c', p: '#79513c', P: '#b7865a',
  r: '#854357', R: '#b85c73', g: '#496e64', G: '#729080', y: '#d5ad60',
  k: '#b8c5c4', K: '#798c91', a: '#5b7085', A: '#8da5b6', u: '#ae976e', U: '#c1ad82',
};

const desk = [
  '.oooooooooooooooooooooooooooooo.',
  'otttttttttttttttttttttttttttttto',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'oTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTo',
  'otttttttttttttttttttttttttttttto',
  'oddddddddddddddddddddddddddddddo',
  'oddddddddddddddddddddddddddddddo',
  'oDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDo',
  '.oooooooooooooooooooooooooooooo.',
  '..oKKo....................oKKo..',
  '..oKKo....................oKKo..',
  '..oKKo....................oKKo..',
  '..oooo....................oooo..',
  '...sssssssssssssssssssssssssss..',
  '....sssssssssssssssssssssssss...',
  '................................',
];

const maps = {
  desk,
  deskLead: desk.map(row => row.slice(0, 16) + row.slice(12, 20) + row.slice(16)),
  chairFront: [
    '..oooooooo..', '.ogGGGGGGgo.', '.ogGGGGGGgo.', '.ogGGGGGGgo.', '.ogGGGGGGgo.', '.oggggggggo.',
    '..oooooooo..', '...oKKKo....', '.oooooooooo.', 'ogGGGGGGGGgo', 'oggggggggggo', '.oooooooooo.',
    '.....oo.....', '.....oo.....', '..oooooooo..', '..oo....oo..',
  ],
  chairBack: [
    '..oooooooo..', '.ogGGGGGGgo.', '.ogGGGGGGgo.', '.ogGGGGGGgo.', '.ogGGGGGGgo.', '.oggggggggo.',
    '.oggggggggo.', '..oooooooo..', '...oKKKo....', '..oKKKKKo...', '..ooooooo...', '.....oo.....',
    '.....oo.....', '..oooooooo..', '..oo....oo..', '............',
  ],
  monitorFront: [
    '.oooooooooo.', 'oKKKKKKKKKKo', 'oKbbbbbbbbKo', 'oKbhhhhhbbKo', 'oKbhhbbbbbKo', 'oKbhhhhbbbKo',
    'oKbbbbbbbbKo', 'oKKKKKKKKKKo', '.oooooooooo.', '.....oo.....', '....oKKo....', '..oooooooo..',
  ],
  monitorSide: [
    '...ooooo....', '...oKKKo....', '...oKbKo....', '...oKbKo....', '...oKbKo....', '...oKbKo....',
    '...oKbKo....', '...oKKKo....', '...ooooo....', '.....oo.....', '....oKKo....', '..oooooooo..',
  ],
  keyboard: ['.oooooooooo.', 'owkwkwkwkwko', 'okwkwwkwkwko', '.oooooooooo.'],
  bookcase: [
    'oooooooooooooooooooooooooooooooo', 'otttttttttttttttttttttttttttttto',
    'oDRRyybbGGwwrrBBggYYwwbbRRyyTDo', 'oDRRyybbGGwwrrBBggYYwwbbRRyyTDo',
    'oDRRyybbGGwwrrBBggYYwwbbRRyyTDo', 'otttttttttttttttttttttttttttttto',
    'oDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDo', 'oDwwGGrrBBYYbbggRRwwyyGGbbrrTDo',
    'oDwwGGrrBBYYbbggRRwwyyGGbbrrTDo', 'oDwwGGrrBBYYbbggRRwwyyGGbbrrTDo',
    'otttttttttttttttttttttttttttttto', 'oDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDo',
    'oooooooooooooooooooooooooooooooo', '..ssssssssssssssssssssssssssss..',
  ].map(row => row.replaceAll('Y', 'y').padEnd(32, '.')),
  plant: [
    '.....lL.....', '..l..LL..l..', '..LLlLLlLL..', '...LLvLLL...', '....lLLl....', '.....ll.....',
    '..oooooooo..', '..oPPPPPpo..', '...pPPPpo...', '...pPPPpo...', '....pppo....', '....ssss....',
  ],
  plantTall: [
    '......ll........', '..ll..lLl...l...', '..lLl.lLL..lLl..', '...lLLlLL.lLLl..', '....lLLLLlLLl...',
    '.ll..lLLLll.....', '.lLLllLLL..ll...', '..lLLLLLL.lLLl..', '....llLLLlLLl...', '......lLLll.....',
    '......lll.......', '......lll.......', '...oooooooooo...', '...oPPPPPPPpo...', '....pPPPPPpo....',
    '....pPPPPPpo....', '.....pPPPpo.....', '.....pppppo.....', '......ssss......', '................',
  ],
  clock: [
    '...oooooo...', '..oDwwwwDo..', '.oDwwwwwwDo.', 'oDwwwoowwwDo', 'oDwwwoowwwDo', 'oDwwwoowwwDo',
    'oDwwworrrwDo', 'oDwwwwwwwwDo', '.oDwwwwwwDo.', '..oDwwwwDo..', '...oooooo...', '....ssss....',
  ],
  picture: [
    'oooooooooooooooo', 'otttttttttttttto', 'odwwwwwwwwwwwwdo', 'odwbbbbbbywwwpdo', 'odwbbbbbyyywwpdo',
    'odwbbbGGGGGwwpdo', 'odwbbGGllGGGwpdo', 'odwGGlllllGGGpdo', 'odwGGllGlllGGpdo', 'oddddddddddddddo',
    'oooooooooooooooo', '.ssssssssssssss.',
  ],
  window: [
    'oooooooooooooooooooooooo', 'oKKKKKKKKKKKKKKKKKKKKKKo', 'oKHhhhhhhhHKKHhhhhhhhHKo', 'oKHhhhhhhbHKKHhhhhhhbHKo',
    'oKHhhhhbbbHKKHhhhhhbbHKo', 'oKHhhhbbbbHKKHhhhhbbbHKo', 'oKHhhbbbbbHKKHhhhbbbbHKo', 'oKKKKKKKKKKKKKKKKKKKKKKo',
    'oKHhhhhhhhHKKHhhhhhhhHKo', 'oKHhhhhhhbHKKHhhhhhhbHKo', 'oKHhhhhhbbHKKHhhhhhbbHKo', 'oKHhhhhbbbHKKHhhhbbbbHKo',
    'oKKKKKKKKKKKKKKKKKKKKKKo', 'otttttttttttttttttttttto', 'oddddddddddddddddddddddo', '.ssssssssssssssssssssss.',
  ],
  sofa: [
    '..oooooooooooooooooooooooooooo..', '.orRRRRRRRRRRRRRRRRRRRRRRRRRRro.', 'orRRRRRRRRRRRRRRRRRRRRRRRRRRRRro',
    'orRRRRRRRRRRRRRRRRRRRRRRRRRRRRro', 'orRRRRRRRRRRRRRRRRRRRRRRRRRRRRro', 'orrrrrrrrrrrrrrrrrrrrrrrrrrrrrro',
    'orrRRRRRRRRRRRRRRRRRRRRRRRRRRrro', 'orrRRRRRRRRRRRRRRRRRRRRRRRRRRrro', 'orrRRRRRRRRRRRRRRRRRRRRRRRRRRrro',
    'orrrrrrrrrrrrrrrrrrrrrrrrrrrrrro', 'orrrrrrrrrrrrrrrrrrrrrrrrrrrrrro', 'oooooooooooooooooooooooooooooooo',
    '..oo........................oo..', '..oo........................oo..', '..ssssssssssssssssssssssssssss..', '................................',
  ],
  coffeeTable: [
    '.oooooooooooooooooooooo.', 'otttttttttttttttttttttto', 'otTTTTTTTTTTTTTTTTTTTTto', 'otTTTTTTTTTTwwTTTTTTTTto',
    'otTTTTTTTTTwkkwTTTTTTTto', 'otTTTTTTTTTTwwTTTTTTTTto', 'otTTTTTTTTTTTTTTTTTTTTto', 'otTTTTTTTTTTTTTTTTTTTTto',
    'oddddddddddddddddddddddo', '.oooooooooooooooooooooo.', '..oDo..............oDo..', '..ooo..............ooo..',
    '...ssssssssssssssssss...', '........................', '........................', '........................',
  ],
  coffeeMachine: [
    '..oooooooooo....', '..oKKKKKKKKo....', '..oKKKKKKKKo....', '..oKoHHHoKKo....', '..oKoooooKKo....',
    '..oKobboKKKo....', '..oKobboKKKo....', '..oKoooooKKo....', '..oKKwwKKKKo....', '..oooooooooo....',
    '.otttttttttto...', '.oddddddddddo...', '.oDDDDDDDDDDo...', '.oDDDDDDDDDDo...', '..oooooooooo....', '...ssssssss.....',
  ],
  bin: ['..oooooo..', '.oKKKKKKo.', 'oKkkkkkkKo', '.oKKKKKKo.', '.oKkKkKKo.', '.oKkKkKKo.', '.oKkKkKKo.', '..oKKKKo..', '..oooooo..', '...ssss...'],
  rug: Array.from({ length: 24 }, (_, y) => y === 0 || y === 23 ? 'uuuuuuuuuuuuuuuuuuuuuuuuuuuuuuuu' : y === 1 || y === 22 ? 'uUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUu' : 'uUuuuuuuuuuuuuuuuuuuuuuuuuuuuuUu'),
  door: [
    'oooooooooooooooo',
    'otttttttttttttto',
    'oDDDDDDDDDDDDDDo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oTo..........oTo',
    'oDo..........oDo',
    'ooo..........ooo',
  ],
};

export type FurnitureId = keyof typeof maps;
export const FURNITURE = Object.fromEntries(
  Object.entries(maps).map(([id, pixels]) => [id, { pixels, width: Math.max(...pixels.map(row => row.length)), height: pixels.length }]),
) as Record<FurnitureId, { pixels: string[]; width: number; height: number }>;
// 기존 호출부와의 호환은 장면 교체가 끝날 때까지 유지한다.
export const PLANT = maps.plant;
export const BOOKCASE = maps.bookcase;
