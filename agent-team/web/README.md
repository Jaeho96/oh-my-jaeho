# web — 에이전트 팀 보드 화면

React 19 · Vite · TypeScript. 보드 서버(`../board.py`)가 빌드 결과(`dist/`)를 그대로 내보낸다.

```bash
npm ci
npm run dev      # 개발 서버. /api·/events 는 BOARD_URL(기본 http://127.0.0.1:8765)로 넘긴다 — 주소창에 ?t=<토큰>
npm run check    # 타입 → 린트 → 시험
npm run build    # dist/ — board.py 가 읽는다
```

## 구조 — FSD 6계층

```
src/
  app/        진입·연결 설정(주소창 ?t= 토큰)·전역 스타일
  pages/      board — 탭(사무실·실행·기록)과 연결 상태 안내
  widgets/    office-floor(캔버스 사무실) · agent-detail(상세) · activity-lists(실행·위키 기록)
  features/   select-agent — 고른 에이전트 id 하나와 키보드로 고르는 목록
  entities/   board — 서버 데이터 타입·가드·스토어·상태→그림 규칙·상태 배지
  shared/     api(SSE 연결·재연결) · lib(backoff·표기)
```

- 위 계층만 아래 계층을 가져온다. 같은 계층의 다른 조각은 가져오지 않는다. 다른 조각은 그 조각의 `index.ts` 로만 가져온다. `index.ts` 에 `export *` 를 쓰지 않는다. `tests/fsd-boundaries.test.ts` 가 지킨다.
- 캔버스 엔진(`widgets/office-floor/engine/`)은 React 를 모른다. 배치(`layout`)·도트(`sprites`)·장면(`renderer`)·루프(`loop`)로 나눴고 배치는 단위 시험이 본다.

## 지키는 것

- 원본은 SSE 하나다. 스토어는 React 밖에 두고(zustand vanilla) 컴포넌트는 좁은 selector 로 구독한다. 캔버스 루프는 `subscribeBoard` 로 직접 읽어 스냅샷이 1초마다 와도 컴포넌트가 다시 그려지지 않는다.
- 계산되는 값은 상태로 두지 않는다. 고른 에이전트는 id 만 두고 객체는 렌더 중에 찾는다. 상태별 인원·정렬도 그때 계산한다.
- 서버 응답은 `unknown` 으로 받아 가드로 좁힌다(`as` 로 덮지 않는다). 모르는 상태 이름은 idle 로 그리되 화면에 알린다.
- 상태 → 말·자세·말풍선은 `switch` 와 `never` 로 닫는다. 서버에 상태가 늘면 타입 오류가 난다.
- 연결 상태는 겹치지 않게 가른다: 처음 연결 중(이때만 `aria-busy`) · 토큰 문제 · 실패 · 재연결 중(마지막 화면 유지) · 연결됨.
- 토큰이 없으면 기본값으로 조용히 가지 않고 「토큰이 필요합니다」를 보인다.
- 캔버스는 키보드로 고를 수 없으므로 오른쪽 목록(`AgentRoster`)이 키보드 길이다.

## 시험

- `*.test.ts` 는 node, `*.dom.test.tsx` 만 jsdom 에서 돈다(셋업 범위로 나눈다).
- 이름은 「~한다」체. 쿼리는 role·label 로 고른다.
- 연결 시험은 실제 경로(connectBoard → openEventStream → 파싱)를 타고 네트워크만 가짜로 바꾼다.
- 핵심 수정은 일부러 되돌려 시험이 깨지는지 본다(2026-10-24 6곳 확인).

## 나누지 않은 것

- 목록 행(`AgentRoster`)과 상세 패널(`AgentDetail`)은 둘 다 에이전트를 보여 주지만 바뀌는 이유가 달라 공통 컴포넌트로 묶지 않았다.
- 실행 기록·위키 기록은 한 위젯(`activity-lists`)에 둔다. 함께 보이고 함께 바뀐다.

## 그림

사람·책상·말풍선은 그림 파일 없이 코드로 그린다(`engine/sprites.ts`). 설계는 [pixel-agents](https://github.com/pixel-agents-hq/pixel-agents)(MIT)의 이벤트·상태 모델을 참고했고 코드와 에셋은 가져오지 않았다.
