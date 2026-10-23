#!/usr/bin/env python3
"""작업을 끝낼 때 공유 LLM Wiki 에 기록했는지 확인하는 Stop 훅 (Claude Code · Codex 공용).

마지막 위키 기록 이후 파일을 고쳤거나 도구를 여러 번 썼는데 raw/ 기록이 없으면, 끝내지 말고 기록하라고 되돌려 보낸다.
- 같은 작업 묶음에는 한 번만 묻는다 — 세션마다 어디까지 물었는지 적어 둔다.
- 예약 작업 세션(첫 지시가 <scheduled-task)과 이미 한 번 되돌린 턴(stop_hook_active)은 통과시킨다.
- 기록할 만한 일이 아니었으면 모델이 이유를 한 줄 말하고 끝낼 수 있다.
- 이 세션이 쓴 기록의 파일명 시각이 저장한 시각보다 늦으면 되돌려 보낸다 — 시각을 짐작해 쓴 것이다.
  2026-10-23 점검에서 Claude Code 기록 108건 중 33건이 실제보다 최대 34분 늦은 이름이었다.
  지난번 확인 뒤에 쓴 기록 중 MAX_AGE 안에 저장된 것만 본다. 이미 올라가 링크가 걸린 옛 기록의 이름을 바꾸게 하면 안 된다.
- 오류가 나면 언제나 통과시킨다. 훅 고장이 작업 종료를 막으면 안 된다.

환경 변수: WIKI_RAW_DIR(기본 ~/Documents/Obsidian Vault/LLM Wiki/raw) · WIKI_GUARD_MIN_CALLS(기본 8)
          · WIKI_GUARD_STATE(기본 ~/.omj/wiki-guard.json) · WIKI_GUARD_AHEAD_SEC(기본 120) · WIKI_GUARD_MAX_AGE_SEC(기본 1800)
Python 3.9 에서도 돈다(데스크톱 앱이 시스템 python3 로 훅을 부를 수 있다).
"""
import datetime
import json
import os
import re
import sys

RAW_DIR = os.path.expanduser(os.environ.get("WIKI_RAW_DIR", "~/Documents/Obsidian Vault/LLM Wiki/raw"))
RAW_MARK = os.path.basename(os.path.dirname(RAW_DIR.rstrip("/"))) + "/" + os.path.basename(RAW_DIR.rstrip("/")) + "/"
MIN_CALLS = int(os.environ.get("WIKI_GUARD_MIN_CALLS", "8"))
STATE = os.path.expanduser(os.environ.get("WIKI_GUARD_STATE", "~/.omj/wiki-guard.json"))
AHEAD_SEC = int(os.environ.get("WIKI_GUARD_AHEAD_SEC", "120"))
MAX_AGE = int(os.environ.get("WIKI_GUARD_MAX_AGE_SEC", "1800"))
RAW_NAME = re.compile(re.escape(RAW_MARK) + r"(\d{8}T\d{6}-[^/\"'\s\\]+?\.md)")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
MCP_WRITE = re.compile(r"(create|update|save|delete|send|publish|execute|move|upload|archive|trash|share|write|patch)", re.I)
SHELL_WRITE = re.compile(r"(>|\btee\b|\*\*\* (Add|Update) File|writeFile|write_text|\bcp\b|\bmv\b)")
CODEX_EDIT = re.compile(r"apply_patch|\*\*\* (Add|Update|Delete) File")


def claude_events(lines):
    """(줄 번호, 종류, 수정 여부) — 종류는 call · raw · scheduled."""
    first_prompt = True
    for n, line in enumerate(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "user" and first_prompt and not d.get("isMeta"):
            c = d.get("message", {}).get("content")
            text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
            if text.strip():
                first_prompt = False
                if text.lstrip().startswith("<scheduled-task"):
                    yield n, "scheduled", False
        if d.get("type") != "assistant":
            continue
        for item in d.get("message", {}).get("content") or []:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name, inp = item.get("name", ""), item.get("input") or {}
            blob = json.dumps(inp, ensure_ascii=False)
            if name in EDIT_TOOLS:
                path = inp.get("file_path") or inp.get("notebook_path") or ""
                yield n, ("raw" if RAW_MARK in path else "call"), True
            elif name == "Bash":
                cmd = inp.get("command", "")
                yield n, ("raw" if RAW_MARK in cmd and SHELL_WRITE.search(cmd) else "call"), False
            elif name.startswith("mcp__"):
                write = bool(MCP_WRITE.search(name.split("__")[-1]))
                yield n, ("raw" if write and RAW_MARK in blob else "call"), write
            else:
                yield n, "call", False


def codex_events(lines):
    for n, line in enumerate(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p = d.get("payload") or {}
        if d.get("type") != "response_item" or p.get("type") not in ("custom_tool_call", "function_call"):
            continue
        text = str(p.get("input") or p.get("arguments") or "")
        if RAW_MARK in text and SHELL_WRITE.search(text):
            yield n, "raw", False
        else:
            yield n, "call", bool(CODEX_EDIT.search(text)) or p.get("name") == "apply_patch"


def decide(events, start):
    """끝내도 되는가. start 는 지난번에 물어본 줄 — 그 뒤 일만 센다."""
    events = list(events)
    if any(k == "scheduled" for _, k, _ in events):
        return False, 0, 0
    last_raw = max([n for n, k, _ in events if k == "raw"] or [-1])
    begin = max(last_raw, start)
    calls = [m for n, k, m in events if k == "call" and n > begin]
    edits = sum(1 for m in calls if m)
    return (edits >= 1 or len(calls) >= MIN_CALLS), len(calls), edits


def ahead_names(events, lines, after):
    """after 줄 뒤에 이 세션이 쓴 raw 기록 중 파일명 시각이 저장 시각(mtime)보다 늦은 것."""
    names = set()
    for n, kind, _ in events:
        if kind == "raw" and n > after:
            names.update(RAW_NAME.findall(lines[n]))
    now = datetime.datetime.now()
    bad = []
    for name in sorted(names):
        path = os.path.join(RAW_DIR, name)
        if not os.path.isfile(path):          # 이미 이름을 고쳤다
            continue
        stamp = datetime.datetime.strptime(name[:15], "%Y%m%dT%H%M%S")
        written = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        if (now - written).total_seconds() > MAX_AGE:   # 옛 기록 — 이미 올라가 링크가 걸렸다
            continue
        if (stamp - written).total_seconds() > AHEAD_SEC:
            bad.append(name)
    return bad


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    keep = dict(list(state.items())[-200:])
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(keep, f)
    os.replace(tmp, STATE)


def reason(calls, edits):
    return (
        "공유 LLM Wiki 기록이 아직 없다 (마지막 기록 뒤 도구 호출 %d회 · 파일 수정 %d회). "
        "끝내기 전에 %s 에 PROTOCOL.md 형식으로 새 기록 파일 하나를 남겨라 — 파일명 YYYYMMDDTHHMMSS-<작성 도구>-<주제>-<고유값>.md, "
        "task_id · project · status(completed/progress/blocked) · 한 일 · 바꾼 파일 · 검증(실행하지 않은 것은 미실행) · 다음 단계 · 출처. "
        "저장한 뒤 다시 읽어 확인하고, 최종 답에 파일 이름을 한 줄로 적어라. "
        "기록할 만한 작업이 아니었으면(단순 조회·질문 답) 기록하지 말고 그 이유를 한 줄로 말한 뒤 끝내라. "
        "이 확인은 같은 작업 묶음에 한 번만 한다." % (calls, edits, RAW_DIR)
    )


def ahead_reason(names):
    return (
        "공유 LLM Wiki 기록의 파일명 시각이 실제로 저장한 시각보다 늦다: %s. "
        "시각을 짐작하지 말고 `date +%%Y%%m%%dT%%H%%M%%S` 로 받아, 이 세션이 방금 쓴 그 기록의 파일명과 created_at 을 "
        "실제 시각으로 고쳐라(mv 로 이름만 바꾼다. 다른 도구·세션의 기록은 건드리지 않는다)." % ", ".join(names)
    )


def main():
    data = json.loads(sys.stdin.read() or "{}")
    if data.get("stop_hook_active"):
        return {}
    path = data.get("transcript_path")
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    codex = any('"type":"session_meta"' in l.replace(" ", "") for l in lines[:3])
    key = data.get("session_id") or path
    state = load_state()
    events = list((codex_events if codex else claude_events)(lines))
    block, calls, edits = decide(events, state.get(key, -1))
    after = state.get(key + "#ahead", -1)
    if not isinstance(after, int):                    # 첫 판이 남긴 목록 — 지금부터 본다
        after = len(lines) - 1
    ahead = ahead_names(events, lines, after)
    state[key + "#ahead"] = len(lines) - 1            # 다음에는 이 뒤에 쓴 기록만 본다
    reasons = []
    if block:
        state[key] = len(lines) - 1
        reasons.append(reason(calls, edits))
    if ahead:
        reasons.append(ahead_reason(ahead))
    save_state(state)
    if not reasons:
        return {}
    return {"decision": "block", "reason": " / ".join(reasons)}


if __name__ == "__main__":
    try:
        out = main()
    except Exception:            # 훅 고장으로 종료를 막지 않는다
        out = {}
    print(json.dumps(out, ensure_ascii=False))
