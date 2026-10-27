# oh-my-jaeho

Claude Code와 Codex에서 쓰는 내 스킬·규칙을 한 레포에서 관리하고, 각 도구의 설정 폴더로 연결해 쓰는 개인 라이브러리.

> 아직 v0(러프한 초안)이다. 쓰면서 채워 간다. 할 일은 [docs/roadmap.md](docs/roadmap.md).

## 원칙

1. **고치는 곳은 이 레포 하나.** `~/.claude/skills/…`에서 직접 고치지 않는다. 배포는 심볼릭 링크라 레포를 고치면 바로 반영된다.
2. **배포한 것만 지운다.** 동기화 도구는 자기가 만든 링크를 `~/.omj/state.json`에 적어 두고, 설정에서 빠진 것만 정리한다. 원래 있던 파일은 건드리지 않는다.
3. **공개 레포에는 공개해도 되는 것만.** 회사 이름·사람 이름·Slack/Notion ID·고객 데이터·토큰·절대 경로는 넣지 않는다. 그런 값은 `*.local.*` 파일(커밋 안 됨)에 둔다. 커밋 전에 `tools/check_public.py`가 막는다.

## 구조

```
config.toml                 무엇을 어디에 배포할지 (공용)
config.local.toml           이 기기만의 추가·제외 (커밋 안 함, 예시: config.local.example.toml)
skills/<이름>/SKILL.md      스킬 (Claude: ~/.claude/skills, Codex: ~/.agents/skills)
rules/<이름>.md             항상 따르는 규칙 (Claude: ~/.claude/rules)
statusline/                 상태줄 등 낱개 파일 (config.toml 의 [[files]])
hooks/                      훅 스크립트 (config.toml 의 [[files]] 로 ~/.claude/hooks 에 연결, Codex hooks.json 도 같은 자리를 부름)
tools/sync.py               배포 도구 (Python 3.11+, 추가 설치 없음)
tools/check_public.py       공개 전 검사 (개인·회사 정보, 토큰, 절대 경로)
docs/                       설계 메모·로드맵
```

## 지금 들어 있는 것

| 종류 | 이름 | 내용 |
|---|---|---|
| 스킬 | `session-handoff` | 다른 에이전트 세션(같은 맥의 Claude·Codex, 원격 맥)에 일을 맡기고 결과를 받는다. herdr는 초인종, 공유 위키 `raw/`는 우편함 |
| 스킬 | `youtube-to-obsidian` | 유튜브 자막 → 옵시디언 노트(원문 → 정리본 → 요약) |
| 스킬 | `collecting-zoom-clips` | Zoom Clips 공유 링크에서 녹취록·챕터·요약을 뽑아 볼트에 저장 |
| 스킬 | `grill` | 실행 전에 목표·요구사항·범위를 질문 라운드(번호 + 추천 답)로 다듬고, 합의 요약을 확인받은 뒤 시작한다. 큰 작업이면 먼저 한 줄로 제안만 한다 (Matt Pocock grilling 기반) |
| 스킬 | `design-compare` | Claude Design 시안과 로컬 렌더를 대조해 미구현 차이만 골라 반영 |
| 스킬 | `work-report` | 업무 현황판 기반 일보·주보와 놓친 일 점검 — **v0 뼈대**(실동작 본은 아직 로컬 비공개, 배포 목록에 없음) |
| 규칙 | `vocabulary` · `verification` · `troubleshooting-log` · `writing` | 금지 단어, 작업 원칙과 완료 기준, 문제 해결 기록, 두괄식 쓰기 |
| 규칙 | `korean-style` · `korean-style-toss` | 사람이 쓴 것처럼 읽히는 한국어 문체(빈 동사, 번역 투, 빈말, 확인한 만큼만 쓰기 등)와 토스 테크니컬 라이팅 가이드 예문. Codex 에는 훅으로 넣는다 |
| 파일 | `statusline/statusline.py` | Claude Code 상태줄 (`~/.claude/statusline.py`로 연결) |
| 파일 | `hooks/korean_style_context.py` | Codex 세션과 하위 에이전트가 시작할 때 한국어 문체 지침을 넣는 훅 (`tools/korean_style_hooks.py` 로 등록) |

레포 밖에서 따로 설치해 쓰는 플러그인·스킬은 [docs/external.md](docs/external.md).

Claude·Codex 공유 위키 연결은 이 레포가 아니라 전역 지침(`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`)의 `SHARED-LLM-WIKI` 블록이 맡는다. 위키의 설치·되돌리기 절차가 그 블록 기준이라 그대로 둔다.

## 쓰는 법

```bash
python3 tools/sync.py            # 미리보기 (아무것도 바꾸지 않음)
python3 tools/sync.py --apply    # 링크 만들기·정리
git config core.hooksPath .githooks   # 커밋 전 공개 검사 켜기 (처음 한 번)
```

- 같은 이름의 폴더가 이미 있으면(예: 예전에 직접 넣은 스킬) 건너뛰고 「충돌」로 알려 준다. 옮겨도 되면 `--backup-existing`을 붙이면 원래 것을 `~/.omj/backups/<시각>/`으로 옮기고 링크를 건다(배포 자리 안에 백업을 두면 같은 이름 스킬이 둘로 잡혀서 밖에 둔다).
- 기기마다 다른 것은 `config.local.toml`에 적는다. 예: 회사 맥에서만 `work-report`를 켠다.

### 한국어 문체 지침을 Codex 에도 넣기

Claude Code 는 `sync.py --apply` 로 연결한 `~/.claude/rules/korean-style*.md` 를 읽는다(일반 하위 에이전트도 받는다). Codex 는 그 폴더를 모르니 훅으로 넣는다.

```bash
python3 tools/korean_style_hooks.py            # 미리보기
python3 tools/korean_style_hooks.py --apply    # Codex hooks.json 에 SessionStart · SubagentStart 훅 등록
```

- 등록한 뒤 Codex 를 열어 `/hooks` 에서 새 훅을 신뢰(Trust)해야 돈다. 신뢰하지 않은 훅은 `codex exec` 에서도 건너뛴다.
- 지침 본문만 고치면 훅 정의는 그대로라 다시 신뢰하지 않아도 된다.
- 빼려면 `--remove --apply`.

## 공유 위키를 여러 맥에서 쓰기

Claude Code·Codex가 함께 쓰는 마크다운 위키(작업 기록 `raw/`, 지식 `omx_wiki/`) 폴더를 비공개 git 저장소로 두고 여러 맥에서 맞춘다.

```bash
python3 tools/sync.py --apply                                        # 훅 파일 링크 (~/.claude/hooks/)
python3 tools/wiki_setup.py --repo <비공개 위키 저장소> --blocks --apply   # clone(또는 확인) + 전역 지침 블록
python3 tools/wiki_hooks.py --apply                                  # Claude settings.json · Codex hooks.json 에 훅 등록
```

- `hooks/wiki_log_guard.py` — Stop 훅. 파일을 고쳤거나 도구를 여러 번 썼는데 위키 기록이 없으면 끝내지 말고 기록하라고 한 번 되돌려 보낸다. 이 세션이 쓴 기록의 파일명 시각이 저장 시각보다 늦어도(시각을 짐작한 것) 한 번 되돌려 보낸다. 예약 작업 세션·재진입·오류는 통과.
- `tools/wiki_sync.py --detach` — 세션 시작에 받고 작업 끝에 커밋·올린다. 충돌이면 멈추고 위키 폴더 `.sync-error` 에 남긴다.
- launchd·cron 은 쓰지 않는다. macOS 개인정보 보호가 백그라운드 작업의 `~/Documents` 접근을 막는다. 훅은 터미널 권한을 물려받는다.
- Codex 는 새 훅을 처음 볼 때 신뢰(Trust) 승인을 한 번 묻는다.

## 참고

[toongri/oh-my-toong-playground](https://github.com/toongri/oh-my-toong-playground)의 생각(중앙 라이브러리, 선언적 동기화, 배포한 것만 정리, 기기별 로컬 오버라이드)을 빌렸다. 코드는 가져오지 않았다.

## 라이선스

MIT. 다만 `rules/korean-style-toss.md` 는 토스 테크니컬 라이팅 가이드를 옮긴 것이라 CC BY-NC-SA 4.0 이다. 고쳐 쓴 다른 사람의 자료와 그 라이선스는 [docs/third-party-licenses.md](docs/third-party-licenses.md)에 있다.
