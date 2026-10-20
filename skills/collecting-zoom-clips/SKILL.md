---
name: collecting-zoom-clips
description: Zoom Clips 공유 링크(us06web.zoom.us/clips/share/…)에서 전체 녹취록·챕터·AI 요약·메타데이터를 추출해 옵시디언 볼트 관례에 맞춰 저장한다. 루퍼스 발제·멘토링·오픈세션 영상이 이 형태로 공유된다.
---

# Zoom Clips 추출

루퍼스 세션 영상은 Zoom Clips 공유 링크 + passcode로 온다. **녹취록을 사람이 내려받을 필요 없다** — 내부 API가 전부 준다.

> ⚠️ 이전 판단 정정: 볼트 `_INBOX.md`에 오래 적혀 있던 *"Zoom 클립은 API로 못 긁는다"* 는 **틀렸다**. 2026-08-10에 R8 발제 클립으로 실증했다.

## 필요한 것

**공유 링크 + passcode** 두 개. 링크의 마지막 경로가 `shareId`다.

```
https://us06web.zoom.us/clips/share/AbCdEfGh1234IjKlMnOpQr
                                    └─────── shareId ───────┘
```

**웹 서브도메인은 무관하다.** `zoom.us/clips/share/…`든 `us06web.zoom.us/clips/share/…`든 API 호스트(`zoomclips.zoom.us`)는 같고 **`shareId`만 중요하다.** 실측 확인: 루퍼스 R1·R3·R4 링크가 `zoom.us/clips/`였는데 같은 API로 그대로 됐다.

**passcode가 없는 클립도 있다.** 인증 없이 `/transcript`를 먼저 찔러보고 `errorCode 1002`가 오면 그때 `validate-passcode`를 부른다. (루퍼스는 R1 클립 3건이 passcode 없이 열렸고, R2부터 걸렸다.)

**`/clips/`가 아니라 `/rec/share/`면 이 스킬 대상이 아니다.** 그건 Clips가 아니라 **회의 녹화**로 API 구조가 다르다. 링크 경로를 먼저 확인하라.

## API

base = `https://zoomclips.zoom.us/nws/marvel/2.0/clips/share/{shareId}`

| 엔드포인트 | 반환 |
|---|---|
| `POST /validate-passcode?pageType=web` | body `{"passwd":"…"}` · 세션 확립 |
| `GET /transcript?pageType=web` | `result.dataList[]` — `{itemId, startTime, endTime, text}` |
| `GET /play/vtt?pageType=web` | WEBVTT 전문 (같은 내용, 표준 포맷) |
| `GET /chapters?pageType=web` | `{startTime, title, summary}[]` — **AI 생성** |
| `GET /summary-features?pageType=web` | `result.summary.text` — **AI 생성** 요약 문단 |
| `GET /{shareId}?pageType=web` | `mediaInfo.{mediaTopic, ownerName, mediaDuration, createdTime, mediaId, playUrl}` · `statisticsInfo.count` |

## 함정 3개 — 전부 실제로 걸렸다

**① DOM을 긁지 마라.** Transcript 패널은 `transcript-virtual-list`(가상 스크롤)라 **화면에 보이는 만큼만 렌더**된다. R8은 전체 652개 중 **100개만** DOM에 있었다 — 552개를 조용히 놓친다. `data-testid="transcript-item-transcript_N"` 개수를 총 개수로 착각하기 쉽다. **API가 유일하게 온전하다.**

**② 인증은 HttpOnly 쿠키다.** 쿠키 없이 GET하면 `{"status":false,"errorCode":1002,"errorMessage":"No permission to operate"}`. 그 쿠키는 `document.cookie`에 **안 보인다**(HttpOnly).

**③ 순수 curl은 안 된다.** `POST /validate-passcode`를 curl로 재현하면 `errorCode 300 "Invalid params"`. CORS 허용 헤더에 `zoom-csrftoken`·`x-xsrf-token`이 있어 CSRF 토큰이나 선행 세션이 필요하다. 리버싱 이득이 없으니 **브라우저 컨텍스트에서 `fetch(credentials:'include')`** 로 간다.

**④ 부수효과 주의.** `/play/vtt`를 in-page `fetch`로 부르면 브라우저가 **다운로드로 처리**해 cwd(`.playwright-mcp/`)에 파일을 떨어뜨린다. 레포 안에서 작업하면 git이 오염된다 — 끝나고 정리하거나 cwd를 옮겨라.

## 절차 — 여러 clip을 한 번에 (권장)

**핵심: 클립마다 페이지를 열 필요가 없다.** `us06web.zoom.us` origin의 아무 clips 페이지에 한 번 들어가면, 그 페이지에서 **다른 shareId의 `validate-passcode`도 통한다.** 실측으로 14건을 두 번의 `browser_evaluate`로 처리했다.

1. **아무 clips 공유 링크 하나 열기** → `browser_navigate` (origin·CSRF 컨텍스트 확보용)
2. **`browser_evaluate` 한 번에 전부** — clip 목록을 루프로 돌며 `validate-passcode` → `/transcript`·`/chapters`·`/summary-features`·`/{shareId}`.
   반드시 **`filename` 파라미터로 파일 저장**하라 — 녹취록 수천 cue를 응답으로 받으면 컨텍스트가 터진다
3. **볼트로 변환** → `node scripts/batch-to-vault.js <clips-batch.json> [--dry]`
   `--dry`로 경로를 먼저 확인한 뒤 실행한다
4. **정합성 검증** — `meta.transcriptCueCount == txt 줄 수 == vtt cue 수`

> `/play/vtt`는 **부르지 않는다.** `/transcript` JSON에 같은 데이터가 있고(`startTime`·`endTime`·`text`), VTT는 `batch-to-vault.js`가 로컬에서 만든다. in-page fetch로 부르면 다운로드 부수효과가 생긴다(아래 함정 ④).

## 절차 — 단건

1. 링크 열기 → passcode 입력(`browser_type` placeholder `Passcode` → Confirm)
   진입 성공 신호: 페이지 title이 `{제목} - Zoom Clips`로 바뀐다
2. `browser_evaluate` — `scripts/extract-snippet.js`의 스니펫
3. VTT가 이미 있으면 `node scripts/vtt-to-txt.js <in.vtt> <meta.json> > out.txt`

## 저장 위치

`프론트_RoundN/{발제|멘토링&라이브 세션}/원본/` — `batch-to-vault.js`가 `kind`로 자동 분기한다(발제·QA → `발제/원본/`, 라이브세션 → `멘토링&라이브 세션/원본/`).

## 저장 규칙

```
프론트_RoundN/발제/원본/
├── RoundN_발제.vtt          ← 원본 (손대지 않는다)
├── RoundN_발제.txt          ← 평문 변환 (읽기·검색용)
└── RoundN_발제_meta.json    ← 챕터·AI요약·메타 (원본 보존)
```

멘토링·오픈세션은 `멘토링&라이브 세션/원본/`에 같은 형태로. 정리 노트 파일명은 기존 관례를 따른다 — `프론트_{멘토}_{종류}_{MMDD}_Obsidian.md`.

## AI 생성물 취급

`chapters`와 `summary`는 **Zoom AI가 만든 것이고 사람이 검수하지 않았다.**

- 노트에 옮길 때 **출처를 반드시 밝힌다** (내가 정리한 본문과 섞지 않는다)
- **chapters의 타임스탬프를 믿지 마라.** R8에서 녹취록과 대조하니 셋 다 어긋났다 — `00:00`에 *"영상 종료 시 감사 인사"*, `07:44`에 *"7라운드 검토 세션"*(실제로는 코드 건전성 신호), `54:06`에 *"스토리북 시각적 테스트"*(실제 Storybook은 **45:44**). 제목은 주제 순서로 대략 맞지만 **시각이 밀려 있어 타임라인으로 못 쓴다**
- **타임라인은 녹취록에서 직접 만든다.** `.txt`에서 주제 앵커를 grep해 시각을 확인하는 게 유일하게 신뢰할 수 있는 방법이다. chapters는 `meta.json`에 원본 보존만 하고 노트 본문에는 쓰지 않는다

## `createdTime`은 업로드 시각이다

세션이 열린 시각이 **아니다.** 루퍼스 발제는 **토요일**인데(R1~R4 라운드 종료일 06.20·06.27·07.04·07.11 전부 토요일) 클립은 다음날 올라올 수 있다. R8은 업로드가 `2026-08-09(일) 11:04 KST`이고 세션은 08-08(토)로 추정된다. 그래서 헤더에 **"업로드"를 명시**한다.

## 영상 파일(MP4)

`mediaInfo.playUrl`에 서명된 MP4 URL이 있다(JWT + CloudFront `Policy`/`Signature`). **만료가 있다** — R8은 `exp` 약 15일. 영상 자체를 보관해야 할 때만 쓰고, 링크를 문서에 박아두지 마라(곧 죽는다).
