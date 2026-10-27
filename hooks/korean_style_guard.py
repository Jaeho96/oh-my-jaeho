#!/usr/bin/env python3
"""기계로 판정할 수 있는 문체 위반을 찾아 한 번 되돌려 보내는 Stop 훅 (Claude Code · Codex 공용, 2026-10-27).

같은 지적을 규칙 문장으로 거듭 쓰는 대신 검사로 막는다(Matt Pocock retro: 기계로 판정할 수 있는 위반은 검사로).
- 한글에 붙은 굵게(별표 두 개): 답, .md 파일, 커밋 메시지
- 줄표(U+2014, U+2015): 답, .md 파일, 커밋 메시지
- 쓰지 않는 단어(rules/vocabulary.md 의 한국어 금지어): 답, .md 파일, 커밋 메시지. 영어 금지어는 언급에만 나와 오탐이 많아 뺀다
- 손으로 쓴 한글 유니코드 이스케이프(백슬래시 u 와 네 자리): 이번에 쓴 모든 파일, 커밋 메시지
- 커밋 메시지의 Claude 표기(Co-Authored-By 의 Claude · Anthropic, Generated with Claude Code)

보는 범위: 마지막 사용자 지시 뒤에 이 세션이 쓴 답, 파일에 새로 쓴 글(Write · Edit 의 새 글, apply_patch 의 + 줄), git commit 명령.
빼는 것: 코드 블록, 백틱 안, 「> 」 인용 줄, 「」 안, 기호만 든 괄호, 기호와 금지어를 설명하는 rules/vocabulary.md · rules/korean-style.md.
연결어미 뒤 쉼표는 오탐이 많아 검사하지 않는다(지침으로만 둔다).
- 같은 작업 묶음에는 한 번만 되돌린다. 세션마다 어디까지 봤는지 적어 둔다. 재진입(stop_hook_active)과 예약 작업 세션은 통과.
- 남의 글 인용처럼 고치면 안 되는 것이면 모델이 이유를 한 줄 말하고 끝낼 수 있다.
- 오류가 나면 언제나 통과시킨다. 훅 고장이 작업 종료를 막으면 안 된다.

  python3 korean_style_guard.py --dump <기록 파일>   # 검사 대상으로 뽑은 글을 보여 준다(점검용)

환경 변수: STYLE_GUARD_STATE(기본 ~/.omj/style-guard.json)
Python 3.9 에서도 돈다(Codex 와 데스크톱 앱이 시스템 python3 로 훅을 부른다).
"""
import json
import os
import re
import sys

STATE = os.path.expanduser(os.environ.get("STYLE_GUARD_STATE", "~/.omj/style-guard.json"))
MAX_HITS = 8
SKIP_FILES = {("rules", "vocabulary.md"), ("rules", "korean-style.md")}

BOLD = re.compile(r"\*\*(?=[^*\n]*[가-힣])[^*\n]+\*\*|\*\*[^*\n]+\*\*(?=[가-힣])")
DASH = re.compile("[—―]")
WORD = re.compile(r"고아(?!성)")
ESCAPE = re.compile(r"\\u(?:a[c-f]|b[0-9a-f]|c[0-9a-f]|d[0-7]|31[3-8])[0-9a-f]{2}", re.I)
CREDIT = re.compile(r"co-authored-by:[^\n]*(?:claude|anthropic)|generated with \[?claude code", re.I)
PROSE_CHECKS = (("굵게", BOLD), ("줄표", DASH), ("쓰지 않는 단어", WORD))
EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}


def prose(text):
    """코드 블록 · 백틱 안 · 인용 줄 · 「」 안 · 「(기호)」처럼 기호만 든 괄호를 뺀 글.
    「」 는 인용 · 화면 글자 · 예문을 감싸는 데 쓰므로(korean-style.md) 금지어나 기호를 언급할 때도 걸리지 않는다."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"「[^」\n]*」", " ", text)
    text = re.sub(r"\(\s*[\u2014\u2015]\s*\)", " ", text)
    return "\n".join(l for l in text.split("\n") if not l.lstrip().startswith(">"))


def skip_file(path):
    return (os.path.basename(os.path.dirname(path)), os.path.basename(path)) in SKIP_FILES


def claude_pieces(lines):
    """(줄 번호, 종류, 이름, 글). 종류는 prompt · scheduled · answer · file · commit."""
    first = True
    for n, line in enumerate(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        kind = d.get("type")
        content = (d.get("message") or {}).get("content")
        if kind == "user" and not d.get("isMeta"):
            if isinstance(content, str):
                text = content
            else:
                text = " ".join(x.get("text", "") for x in content or [] if isinstance(x, dict) and x.get("type") == "text")
            if text.strip():
                if first and text.lstrip().startswith("<scheduled-task"):
                    yield n, "scheduled", "", ""
                first = False
                yield n, "prompt", "", ""
        if kind != "assistant" or not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                yield n, "answer", "", item.get("text", "")
            elif item.get("type") == "tool_use":
                name, inp = item.get("name", ""), item.get("input") or {}
                if name in EDIT_TOOLS:
                    path = inp.get("file_path", "")
                    new = [inp.get("content") or "", inp.get("new_string") or ""]
                    new += [e.get("new_string", "") for e in inp.get("edits") or [] if isinstance(e, dict)]
                    yield n, "file", path, "\n".join(x for x in new if x)
                elif name == "Bash" and "git commit" in inp.get("command", ""):
                    yield n, "commit", "", inp.get("command", "")


def patch_files(text):
    """apply_patch 글에서 (파일, 더한 줄)."""
    files, cur = {}, None
    for line in text.split("\n"):
        m = re.match(r"\*\*\* (?:Add|Update) File: (.+)", line)
        if m:
            cur = m.group(1).strip()
            files.setdefault(cur, [])
        elif line.startswith("*** "):
            cur = None if not line.startswith("*** Move to:") else cur
        elif cur and line.startswith("+") and not line.startswith("+++"):
            files[cur].append(line[1:])
    return [(p, "\n".join(ls)) for p, ls in files.items()]


def js_unescape(text):
    """Codex 의 exec 도구는 자바스크립트로 부른다(tools.apply_patch("…")). 문자열 안의 이스케이프를 푼다."""
    table = {"n": "\n", "t": "\t", "r": "\r"}

    def one(m):
        s = m.group(1)
        return chr(int(s[1:], 16)) if s[0] == "u" else table.get(s, s)
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", one, text)


def codex_pieces(lines):
    for n, line in enumerate(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p = d.get("payload") or {}
        if d.get("type") == "event_msg" and p.get("type") in ("task_started", "user_message"):
            yield n, "prompt", "", ""   # 턴 시작
            continue
        if d.get("type") != "response_item":
            continue
        if p.get("type") == "message" and p.get("role") == "assistant":
            for item in p.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "output_text":
                    yield n, "answer", "", item.get("text", "")
        elif p.get("type") in ("custom_tool_call", "function_call"):
            raw = p.get("input") or p.get("arguments") or ""
            text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            if p.get("type") == "function_call":
                try:   # 인자는 JSON 문자열이다. 풀어야 줄바꿈 · 한글이 원래 모양이 된다
                    text = _flatten(json.loads(text))
                except ValueError:
                    pass
            elif "*** Begin Patch\\n" in text or "git commit" in text:
                text = js_unescape(text)
            if "*** Begin Patch" in text:
                for path, added in patch_files(text):
                    yield n, "file", path, added
            elif "git commit" in text:
                yield n, "commit", "", text


def _flatten(value):
    if isinstance(value, dict):
        return "\n".join(_flatten(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten(v) for v in value)
    return str(value)


def snippet(text, m):
    s = text[max(0, m.start() - 15):m.end() + 15].replace("\n", " ")
    return "…%s…" % s.strip()


def find(pieces):
    hits = []
    for _, kind, name, text in pieces:
        if not text:
            continue
        where = {"answer": "답", "commit": "커밋 메시지"}.get(kind) or "파일 %s" % os.path.basename(name)
        if kind == "file" and skip_file(name):
            continue
        checks = []
        if kind in ("answer", "commit") or (kind == "file" and name.endswith(".md")):
            body = prose(text)
            checks += [(label, rx, body) for label, rx in PROSE_CHECKS]
        if kind in ("file", "commit"):
            checks.append(("한글 이스케이프", ESCAPE, text))
        if kind == "commit":
            checks.append(("Claude 표기", CREDIT, text))
        for label, rx, body in checks:
            for m in rx.finditer(body):
                hits.append("- %s: %s %s" % (where, label, snippet(body, m)))
    return hits


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


def read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.readlines()


def pieces_of(lines):
    codex = any('"type":"session_meta"' in l.replace(" ", "") for l in lines[:3])
    return list((codex_pieces if codex else claude_pieces)(lines))


def main():
    data = json.loads(sys.stdin.read() or "{}")
    if data.get("stop_hook_active"):
        return {}
    path = data.get("transcript_path")
    if not path or not os.path.isfile(path):
        return {}
    lines = read_lines(path)
    pieces = pieces_of(lines)
    if any(k == "scheduled" for _, k, _, _ in pieces):
        return {}
    key = data.get("session_id") or path
    state = load_state()
    turn = max([n for n, k, _, _ in pieces if k == "prompt"] or [-1])
    start = max(turn, state.get(key, -1))
    hits = find(p for p in pieces if p[0] > start)
    if not hits:
        return {}
    state[key] = len(lines) - 1
    save_state(state)
    shown = hits[:MAX_HITS] + (["- 그 밖에 %d곳" % (len(hits) - MAX_HITS)] if len(hits) > MAX_HITS else [])
    return {"decision": "block", "reason": (
        "문체 검사에 걸린 곳이 %d곳 있다. 고칠 수 있으면 고친다(답이면 고친 문장을 다시 쓰고, 파일 · 커밋이면 고친다). "
        "남의 글 인용처럼 고치면 안 되는 것이면 이유를 한 줄 말하고 끝낸다. 이 확인은 같은 작업 묶음에 한 번만 한다.\n%s"
        % (len(hits), "\n".join(shown)))}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--dump":
        for n, kind, name, text in pieces_of(read_lines(sys.argv[2])):
            print("%5d %-9s %s %s" % (n, kind, name, text[:120].replace("\n", " ")))
        sys.exit(0)
    try:
        out = main()
    except Exception:            # 훅 고장으로 종료를 막지 않는다
        out = {}
    print(json.dumps(out, ensure_ascii=False))
