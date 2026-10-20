# 로드맵

v0은 뼈대다. 쓰면서 위에서부터 채운다.

## 다음
- [ ] **`work-report` 실동작 본 옮기기** — 가장 많이 쓰는 스킬이다(2026-10-20 기준 Claude 호출 419회, Codex가 스킬 파일을 읽은 횟수 1,231회). 회사 값(현황판 경로, 회의록 DB, 내 ID, 채널)은 `config.local.toml`로 빼고 스크립트를 설정 기반으로. 예약 작업·Codex가 `~/.claude/skills/work-report/SKILL.md` 경로로 읽으므로 그 경로는 유지한다
- [ ] 전역 `~/.claude/CLAUDE.md`에서 `rules/`로 옮긴 내용 빼기(중복 로드 방지)
- [ ] 다른 맥(원격 머신)에서 clone → `sync.py --apply`로 같은 환경 만들기

## 그다음
- [ ] Codex 규칙 배포 — `~/.codex/AGENTS.md`가 이미 `<!-- 이름:START -->`…`<!-- 이름:END -->` 표시로 구획돼 있으니, 그 형식으로 규칙 블록을 넣고 빼는 방식
- [ ] Codex `AGENTS.md`의 일반 규칙(실행 전 계획·보고, 설치·텔레메트리 검토)을 `rules/`로 옮길지 결정
- [ ] `frontend-mentoring-obsidian-notes`(claude.ai 동기화 스킬)의 원본을 레포에 둘지 결정
- [ ] 자주 쓰는 서브에이전트 정의(`agents/`)
- [ ] 스킬별 간단한 동작 확인 스크립트

## 넣지 않기로 한 것
- `collecting-loopers-rt`: 유료 강의 사이트의 로그인 쿠키로 내부 API를 읽는 방법이 들어 있어 공개하지 않는다. 로컬 스킬로 둔다.
- 다른 사람이 만든 플러그인·스킬: [external.md](external.md)에 목록만 둔다.
