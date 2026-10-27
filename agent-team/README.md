# agent-team — Codex 세션을 에이전트 팀으로

Claude Code 세션이 총괄하고, Codex 매니저 스레드 하나가 Codex 내장 하위 에이전트(`multi_agent`, 0.163 기준 stable)로 팀을 꾸린다. 총괄은 매니저와만 말한다. 공유 작업 기록은 새로 만들지 않고 LLM Wiki `raw/`를 쓴다.

```
Claude Code(총괄) ──요청·검수·기록──▶ Codex 매니저 ──spawn_agent/wait_agent──▶ explorer · worker · reviewer
                                            │
   보드(board.py + web/) ◀── Codex rollout · Claude Code transcript · runs/*.meta.json · herdr · wiki raw  (SSE + 토큰)
```

## 들어 있는 것

| 파일 | 무엇 |
|---|---|
| `agents/*.toml` | Codex 하위 에이전트 역할 3개. `~/.codex/agents/` 에 등록한다 |
| `run_team.py` | 과제 하나를 `codex exec --json` 으로 팀(team) 또는 단일(single) 모드로 돌리고 `runs/` 에 기록 |
| `board.py` | 로컬 웹 보드. 팀 실행(매니저·하위 에이전트 트리·토큰·보고) · 그 밖의 Codex 스레드 · 위키 작업 기록 · herdr 세션 |
| `office.py` | 사무실 데이터 — Codex 세션 기록·Claude Code 대화 기록을 같은 이벤트로 읽어 캐릭터 상태(작업·읽기·생각·팀 대기·입력 대기·승인 대기·멈춤 의심·끝)를 만든다 |
| `web/` | 화면 — React·Vite·TypeScript, 픽셀 사무실(캔버스)과 실행·기록 탭. 구조와 규칙은 `web/README.md` |
| `test_agent_team.py` · `test_office.py` | 회귀 시험 (`python3 -m unittest agent-team/test_agent_team.py agent-team/test_office.py`) |

## 쓰는 법

```bash
# 역할 등록 (한 번). ~/.codex/agents 가 없으면 폴더째 링크하고, 이미 있으면 파일마다 링크한다(이름이 같으면 건너뛴다)
[ -e ~/.codex/agents ] || ln -s "$(pwd)/agent-team/agents" ~/.codex/agents
[ -L ~/.codex/agents ] || for f in agent-team/agents/*.toml; do [ -e ~/.codex/agents/$(basename $f) ] || ln -s "$(pwd)/$f" ~/.codex/agents/; done

# 화면 빌드 (한 번, 화면을 고친 뒤에도)
(cd agent-team/web && npm ci && npm run build)

# 보드 — 찍힌 주소(http://127.0.0.1:8765/?t=<토큰>)로 연다. 토큰은 ~/.omj/agent-team/board.token(0600)
# --machines 는 'herdr 머신 이름=화면 이름' 을 쉼표로. --local-label 은 이 맥의 화면 이름
python3 agent-team/board.py --local-label "<이 맥 화면 이름>" --machines "<herdr 원격 머신 이름>=<화면 이름>"

# 과제 실행 — 읽기 전용, 팀. 같은 과제를 --mode single 로도 돌려 비교 기준선으로 쓴다
python3 agent-team/run_team.py --name review-x --cwd <폴더> --mode team --task "…" --background --timeout 1800
```

- 기본은 읽기 전용 샌드박스다. `--write` 를 주면 cwd 안에, `--add-dir` 로 준 폴더에도 쓸 수 있다. 승인은 묻지 않는 설정이라 승인이 필요한 행동은 실패해 매니저에게 돌아온다.
- 하위 에이전트는 부모 턴의 샌드박스·승인을 상속한다. 역할 파일로 바꿀 수 없다(공식 문서).
- `--background` 는 감시 프로세스를 띄우고 바로 돌아온다. 감시 프로세스가 끝까지 기다려 종료 코드를 `.meta.json` 에 남기고, 보드는 그 종료 코드로 성공·실패를 판정한다.
- 실행 기록 폴더(기본 `~/.omj/agent-team/runs`, `AGENT_BOARD_RUNS`)는 0700, 파일은 0600 이다. 과제 본문이 들어간다.
- 한도는 `~/.codex/config.toml` 의 `[agents]`(max_threads 등)를 따른다. 하위 에이전트마다 토큰을 따로 쓴다.

## 보드가 읽는 것과 한계

- 팀 트리는 Codex 세션 기록(`~/.codex/sessions/**/rollout-*.jsonl`)에서 만든다. `codex exec --json` 이벤트에는 하위 에이전트를 띄운 사실이 나오지 않는다(0.163 확인: spawn_agent 3번이 이벤트에는 `wait` 한 번만 보였다).
- `exec` 이벤트는 0.163 에서 확인한 이름만 안다: `thread.started` · `turn.started` · `turn.completed` · `turn.failed` · `item.started` · `item.updated` · `item.completed` · `error`. 이 밖의 이름은(앞부분이 같아도) 보드에 「모르는 이벤트」로 띄운다.
- 「그 밖의 Codex 스레드」는 `codex app-server`(stdio)를 따로 띄워 `thread/list` 로 읽는다. `sourceKinds` 를 비우면 대화형만 오므로 10가지를 모두 적는다. 보드는 파일을 쓰지 않지만, 띄운 app-server 는 Codex 상태 DB 를 스스로 갱신할 수 있다.
- 돌고 있는 app-server 데몬에 직접 붙는 길(`codex app-server proxy`·control socket)은 핸드셰이크가 달라 아직 안 된다.
- 사무실은 최근 `--office-min`(기본 60)분 안에 움직인 세션만 앉힌다. 며칠 전에 시작해 지금도 쓰는 세션도 1분마다 전체 기록 폴더를 훑어 찾는다. 깨진 기록 파일 하나는 건너뛰고 나머지를 그린다. 일하는 중인데 `--stall-sec`(기본 600)초 소식이 없으면 「멈춤 의심」, herdr 가 승인·질문 화면이라고 알리면 「승인 기다림」이다.
- 대화 내용은 화면에 싣지 않는다. 도구 이름·파일 이름·명령 첫 단어·Bash 설명만 쓴다. 예외는 둘이다: 세션 이름으로 쓰는 사용자 지시 첫 줄(60자까지)과 Codex 하위 에이전트의 보고문. 명령 앞에 붙은 `VAR=값` 은 값째 버린다.
- herdr 가 실패하면 세션 목록은 마지막 성공값을 그대로 두고 오류만 적는다(원격 기기도 기기마다 같다).
- 데이터 길(`/api/state`·SSE `/events`)은 토큰이 있어야 열린다. 보드는 127.0.0.1 에만 묶고, 다른 주소는 `--allow-remote` 를 함께 줘야 한다.

## 원칙 (OpenAI DevDay Seoul 2026 「What Comes After Loops?」에서)

- 시작은 에이전트 하나. 추가는 단일 기준선과 비교해 이득이 분명할 때만.
- 독립 업무 분할, 난이도별 모델(탐색 luna · 핵심 sol), 명확한 소유권, 중복 편집 금지, 최소 승인.
- 하나의 공유 작업 기록을 모두가 읽고 쓴다. 여기서는 LLM Wiki `raw/` 가 그것이다.

## 첫 비교 (2026-10-23, 이 폴더 코드 리뷰, 읽기 전용, gpt-6.1-sol high)

| | 팀 (매니저 + explorer·worker·reviewer) | 단일 |
|---|---|---|
| 걸린 시간 | 8분 3초 | 11분 4초 |
| 토큰 합계 | 약 3.19M (출력 23.1k) | 약 1.67M (출력 18.5k) |
| 지적 | 14건 (단일과 겹침 8) | 11건 (팀과 겹침 8) |

팀이 3분 빨랐고 고유 지적이 5건 더 나왔지만(단일 고유 3건), 토큰은 1.9배였다. 토큰 대부분은 캐시 입력이다.
