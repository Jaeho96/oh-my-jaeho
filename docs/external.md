# 이 레포 밖에서 설치해 쓰는 것

내가 만든 것이 아니라서 레포에 넣지 않는다. 새 기기에서는 따로 설치한다. (2026-10-20, 실제 사용 기록 기준)

## Claude Code 플러그인
| 플러그인 | 쓰임 |
|---|---|
| superpowers | brainstorming · writing-plans · subagent-driven-development · systematic-debugging 등 (자주 씀) |
| codex (openai-codex) | Claude 안에서 Codex 호출 (`/codex:rescue` 등) |
| context7 · playwright · notion · figma · ralph-loop | 문서 조회, 브라우저 조작, 노션, 피그마, 반복 실행 |

## 다른 사람이 만든 스킬
| 스킬 | 위치 | 비고 |
|---|---|---|
| find-skills | `~/.agents/skills` (Claude 쪽은 링크) | 스킬 찾기·설치 |
| orchestration | `~/.agents/skills` | Orca 다중 에이전트 조율 |
| reverse-engineer-anything | `~/.agents/skills` | REA |
| Cloudflare 스킬 묶음 (agents-sdk, wrangler, durable-objects 등) | `~/.claude/skills`, `~/.codex/skills` | Cloudflare 공식 |

Claude 에서 꺼 둔 스킬(`~/.claude/settings.json` 의 `skillOverrides: off`): Cloudflare 묶음, find-skills, collecting-loopers-rt, design-compare. 꺼 둔 스킬은 Codex 에도 배포하지 않는다(Codex 는 이 설정을 모른다).

## 도구
- herdr — 터미널 작업 공간, 세션 간 요청(`session-handoff` 스킬)
- Orca — `~/.claude/settings.json` 의 훅을 넣은 도구

## 레포 밖에 두는 내 것
- `collecting-loopers-rt` — 공개 부적합(유료 강의 사이트 내부 API)
- `work-report` 실동작 본과 예약 작업(`~/.claude/scheduled-tasks`) — 회사 값이 많다. 일반화 중
- `frontend-mentoring-obsidian-notes` — claude.ai 계정에서 동기화되는 스킬
