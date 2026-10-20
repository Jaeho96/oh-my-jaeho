# 이 레포에서 일하는 에이전트를 위한 규칙

이 레포는 내 Claude Code·Codex 스킬과 규칙의 원본이다. `CLAUDE.md`는 이 파일을 가리키는 링크다.

## 반드시

- **공개 레포다.** 회사 이름, 동료 이름, Slack·Notion·Linear ID, 고객 데이터, 토큰, `/Users/<이름>/` 같은 절대 경로를 쓰지 않는다. 기기·회사마다 다른 값은 `*.local.*` 파일(커밋 안 됨)이나 환경변수로 뺀다.
- 커밋 전에 `python3 tools/check_public.py`를 돌려 통과시킨다. `.githooks/pre-commit`이 같은 검사를 한다.
- 커밋·푸시는 사용자가 요청할 때만 한다.
- 스킬을 고칠 때는 이 레포에서 고친다. 배포된 쪽(`~/.claude/skills/…`)은 링크라 따로 고칠 필요가 없다.

## 새 스킬 넣기

1. `skills/<이름>/SKILL.md` — frontmatter `name`·`description`. description에는 언제 쓰는지(사용자가 하는 말)를 적는다.
2. 경로·ID는 하드코딩하지 말고 환경변수나 `skills/<이름>/config.local.toml`에서 읽는다. 공개용 예시는 `config.example.toml`.
3. `config.toml`의 `[skills] items`에 넣는다(모든 기기). 특정 기기만이면 `config.local.toml`의 `add`에 넣는다.
4. `python3 tools/sync.py`로 미리보기 → `--apply`.

## 배포 위치

| 종류 | Claude | Codex |
|---|---|---|
| 스킬 | `~/.claude/skills/<이름>` | `~/.agents/skills/<이름>` |
| 규칙 | `~/.claude/rules/<이름>.md` | 아직 없음(로드맵) |
