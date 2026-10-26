"""사무실 화면 데이터 — Codex 세션 기록(rollout)과 Claude Code 대화 기록(transcript)을 같은 이벤트로 읽어 에이전트 상태를 만든다.

pixel-agents(MIT, github.com/pixel-agents-hq/pixel-agents)의 설계 — 공급자마다 기록을 정규화 이벤트로 바꾸고,
상태 저장소가 이벤트와 타이머로 캐릭터 상태를 정한다 — 를 참고해 다시 썼다. 코드는 가져오지 않았다.

흐름: 파일 찾기(Registry) → 새 줄만 읽기(TailReader) → 공급자 파서(parse_codex_line·parse_claude_line)가 이벤트 목록을 낸다
      → AgentTrack.apply 가 상태를 쌓는다 → AgentTrack.snapshot(now) 이 화면용 상태(status·activity·context)를 낸다.
대화 내용은 화면에 싣지 않는다. 도구 이름·파일 이름·명령 첫 단어·Bash 설명 정도만 쓴다. Codex 하위 에이전트의 보고문만 예외다.
"""
import glob
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

# 상태 — 화면이 이 이름으로 그림을 고른다(web/src/domain/agent.ts 와 같아야 한다)
TYPING, READING, THINKING, TEAM, WAITING, IDLE, DONE, STALLED, PERMISSION, ERROR = (
    "typing", "reading", "thinking", "team", "waiting", "idle", "done", "stalled", "permission", "error")

READ_COMMANDS = {"cat", "rg", "grep", "sed", "ls", "head", "tail", "find", "wc", "less", "awk", "jq", "stat", "file",
                 "tree", "pwd", "nl", "sort", "uniq", "diff", "which", "du", "df", "date", "echo", "printf", "realpath"}
GIT_READ = {"log", "diff", "show", "status", "blame", "grep", "ls-files", "rev-parse", "branch"}
CLAUDE_READ_TOOLS = {"Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "NotebookRead", "ToolSearch",
                     "ListMcpResourcesTool", "ReadMcpResourceTool", "TaskList", "TaskGet"}
CLAUDE_TEAM_TOOLS = {"Agent", "Task", "SendMessage", "Workflow"}
CODEX_TEAM_TOOLS = {"spawn_agent", "wait_agent", "wait", "send_message", "followup_task", "list_agents",
                    "close_agent", "resume_agent", "interrupt_agent", "send_input"}
MCP_READ_HINT = re.compile(r"(read|search|get|list|fetch|query|find|snapshot|describe)", re.I)
CODEX_CMD = re.compile(r'(?:\bcmd\s*:\s*|"cmd"\s*:\s*|"command"\s*:\s*\[?\s*)"((?:[^"\\]|\\.)*)"')

CLAUDE_WINDOW = 200_000
CLAUDE_WIDE_WINDOW = 1_000_000


def ts_of(value):
    """기록의 시각 문자열 → 초. 없거나 틀리면 None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def iso(ts):
    return datetime.fromtimestamp(ts, KST).isoformat(timespec="seconds") if ts else None


def short_path(p):
    return "/".join([x for x in (p or "").split("/") if x][-2:])


# ---------- 명령·도구 분류 ----------

def classify_command(cmd):
    """셸 명령 → (mode, 보여 줄 말). 명령 전체는 싣지 않는다(비밀이 섞일 수 있다)."""
    words = re.findall(r"[^\s|;&()]+", cmd or "")
    words = [w for w in words if not re.match(r"^[A-Z_]+=", w) and w not in ("cd", "sudo", "env", "time", "-lc", "/bin/zsh", "/bin/bash", "zsh", "bash")]
    if not words:
        return TYPING, "명령 실행"
    prog = os.path.basename(words[0].strip("'\""))
    if prog == "git" and len(words) > 1:
        sub = words[1]
        return (READING if sub in GIT_READ else TYPING), "git %s" % sub
    if prog in READ_COMMANDS:
        if prog == "sed" and "-i" in words:
            return TYPING, "sed -i"
        return READING, prog
    return TYPING, prog


def classify_claude_tool(name, inp):
    inp = inp if isinstance(inp, dict) else {}
    if name in CLAUDE_TEAM_TOOLS:
        return TEAM, inp.get("description") or "하위 에이전트"
    if name in CLAUDE_READ_TOOLS:
        target = os.path.basename(str(inp.get("file_path") or inp.get("path") or ""))
        return READING, ("%s %s" % (name, target)).strip()
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return TYPING, ("%s %s" % (name, os.path.basename(str(inp.get("file_path") or inp.get("notebook_path") or "")))).strip()
    if name == "Bash":
        mode, prog = classify_command(str(inp.get("command") or ""))
        return mode, (inp.get("description") or prog)[:80]
    if name.startswith("mcp__"):
        short = name.split("__")[-1]
        return (READING if MCP_READ_HINT.search(short) else TYPING), short
    return TYPING, name


def classify_codex_tool(name, payload):
    if name in CODEX_TEAM_TOOLS:
        label = {"spawn_agent": "팀원 띄우기", "wait_agent": "팀 기다림", "wait": "팀 기다림", "send_message": "지시 보냄",
                 "followup_task": "추가 지시", "list_agents": "팀 확인", "close_agent": "팀원 닫기"}.get(name, name)
        return TEAM, label
    if name == "apply_patch":
        return TYPING, "파일 수정"
    if name in ("exec", "exec_command", "shell", "local_shell"):
        raw = str(payload.get("input") or payload.get("arguments") or "")
        m = CODEX_CMD.search(raw)
        return classify_command(m.group(1).encode().decode("unicode_escape", "ignore") if m else "")
    if name in ("web_search", "web.run"):
        return READING, "웹 검색"
    return TYPING, name


# ---------- 공급자 파서: 기록 한 줄 → 이벤트 목록 ----------
# 이벤트: (kind, data) — meta · model · title · turn_start · turn_end · tool_start · tool_end · context · tokens · message

def parse_codex_line(d):
    out = []
    if not isinstance(d, dict):
        return out
    typ = d.get("type")
    p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
    ptype = p.get("type")
    if typ == "session_meta":
        src = p.get("source")
        spawn = {}
        if isinstance(src, dict):
            spawn = ((src.get("subagent") or {}).get("thread_spawn") or {}) if isinstance(src.get("subagent"), dict) else {}
        out.append(("meta", {"id": p.get("id"), "parent": p.get("parent_thread_id") or spawn.get("parent_thread_id"),
                             "role": p.get("agent_role") or spawn.get("agent_role"),
                             "nickname": p.get("agent_nickname") or spawn.get("agent_nickname"),
                             "cwd": p.get("cwd"), "source": src if isinstance(src, str) else ("subagent" if spawn else None)}))
    elif typ == "turn_context":
        out.append(("model", {"model": p.get("model"), "effort": p.get("effort")}))
    elif typ == "event_msg" and ptype == "task_started":
        out.append(("turn_start", {}))
    elif typ == "event_msg" and ptype == "task_complete":
        out.append(("turn_end", {"message": p.get("last_agent_message")}))
    elif typ == "event_msg" and ptype == "token_count":
        info = p.get("info") if isinstance(p.get("info"), dict) else {}
        last = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
        total = info.get("total_token_usage") if isinstance(info.get("total_token_usage"), dict) else {}
        if last:
            out.append(("context", {"used": (last.get("input_tokens") or 0) + (last.get("output_tokens") or 0),
                                    "window": info.get("model_context_window")}))
        if total:
            out.append(("tokens", {"total": total.get("total_tokens"), "output": total.get("output_tokens")}))
    elif typ == "response_item" and ptype in ("function_call", "custom_tool_call"):
        mode, label = classify_codex_tool(p.get("name") or "", p)
        out.append(("tool_start", {"id": p.get("call_id") or p.get("id"), "name": p.get("name"), "mode": mode, "label": label}))
    elif typ == "response_item" and ptype in ("function_call_output", "custom_tool_call_output"):
        out.append(("tool_end", {"id": p.get("call_id")}))
    elif typ == "response_item" and ptype == "web_search_call":
        out.append(("tool_start", {"id": p.get("id"), "name": "web_search", "mode": READING, "label": "웹 검색", "instant": True}))
    elif typ == "response_item" and ptype == "message" and p.get("role") == "user":
        for c in p.get("content") or []:
            title = prompt_title((c or {}).get("text") if isinstance(c, dict) else None)
            if title:
                out.append(("title", {"text": title, "weak": True}))
                break
    return out


INJECTED = re.compile(r"^\s*(# AGENTS\.md|<environment_context|<user_instructions|<INSTRUCTIONS|<permissions|<skills_instructions)")


def prompt_title(text):
    """사용자 지시의 첫 줄을 이름으로. Codex 가 앞에 끼워 넣는 지침·환경 블록은 건너뛴다."""
    if not text or INJECTED.match(text):
        return None
    text = re.sub(r"^\s*<[a-z_]+>\s*", "", text)          # <task> 같은 여는 태그는 떼고 본다
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return first[:60] or None


def parse_claude_line(d):
    out = []
    if not isinstance(d, dict) or d.get("isMeta"):
        return out
    typ = d.get("type")
    if typ in ("user", "assistant") and d.get("cwd"):
        out.append(("meta", {"cwd": d["cwd"]}))
    if typ == "ai-title" and d.get("aiTitle"):
        out.append(("title", {"text": d["aiTitle"][:60]}))
    elif typ == "agent-name" and d.get("agentName"):
        out.append(("title", {"text": d["agentName"][:60], "weak": True}))
    elif typ == "assistant":
        m = d.get("message") if isinstance(d.get("message"), dict) else {}
        if m.get("model"):
            out.append(("model", {"model": m.get("model"), "effort": d.get("effort")}))
        u = m.get("usage") if isinstance(m.get("usage"), dict) else {}
        if u:
            used = sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            out.append(("context", {"used": used + (u.get("output_tokens") or 0), "window": None}))
        for c in m.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                mode, label = classify_claude_tool(c.get("name") or "", c.get("input"))
                out.append(("tool_start", {"id": c.get("id"), "name": c.get("name"), "mode": mode, "label": label}))
        if m.get("stop_reason") == "end_turn":
            out.append(("turn_end", {"awaiting_input": True}))
        elif m.get("stop_reason") is None and not any(e[0] == "tool_start" for e in out):
            out.append(("turn_start", {}))
    elif typ == "user":
        m = d.get("message") if isinstance(d.get("message"), dict) else {}
        content = m.get("content")
        if isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    out.append(("tool_end", {"id": c.get("tool_use_id"), "error": bool(c.get("is_error"))}))
        elif content:
            out.append(("turn_start", {}))
    return out


# ---------- 새 줄만 읽기 ----------

class TailReader:
    """JSONL 파일에서 지난번 뒤에 붙은 줄만 읽는다. 처음에는 끝 initial_bytes 만 읽는다(이 세션 기록은 200MB 가 넘는다)."""

    def __init__(self, path, initial_bytes=2_000_000):
        self.path = path
        self.pos = None
        self.inode = None
        self.buf = b""
        self.initial_bytes = initial_bytes

    def read_new(self):
        try:
            st = os.stat(self.path)
        except OSError:
            return []
        if self.inode is not None and (st.st_ino != self.inode or st.st_size < (self.pos or 0)):
            self.pos, self.buf = None, b""            # 파일이 바뀌었다 — 처음부터
        self.inode = st.st_ino
        first = self.pos is None
        start = max(0, st.st_size - self.initial_bytes) if first else self.pos
        if not first and start >= st.st_size:
            return []
        with open(self.path, "rb") as f:
            f.seek(start)
            data = f.read()
            self.pos = f.tell()
        data = self.buf + data
        lines = data.split(b"\n")
        self.buf = lines.pop()                         # 끝이 덜 쓰인 줄은 다음에
        if first and start > 0 and lines:
            lines = lines[1:]                          # 중간부터 읽었으면 첫 줄은 잘린 줄
        out = []
        for raw in lines:
            if not raw.strip():
                continue
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
        return out


def first_json_line(path):
    try:
        with open(path, "rb") as f:
            return json.loads(f.readline())
    except (OSError, ValueError):
        return None


# ---------- 에이전트 상태 ----------

class AgentTrack:
    def __init__(self, agent_id, provider, kind="lead", parent=None, machine="local"):
        self.id = agent_id
        self.provider = provider
        self.kind = kind
        self.parent = parent
        self.machine = machine
        self.role = None
        self.nickname = None
        self.title = None
        self.title_weak = True
        self.cwd = None
        self.source = None
        self.model = None
        self.effort = None
        self.open_tools = {}           # id → {mode, label, started}
        self.last_tool = None
        self.turn = "none"             # none · active · ended
        self.awaiting_input = False
        self.completed = False
        self.errors = 0
        self.context_used = None
        self.context_window = None
        self.tokens_total = None
        self.tokens_output = None
        self.last_message = None
        self.first_ts = None
        self.last_ts = None
        self.status_changed_at = None
        self.last_status = None
        self.blocked = False           # herdr 가 승인·질문 화면이라고 알려 주면 켠다

    def apply(self, events, ts):
        if ts:
            self.first_ts = self.first_ts or ts
            self.last_ts = max(self.last_ts or 0, ts)
        for kind, data in events:
            if kind == "meta":
                self.parent = self.parent or data.get("parent")
                self.role = data.get("role") or self.role
                self.nickname = data.get("nickname") or self.nickname
                self.cwd = data.get("cwd") or self.cwd
                self.source = data.get("source") or self.source
                if self.parent:
                    self.kind = "subagent"
            elif kind == "model":
                self.model = data.get("model") or self.model
                self.effort = data.get("effort") or self.effort
            elif kind == "title":
                if data.get("text") and (self.title is None or (self.title_weak and not data.get("weak"))):
                    self.title, self.title_weak = data["text"], bool(data.get("weak"))
            elif kind == "turn_start":
                self.turn, self.awaiting_input, self.completed = "active", False, False
            elif kind == "turn_end":
                self.turn = "ended"
                self.open_tools.clear()
                self.awaiting_input = bool(data.get("awaiting_input"))
                if data.get("message"):
                    self.last_message = data["message"][:2000]
                if self.provider == "codex" and (self.kind == "subagent" or self.source == "exec"):
                    self.completed = True
            elif kind == "tool_start":
                self.turn, self.completed = "active", False
                self.last_tool = {"mode": data.get("mode"), "label": data.get("label")}
                if not data.get("instant") and data.get("id"):
                    self.open_tools[data["id"]] = {"mode": data.get("mode"), "label": data.get("label"), "started": ts}
            elif kind == "tool_end":
                self.open_tools.pop(data.get("id"), None)
                if data.get("error"):
                    self.errors += 1
            elif kind == "context":
                self.context_used = data.get("used")
                if data.get("window"):
                    self.context_window = data["window"]
            elif kind == "tokens":
                self.tokens_total = data.get("total")
                self.tokens_output = data.get("output")

        event_status, _ = self.status(ts or self.last_ts or 0, float("inf"))
        if event_status != self.last_status:
            self.last_status = event_status
            self.status_changed_at = ts or self.last_ts

    def status(self, now, stall_sec):
        if self.blocked:
            return PERMISSION, "승인·질문 대기"
        if self.completed:
            return DONE, "끝"
        if self.open_tools:
            tools = list(self.open_tools.values())
            pick = next((t for t in tools if t["mode"] == TEAM), None) or \
                next((t for t in tools if t["mode"] == TYPING), None) or tools[-1]
            st, label = pick["mode"], pick["label"]
        elif self.turn == "active":
            st, label = THINKING, "생각 중"
        elif self.turn == "ended":
            return (WAITING, "입력 기다림") if self.awaiting_input else (IDLE, "쉬는 중")
        else:
            return IDLE, "쉬는 중"
        if st in (TYPING, READING, THINKING) and self.last_ts and now - self.last_ts > stall_sec:
            return STALLED, "%d분째 소식 없음" % int((now - self.last_ts) // 60)
        return st, label

    def snapshot(self, now, stall_sec):
        st, activity = self.status(now, stall_sec)
        if st != self.last_status:
            self.status_changed_at = (self.last_ts + stall_sec) if st == STALLED and self.last_ts else now
            self.last_status = st
        window = self.context_window
        if self.provider == "claude" and self.context_used:
            window = CLAUDE_WIDE_WINDOW if self.context_used > CLAUDE_WINDOW else CLAUDE_WINDOW
        ctx = None
        if self.context_used:
            ctx = {"used": self.context_used, "window": window,
                   "pct": round(100.0 * self.context_used / window, 1) if window else None}
        return {
            "id": self.id, "provider": self.provider, "kind": self.kind, "parent": self.parent, "machine": self.machine,
            "role": self.role, "nickname": self.nickname, "title": self.title, "cwd": short_path(self.cwd),
            "model": self.model, "effort": self.effort, "status": st, "statusChangedAt": iso(self.status_changed_at), "activity": activity,
            "context": ctx, "tokens": {"total": self.tokens_total, "output": self.tokens_output} if self.tokens_total else None,
            "lastMessage": self.last_message if self.provider == "codex" else None,
            "startedAt": iso(self.first_ts), "lastEventAt": iso(self.last_ts), "errors": self.errors,
        }


# ---------- 파일 찾기와 묶기 ----------

class Registry:
    """최근에 바뀐 기록 파일을 찾아 AgentTrack 으로 유지한다. 한 번 읽은 파일은 새 줄만 읽는다."""

    def __init__(self, codex_root, claude_root, active_min=60, stall_sec=600):
        self.codex_root = codex_root
        self.claude_root = claude_root
        self.active_sec = active_min * 60
        self.stall_sec = stall_sec
        self.files = {}      # path → (reader, track, provider)

    def _day_dirs(self, now):
        out, d = [], datetime.fromtimestamp(now - self.active_sec - 86400, KST).date()
        today = datetime.fromtimestamp(now, KST).date()
        while d <= today:
            out.append(os.path.join(self.codex_root, "%04d" % d.year, "%02d" % d.month, "%02d" % d.day))
            d += timedelta(days=1)
        return out

    def discover(self, now):
        found = []
        for dd in self._day_dirs(now):
            for f in glob.glob(os.path.join(dd, "rollout-*.jsonl")):
                found.append((f, "codex", None, None))
        for f in glob.glob(os.path.join(self.claude_root, "*", "*.jsonl")):
            found.append((f, "claude", None, None))
            sub = os.path.join(f[:-6], "subagents")
            for sf in glob.glob(os.path.join(sub, "agent-*.jsonl")):
                found.append((sf, "claude", os.path.basename(f)[:-6], sf[:-6] + ".meta.json"))
        out = []
        for path, provider, parent, meta_path in found:
            try:
                if now - os.path.getmtime(path) > self.active_sec and path not in self.files:
                    continue
            except OSError:
                continue
            out.append((path, provider, parent, meta_path))
        return out

    def _new_track(self, path, provider, parent, meta_path):
        if provider == "codex":
            first = first_json_line(path) or {}
            agent_id = ((first.get("payload") or {}).get("id")) or os.path.basename(path)
            track = AgentTrack(agent_id, "codex")
            track.apply(parse_codex_line(first), ts_of(first.get("timestamp")))   # 머리 줄은 늘 읽는다(부모·역할)
            return track
        agent_id = os.path.basename(path)[:-6]
        track = AgentTrack(agent_id, "claude", kind="subagent" if parent else "lead", parent=parent)
        if parent:
            meta = {}
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                pass
            track.role = meta.get("agentType")
            track.title, track.title_weak = (meta.get("description") or "")[:60] or None, False
            track.completed = bool(meta.get("finished"))
        return track

    def refresh(self, now=None):
        now = now or time.time()
        for path, provider, parent, meta_path in self.discover(now):
            if path not in self.files:
                self.files[path] = (TailReader(path), self._new_track(path, provider, parent, meta_path), provider)
            reader, track, prov = self.files[path]
            parse = parse_codex_line if prov == "codex" else parse_claude_line
            for d in reader.read_new():
                track.apply(parse(d), ts_of(d.get("timestamp")) if isinstance(d, dict) else None)
            if prov == "claude" and track.kind == "subagent" and meta_path:
                try:
                    with open(meta_path, encoding="utf-8") as f:
                        if json.load(f).get("finished"):
                            track.completed = True
                except (OSError, ValueError):
                    pass
            if track.last_ts is None:
                try:
                    track.last_ts = os.path.getmtime(path)
                except OSError:
                    pass
        # 오래 조용한 파일은 잊는다(다시 바뀌면 처음부터 읽는다)
        for path in [p for p, (_, t, _) in self.files.items() if t.last_ts and now - t.last_ts > self.active_sec * 3]:
            del self.files[path]

    def tracks(self):
        return [t for _, t, _ in self.files.values()]


def build_office(registry, now, sessions=None, runs=None, local_label="이 맥", active_min=60, hide_re=None):
    """화면용 사무실 데이터. 방(기기) → 팀(리더와 하위 에이전트).
    hide_re 에 맞는 이름의 혼자인 리더(자동 리뷰 같은 것)는 그리지 않고 개수만 센다."""
    tracks = registry.tracks()
    by_id = {t.id: t for t in tracks}
    sessions = sessions or {}
    local_panes = [a for a in (sessions.get("local") or []) if isinstance(a, dict)]

    # herdr 의 승인·질문(blocked) 표시를 같은 폴더의 가장 최근 세션에 옮긴다
    for t in tracks:
        t.blocked = False
    for pane in local_panes:
        if pane.get("status") == "blocked":
            cands = [t for t in tracks if t.kind == "lead" and t.provider == pane.get("agent") and t.cwd and pane.get("cwd")
                     and t.cwd.rstrip("/") == pane["cwd"].rstrip("/")]
            if cands:
                max(cands, key=lambda t: t.last_ts or 0).blocked = True

    run_names = {}
    for r in runs or []:
        if isinstance(r, dict) and r.get("thread_id"):
            run_names[r["thread_id"]] = "%s (%s)" % ((r.get("name") or "").split("-", 2)[-1], (r.get("meta") or {}).get("mode") or "")

    snaps = {t.id: t.snapshot(now, registry.stall_sec) for t in tracks}
    for tid, label in run_names.items():
        if tid in snaps:
            snaps[tid]["title"] = "실행: " + label

    cutoff = now - active_min * 60
    teams, hidden = [], 0
    for t in tracks:
        if t.kind == "subagent" and t.parent in by_id:
            continue
        members = [x for x in tracks if x.parent == t.id]
        grand = [y for m in members for y in tracks if y.parent == m.id]
        if (t.last_ts or 0) < cutoff and not any((m.last_ts or 0) >= cutoff for m in members + grand):
            continue
        lead = snaps[t.id]
        if hide_re is not None and not members and hide_re.search(lead.get("title") or ""):
            hidden += 1
            continue
        teams.append({"id": t.id, "provider": t.provider, "label": lead.get("title") or lead.get("cwd") or t.id[:8],
                      "lead": lead,
                      "members": sorted([snaps[m.id] for m in members + grand], key=lambda s: s.get("startedAt") or "")})
    teams.sort(key=lambda x: (0 if x["provider"] == "claude" else 1, x["lead"].get("startedAt") or ""))
    rooms = [{"id": "local", "label": local_label, "teams": teams, "hidden": hidden, "error": None}]

    for label, agents in (sessions.get("remote") or {}).items():
        room = {"id": "remote:" + label, "label": label, "teams": [], "hidden": 0, "error": None}
        if isinstance(agents, dict):
            room["error"] = agents.get("error")
        else:
            for a in agents:
                st = {"working": TYPING, "idle": IDLE, "done": DONE, "blocked": PERMISSION}.get(a.get("status"), IDLE)
                aid = "%s:%s" % (label, a.get("pane"))
                lead = {"id": aid, "provider": a.get("agent"), "kind": "lead", "parent": None, "machine": label,
                        "role": None, "nickname": a.get("name"), "title": a.get("title"), "cwd": short_path(a.get("cwd")),
                        "model": None, "effort": None, "status": st, "activity": a.get("status"), "context": None,
                        "tokens": None, "lastMessage": None, "startedAt": None, "lastEventAt": None, "errors": 0}
                room["teams"].append({"id": aid, "provider": a.get("agent"), "label": a.get("title") or aid, "lead": lead, "members": []})
        rooms.append(room)

    counts = {}
    for room in rooms:
        for team in room["teams"]:
            for a in [team["lead"]] + team["members"]:
                counts[a["status"]] = counts.get(a["status"], 0) + 1
    return {"rooms": rooms, "counts": counts, "generatedAt": iso(now), "stallSec": registry.stall_sec}
