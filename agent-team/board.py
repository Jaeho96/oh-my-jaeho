#!/usr/bin/env python3
"""에이전트 팀 보드 — Claude Code 총괄과 Codex 매니저·하위 에이전트를 한 화면에서 본다 (로컬 웹).

보는 것 다섯 가지. 수집기마다 따로 돌고, 하나가 막히거나 실패해도 나머지는 마지막 성공값으로 그린다.
- 세션: `herdr api snapshot` (이 맥) + `herdr --machine <이름> agent list` (원격 맥, --machines)
- 팀 실행: run_team.py 가 남긴 runs/<이름>.meta.json·.jsonl·.last.md
- 팀 트리: Codex 세션 기록 ~/.codex/sessions/**/rollout-*.jsonl. `codex exec --json` 이벤트에는 하위 에이전트를
  띄운 사실이 나오지 않아서(2026-10-23, 0.163 확인), 매니저 스레드를 부모로 둔 기록 파일을 찾아 잇는다
- 그 밖의 Codex 스레드: `codex app-server`(stdio) thread/list — sourceKinds 를 다 적어야 exec·하위 에이전트까지 온다
- 공유 작업 기록: LLM Wiki raw/*.md 의 frontmatter(task_id·status·title) 최근 N시간

보드는 파일을 쓰지 않는다. 다만 `codex app-server` 를 띄우므로 Codex 쪽 상태 DB 는 Codex 가 스스로 갱신할 수 있다.
기본은 127.0.0.1 에만 묶는다. 다른 주소는 --allow-remote 를 줘야 한다(인증이 없다).
표준 라이브러리만 쓴다. Python 3.9 에서 돈다.
"""
import argparse
import glob
import ipaddress
import json
import os
import queue
import re
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOURCE_KINDS = ["cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview", "subAgentCompact",
                "subAgentThreadSpawn", "subAgentOther", "unknown"]
DEFAULT_WIKI = "~/Documents/Obsidian Vault/LLM Wiki"
DEFAULT_RUNS = "~/.omj/agent-team/runs"
DEFAULT_SESSIONS = "~/.codex/sessions"
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
            r["final"] = (read_text(base + ".last.md") or r.get("final") or "")[:4000]
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

    def start(self):
        r = self.args.refresh
        for name, fn, every in (("runs", self.collect_runs, r), ("threads", self.collect_threads, r * 2),
                                ("sessions", lambda: collect_herdr(self.args.machines, self.args.local_label), r * 2),
                                ("wiki", lambda: collect_wiki(os.path.join(self.args.wiki, "raw"), hours=self.args.hours), r * 3)):
            threading.Thread(target=self.loop, args=(name, fn, every), daemon=True).start()

    def snapshot(self):
        with self.lock:
            data = {"generated_at": now_iso(), "refresh_sec": self.args.refresh,
                    "slots": {k: {"at": v["at"], "error": v["error"]} for k, v in self.slots.items()}}
            for k, v in self.slots.items():
                data[k] = v["value"]
            return json.dumps(data, ensure_ascii=False)


# ---------- HTTP ----------

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>에이전트 팀 보드</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#1c1e21;--muted:#6b7280;--line:#e5e7eb;--ok:#15803d;--warn:#b45309;--bad:#b91c1c;--run:#1d4ed8;--acc:#4f46e5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--fg:#e5e7eb;--muted:#9ca3af;--line:#2a2f3a;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;--run:#60a5fa;--acc:#a5b4fc}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,"Apple SD Gothic Neo",sans-serif}
header{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid var(--line)}
header h1{font-size:16px;margin:0}header .meta{color:var(--muted);font-size:12px}
main{display:grid;grid-template-columns:1.5fr 1fr 0.9fr;gap:12px;padding:12px 16px}
@media (max-width:1100px){main{grid-template-columns:1fr}}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;min-height:160px;min-width:0}
h2{font-size:13px;margin:0 0 8px;color:var(--muted);letter-spacing:.02em}
h3{font-size:12px;margin:14px 0 6px;color:var(--muted)}
.row{padding:6px 8px;border-radius:8px;margin:2px 0}.row:hover{background:var(--bg)}
.run{border:1px solid var(--line);border-radius:10px;padding:10px;margin:0 0 10px}
.node{margin:6px 0 0;padding:6px 8px;border-left:3px solid var(--line);border-radius:6px}
.child{margin-left:18px;border-left-color:var(--acc)}
.badge{display:inline-block;font-size:11px;padding:1px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);margin:0 4px 2px 0}
.s-running,.s-working,.s-active{color:var(--run);border-color:var(--run)}
.s-done,.s-completed,.s-idle{color:var(--ok);border-color:var(--ok)}
.s-error,.s-errored,.s-blocked,.s-failed{color:var(--bad);border-color:var(--bad)}
.s-stale,.s-notLoaded,.s-progress,.s-started,.s-unknown{color:var(--warn);border-color:var(--warn)}
.muted{color:var(--muted);font-size:12px}.err{color:var(--bad);font-size:12px}
.nums{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:4px}.nums b{color:var(--fg);font-weight:600}
pre{white-space:pre-wrap;font:12px/1.4 ui-monospace,Menlo,monospace;background:var(--bg);padding:8px;border-radius:6px;max-height:260px;overflow:auto;margin:6px 0 0}
details summary{cursor:pointer;color:var(--muted);font-size:12px}
</style></head><body>
<header><h1>에이전트 팀 보드</h1><span class="meta" id="meta">불러오는 중…</span></header>
<main>
<section><h2>팀 실행 — 매니저와 하위 에이전트</h2><div id="runs"></div><h3>그 밖의 Codex 스레드</h3><div id="tree"></div></section>
<section><h2>공유 작업 기록 — LLM Wiki raw</h2><div id="wiki"></div></section>
<section><h2>세션 — herdr</h2><div id="sessions"></div></section>
</main>
<script>
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const badge=(t,cls)=>t?`<span class="badge ${cls?'s-'+esc(cls):''}">${esc(t)}</span>`:'';
const n=v=>typeof v==='number'?v.toLocaleString():'-';
const k=v=>typeof v==='number'?(v>=1e6?(v/1e6).toFixed(2)+'M':v>=1e3?(v/1e3).toFixed(1)+'k':String(v)):'-';
const dur=s=>s==null?'-':s<60?s+'초':Math.floor(s/60)+'분 '+(s%60)+'초';
const ago=iso=>{if(!iso)return'';const d=(Date.now()-new Date(iso).getTime())/1000;if(d<60)return Math.round(d)+'초 전';if(d<3600)return Math.round(d/60)+'분 전';if(d<86400)return Math.round(d/3600)+'시간 전';return Math.round(d/86400)+'일 전'};
const last=p=>(p||'').split('/').filter(Boolean).slice(-2).join('/');
function member(m,child){const t=m.tokens||{};const tools=Object.entries(m.tools||{}).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([x,c])=>x+' '+c).join(' · ');
 return `<div class="node ${child?'child':''}">${badge(m.state,m.state)}${badge(child?(m.role||'agent'):'매니저')}${badge(m.nickname)}${badge((m.models||[]).join('/')+((m.efforts||[]).length?' · '+m.efforts.join('/'):''))}
 <div class="nums"><span>토큰 <b>${k(t.total_tokens)}</b></span><span>캐시 ${k(t.cached_input_tokens)}</span><span>출력 <b>${k(t.output_tokens)}</b></span><span>도구 ${n(m.tool_calls)}</span>${m.updated?`<span>${ago(m.updated)}</span>`:''}</div>
 ${tools?`<div class="muted">${esc(tools)}</div>`:''}
 ${m.last_message?`<details><summary>${child?'보고':'최종 보고'} 보기</summary><pre>${esc(m.last_message)}</pre></details>`:''}
 ${(m.children||[]).map(c=>member(c,true)).join('')}</div>`}
function run(r){const m=r.meta||{};const tt=r.team_tokens||{};
 return `<div class="run">${badge(r.state,r.state)}${badge(m.mode)}${badge(m.model?(m.model+(m.effort?' · '+m.effort:'')):'')}${m.write?badge('쓰기'):badge('읽기 전용')}<b>${esc(r.name)}</b>
 <div class="nums"><span>걸린 시간 <b>${dur(r.elapsed_sec)}</b></span><span>에이전트 <b>${1+(r.members||0)}</b></span><span>합계 토큰 <b>${k(tt.total_tokens)}</b></span><span>출력 <b>${k(tt.output_tokens)}</b></span>${m.exit_code!=null?`<span>종료 코드 ${esc(m.exit_code)}</span>`:''}</div>
 ${m.task?`<div class="muted">${esc(m.task.slice(0,180))}</div>`:''}
 ${r.collect_error||m.error?`<div class="err">${esc(r.collect_error||m.error)}</div>`:''}
 ${r.unknown&&Object.keys(r.unknown).length?`<div class="err">모르는 이벤트: ${esc(Object.keys(r.unknown).join(', '))}</div>`:''}
 ${r.team?member(r.team,false):'<div class="muted">세션 기록을 아직 못 찾음</div>'}
 ${r.final?`<details><summary>결과 문서(.last.md)</summary><pre>${esc(r.final)}</pre></details>`:''}</div>`}
function node(t,child){return `<div class="node ${child?'child':''}">${badge(t.status,t.status)}${badge(t.role)}${badge(t.nickname)}${badge(t.model?(t.model+(t.effort?' · '+t.effort:'')):'')}${t.source==='spawn'?badge('spawn'):''}<div>${esc(t.name||t.preview||t.id)}</div><div class="muted">${esc(last(t.cwd))} · ${ago(t.updatedAt)}</div>${(t.children||[]).map(c=>node(c,true)).join('')}</div>`}
function wiki(ts){return (ts||[]).map(t=>`<div class="row">${badge(t.latest.status||'?',t.latest.status)}<b>${esc(t.task_id)}</b> <span class="muted">${t.count}건 · ${esc(t.authors.join(','))}${t.latest.machine?' · '+esc(t.latest.machine):''}</span><div>${esc(t.latest.title)}</div><div class="muted">${esc(t.latest.file)}</div></div>`).join('')||'<div class="muted">최근 기록 없음</div>'}
function sess(s){if(!s)return'';let h='';if(s.error)h+=`<div class="err">${esc(s.error)}</div>`;h+=`<div class="muted">${esc(s.local_label||'이 맥')}</div>`+(s.local||[]).map(a=>`<div class="row">${badge(a.status,a.status)}${badge(a.agent)}${badge(a.name)}<b>${esc(a.pane)}</b> ${esc(a.title)}<div class="muted">${esc(last(a.cwd))}</div></div>`).join('');for(const [m,v] of Object.entries(s.remote||{})){h+=`<div class="muted" style="margin-top:8px">${esc(m)}</div>`;if(v.error){h+=`<div class="err">${esc(v.error)}</div>`;continue}h+=v.map(a=>`<div class="row">${badge(a.status,a.status)}${badge(a.agent)}<b>${esc(a.pane)}</b> ${esc(a.title)}</div>`).join('')}return h}
const slotErr=(d,name)=>d.slots?.[name]?.error?`<div class="err">${esc(name)}: ${esc(d.slots[name].error)}</div>`:'';
async function tick(){try{const r=await fetch('/api/state');const d=await r.json();
 const th=d.threads||{};document.getElementById('meta').textContent=`갱신 ${d.generated_at||'-'} · ${d.refresh_sec}초마다 · 그 밖의 Codex 스레드 ${th.total??'-'}개`;
 document.getElementById('runs').innerHTML=slotErr(d,'runs')+((d.runs||[]).map(run).join('')||'<div class="muted">실행 기록 없음 — run_team.py 로 시작하면 여기 뜹니다</div>');
 document.getElementById('tree').innerHTML=slotErr(d,'threads')+((th.tree||[]).map(t=>node(t,false)).join('')||'<div class="muted">최근 스레드 없음</div>')+(th.hidden?`<div class="muted">자동 리뷰 스레드 ${th.hidden}개 숨김</div>`:'');
 document.getElementById('wiki').innerHTML=slotErr(d,'wiki')+wiki(d.wiki);
 document.getElementById('sessions').innerHTML=slotErr(d,'sessions')+sess(d.sessions)}catch(e){document.getElementById('meta').textContent='보드 서버에 닿지 않음: '+e}}
tick();setInterval(tick,3000);
</script></body></html>"""


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/state"):
                body = state.snapshot().encode("utf-8")
                ctype = "application/json; charset=utf-8"
            else:
                body = PAGE.encode("utf-8")
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

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
    ap.add_argument("--allow-remote", action="store_true", help="127.0.0.1 밖에 묶는 것을 허용한다(인증 없음 — 작업 내용이 보인다)")
    ap.add_argument("--refresh", type=int, default=3, help="수집 주기(초, 1 이상)")
    ap.add_argument("--hours", type=int, default=24, help="보여 줄 최근 범위(시간)")
    ap.add_argument("--wiki", default=os.environ.get("AGENT_BOARD_WIKI", DEFAULT_WIKI))
    ap.add_argument("--runs", default=os.environ.get("AGENT_BOARD_RUNS", DEFAULT_RUNS))
    ap.add_argument("--sessions", default=os.environ.get("AGENT_BOARD_SESSIONS", DEFAULT_SESSIONS), help="Codex 세션 기록 폴더")
    ap.add_argument("--machines", default=os.environ.get("AGENT_BOARD_MACHINES", ""),
                    help="herdr 원격 머신. 'herdr 이름=화면 이름' 을 쉼표로 (화면 이름은 생략 가능)")
    ap.add_argument("--local-label", default=os.environ.get("AGENT_BOARD_LOCAL_LABEL", "이 맥"), help="이 맥의 화면 이름")
    ap.add_argument("--thread-limit", type=int, default=100)
    ap.add_argument("--hide-pattern", default=r"^Codex Companion Task",
                    help="그 밖의 스레드에서 개수만 셀 루트 이름(정규식). 빈 문자열이면 모두 보여 준다")
    args = ap.parse_args()
    if args.refresh < 1:
        ap.error("--refresh 는 1 이상이어야 한다")
    if not is_loopback(args.host) and not args.allow_remote:
        ap.error("--host %s 는 루프백이 아니다. 인증이 없어 작업 내용이 보이므로 --allow-remote 를 함께 줘야 한다" % args.host)
    args.hide_re = re.compile(args.hide_pattern) if args.hide_pattern else None
    for k in ("wiki", "runs", "sessions"):
        setattr(args, k, os.path.abspath(os.path.expanduser(getattr(args, k))))
    args.machines = parse_machines(args.machines)

    state = State(args)
    state.start()
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print("에이전트 팀 보드: http://%s:%d  (위키 %s · 실행 기록 %s · 세션 기록 %s · 이 맥 %s · 원격 %s)" % (
        args.host, args.port, args.wiki, args.runs, args.sessions, args.local_label,
        ", ".join("%s(%s)" % (l, n) for n, l in args.machines) or "없음"), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
