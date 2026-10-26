#!/usr/bin/env python3
"""에이전트 팀 보드 — Claude Code 총괄과 Codex 매니저·하위 에이전트를 한 화면에서 본다 (로컬 웹).

보는 것 다섯 가지. 수집기마다 따로 돌고, 하나가 막히거나 실패해도 나머지는 마지막 성공값으로 그린다.
- 세션: `herdr api snapshot` (이 맥) + `herdr --machine <이름> agent list` (원격 맥, --machines)
- 팀 실행: run_team.py 가 남긴 runs/<이름>.meta.json·.jsonl·.last.md
- 팀 트리: Codex 세션 기록 ~/.codex/sessions/**/rollout-*.jsonl. `codex exec --json` 이벤트에는 하위 에이전트를
  띄운 사실이 나오지 않아서(2026-10-23, 0.163 확인), 매니저 스레드를 부모로 둔 기록 파일을 찾아 잇는다
- 그 밖의 Codex 스레드: `codex app-server`(stdio) thread/list — sourceKinds 를 다 적어야 exec·하위 에이전트까지 온다
- 공유 작업 기록: LLM Wiki raw/*.md 의 frontmatter(task_id·status·title) 최근 N시간

- 사무실: office.py 가 Codex 세션 기록과 Claude Code 대화 기록을 같은 이벤트로 읽어 캐릭터 상태를 만든다(1초마다)

화면은 web/(React·Vite·TypeScript) 빌드 결과(web/dist)를 그대로 내보낸다. 데이터는 /api/state 와 SSE(/events)로 준다.
데이터 길은 토큰이 있어야 열린다(?t= 또는 X-Board-Token). 토큰은 ~/.omj/agent-team/board.token(0600)에 둔다.
보드는 토큰 파일 말고는 파일을 쓰지 않는다. 다만 `codex app-server` 를 띄우므로 Codex 쪽 상태 DB 는 Codex 가 스스로 갱신할 수 있다.
기본은 127.0.0.1 에만 묶는다. 다른 주소는 --allow-remote 를 줘야 한다.
표준 라이브러리만 쓴다. Python 3.9 에서 돈다.
"""
import argparse
import glob
import hmac
import ipaddress
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import office  # noqa: E402  같은 폴더의 사무실 데이터 모듈

SOURCE_KINDS = ["cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview", "subAgentCompact",
                "subAgentThreadSpawn", "subAgentOther", "unknown"]
DEFAULT_WIKI = "~/Documents/Obsidian Vault/LLM Wiki"
DEFAULT_RUNS = "~/.omj/agent-team/runs"
DEFAULT_SESSIONS = "~/.codex/sessions"
DEFAULT_CLAUDE = "~/.claude/projects"
DEFAULT_TOKEN_FILE = "~/.omj/agent-team/board.token"
KST = timezone(timedelta(hours=9))


def now_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def run_cmd(args, timeout=10):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def to_ts(v):
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e12 else v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def iso_ts(v):
    """app-server 는 시각을 초 단위 숫자로도 준다. 화면에는 늘 ISO 문자열로 보낸다."""
    ts = to_ts(v)
    return datetime.fromtimestamp(ts, KST).isoformat(timespec="seconds") if ts else None


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def as_dict(v):
    return v if isinstance(v, dict) else {}


def as_list(v):
    return v if isinstance(v, list) else []


# ---------- 세션 (herdr) ----------

def collect_herdr(machines, local_label):
    """machines: [(herdr 머신 이름, 화면 이름)]. 화면에는 화면 이름을 쓴다."""
    out = {"local": [], "local_label": local_label, "remote": {}, "error": None}
    code, so, se = run_cmd(["herdr", "api", "snapshot"], timeout=10)
    if code == 0:
        try:
            snap = as_dict(as_dict(json.loads(so).get("result")).get("snapshot"))
            out["local"] = [pick_agent(a) for a in as_list(snap.get("agents")) if isinstance(a, dict)]
        except ValueError as e:
            out["error"] = "snapshot 파싱 실패: %s" % e
    else:
        out["error"] = (se or so).strip()[:200] or "herdr 없음"
    for m, label in machines:
        code, so, se = run_cmd(["herdr", "--machine", m, "agent", "list"], timeout=20)
        if code == 0:
            try:
                agents = as_list(as_dict(json.loads(so).get("result")).get("agents"))
                out["remote"][label] = [pick_agent(a) for a in agents if isinstance(a, dict)]
            except ValueError as e:
                out["remote"][label] = {"error": "파싱 실패: %s" % e}
        else:
            out["remote"][label] = {"error": (se or so).strip()[:200] or "연결 실패"}
    return out


def pick_agent(a):
    return {
        "agent": a.get("agent"),
        "status": a.get("agent_status"),
        "pane": a.get("pane_id"),
        "name": a.get("name"),
        "title": a.get("terminal_title_stripped") or a.get("terminal_title"),
        "cwd": a.get("cwd"),
    }


def parse_machines(text):
    """'herdr 이름=화면 이름, …' — 화면 이름을 안 쓰면 herdr 이름을 그대로 쓴다."""
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, label = part.partition("=")
        out.append((name.strip(), label.strip() or name.strip()))
    return out


# ---------- 그 밖의 Codex 스레드 (app-server stdio) ----------

class CodexThreads:
    """`codex app-server` 를 하나 띄워 두고 thread/list 만 묻는다.
    응답은 읽기 전용 스레드가 큐에 넣는다 — select 뒤 readline 으로 읽으면 제한 시간을 넘겨 막힐 수 있다."""

    def __init__(self):
        self.proc = None
        self.q = None
        self.next_id = 1

    def _start(self):
        self.proc = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.q = queue.Queue()
        threading.Thread(target=self._reader, args=(self.proc, self.q), daemon=True).start()
        res = self._request("initialize", {"clientInfo": {"name": "agent-team-board", "version": "0.2.0"}})
        if not isinstance(res, dict) or "result" not in res:
            raise RuntimeError("initialize 실패")
        self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    @staticmethod
    def _reader(proc, q):
        try:
            for line in proc.stdout:
                q.put(line)
        finally:
            q.put(None)

    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _request(self, method, params, timeout=15):
        rid = self.next_id
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                line = self.q.get(timeout=remaining)
            except queue.Empty:
                return None
            if line is None:
                return None
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("id") == rid:
                return msg

    def _close(self):
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.terminate()
            except OSError:
                pass
        self.proc = None

    def list(self, limit=100, pages=3):
        try:
            if self.proc is None or self.proc.poll() is not None:
                self._close()
                self._start()
            threads, cursor = [], None
            for _ in range(pages):
                params = {"limit": limit, "sourceKinds": SOURCE_KINDS}
                if cursor:
                    params["cursor"] = cursor
                res = self._request("thread/list", params)
                if res is None:
                    self._close()
                    raise RuntimeError("thread/list 응답 없음")
                if "error" in res:
                    raise RuntimeError(str(res["error"])[:200])
                result = as_dict(res.get("result"))
                threads += [pick_thread(t) for t in as_list(result.get("data") or result.get("threads")) if isinstance(t, dict)]
                cursor = result.get("nextCursor")
                if not cursor:
                    break
            return threads
        except (OSError, ValueError) as e:
            self._close()
            raise RuntimeError("codex app-server: %s" % e)


def pick_thread(t):
    status = t.get("status")
    if isinstance(status, dict):
        status = status.get("type") or json.dumps(status)[:40]
    src = t.get("source")
    kind, spawn = None, {}
    if isinstance(src, dict):
        inner = as_dict(src.get("subAgent")) or src
        if isinstance(inner.get("thread_spawn"), dict):
            kind, spawn = "spawn", inner["thread_spawn"]
        else:
            kind = next(iter(src.keys()), None)
    elif isinstance(src, str):
        kind = src
    return {
        "id": t.get("id"),
        "name": t.get("name") or (t.get("preview") or "")[:80],
        "preview": (t.get("preview") or "")[:160],
        "parent": t.get("parentThreadId") or spawn.get("parent_thread_id"),
        "role": t.get("agentRole") or spawn.get("agent_role"),
        "nickname": t.get("agentNickname") or spawn.get("agent_nickname"),
        "status": status,
        "model": t.get("model"),
        "effort": t.get("reasoningEffort"),
        "cwd": t.get("cwd"),
        "source": kind,
        "updatedAt": iso_ts(t.get("updatedAt")),
        "createdAt": iso_ts(t.get("createdAt")),
    }


def build_tree(threads, hours, hide_re=None, exclude_ids=()):
    """최근 N시간 안에 바뀐 루트와, 부모가 있는 스레드는 시간과 무관하게 넣는다.
    hide_re 에 맞는 이름의 루트(자식 없음)는 개수만 센다. exclude_ids 는 팀 실행 칸에 이미 그린 스레드."""
    cutoff = time.time() - hours * 3600
    by_id = {t["id"]: dict(t, children=[]) for t in threads if t.get("id") and t["id"] not in exclude_ids}
    roots = []
    for t in by_id.values():
        p = t.get("parent")
        if p and p in by_id:
            by_id[p]["children"].append(t)
        elif p:
            continue                   # 부모가 팀 실행 칸에 있거나 목록 밖 — 여기서는 빼다
        elif to_ts(t.get("updatedAt")) >= cutoff:
            roots.append(t)
    for t in by_id.values():
        if not t.get("parent") and t["children"] and t not in roots:
            roots.append(t)
    hidden = 0
    if hide_re is not None:
        kept = []
        for t in roots:
            if not t["children"] and hide_re.search(t.get("name") or ""):
                hidden += 1
            else:
                kept.append(t)
        roots = kept
    roots.sort(key=lambda x: to_ts(x.get("updatedAt")), reverse=True)
    for t in by_id.values():
        t["children"].sort(key=lambda x: to_ts(x.get("createdAt")))
    return roots, hidden


# ---------- Codex 세션 기록 (rollout) ----------

class Rollouts:
    """~/.codex/sessions 의 rollout 파일을 읽어 스레드별 요약을 만든다. 파일 크기·수정 시각이 같으면 다시 읽지 않는다."""

    def __init__(self, root):
        self.root = root
        self.cache = {}          # path → (size, mtime, summary)
        self.meta_cache = {}     # path → (size, session_meta 요약)  첫 줄만

    def day_dirs(self, since_ts):
        out, d = [], datetime.fromtimestamp(since_ts, KST).date()
        today = datetime.now(KST).date()
        while d <= today:
            out.append(os.path.join(self.root, "%04d" % d.year, "%02d" % d.month, "%02d" % d.day))
            d += timedelta(days=1)
        return out

    def files_since(self, since_ts):
        files = []
        for dd in self.day_dirs(since_ts - 86400):   # 시간대 차이로 하루 앞도 본다
            for f in glob.glob(os.path.join(dd, "rollout-*.jsonl")):
                try:
                    if os.path.getmtime(f) >= since_ts - 120:
                        files.append(f)
                except OSError:
                    continue
        return files

    def session_meta(self, path):
        try:
            size = os.path.getsize(path)
        except OSError:
            return None
        hit = self.meta_cache.get(path)
        if hit and hit[0] == size:
            return hit[1]
        meta = None
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                first = json.loads(f.readline())
            p = as_dict(first.get("payload"))
            spawn = as_dict(as_dict(as_dict(p.get("source")).get("subagent")).get("thread_spawn"))
            meta = {"id": p.get("id"), "parent": p.get("parent_thread_id") or spawn.get("parent_thread_id"),
                    "role": p.get("agent_role") or spawn.get("agent_role"),
                    "nickname": p.get("agent_nickname") or spawn.get("agent_nickname"),
                    "path": p.get("agent_path") or spawn.get("agent_path"), "cwd": p.get("cwd")}
        except (OSError, ValueError):
            meta = None
        self.meta_cache[path] = (size, meta)
        return meta

    def summarize(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return None
        hit = self.cache.get(path)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime:
            return hit[2]
        models, efforts, tools = [], [], Counter()
        tokens, last_msg, started, updated = None, None, None, None
        state = "unknown"
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                ts = d.get("timestamp")
                started = started or ts
                updated = ts or updated
                p = as_dict(d.get("payload"))
                typ, ptype = d.get("type"), p.get("type")
                if typ == "turn_context":
                    if p.get("model") and p["model"] not in models:
                        models.append(p["model"])
                    e = p.get("effort") or as_dict(p.get("reasoning")).get("effort")
                    if e and e not in efforts:
                        efforts.append(e)
                elif typ == "event_msg" and ptype == "task_started":
                    state = "running"
                elif typ == "event_msg" and ptype == "task_complete":
                    state = "completed"
                    last_msg = p.get("last_agent_message") or last_msg
                elif typ == "event_msg" and ptype == "token_count":
                    tokens = as_dict(as_dict(p.get("info")).get("total_token_usage")) or tokens
                elif typ == "response_item" and ptype in ("function_call", "custom_tool_call"):
                    tools[p.get("name") or "?"] += 1
        s = {"models": models, "efforts": efforts, "tools": dict(tools), "tool_calls": sum(tools.values()),
             "tokens": tokens, "last_message": (last_msg or "")[:2000], "started": iso_ts(started),
             "updated": iso_ts(updated), "state": state}
        self.cache[path] = (st.st_size, st.st_mtime, s)
        return s

    def team(self, thread_id, since_ts):
        """매니저 스레드와 그 아래(손자까지) 하위 에이전트 요약."""
        files = self.files_since(since_ts)
        metas = {}
        for f in files:
            m = self.session_meta(f)
            if m and m.get("id"):
                metas[m["id"]] = (f, m)
        if thread_id not in metas:
            return None

        def node(tid, depth):
            f, m = metas[tid]
            s = dict(self.summarize(f) or {})
            s.update({k: m.get(k) for k in ("id", "role", "nickname", "path")})
            s["children"] = [node(cid, depth + 1) for cid, (_, cm) in sorted(metas.items(), key=lambda kv: kv[1][0])
                             if cm.get("parent") == tid] if depth < 4 else []
            return s

        return node(thread_id, 0)


def team_totals(node):
    tot = Counter()
    if not node:
        return {}
    stack = [node]
    while stack:
        n = stack.pop()
        for k, v in as_dict(n.get("tokens")).items():
            if isinstance(v, (int, float)):
                tot[k] += v
        stack.extend(n.get("children") or [])
    return dict(tot)


# ---------- 팀 실행 (run_team.py 기록) ----------

def collect_runs(runs_dir, rollouts, limit=20):
    runs, team_ids = [], set()
    if not os.path.isdir(runs_dir):
        return runs, team_ids
    names = sorted((f[:-10] for f in os.listdir(runs_dir) if f.endswith(".meta.json")), reverse=True)[:limit]
    for name in names:
        base = os.path.join(runs_dir, name)
        try:
            meta = read_json(base + ".meta.json") or {}
            r = summarize_events(base + ".jsonl")
            r["name"] = name
            r["meta"] = {k: meta.get(k) for k in ("mode", "model", "effort", "cwd", "write", "task", "started",
                                                  "finished", "exit_code", "error", "timed_out", "pid")}
            last_text = read_text(base + ".last.md") or ""
            first_line = next((line.strip() for line in last_text.splitlines() if line.strip()), "")
            first_line = re.sub(r"^\s*(?:[#>*+\-]+|\d+[.)])\s*", "", first_line)
            first_line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", first_line)
            r["resultHead"] = re.sub(r"[*_`~]", "", first_line).strip()[:200]
            r["final"] = (last_text or r.get("final") or "")[:4000]
            r["state"] = run_state(meta, r)
            r["elapsed_sec"] = elapsed(meta.get("started"), meta.get("finished") or (r.get("updated") if r["state"] != "running" else None))
            team = None
            if r.get("thread_id"):
                team = rollouts.team(r["thread_id"], to_ts(meta.get("started")) or time.time() - 86400)
            r["team"] = team
            r["team_tokens"] = team_totals(team)
            r["members"] = count_members(team)
            if team:
                stack = [team]
                while stack:
                    n = stack.pop()
                    team_ids.add(n.get("id"))
                    stack.extend(n.get("children") or [])
        except Exception as e:     # 실행 하나가 깨져도 나머지는 그린다
            r = {"name": name, "state": "error", "collect_error": "%s: %s" % (type(e).__name__, e), "meta": {}}
        runs.append(r)
    return runs, team_ids


def count_members(node):
    if not node:
        return 0
    return sum(1 + count_members(c) for c in node.get("children") or [])


def elapsed(start, end):
    s = to_ts(start)
    e = to_ts(end) if end else time.time()
    return int(e - s) if s and e >= s else None


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def run_state(meta, r):
    """종료 코드가 있으면 그것이 기준. 없으면 프로세스 생존, 그다음 이벤트로 본다."""
    if meta.get("exit_code") is not None:
        return "done" if meta["exit_code"] == 0 else "error"
    if meta.get("error"):
        return "error"
    if pid_alive(meta.get("pid")):
        return "running"
    if meta.get("pid"):
        return "stale"           # 감시 프로세스가 끝났는데 결과가 안 남았다
    # 이 판 이전 기록(pid 없음) — 이벤트로 판단
    if r.get("last_terminal") == "completed":
        return "done"
    if r.get("last_terminal") == "failed":
        return "error"
    if r.get("events") and time.time() - to_ts(r.get("updated")) < 120:
        return "running"
    return "stale" if r.get("events") else "unknown"


# 지원하는 `codex exec --json` 이벤트 (0.163 확인): thread.started · turn.started · turn.completed · turn.failed ·
# item.started/updated/completed(item.type: agent_message · command_execution · reasoning · web_search · collab_tool_call …) · error
TERMINAL_OK = ("turn.completed",)
TERMINAL_FAIL = ("turn.failed", "error")


def summarize_events(path):
    events, kinds, unknown = 0, Counter(), Counter()
    tokens, final, thread_id, last_terminal = None, None, None, None
    try:
        f = open(path, encoding="utf-8", errors="replace")
        mtime = os.path.getmtime(path)
    except OSError:
        return {"events": 0, "kinds": {}, "unknown": {}, "updated": None}
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            events += 1
            etype = str(ev.get("type") or "?")
            item = as_dict(ev.get("item"))
            itype = str(item.get("type") or "")
            kinds[etype + (":" + itype if itype else "")] += 1
            if not (etype.startswith(("thread.", "turn.", "item.")) or etype == "error"):
                unknown[etype] += 1
            thread_id = thread_id or ev.get("thread_id")
            if isinstance(ev.get("usage"), dict):
                tokens = ev["usage"]
            if itype == "agent_message" and item.get("text"):
                final = item["text"]
            if etype in TERMINAL_OK:
                last_terminal = "completed"
            elif etype in TERMINAL_FAIL:
                last_terminal = "failed"
    return {"events": events, "kinds": dict(kinds), "unknown": dict(unknown), "tokens": tokens, "final": final,
            "thread_id": thread_id, "last_terminal": last_terminal,
            "updated": datetime.fromtimestamp(mtime, KST).isoformat(timespec="seconds")}


# ---------- 공유 작업 기록 (LLM Wiki raw) ----------

FM_KEY = re.compile(r'^([A-Za-z_]+):\s*"?(.*?)"?\s*$')


def collect_wiki(raw_dir, hours=48, limit=40):
    if not os.path.isdir(raw_dir):
        raise RuntimeError("raw 폴더 없음: %s" % raw_dir)
    cutoff = time.time() - hours * 3600
    rows = []
    for f in os.listdir(raw_dir):
        if not f.endswith(".md"):
            continue
        p = os.path.join(raw_dir, f)
        try:
            if os.path.getmtime(p) < cutoff:
                continue
            with open(p, encoding="utf-8", errors="replace") as fh:
                head = fh.read(4000)
        except OSError:
            continue
        fm = parse_frontmatter(head)
        if not fm.get("task_id"):
            continue
        rows.append({"file": f, "task_id": fm.get("task_id"), "status": fm.get("status"),
                     "title": fm.get("title", "")[:140], "author": fm.get("author"), "machine": fm.get("machine")})
    rows.sort(key=lambda r: r["file"], reverse=True)
    tasks = {}
    for r in rows:
        t = tasks.setdefault(r["task_id"], {"task_id": r["task_id"], "latest": r, "count": 0, "authors": set()})
        t["count"] += 1
        if r["author"]:
            t["authors"].add(r["author"])
    out = []
    for t in tasks.values():
        t["authors"] = sorted(t["authors"])
        out.append(t)
    out.sort(key=lambda t: t["latest"]["file"], reverse=True)
    return out[:limit]


def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        m = FM_KEY.match(line)
        if m:
            fm[m.group(1)] = m.group(2)
    return fm


# ---------- 수집기 ----------


class State:
    """수집기마다 스레드 하나. 실패하면 마지막 성공값을 두고 오류만 적는다."""

    def __init__(self, args):
        self.args = args
        self.codex = CodexThreads()
        self.rollouts = Rollouts(args.sessions)
        self.registry = office.Registry(args.sessions, args.claude, active_min=args.office_min, stall_sec=args.stall_sec)
        self.lock = threading.Lock()
        self.slots = {}      # 이름 → {"value", "at", "error"}
        self.team_ids = set()

    def put(self, name, value=None, error=None):
        with self.lock:
            slot = self.slots.setdefault(name, {"value": None, "at": None, "error": None})
            if error is None:
                slot.update(value=value, at=now_iso(), error=None)
            else:
                slot["error"] = error

    def value(self, name):
        with self.lock:
            return (self.slots.get(name) or {}).get("value")

    def loop(self, name, fn, every):
        while True:
            try:
                self.put(name, fn())
            except Exception as e:
                self.put(name, error="%s: %s" % (type(e).__name__, e))
            time.sleep(every)

    def collect_runs(self):
        runs, ids = collect_runs(self.args.runs, self.rollouts)
        with self.lock:
            self.team_ids = ids
        return runs

    def collect_threads(self):
        threads = self.codex.list(limit=self.args.thread_limit)
        with self.lock:
            ids = set(self.team_ids)
        tree, hidden = build_tree(threads, self.args.hours, self.args.hide_re, ids)
        return {"tree": tree, "hidden": hidden, "total": len(threads)}

    def collect_office(self):
        self.registry.refresh()
        return office.build_office(self.registry, time.time(), sessions=self.value("sessions"), runs=self.value("runs"),
                                   local_label=self.args.local_label, active_min=self.args.office_min,
                                   hide_re=self.args.hide_re)

    def start(self):
        r = self.args.refresh
        for name, fn, every in (("office", self.collect_office, 1),
                                ("runs", self.collect_runs, r), ("threads", self.collect_threads, r * 2),
                                ("sessions", lambda: collect_herdr(self.args.machines, self.args.local_label), r * 2),
                                ("wiki", lambda: collect_wiki(os.path.join(self.args.wiki, "raw"), hours=self.args.hours), r * 3)):
            threading.Thread(target=self.loop, args=(name, fn, every), daemon=True).start()

    def payload(self):
        """시각을 뺀 상태. SSE 는 이것이 바뀔 때만 보낸다."""
        with self.lock:
            data = {"refreshSec": self.args.refresh,
                    "slots": {k: {"at": v["at"], "error": v["error"]} for k, v in self.slots.items()}}
            for k, v in self.slots.items():
                data[k] = v["value"]
        for slot in data["slots"].values():
            slot.pop("at", None)
        return data

    def snapshot(self):
        data = self.payload()
        data["generatedAt"] = now_iso()
        return json.dumps(data, ensure_ascii=False)


# ---------- HTTP ----------

FALLBACK_PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8"><title>에이전트 팀 보드</title>
<body style="font:14px -apple-system,sans-serif;padding:24px">
<h1 style="font-size:16px">화면 빌드가 아직 없습니다</h1>
<p>보드 서버는 돌고 있습니다. 화면을 만들려면:</p>
<pre>cd agent-team/web &amp;&amp; npm ci &amp;&amp; npm run build</pre>
<p>데이터는 <code>/api/state?t=&lt;토큰&gt;</code> 에서 볼 수 있습니다.</p></body></html>"""

CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json",
                 ".woff2": "font/woff2", ".map": "application/json"}


def load_token(path, given=None):
    """토큰: --token 이 있으면 그것, 없으면 파일(0600)에서 읽고, 파일도 없으면 새로 만든다."""
    if given:
        return given
    try:
        with open(path, encoding="utf-8") as f:
            tok = f.read().strip()
        if tok:
            return tok
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tok = secrets.token_urlsafe(18)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(tok + "\n")
    return tok


def static_path(dist, url_path):
    """빌드 폴더 안의 파일만 돌려준다(경로 밖으로 나가는 요청은 None)."""
    rel = url_path.lstrip("/") or "index.html"
    full = os.path.realpath(os.path.join(dist, rel))
    root = os.path.realpath(dist)
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
        return None
    return full


def make_handler(state, token, dist):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self, query):
            got = (parse_qs(query).get("t") or [""])[0] or self.headers.get("X-Board-Token", "")
            return hmac.compare_digest(got.encode(), token.encode())

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/") or path == "/events":
                if not self._authorized(parsed.query):
                    return self._send(401, b'{"error":"token required"}', "application/json; charset=utf-8")
                if path == "/api/state":
                    return self._send(200, state.snapshot().encode("utf-8"), "application/json; charset=utf-8")
                if path == "/events":
                    return self._stream()
                return self._send(404, b'{"error":"not found"}', "application/json; charset=utf-8")
            full = static_path(dist, "index.html" if path in ("/", "/index.html") else path)
            if full is None:
                if path in ("/", "/index.html"):
                    return self._send(200, FALLBACK_PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            with open(full, "rb") as f:
                body = f.read()
            ctype = CONTENT_TYPES.get(os.path.splitext(full)[1], "application/octet-stream")
            self._send(200, body, ctype)

        def _stream(self):
            """SSE: 상태가 바뀔 때만 보낸다. 15초마다 주석 한 줄로 연결을 확인한다."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last, last_beat = None, time.monotonic()
            try:
                while True:
                    body = json.dumps(state.payload(), ensure_ascii=False, sort_keys=True)
                    if body != last:
                        self.wfile.write(("event: state\ndata: %s\n\n" % state.snapshot()).encode("utf-8"))
                        self.wfile.flush()
                        last, last_beat = body, time.monotonic()
                    elif time.monotonic() - last_beat > 15:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        last_beat = time.monotonic()
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def log_message(self, fmt, *args):  # 요청 로그는 조용히
            return

    return Handler


def is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main():
    ap = argparse.ArgumentParser(description="에이전트 팀 보드 (로컬 웹)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--allow-remote", action="store_true", help="127.0.0.1 밖에 묶는 것을 허용한다(토큰만으로 막는다)")
    ap.add_argument("--refresh", type=int, default=3, help="수집 주기(초, 1 이상). 사무실은 1초마다")
    ap.add_argument("--hours", type=int, default=24, help="목록에 보여 줄 최근 범위(시간)")
    ap.add_argument("--office-min", type=int, default=60, help="사무실에 앉힐 범위 — 최근 N분 안에 움직인 세션")
    ap.add_argument("--stall-sec", type=int, default=600, help="일하는 중인데 이 초 동안 소식이 없으면 「멈춤 의심」")
    ap.add_argument("--wiki", default=os.environ.get("AGENT_BOARD_WIKI", DEFAULT_WIKI))
    ap.add_argument("--runs", default=os.environ.get("AGENT_BOARD_RUNS", DEFAULT_RUNS))
    ap.add_argument("--sessions", default=os.environ.get("AGENT_BOARD_SESSIONS", DEFAULT_SESSIONS), help="Codex 세션 기록 폴더")
    ap.add_argument("--claude", default=os.environ.get("AGENT_BOARD_CLAUDE", DEFAULT_CLAUDE), help="Claude Code 대화 기록 폴더")
    ap.add_argument("--machines", default=os.environ.get("AGENT_BOARD_MACHINES", ""),
                    help="herdr 원격 머신. 'herdr 이름=화면 이름' 을 쉼표로 (화면 이름은 생략 가능)")
    ap.add_argument("--local-label", default=os.environ.get("AGENT_BOARD_LOCAL_LABEL", "이 맥"), help="이 맥의 화면 이름")
    ap.add_argument("--thread-limit", type=int, default=100)
    ap.add_argument("--hide-pattern", default=r"^(Codex Companion Task|Run a stop-gate review)",
                    help="혼자인 세션 중 이름이 맞으면 개수만 센다(정규식). 빈 문자열이면 모두 보여 준다")
    ap.add_argument("--token-file", default=os.environ.get("AGENT_BOARD_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    ap.add_argument("--token", default=os.environ.get("AGENT_BOARD_TOKEN"), help="토큰을 직접 준다(파일보다 우선)")
    ap.add_argument("--web-dist", default=os.path.join(HERE, "web", "dist"), help="React 빌드 결과 폴더")
    args = ap.parse_args()
    if args.refresh < 1:
        ap.error("--refresh 는 1 이상이어야 한다")
    if not is_loopback(args.host) and not args.allow_remote:
        ap.error("--host %s 는 루프백이 아니다. 화면에 작업 내용이 보이므로 --allow-remote 를 함께 줘야 한다" % args.host)
    args.hide_re = re.compile(args.hide_pattern) if args.hide_pattern else None
    for k in ("wiki", "runs", "sessions", "claude", "token_file", "web_dist"):
        setattr(args, k, os.path.abspath(os.path.expanduser(getattr(args, k))))
    args.machines = parse_machines(args.machines)
    token = load_token(args.token_file, args.token)

    state = State(args)
    state.start()
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(state, token, args.web_dist))
    srv.daemon_threads = True
    print("에이전트 팀 보드: http://%s:%d/?t=%s" % (args.host, srv.server_address[1], token), flush=True)
    print("  토큰 파일 %s · 화면 %s%s · 이 맥 %s · 원격 %s" % (
        args.token_file, args.web_dist, "" if os.path.isdir(args.web_dist) else " (빌드 없음)", args.local_label,
        ", ".join("%s(%s)" % (l, n) for n, l in args.machines) or "없음"), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
