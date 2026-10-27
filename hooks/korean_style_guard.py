#!/usr/bin/env python3
"""기계로 판정할 수 있는 문체 위반을 찾아 한 번 되돌려 보내는 Stop 훅 (Claude Code · Codex 공용, 2026-10-27).

같은 지적을 규칙 문장으로 거듭 쓰는 대신 검사로 막는다(Matt Pocock retro: 기계로 판정할 수 있는 위반은 검사로).
- 한글에 붙은 굵게(별표 두 개): 답, .md 파일, 커밋 메시지
- 줄표(U+2014, U+2015): 답, .md 파일, 커밋 메시지
- 쓰지 않는 단어(rules/vocabulary.md 의 한국어 금지어): 답, .md 파일, 커밋 메시지. 영어 금지어는 언급에만 나와 오탐이 많아 뺀다
- 손으로 쓴 한글 유니코드 이스케이프(백슬래시 u 와 네 자리): 이번에 쓴 모든 파일, 커밋 메시지. 정규식 범위(… - …)는 코드라 뺀다
- 커밋 메시지의 Claude 표기(Co-Authored-By 의 Claude · Anthropic, Generated with Claude Code)

보는 범위: 마지막 사용자 지시 뒤에 이 세션이 쓴 답, 파일에 새로 쓴 글, git commit 의 메시지.
- 파일: 이번 턴 첫 수정 직전 파일과 지금 파일을 비교해, 이번 턴에 바뀌어 지금 남아 있는 단어만 본다. 수정 직전 파일은 지금 파일에서
  이번 턴 수정을 뒤에서부터 되돌려 만든다(Claude 결과의 originalFile · structuredPatch, Codex 패치 덩어리). 코드 블록 판정은
  지금 파일 전체로 하므로 기존 코드 블록 안을 고친 글은 문장으로 보지 않는다. 고쳐 놓은 글, 줄 일부 수정의 손대지 않은 부분은 보지 않는다.
- 커밋: git 옵션(-C 경로, -c 키=값)을 건너 commit 을 찾고 메시지만 꺼낸다(-m, --message, -F 파일, -F - 의 heredoc,
  -m "$(cat <<'EOF' … EOF)"). 같은 명령줄의 다른 명령은 보지 않는다. Codex 는 exec 자바스크립트의 cmd 문자열에서 찾는다.
빼는 것: 코드 블록, 백틱 안, 「> 」 인용 줄, 「」 안, 기호만 든 괄호, 기호와 금지어를 설명하는 rules/vocabulary.md · rules/korean-style.md.
연결어미 뒤 쉼표는 오탐이 많아 검사하지 않는다(지침으로만 둔다).
- 같은 사용자 지시 안에서는 한 번만 되돌린다. 세션마다 마지막으로 되돌린 줄을 적어 두고, 그 줄이 지금 지시 뒤면 통과시킨다.
  stop_hook_active 만 보고 통과시키지 않는다. 그 값은 다른 Stop 훅(위키 기록 확인, Codex 검토)이 되돌려도 켜져서,
  그 뒤에 이어 쓴 글을 하나도 못 보게 된다. 예약 작업 세션은 통과.
- 남의 글 인용처럼 고치면 안 되는 것이면 모델이 이유를 한 줄 말하고 끝낼 수 있다.
- 오류가 나면 언제나 통과시킨다. 훅 고장이 작업 종료를 막으면 안 된다.

  python3 korean_style_guard.py --dump <기록 파일>   # 검사 대상으로 뽑은 글을 보여 준다(점검용)

환경 변수: STYLE_GUARD_STATE(기본 ~/.omj/style-guard.json)
Python 3.9 에서도 돈다(Codex 와 데스크톱 앱이 시스템 python3 로 훅을 부른다).
"""
import difflib
import json
import os
import re
import shlex
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

GIT_COMMIT = re.compile(r"""\bgit((?:\s+(?:-[cC]\s+(?:"[^"]*"|'[^']*'|\S+)|--[\w-]+(?:=\S+)?))*)\s+commit\b""")
HEREDOC = re.compile(r"""<<-?\s*(['"]?)([A-Za-z_]\w*)\1""")
OPERATORS = {"&&", "||", ";", "|", "&", ";;"}
JS_STR = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`'
JS_CMD = re.compile(r"\bcmd\s*:\s*(%s)" % JS_STR, re.S)
JS_PATCH = re.compile(r"apply_patch\(\s*(%s)" % JS_STR, re.S)


def blank(m):
    """찾은 자리를 같은 길이의 공백으로 바꾼다(줄바꿈은 남긴다). 자리 번호를 지키려는 것이다."""
    return re.sub(r"[^\n]", " ", m.group(0))


def mask(text):
    """코드 블록 · 백틱 안 · 인용 줄 · 「」 안 · 기호만 든 괄호를 공백으로 지운 글. 길이와 자리는 그대로다.
    「」 는 인용 · 화면 글자 · 예문을 감싸는 데 쓰므로(korean-style.md) 금지어나 기호를 언급할 때도 걸리지 않는다."""
    text = re.sub(r"```.*?```", blank, text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", blank, text)
    text = re.sub(r"「[^」\n]*」", blank, text)
    text = re.sub(r"\(\s*[—―]\s*\)", blank, text)
    return re.sub(r"(?m)^[ \t]*>.*$", blank, text)


def skip_file(path):
    return (os.path.basename(os.path.dirname(path)), os.path.basename(path)) in SKIP_FILES


def js_unescape(text):
    """Codex 의 exec 도구는 자바스크립트로 부른다(tools.apply_patch("…")). 문자열 안의 이스케이프를 푼다."""
    table = {"n": "\n", "t": "\t", "r": "\r"}

    def one(m):
        s = m.group(1)
        return chr(int(s[1:], 16)) if s[0] == "u" else table.get(s, s)
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", one, text)


def heredoc_body(text):
    m = HEREDOC.search(text)
    if not m:
        return None
    nl = text.find("\n", m.end())
    if nl < 0:
        return None
    end = re.compile(r"(?m)^[ \t]*%s[ \t]*$" % re.escape(m.group(2))).search(text, nl + 1)
    return text[nl + 1:end.start() if end else len(text)]


def first_line(seg):
    """따옴표 밖의 첫 줄바꿈까지. 따옴표 안 줄바꿈(-m 의 여러 줄 메시지)은 넘긴다."""
    quote = None
    i = 0
    while i < len(seg):
        c = seg[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "\\":
            i += 1
        elif c == "\n":
            return seg[:i]
        i += 1
    return seg


CD = re.compile(r"""(?:^|&&|;|\|\||\n)\s*cd\s+("[^"]*"|'[^']*'|[^\s;&|]+)""")


def resolve(path, base):
    path = os.path.expanduser(path.strip("'\""))
    return path if os.path.isabs(path) or not base else os.path.join(base, path)


def commit_messages(cmd, cwd=None):
    """셸 명령에서 git commit 메시지만 꺼낸다. -F 파일은 앞선 cd, git -C 를 따라간 폴더 기준으로 읽는다."""
    out = []
    for m in GIT_COMMIT.finditer(cmd):
        base = cwd
        for c in CD.finditer(cmd[:m.start()]):
            base = resolve(c.group(1), base)
        opts = re.search(r"""-C\s+("[^"]*"|'[^']*'|\S+)""", m.group(1) or "")
        if opts:
            base = resolve(opts.group(1), base)
        rest = cmd[m.end():]
        head = first_line(rest)
        try:
            lex = shlex.shlex(head, posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            tokens = list(lex)
        except ValueError:
            continue
        values, files = [], []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if t in OPERATORS:
                break
            if t in ("-m", "--message") and nxt is not None:
                values.append(nxt)
                i += 1
            elif t.startswith("--message="):
                values.append(t[len("--message="):])
            elif t.startswith("-m") and len(t) > 2:
                values.append(t[2:])
            elif re.match(r"^-[a-zA-Z]*m$", t) and nxt is not None:      # -am "…"
                values.append(nxt)
                i += 1
            elif t in ("-F", "--file") and nxt is not None:
                files.append(nxt)
                i += 1
            elif t.startswith("--file="):
                files.append(t[len("--file="):])
            elif t.startswith("-F") and len(t) > 2:
                files.append(t[2:])
            i += 1
        for v in values:
            out.append(heredoc_body(v) if "<<" in v and heredoc_body(v) is not None else v)
        for f in files:
            if f == "-":
                body = heredoc_body(rest)
                if body is not None:
                    out.append(body)
                continue
            text = read_file(resolve(f, base))
            if text is not None:
                out.append(text)
    return out


def claude_results(lines):
    """도구 결과(toolUseResult)를 tool_use_id 로 묶는다. Edit 결과에는 수정 직전 파일(originalFile)과 바뀐 줄(structuredPatch)이 있다."""
    out = {}
    for line in lines:
        if '"toolUseResult"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        res = d.get("toolUseResult")
        content = (d.get("message") or {}).get("content")
        if isinstance(res, dict) and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("tool_use_id"):
                    out[c["tool_use_id"]] = res
    return out


def claude_pieces(lines):
    """(줄 번호, 종류, 경로, 글, 작업 폴더, 덧붙임). 종류는 prompt · scheduled · answer · write · edit · shell."""
    results = claude_results(lines)
    first = True
    for n, line in enumerate(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        kind = d.get("type")
        cwd = d.get("cwd")
        content = (d.get("message") or {}).get("content")
        if kind == "user" and not d.get("isMeta"):
            if isinstance(content, str):
                text = content
            else:
                text = " ".join(x.get("text", "") for x in content or [] if isinstance(x, dict) and x.get("type") == "text")
            if text.strip():
                if first and text.lstrip().startswith("<scheduled-task"):
                    yield n, "scheduled", "", "", cwd, {}
                first = False
                yield n, "prompt", "", "", cwd, {}
        if kind != "assistant" or not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                yield n, "answer", "", item.get("text", ""), cwd, {}
            elif item.get("type") == "tool_use":
                name, inp = item.get("name", ""), item.get("input") or {}
                path = inp.get("file_path", "")
                res = results.get(item.get("id")) or {}
                if name == "Write":
                    yield n, "write", path, inp.get("content") or "", cwd, {"tool": "Write", "result": res}
                elif name == "Edit" and inp.get("old_string"):           # 새 글이 비어도(지우기) 되돌리기에 쓴다
                    new = inp.get("new_string") or ""
                    edits = [(inp["old_string"], new, bool(inp.get("replace_all")))]
                    yield n, "edit", path, new, cwd, {"tool": "Edit", "result": res, "edits": edits}
                elif name == "MultiEdit":
                    edits = [(e.get("old_string") or "", e.get("new_string") or "", bool(e.get("replace_all")))
                             for e in inp.get("edits") or [] if isinstance(e, dict)]
                    if edits:
                        yield n, "edit", path, "\n".join(e[1] for e in edits), cwd, {
                            "tool": "MultiEdit", "result": res, "edits": edits}
                elif name == "Bash":
                    yield n, "shell", "", inp.get("command", ""), cwd, {}


def patch_files(text):
    """apply_patch 글에서 (종류, 파일, 더한 글, 덩어리 목록). Add File 은 write, Update File 은 edit.
    덩어리(hunk)는 문맥 · 뺀 · 더한 줄을 표시(' ', '-', '+')를 붙인 채 차례대로 담는다."""
    files, cur = [], None
    for line in text.split("\n"):
        m = re.match(r"\*\*\* (Add|Update) File: (.+)", line)
        if m:
            cur = {"kind": "write" if m.group(1) == "Add" else "edit", "path": m.group(2).strip(),
                   "added": [], "hunks": [[]]}
            files.append(cur)
        elif line.startswith("*** "):
            cur = cur if line.startswith("*** Move to:") else None
        elif cur is None:
            continue
        elif line.startswith("@@"):
            cur["hunks"].append([])
        elif line.startswith("+"):
            cur["added"].append(line[1:])
            cur["hunks"][-1].append(line)
        elif line.startswith("-"):
            cur["hunks"][-1].append(line)
        else:
            cur["hunks"][-1].append(" " + line[1:] if line.startswith(" ") else " " + line)
    return [(f["kind"], f["path"], "\n".join(f["added"]), [h for h in f["hunks"] if h]) for f in files]


def shell_from_args(args):
    if isinstance(args, dict):
        for key in ("cmd", "command"):
            v = args.get(key)
            if isinstance(v, str):
                return v
            if isinstance(v, list) and v:
                if len(v) >= 3 and str(v[1]) in ("-c", "-lc"):
                    return str(v[2])
                return " ".join(str(x) for x in v)
    return ""


def js_objects(code, call):
    """code 에서 call({ … }) 의 객체 글을 차례로 꺼낸다. 문자열 안의 중괄호는 세지 않는다."""
    for m in re.finditer(re.escape(call) + r"\(\s*\{", code):
        start = m.end() - 1
        depth, quote, j = 0, None, start
        while j < len(code):
            ch = code[j]
            if quote:
                if ch == "\\":
                    j += 1
                elif ch == quote:
                    quote = None
            elif ch in "\"'`":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield code[start:j + 1]
                    break
            j += 1


def js_prop(obj, name):
    m = re.search(r"\b%s\s*:\s*(%s)" % (name, JS_STR), obj, re.S)
    return js_unescape(m.group(1)[1:-1]) if m else None


def codex_pieces(lines):
    cwd = None
    for n, line in enumerate(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p = d.get("payload") or {}
        if d.get("type") in ("session_meta", "turn_context") and p.get("cwd"):
            cwd = p.get("cwd")
        if d.get("type") == "event_msg" and p.get("type") in ("task_started", "user_message"):
            yield n, "prompt", "", "", cwd, {}   # 턴 시작
            continue
        if d.get("type") != "response_item":
            continue
        if p.get("type") == "message" and p.get("role") == "assistant":
            for item in p.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "output_text":
                    yield n, "answer", "", item.get("text", ""), cwd, {}
            continue
        if p.get("type") not in ("custom_tool_call", "function_call"):
            continue
        raw = p.get("input") or p.get("arguments") or ""
        raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
        shells, patches = [], []                      # shells: (명령, 명령 폴더)
        if p.get("type") == "function_call":
            try:
                args = json.loads(raw)
            except ValueError:
                args = {}
            if isinstance(args, dict):
                shells.append((shell_from_args(args), args.get("workdir") or args.get("cwd")))
                if isinstance(args.get("input"), str):
                    patches.append(args["input"])
        elif p.get("name") == "apply_patch":
            patches.append(raw)
        else:                                         # exec: 자바스크립트
            objs = list(js_objects(raw, "exec_command"))
            if objs:
                shells += [(js_prop(o, "cmd"), js_prop(o, "workdir")) for o in objs]
            else:
                shells += [(js_unescape(s[1:-1]), None) for s in JS_CMD.findall(raw)]
            patches += [js_unescape(s[1:-1]) for s in JS_PATCH.findall(raw)]
        for patch in patches:
            if "*** Begin Patch" in patch:
                for kind, path, added, hunks in patch_files(patch):
                    if path and not os.path.isabs(path) and cwd:
                        path = os.path.join(cwd, path)
                    yield n, kind, path, added, cwd, {"tool": "patch", "hunks": hunks}
        for sh, wd in shells:
            if sh:
                yield n, "shell", "", sh, resolve(wd, cwd) if wd else cwd, {}


def read_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def changed_spans(old, new):
    """new 에서 old 와 달라진 범위. 공백까지 넓혀 단어 단위로 돌려준다. 손대지 않은 글의 위반은 이번 수정 탓이 아니다."""
    spans = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=len(new) > 5000)
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        a, b = j1, j2
        while a > 0 and not new[a - 1].isspace():
            a -= 1
        while b < len(new) and not new[b].isspace():
            b += 1
        spans.append((a, b))
    return spans


def keep(text, spans):
    """spans 밖 글자를 공백으로 지운다(줄바꿈은 남긴다). spans 가 None 이면 그대로."""
    if spans is None:
        return text
    out = [c if c == "\n" else " " for c in text]
    for a, b in spans:
        out[a:b] = text[a:b]
    return "".join(out)


def net_spans(base, final):
    """base 에서 final 로 달라진 범위(final 의 글자 자리). 줄 단위로 맞춘 뒤 바뀐 줄은 단어 단위까지 좁힌다."""
    a, b = base.split("\n"), final.split("\n")
    starts, pos = [], 0
    for line in b:
        starts.append(pos)
        pos += len(line) + 1
    spans = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        for k in range(j2 - j1):
            j = j1 + k
            if tag == "replace" and k < i2 - i1:
                spans += [(starts[j] + x, starts[j] + y) for x, y in changed_spans(a[i1 + k], b[j])]
            else:
                spans.append((starts[j], starts[j] + len(b[j])))
    return spans


def ink(s):
    """지워지지 않고 남은 글자 수. 자리를 못 정할 때 가장 많이 지워진(코드 안) 자리를 골라 오탐을 피하는 데 쓴다."""
    return len(re.sub(r"\s", "", s))


def reverse_hunks(content, hunks, hints=None):
    """덩어리(문맥 · 뺀 · 더한 줄)를 거꾸로 적용해 수정 전 글을 만든다. 덩어리를 못 찾으면 None.
    같은 덩어리가 여러 자리에 있으면 줄 번호 힌트에 가장 가까운 자리, 힌트가 없으면 더한 줄이 가장 많이 지워진 자리."""
    lines = content.split("\n")
    for k in range(len(hunks) - 1, -1, -1):
        hunk = [l for l in hunks[k] if l[:1] in (" ", "-", "+")]
        new = [l[1:] for l in hunk if l[:1] in (" ", "+")]
        old = [l[1:] for l in hunk if l[:1] in (" ", "-")]
        if new == old or not new:      # 바뀐 게 없거나, 문맥 없이 지우기만 해서 자리를 모른다(지운 줄은 검사와 상관없다)
            continue
        starts = [s for s in range(len(lines) - len(new) + 1)
                  if lines[s] == new[0] and lines[s:s + len(new)] == new]
        if not starts:
            return None
        hint = hints[k] if hints and k < len(hints) else None
        if hint is not None:
            s = min(starts, key=lambda x: abs(x - hint))
        elif len(starts) == 1:
            s = starts[0]
        else:
            masked = mask("\n".join(lines)).split("\n")
            added = [i for i, l in enumerate(l for l in hunk if l[:1] in (" ", "+")) if l.startswith("+")]
            s = min(starts, key=lambda x: ink("".join(masked[x + i] for i in added)))
        lines[s:s + len(new)] = old
    return "\n".join(lines)


def reverse_patch(content, patch):
    """Claude 결과의 structuredPatch 를 거꾸로 적용한다. newStart 는 그 수정 직후 파일의 줄 번호다."""
    return reverse_hunks(content, [h.get("lines") or [] for h in patch], [h.get("newStart", 1) - 1 for h in patch])


def turn_base(ops, final):
    """이번 턴 첫 수정 직전의 파일. 지금 파일에서 이번 턴 수정을 뒤에서부터 되돌린다. 못 되돌리면 None.
    수정마다 쓰는 것: Claude Edit 는 수정 직전 파일(originalFile) > 바뀐 덩어리(structuredPatch) > 문자열 되바꾸기,
    Claude Write 는 덮어쓴 경우 바뀐 덩어리, 새로 만든 경우 빈 글. Codex 는 Add File 이면 빈 글, Update File 이면 덩어리."""
    content = final
    for kind, text, extra in reversed(ops):
        res = extra.get("result") or {}
        tool = extra.get("tool")
        if tool == "patch":
            if kind == "write":
                return ""
            content = reverse_hunks(content, extra.get("hunks") or [])
        elif tool == "Write":
            if res.get("type") == "update" and res.get("structuredPatch"):
                content = reverse_patch(content, res["structuredPatch"])
            else:
                return ""               # 새로 만들었거나 결과가 없다. 쓴 내용 전체가 이번 턴 글이다
        elif isinstance(res.get("originalFile"), str):
            content = res["originalFile"]
        elif res.get("structuredPatch"):
            content = reverse_patch(content, res["structuredPatch"])
        else:
            for old, new, every in reversed(extra.get("edits") or []):
                if not new:
                    continue                # 지우기만 한 수정은 자리를 모른다. 지운 글은 지금 파일에 없으니 건너뛴다
                if new not in content:
                    return None
                if every:
                    return None             # 원래 있던 같은 글까지 되돌리게 되니 자리를 모르는 것으로 본다
                spots, i = [], content.find(new)
                while i >= 0:
                    spots.append(i)
                    i = content.find(new, i + 1)
                masked = mask(content) if len(spots) > 1 else None
                at = min(spots, key=lambda x: ink(masked[x:x + len(new)])) if masked else spots[0]
                content = content[:at] + old + content[at + len(new):]
        if content is None:
            return None
    return content


def file_targets(path, ops):
    """이번 턴에 이 파일에서 바뀌어 지금 남아 있는 글. (문장 검사할 글, 원문) 목록."""
    final = read_file(path)
    if final is None:
        return []                       # 지웠거나 옮겼다
    base = turn_base(ops, final)
    if base is not None:
        spans = net_spans(base, final)
        if not spans:
            return []
        return [(keep(mask(final), spans) if path.endswith(".md") else None, keep(final, spans))]
    out = []                            # 되돌리지 못하면 수정마다 새 글이 지금 파일에 있는 자리를 찾아 파일 전체 기준으로 본다
    masked = mask(final)
    for kind, text, extra in ops:
        pairs = extra.get("edits") or [(None, text, False)]
        for old, new, _ in pairs:
            spots, i = [], final.find(new) if new else -1
            while i >= 0:
                spots.append(i)
                i = final.find(new, i + 1)
            if not spots:
                continue                # 지금 파일에 없다(뒤에 고쳤거나 지웠다)
            spans = changed_spans(old, new) if old else None
            at = min(spots, key=lambda x: ink(keep(masked[x:x + len(new)], spans)))   # 여러 자리면 코드 안 쪽(오탐 피하기)
            out.append((keep(masked[at:at + len(new)], spans) if path.endswith(".md") else None,
                        keep(final[at:at + len(new)], spans)))
    return out


def escapes(text):
    """정규식 범위(앞뒤에 -)가 아닌 한글 이스케이프."""
    for m in ESCAPE.finditer(text):
        if text[m.end():m.end() + 1] == "-" or text[max(0, m.start() - 1):m.start()] == "-":
            continue
        yield m


def snippet(text, m):
    s = text[max(0, m.start() - 15):m.end() + 15].replace("\n", " ")
    return "…%s…" % re.sub(r"\s+", " ", s).strip()


def find(pieces):
    hits, files = [], {}
    targets = []                       # (어디, 문장 검사할 글, 원문)
    for _, kind, path, text, cwd, extra in pieces:
        if kind == "answer" and text:
            targets.append(("답", mask(text), None))
        elif kind in ("write", "edit") and path and not skip_file(path):
            files.setdefault(path, []).append((kind, text, extra))
        elif kind == "shell" and text:
            for msg in commit_messages(text, cwd):
                targets.append(("커밋 메시지", mask(msg), msg))
    for path, ops in files.items():
        for body, raw in file_targets(path, ops):
            targets.append(("파일 %s" % os.path.basename(path), body, raw))
    for where, body, raw in targets:
        if body:
            for label, rx in PROSE_CHECKS:
                for m in rx.finditer(body):
                    hits.append("- %s: %s %s" % (where, label, snippet(body, m)))
        if raw:
            for m in escapes(raw):
                hits.append("- %s: 한글 이스케이프 %s" % (where, snippet(raw, m)))
        if raw and where == "커밋 메시지":
            for m in CREDIT.finditer(raw):
                hits.append("- %s: Claude 표기 %s" % (where, snippet(raw, m)))
    return list(dict.fromkeys(hits))           # 같은 지적은 한 번만


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
    path = data.get("transcript_path")
    if not path or not os.path.isfile(path):
        return {}
    lines = read_lines(path)
    pieces = pieces_of(lines)
    if any(p[1] == "scheduled" for p in pieces):
        return {}
    key = data.get("session_id") or path
    state = load_state()
    turn = max([p[0] for p in pieces if p[1] == "prompt"] or [-1])
    if state.get(key, -1) > turn:                 # 이 지시 안에서 이미 한 번 되돌렸다
        return {}
    hits = find(p for p in pieces if p[0] > turn)
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
        for n, kind, name, text, cwd, _ in pieces_of(read_lines(sys.argv[2])):
            print("%5d %-9s %s %s" % (n, kind, name, text[:120].replace("\n", " ")))
            if kind == "shell":
                for msg in commit_messages(text, cwd):
                    print("      커밋 메시지: %s" % msg[:120].replace("\n", " "))
        sys.exit(0)
    try:
        out = main()
    except Exception:            # 훅 고장으로 종료를 막지 않는다
        out = {}
    print(json.dumps(out, ensure_ascii=False))
