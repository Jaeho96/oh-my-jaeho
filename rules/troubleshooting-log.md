# 문제 해결 기록

- **시작 전:** `~/.claude/troubleshooting/INDEX.md`에서 비슷한 사례를 먼저 찾는다.
- **끝난 뒤:** 사소한 것도 기록한다. 쌓이면 패턴이 보인다.
  - 위치: `~/.claude/troubleshooting/YYYY-MM-DD-<키워드>.md`
  - 내용: 증상, 원인, 고친 것(전/후), 교훈, 재발 방지
  - 기록 후 `INDEX.md`에 한 줄 추가. 비슷한 기록이 있으면 새 파일 대신 그 기록에 이어 쓴다.

```yaml
---
date: YYYY-MM-DD
category: [ocr|환경|의존성|타입|빌드|배포|DB|인증|네트워크|기타]
severity: [minor|moderate|critical]
project: <프로젝트명>
tags: [관련 키워드]
---
```

- 기록에 토큰·비밀번호·고객 데이터를 넣지 않는다.
