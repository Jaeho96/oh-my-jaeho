---
name: session-handoff
description: 다른 에이전트 세션에 일을 맡기거나, 상태를 묻거나, 결과를 받아올 때 쓴다. 같은 맥의 다른 Claude Code·Codex 세션과 herdr에 등록된 원격 맥의 세션이 대상이다. 사용자가 "코덱스한테 시켜", "그 세션에 맡겨", "OO 맥북 세션으로 넣어", "다른 세션 뭐 하고 있어?", "결과 받아와"라고 하면 이 스킬을 쓴다.
---

# 세션 간 작업 요청

**herdr는 초인종, 공유 위키 `raw/`는 우편함이다.** 긴 요청은 요청서 파일로 쓰고, herdr로는 「요청서 읽고 진행해」 한 줄만 보낸다. 터미널에 긴 글을 밀어 넣으면 잘리고, 받는 쪽은 배경을 모르며, 나중에 무엇을 맡겼는지 남지 않는다.

## 지킬 것

- **다른 세션을 움직이기 전에 사용자에게 확인한다.** 대상과 요청을 한 줄로 보여 주고 승인받는다. 이전에 받은 승인은 다음 요청으로 이어지지 않는다.
- 비밀번호·토큰·개인정보는 요청서와 프롬프트에 넣지 않는다.
- 받는 쪽이 승인 창이나 질문에 멈춰 있으면(`blocked`) **대신 답하지 않는다.** 화면을 읽어 사용자에게 묻는다.
- 시간 초과나 `agent_prompt_stalled`는 전달 실패의 증거가 아니다. **다시 보내기 전에 먼저 읽는다.**

## 순서

### 1. 대상 찾기

```bash
herdr agent list                                  # 이 맥
herdr --machine "<저장된 머신 이름>" agent list     # 원격 맥 (herdr machine list 로 이름 확인)
```

- 결과의 `pane_id`(예: `w5:p1`)나 에이전트 이름이 대상이다. 원격 머신의 ID는 그 머신에서 조회한 값만 쓴다(이 맥의 ID와 겹칠 수 있다).
- `--machine`은 `--session`·`--remote`와 같이 쓰지 않는다.
- Claude Code끼리는 내장 `ListAgents`·`SendMessage`로도 주고받을 수 있다. Codex와 원격 맥은 herdr만 된다.
- 받는 쪽 `agent_status`가 `working`이면 끝나기를 기다리거나 다른 세션을 고른다.

### 2. 요청서 쓰기

공유 위키 `raw/`에 쓴다(위치·규칙은 전역 지침의 공유 위키 블록과 위키 안 `PROTOCOL.md`, 기본 위치 `~/Documents/Obsidian Vault/LLM Wiki`). 파일명: `YYYYMMDDTHHMMSS-<보내는 도구>-handoff-<주제>-<고유값>.md`. 시각은 짐작하지 말고 `date +%Y%m%dT%H%M%S`로 받는다 — 짐작한 시각이 받는 쪽 완료 기록보다 늦으면 끝난 일이 진행 중으로 정렬된다.

```markdown
---
title: "요청: <한 줄>"
task_id: "<고유 id>"
author: "<보내는 도구>"
machine: "<보내는 머신: jaeho-macbook | 276-macbook>"
to: "<대상 세션 / 머신>"
status: "started"
created_at: "<ISO 시각>"
---
## 목표
## 범위와 금지 (하지 말 것, 건드리지 말 것)
## 입력 자료 (파일 경로·링크)
## 완료 기준 (무엇을 확인하면 끝인가)
## 결과를 남길 곳 (raw/ 완료 기록, 산출물 경로)
```

### 3. 사용자 확인 → 보내기

```bash
herdr agent prompt <대상> "공유 위키 raw/<요청서 파일명> 을 읽고 진행해줘. 끝나면 같은 task_id로 raw/에 completed 기록을 남겨줘." --wait --timeout 600000
```

- `--wait`는 받는 쪽이 일을 시작했다가 `idle`·`done`·`blocked`가 될 때까지 기다린다. 긴 작업이면 `--wait` 없이 보내고 나중에 확인한다.
- 원격이면 앞에 `--machine "<이름>"`을 붙인다.

### 4. 결과 확인

```bash
herdr agent read <대상> --source recent-unwrapped --lines 120
herdr agent wait <대상> --timeout 600000      # 끝날 때까지 기다리기
```

그리고 위키 `raw/`에서 같은 task_id의 완료 기록을 찾는다. 터미널 출력보다 완료 기록을 근거로 보고한다.

## 자주 막히는 곳

| 증상 | 원인 | 할 일 |
|---|---|---|
| `agent_blocked` | 받는 쪽이 승인·질문 화면 | `agent read`로 화면을 보고 사용자에게 묻는다 |
| 받는 쪽이 "Login expired" | 그 세션 로그인 만료 | 사용자에게 알린다. 대신 로그인하지 않는다 |
| `agent_prompt_stalled` / `timeout` | 시작 신호를 못 봄 | 다시 보내지 말고 `agent read`부터 |
| `--wait` 없이 보낸 직후 `agent wait`가 바로 끝남 | 받는 쪽이 일을 시작하기 전의 `idle`을 잡음(대기는 차례를 추적하지 않는다) | 처음부터 `prompt --wait`로 보내거나, `agent read`로 「Working」을 확인한 뒤 `agent wait` |
| 원격에서 `prompt --wait`도 곧바로 `idle`로 돌아옴 | 원격 머신에서도 시작 전 `idle`을 잡는 경우가 있다(2026-10-20 두 번) | 결과로 믿지 말고 몇십 초 뒤 `agent read`로 진행·완료 문구를 확인 |
| `unknown machine '…'` | `--machine`에 목록 셋째 칸(슬러그)을 줌 | `herdr machine list`의 둘째 칸 이름(예: 「276 맥북」)이나 첫 칸 ID를 쓴다 |
| 새로 연 탭에 보낸 명령의 첫 글자가 사라짐(`cho: command not found`) | 새 셸의 oh-my-zsh 업데이트 질문이 첫 글자를 답으로 먹음 | `pane read`로 프롬프트가 뜬 것을 본 뒤 보낸다. 여러 줄 명령은 `quote>`에 걸리니 base64 한 줄로. 결과 줄을 읽기 전에 탭을 닫지 않는다 |
| 원격 Claude가 「신뢰되지 않은 코드」로 레포 스크립트 실행을 막음 | auto 권한 모드의 분류기 | 사용자에게 묻는다. 권한 모드를 바꾸는 것은 사용자 결정이다 |
| 원격 대상이 안 보임 | 머신 프로필 꺼짐·이름 틀림 | `herdr machine list`로 확인 |
