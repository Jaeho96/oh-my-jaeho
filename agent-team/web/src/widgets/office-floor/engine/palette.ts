export interface OfficeTheme {
  floorA: string;
  floorB: string;
  wall: string;
  wallTrim: string;
  desk: string;
  deskEdge: string;
  chair: string;
  rugClaude: string;
  rugCodex: string;
  rugOther: string;
  text: string;
  plate: string;
  select: string;
}
export const LIGHT: OfficeTheme = {
  floorA: '#c8b89b',
  floorB: '#c2b295',
  wall: '#2e3b4b',
  wallTrim: '#56697c',
  desk: '#b88b57',
  deskEdge: '#805b3c',
  chair: '#52647a',
  rugClaude: '#b8a28c',
  rugCodex: '#9eafa2',
  rugOther: '#a9acb7',
  text: '#202c3b',
  plate: '#f7fafc',
  select: '#4d60cf',
};
export const DARK: OfficeTheme = {
  floorA: '#665d53',
  floorB: '#62594f',
  wall: '#262D39',
  wallTrim: '#344154',
  desk: '#9a744d',
  deskEdge: '#654831',
  chair: '#58677b',
  rugClaude: '#675a52',
  rugCodex: '#4e625b',
  rugOther: '#555e70',
  text: '#edf3f8',
  plate: '#263447',
  select: '#b1bdff',
};
const HAIR = [
  ['#382b30', '#5f4240', '#87624e'],
  ['#6a412d', '#a36839', '#d9a060'],
  ['#202e3d', '#3e5061', '#6b7b8d'],
  ['#453344', '#725368', '#aa849d'],
  ['#3b3429', '#756644', '#aa956b'],
  ['#343439', '#646572', '#9b9dab'],
];
const SKIN = [
  ['#b87554', '#d99970', '#f0bc8e'],
  ['#815346', '#ae735b', '#d39778'],
  ['#bd896b', '#dfad8b', '#f5d4ad'],
  ['#704d42', '#9b6a52', '#bc8b6e'],
  ['#aa7564', '#d99b87', '#efbdab'],
  ['#a67a56', '#d3a779', '#eed0a2'],
];
export function spritePalette(appearance: number, role: string | null): Record<string, string> {
  const hair = HAIR[appearance] ?? HAIR[0];
  const skin = SKIN[appearance] ?? SKIN[0];
  // 외형마다 옷과 바지를 달리해 뒷모습에서도 구분한다.
  const outfits = [
    ['#b5bac8', '#7986a4', '#56617b', '#344357', '#53647b'],
    ['#c99a6d', '#a37252', '#77503d', '#3e494a', '#667371'],
    ['#98ad9c', '#658675', '#476454', '#374555', '#596a7b'],
    ['#c293a4', '#9b677e', '#70465d', '#453f52', '#70647e'],
    ['#d2bc7e', '#aa8e58', '#79643e', '#474e47', '#727d67'],
    ['#a9b9c4', '#7b94a8', '#516c85', '#4b4145', '#75626b'],
  ];
  const outfit = outfits[appearance] ?? outfits[0];
  return { o: '#293343', h: hair[0], H: hair[1], L: hair[2], s: skin[1], S: skin[2],
    C: outfit[0], c: outfit[1], d: outfit[2], p: outfit[3], P: outfit[4],
    b: '#202b38', w: '#f1ebd9', g: role === 'reviewer' ? '#729080' : '#8195a4' };
}
