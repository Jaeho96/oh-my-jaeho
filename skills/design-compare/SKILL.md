---
name: design-compare
description: Use when comparing a Claude Design mockup (claude.ai/design) against a local web app render, or implementing/reflecting a dc.html design in code. Pulls the design via DesignSync, renders BOTH sides with Playwright, classifies every discrepancy into genuine-gap / data-gated / policy-hidden, and fixes ONLY genuine gaps. Project specifics (projectId, run command, fixtures, invariants, target files) are resolved from a pasted Claude Design export prompt or URL, from the repo (package.json, CLAUDE.md), or by asking — nothing is hardcoded to one project. Triggers on "시안 비교", "claude design 비교", "design compare", "dc.html 구현·반영", "/design-compare".
---

# Claude Design ↔ 로컬 비교 (범용)

UI 시안(Claude Design)을 실제 로컬 렌더와 대조해 **진짜 미구현 갭만** 정확히 골라 반영한다. 어떤 프로젝트에서도 쓸 수 있도록 방법론은 고정, 프로젝트 설정은 매번 해석한다.

## 왜 이 방법이 필요한가 (과거 실패 교정)

| 과거 실패 패턴 | 교정 |
|---|---|
| dc.html 코드만 읽고 눈으로 렌더 대조 안 함 → 시각 갭 누락 | 시안·로컬 **둘 다 실제 렌더(Playwright)** 후 대조 |
| 비어 보이는 걸 전부 "미구현"으로 오판 → 데이터·환경 이슈를 헛수정 | 모든 불일치를 **3분류(진짜 갭 / 데이터 없음 / 정책상 숨김)** 로 판정 |
| 시안 요소를 채우려 없는 데이터를 지어냄 | 데이터 없으면 파생·빈 상태. 표시 계층만 수정 |
| 한 화면만 보고 끝 | **모든 탭·상태 전수** 대조, 수정 후 **재대조** |

## 0. 프로젝트 컨텍스트 해석 (렌더 전에 반드시)

아래를 채운 뒤 사용자에게 **한 줄로 확인**받고 진행한다. 하드코딩 금지 — 매번 해석한다.

| 필요 항목 | 해석 순서 |
|---|---|
| **projectId** | ① 사용자가 붙인 **Claude Design export prompt / URL**에서 `claude.ai/design/p/<uuid>` 정규식 추출 → ② 없으면 사용자에게 URL/ID 요청. (⚠️ `DesignSync list_projects`는 "디자인 시스템" 타입만 나열 → 일반 디자인 프로젝트는 URL/ID 필수) |
| **대상 시안 파일** | export prompt에 언급된 dc.html 이름 → 없으면 `DesignSync list_files`로 목록 확인 후 사용자와 선택 (래퍼 dc.html → 하위 컴포넌트 dc.html) |
| **로컬 실행/포트** | repo `package.json` scripts의 dev 명령 추론(점유 포트 충돌 시 `PORT=<free>` 지정) |
| **테스트 픽스처** | 대상 화면에 **데이터가 채워진 상태**로 도달하는 경로(쿼리·라우트·계정). repo에서 못 찾으면 사용자에게 질문 |
| **불변 원칙(가드레일)** | repo **CLAUDE.md**/규칙 문서에서 도메인 규칙(용어 규칙, 표시 정책, SSOT 파일 등) 수집 → 불명확하면 질문 |
| **구현 대상 파일** | 해당 화면 컴포넌트. 시안 컴포넌트↔코드 컴포넌트 매핑 |

export prompt에서 못 얻는 값은 **대화로 질문**해 채운다(폴백).

## 파이프라인 (todo로 만들어 하나씩)

1. **시안 확보** — `DesignSync get_file`로 대상 dc.html(+ 하위 컴포넌트, `support.js`) 수신. 같은 URL 재요청이면 이전 구현과 diff.
2. **시안 렌더(참조)** — dc.html+support.js를 임시 폴더에 저장 → `python3 -m http.server <port>`로 서빙(⚠️ `file://` 불가 — dc-import가 HTTP fetch로 해석, React UMD는 unpkg CDN이라 인터넷 필요) → Playwright로 각 화면/탭 **참조 스크린샷**. 정밀 수치(색·라벨·enum)는 dc.html 소스도 직접 확인. 완료 후 서버 종료.
3. **로컬 렌더** — dev 서버 확인·로그인 → **시안과 동일 화면/탭/픽스처**로 접속 → Playwright 스크린샷.
4. **대조 & 갭 분류** — 아래 표로 모든 불일치 판정.
5. **수정** — **A(진짜 갭)만** 표시 계층에서 수정, 불변 원칙 준수.
6. **재대조·검증·정리** — Playwright 재확인 → 타입체크(baseline 유지) + 테스트 → 임시 산출물·시안 서버 정리, 부수 변경 원복.

## 갭 분류 (모든 불일치를 하나로 판정)

| 분류 | 정의 | 판별 | 조치 |
|---|---|---|---|
| **A. 진짜 미구현 갭** | 시안엔 있고 로컬엔 없음/다르게 구현 | 데이터·정책과 무관하게 마크업/레이아웃 자체가 부재·상이 | **수정**(표시 계층) |
| **B. 데이터 없음(게이트)** | 구현됐으나 로컬에 데이터 소스 없어 비어 보임 | 프로덕션/데이터 연결 시 채워짐(백엔드 미연동, 외부 API 미응답, 이력 뷰 미복원 등) | **버그 아님** — 환경 이슈로 기록. 빈 상태 UX만 개선 가능 |
| **C. 정책상 숨김** | 의도적 숨김/대체 | 표시 스위치 조건부 렌더, 도메인 용어/표시 규칙, 상단 바=앱 GNB 대체 등 | **그대로 둠** |

> 흔한 함정: "안 맞는 부분"의 다수가 **B**일 수 있다(로컬에서 백엔드·외부데이터 미연동). A만 정확히 골라내는 게 이 스킬의 목적.

## 불변 원칙 (수정 가드레일 — 프로젝트별로 해석)
- **표시 계층만 수정.** 데이터 배선·계산·모델 로직 불변 (사용자가 명시 허용하지 않는 한)
- **없는 데이터는 지어내지 않는다** — 결정적 파생 또는 빈 상태로
- **프로젝트 CLAUDE.md의 도메인 규칙 준수** (용어 규칙, 표시 정책 등)
- **SSOT 존중** — 색·토큰·상수는 프로젝트가 정한 단일 정의만 사용
- 숨김은 조건부 렌더로 (프로젝트 관례 따름; 예: `display:none` 지양)

## 갭 리포트 포맷
```
[화면/탭 이름]
- A(갭)  : <시안엔 있는데 없는 요소> → <조치>
- B(데이터): <비어 있는 요소> (<데이터 소스 미연동 이유>, 프로덕션 채워짐)
- C(정책): <숨겨진/대체된 요소> = <이유> (정상)
```

## 알려진 함정
- **dc.html은 http로 서빙** — DC 런타임(`support.js`) + React UMD(unpkg, 인터넷 필요), `dc-import`가 `./Name.dc.html`을 HTTP fetch. `file://` 실패
- **`DesignSync list_projects`는 디자인 시스템 타입만** — 일반 디자인 프로젝트 id는 URL/export/사용자에게서 확보
- **백엔드·외부데이터 로컬 미연동** → 비면 대개 B(데이터 없음). 프로덕션/스테이징에서 재확인
- **DesignSync 도구가 목록에 없으면** `ToolSearch(query:"select:DesignSync")`로 먼저 로드
- **점유 포트 충돌** → `PORT=<free> <dev cmd>`로 회피

## 부록: projectId 추출
Claude Design URL/export prompt에서:
```
claude.ai/design/p/<uuid>   →   uuid = projectId
정규식: /claude\.ai\/design\/p\/([0-9a-fA-F-]{36})/
```

## 부록: 프로젝트별 값
프로젝트마다 다른 값(projectId, 시안 파일, 실행 명령, 픽스처, 테스트 계정, 지켜야 할 용어)은 그 레포의 `docs/frontend/design-compare-spec.md`에 두고 거기서 읽는다. 이 스킬에는 적지 않는다.
