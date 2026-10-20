# 문제 해결 기록

- **시작 전:** `~/.claude/troubleshooting/INDEX.md`를 참조해 유사 사례를 먼저 확인한다.
- **트러블슈팅/디버깅 완료 후 무조건 기록한다.**
  - 모든 버그 수정, 에러 해결, 트러블슈팅 결과를 기록한다.
  - 사소한 것도 쌓이면 패턴이 보인다.

- 기록 위치: `~/.claude/troubleshooting/`
- 기록 형식: `YYYY-MM-DD-[키워드].md` (예: `2026-03-24-docker-port-conflict.md`)
- 기록 내용: 증상, 원인, 코드 수정(Before/After), 교훈, 재발방지
- 기록 후: `INDEX.md` 업데이트. 유사 패턴이 기존 로그에 있으면 그 로그에 통합한다.
- 기록에 토큰·비밀번호·고객 데이터를 넣지 않는다.

파일 frontmatter 형식:

```yaml
---
date: YYYY-MM-DD
category: [ocr|환경|의존성|타입|빌드|배포|DB|인증|네트워크|기타]
severity: [minor|moderate|critical]
project: [프로젝트명]
tags: [관련 키워드]
---
```
