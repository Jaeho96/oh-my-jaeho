#!/usr/bin/env python3
"""Codex 매니저 실행기 — 과제 하나를 Codex 팀(매니저 + 하위 에이전트) 또는 단일 Codex 로 돌리고 기록을 남긴다.

    run_team.py --name <이름> --cwd <폴더> --mode team|single [--write] [--background] [--timeout 초]
                (--task "<과제>" | --task-file <파일>)

- `codex exec --json` 으로 돈다. runs/<이름>.jsonl(이벤트) · .err · .last.md(마지막 메시지) · .meta.json(조건·결과).
  board.py 가 이 폴더와 Codex 세션 기록(~/.codex/sessions)을 읽어 팀 트리를 그린다.
- 기본은 읽기 전용 샌드박스다. --write 는 cwd(와 --add-dir 로 준 폴더) 안에 쓸 수 있게 한다(workspace-write).
  승인은 묻지 않는 설정이라, 승인이 필요한 행동은 실패해 매니저에게 돌아온다.
- --background 는 감시 프로세스를 따로 띄우고 바로 돌아온다. 감시 프로세스가 끝까지 기다려 종료 코드를 .meta.json 에 남긴다.
- 실행 기록 폴더는 0700, 파일은 0600 으로 만든다(과제 본문이 들어간다). 같은 이름을 다시 써도 덮어쓰지 않는다.
- 공유 작업 기록(LLM Wiki raw/)은 이 실행기가 쓰지 않는다. 총괄(Claude Code)이 결과를 보고 쓴다.
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta

DEFAULT_RUNS = "~/.omj/agent-team/runs"
KST = timezone(timedelta(hours=9))
NAME_RE = re.compile(r"^[0-9A-Za-z가-힣._-]{1,60}$")

TEAM_PROMPT = """너는 이 과제의 매니저다. 아래 과제를 하위 에이전트 팀으로 나눠 끝내고, 결과를 하나로 합쳐 보고한다.

## 팀 운영 규칙
- 하위 에이전트는 `explorer`(읽기 전용 탐색), `worker`(구현·제안), `reviewer`(검증) 역할을 쓴다. 한 번에 {max_agents}개를 넘기지 않고, 하위 에이전트가 또 에이전트를 띄우게 하지 않는다.
- 독립적인 부분으로 나눠 병렬로 맡기고, 각 에이전트에 「무엇을, 어느 경로에서, 무엇을 내면 끝인지」를 적어 준다. 같은 파일을 두 에이전트가 고치게 하지 않는다.
- 모두 기다린 뒤 결과를 합친다. 결과가 서로 어긋나면 reviewer 에게 확인시킨다. 계획이 바뀌거나 풀 수 없는 것은 숨기지 말고 보고한다.
- {write_rule}
- 끝나면 하위 에이전트를 닫는다.

## 보고 형식 (두괄식)
1. 결론 — 됐다/안 됐다/막혔다 와 한 문장 요약
2. 총괄이 할 일 — 결정해 주면 되는 것
3. 핵심 근거 — 각 에이전트가 찾은 것(경로:줄)
4. 상세 — 분담표(에이전트·역할·범위·결과), 미확인·미실행, 바꾼 파일(있다면)

## 과제
{task}
"""

SINGLE_PROMPT = """아래 과제를 혼자서 끝내고 보고한다. 하위 에이전트를 띄우지 않는다.
- {write_rule}

## 보고 형식 (두괄식)
1. 결론 — 됐다/안 됐다/막혔다 와 한 문장 요약
2. 총괄이 할 일 — 결정해 주면 되는 것
3. 핵심 근거 — 찾은 것(경로:줄)
4. 상세 — 미확인·미실행, 바꾼 파일(있다면)

## 과제
{task}
"""


def now_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def write_private(path, data, exclusive=False):
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def open_private(path):
    """새 파일만 만든다 — 같은 이름이 있으면 FileExistsError (덮어쓰기 방지)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def stop_group(proc, grace=15):
    """proc 이 이끄는 프로세스 그룹 전체에 TERM, grace 초 뒤에도 남으면 KILL."""
    def send(sig):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            pass
    send(signal.SIGTERM)
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        send(signal.SIGKILL)
        proc.wait()
    send(signal.SIGKILL)                # codex 는 끝났는데 남은 자손이 있으면 정리한다


def supervise(base):
    """명령을 실행하고 끝까지 기다려 결과를 .meta.json 에 남긴다. 포그라운드·백그라운드 둘 다 이 길로 간다."""
    try:
        spec, meta = read_json(base + ".cmd.json"), read_json(base + ".meta.json")
        if not isinstance(spec, dict) or not isinstance(meta, dict):
            raise ValueError("JSON 객체가 아니다")
    except (OSError, ValueError) as e:
        print("실행 기록을 읽지 못했다(%s): %s" % (base, e), file=sys.stderr)
        return 1

    def finish(**kw):
        meta.update(kw)
        meta["finished"] = now_iso()
        write_private(base + ".meta.json", meta)
        try:
            os.chmod(base + ".last.md", 0o600)      # 이 파일은 codex 가 만든다(-o). 다른 기록처럼 0600 으로 맞춘다
        except OSError:
            pass

    try:
        out, err = open_private(base + ".jsonl"), open_private(base + ".err")
    except FileExistsError as e:
        finish(exit_code=None, error="기록 파일이 이미 있다: %s" % e.filename)
        return 1
    with out, err:
        try:
            # 새 프로세스 그룹으로 띄워, 멈출 때 codex 가 띄운 MCP · 명령까지 함께 멈춘다
            proc = subprocess.Popen(spec["cmd"], stdout=out, stderr=err, stdin=subprocess.DEVNULL, cwd=spec["cwd"],
                                    start_new_session=True)
        except OSError as e:
            finish(exit_code=None, error="시작 실패: %s" % e)
            return 127
        meta["pid"] = os.getpid()       # 보드는 이 감시 프로세스가 살아 있는지로 「실행 중」을 본다
        meta["codex_pid"] = proc.pid
        write_private(base + ".meta.json", meta)
        timeout = spec.get("timeout") or None
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_group(proc)
            finish(exit_code=proc.returncode, timed_out=True, error="제한 시간 %s초 초과로 멈춤" % timeout)
            return 124
        except KeyboardInterrupt:       # 새 그룹이라 터미널의 Ctrl-C 가 codex 에 가지 않는다 — 직접 멈춘다
            stop_group(proc)
            finish(exit_code=proc.returncode, error="사용자가 멈춤")
            return 130
    finish(exit_code=code)
    return code


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--_supervise":
        return supervise(sys.argv[2])

    ap = argparse.ArgumentParser(description="Codex 팀/단일 실행기")
    ap.add_argument("--name", required=True, help="실행 이름(영문·숫자·한글·._- 60자까지)")
    ap.add_argument("--cwd", required=True, help="Codex 가 볼 작업 폴더")
    ap.add_argument("--mode", choices=["team", "single"], default="team")
    ap.add_argument("--task", help="과제 본문")
    ap.add_argument("--task-file", help="과제 본문 파일")
    ap.add_argument("--model", default="gpt-6.1-sol")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--max-agents", type=int, default=3)
    ap.add_argument("--write", action="store_true", help="cwd 안 쓰기 허용(workspace-write). 기본은 읽기 전용")
    ap.add_argument("--add-dir", action="append", default=[], help="쓰기를 허용할 폴더를 더한다(--write 와 함께)")
    ap.add_argument("--timeout", type=int, default=0, help="이 초를 넘기면 멈춘다(0 이면 제한 없음)")
    ap.add_argument("--image", action="append", default=[], help="과제와 함께 넘길 그림(화면 캡처 등). 여러 번 줄 수 있다")
    ap.add_argument("--browser", metavar="DIR",
                    help="Playwright MCP 를 붙인다(샌드박스 안에서는 크롬이 안 뜬다). 캡처는 DIR 에 저장하게 한다")
    ap.add_argument("--background", action="store_true", help="감시 프로세스를 띄우고 바로 돌아온다")
    ap.add_argument("--runs", default=os.environ.get("AGENT_BOARD_RUNS", DEFAULT_RUNS))
    ap.add_argument("--extra", action="append", default=[], help="codex exec 에 그대로 넘길 인자")
    args = ap.parse_args()

    if not args.task and not args.task_file:
        ap.error("--task 또는 --task-file 이 필요하다")
    if not NAME_RE.fullmatch(args.name):
        ap.error("--name 은 영문·숫자·한글·._- 만, 60자까지 (경로 구분자 금지)")
    if args.add_dir and not args.write:
        ap.error("--add-dir 은 --write 와 함께 쓴다")
    cwd = os.path.abspath(os.path.expanduser(args.cwd))
    if not os.path.isdir(cwd):
        ap.error("--cwd 폴더가 없다: %s" % cwd)
    task = args.task or open(args.task_file, encoding="utf-8").read()
    runs = os.path.abspath(os.path.expanduser(args.runs))
    os.makedirs(runs, mode=0o700, exist_ok=True)
    os.chmod(runs, 0o700)

    name = "%s-%s-%s-%s" % (datetime.now(KST).strftime("%Y%m%dT%H%M%S"), args.mode, args.name, uuid.uuid4().hex[:4])
    base = os.path.join(runs, name)
    if args.write:
        dirs = [cwd] + [os.path.abspath(os.path.expanduser(d)) for d in args.add_dir]
        write_rule = "쓰기는 이 폴더 안에서만 허용된다: %s. 고친 파일은 보고에 적는다." % ", ".join(dirs)
    else:
        write_rule = "이번 실행은 읽기 전용이다. 파일을 고치지 말고, 고칠 것은 패치 제안으로 적는다."
    shots = os.path.abspath(os.path.expanduser(args.browser)) if args.browser else None
    if shots:
        # 상대 경로로 저장하면 cwd 맨 위에 떨어져 커밋될 수 있어 절대 경로를 못 박는다
        write_rule += (" 브라우저: playwright MCP 도구로 화면을 열고 캡처할 수 있다. 캡처는 %s 아래 절대 경로로 저장하고,"
                       " 저장한 그림을 view_image 로 직접 본 뒤 판단한다." % shots)
    prompt = (TEAM_PROMPT if args.mode == "team" else SINGLE_PROMPT).format(
        task=task.strip(), write_rule=write_rule, max_agents=args.max_agents)

    cmd = ["codex", "exec", "--json", "-C", cwd, "-m", args.model,
           "-c", 'model_reasoning_effort="%s"' % args.effort,
           "-s", "workspace-write" if args.write else "read-only",
           "--skip-git-repo-check", "-o", base + ".last.md"]
    for d in args.add_dir:
        cmd += ["--add-dir", os.path.abspath(os.path.expanduser(d))]
    for img in args.image:
        cmd += ["-i", os.path.abspath(os.path.expanduser(img))]
    if shots:
        # MCP 서버는 샌드박스 밖에서 돈다. exec 는 승인 창을 못 띄우므로 이 서버 도구만 미리 허용한다
        cmd += ["-c", 'mcp_servers.playwright.command="npx"',
                "-c", "mcp_servers.playwright.args=%s" % json.dumps(
                    ["@playwright/mcp@latest", "--headless", "--isolated", "--output-dir=" + shots]),
                "-c", 'mcp_servers.playwright.default_tools_approval_mode="approve"']
    cmd += args.extra + ["--", prompt]          # -i 는 값을 여럿 받으므로 -- 로 과제 본문과 가른다

    meta = {"name": name, "mode": args.mode, "model": args.model, "effort": args.effort, "cwd": cwd,
            "write": args.write, "add_dirs": args.add_dir, "max_agents": args.max_agents,
            "task": task.strip()[:600], "started": now_iso(), "timeout": args.timeout or None,
            "exit_code": None}
    write_private(base + ".cmd.json", {"cmd": cmd, "cwd": cwd, "timeout": args.timeout or None}, exclusive=True)
    write_private(base + ".meta.json", meta, exclusive=True)

    print("실행:", name)
    print("기록:", base + ".jsonl")
    if args.background:
        sup = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--_supervise", base],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
        print("감시 pid:", sup.pid)
        return 0
    code = supervise(base)
    print("끝. 종료 코드", code, "· 마지막 메시지:", base + ".last.md")
    return code


if __name__ == "__main__":
    sys.exit(main())
