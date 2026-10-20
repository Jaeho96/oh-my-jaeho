#!/usr/bin/env python3
"""Claude Code 상태줄.

설정(~/.claude/settings.json):
  "statusLine": {"type": "command", "command": "/usr/bin/python3 ~/.claude/statusline.py", "refreshInterval": 60}

입력 필드는 https://code.claude.com/docs/en/statusline 「Available data」 기준(2026-10-01, v2.1.286).
맥 기본 /usr/bin/python3(3.9)의 표준 라이브러리만 쓴다 — 설치할 것이 없다.

예전 셸 판(statusline-command.sh)에서 고친 것
- 적중률: `total_input_tokens` 는 v2.1.132 부터 캐시 읽기를 이미 포함한다. 거기에 캐시 읽기를
  한 번 더 더해 나눠서 **50% 를 넘을 수 없었다.** 세션 값은 공식 `prompt_cache.hit_ratio` 를 쓴다.
- 그릴 때마다 jq·python3 를 30번 가까이 띄웠다(0.35~0.72초). Claude Code 는 새 갱신이 오면
  돌던 스크립트를 취소하므로 느리면 갱신을 놓친다. 지금은 프로세스 하나 + git(5초 캐시).
- 남은 시간이 「1h 30m」이면 왼쪽 칸을 넘쳤다. 칸마다 폭을 재서 넘치면 …로 자른다.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unicodedata

R = "\033[0m"
BD = "\033[1m"
DM = "\033[2m"
CY = "\033[36m"
YL = "\033[33m"
GR = "\033[32m"
RD = "\033[31m"
WH = "\033[97m"

GIT_CACHE_SEC = 5
NOW = time.time()


# ── 입력 ──────────────────────────────────────────────────────────
def get(d, path, default=None):
    for k in path.split("."):
        if not isinstance(d, dict) or d.get(k) is None:
            return default
        d = d[k]
    return d


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ── 포맷 ──────────────────────────────────────────────────────────
def fmt_span(sec):
    """남은 시간·경과 시간 — 3d4h · 1h05m · 40m · <1m"""
    s = max(0, int(sec))
    d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
    if d:
        return "%dd%dh" % (d, h)
    if h:
        return "%dh%02dm" % (h, m)
    return "%dm" % m if m else "<1m"


def fmt_tok(n):
    n = int(n)
    if n >= 1000000:
        return "%.1fM" % (n / 1000000.0)
    if n >= 1000:
        return "%dk" % (n // 1000)
    return str(n)


def tone(pct):
    return RD if pct >= 80 else YL if pct >= 50 else GR


def bar(pct, width):
    filled = max(0, min(width, int(pct * width / 100)))
    return "█" * filled + "░" * (width - filled)


# ── 폭 계산 — 한글 2칸, ANSI 는 0칸 ────────────────────────────────
def cw(c):
    if unicodedata.combining(c):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def width(s):
    return sum(cw(c) for c in s)


def cell(segs, w):
    """(글자, 색[, 링크]) 조각들을 정확히 w 칸으로 — 넘치면 …로 자르고 모자라면 채운다."""
    segs = [s for s in segs if s and s[0]]
    over = sum(width(s[0]) for s in segs) > w
    limit = w - 1 if over else w
    out, used, full = [], 0, False
    for seg in segs:
        text, sgr = seg[0], seg[1]
        url = seg[2] if len(seg) > 2 else None
        piece = ""
        for c in text:
            if used + cw(c) > limit:
                full = True
                break
            piece += c
            used += cw(c)
        if piece:
            s = sgr + piece + R if sgr else piece
            if url:  # OSC 8 — 지원하는 터미널에서 Cmd+클릭으로 열린다
                s = "\033]8;;%s\033\\%s\033]8;;\033\\" % (url, s)
            out.append(s)
        if full:
            break
    if over:
        out.append(DM + "…" + R)
        used += 1
    return "".join(out) + " " * (w - used)


# ── git — 세션별로 5초 캐시 ────────────────────────────────────────
def run_git(cwd, *args):
    try:
        p = subprocess.run(
            ["git", "-C", cwd, "--no-optional-locks"] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2,
            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0", LC_ALL="C"),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None


def git_info(cwd, session_id):
    if not cwd or not os.path.isdir(cwd):
        return None
    key = "".join(c for c in (session_id or "") if c.isalnum() or c == "-")[:64] or "nosession"
    cache = os.path.join(tempfile.gettempdir(), "claude-statusline-git-%s.json" % key)
    try:
        if NOW - os.path.getmtime(cache) < GIT_CACHE_SEC:
            with open(cache) as f:
                saved = json.load(f)
            if saved.get("cwd") == cwd:
                return saved.get("info")
    except (OSError, ValueError):
        pass

    info = None
    top = run_git(cwd, "rev-parse", "--show-toplevel")
    if top:
        st = run_git(cwd, "status", "--porcelain=v2", "--branch") or ""
        branch, oid, dirty, untracked = "", "", 0, 0
        for line in st.splitlines():
            if line.startswith("# branch.head "):
                branch = line[len("# branch.head "):]
            elif line.startswith("# branch.oid "):
                oid = line[len("# branch.oid "):][:7]
            elif line.startswith("? "):
                untracked += 1
                dirty += 1
            elif line[:2] in ("1 ", "2 ", "u "):
                dirty += 1
        if branch == "(detached)":
            branch = oid or "detached"
        wt = run_git(cwd, "worktree", "list", "--porcelain") or ""
        info = {
            "project": os.path.basename(top.strip()),
            "branch": branch,
            "dirty": dirty,
            "untracked": untracked,
            "worktrees": max(1, sum(1 for l in wt.splitlines() if l.startswith("worktree "))),
        }
    try:
        with open(cache, "w") as f:
            json.dump({"cwd": cwd, "info": info}, f)
    except OSError:
        pass
    return info


def hooks_count():
    try:
        with open(os.path.expanduser("~/.claude/settings.json")) as f:
            hooks = json.load(f).get("hooks") or {}
    except (OSError, ValueError):
        return 0
    return sum(len(v) if isinstance(v, list) else 1 for v in hooks.values())


# ── 조각 ──────────────────────────────────────────────────────────
PERM_SHORT = {"default": "default", "acceptEdits": "edits", "bypassPermissions": "bypass",
              "plan": "plan", "auto": "auto", "dontAsk": "dontAsk"}
REVIEW = {"approved": ("승인", GR), "pending": ("리뷰대기", YL),
          "changes_requested": ("수정요청", RD), "draft": ("초안", DM)}
MISS_CAUSE = {"tools_changed": "도구 바뀜", "system_prompt_changed": "시스템 바뀜",
              "ttl_expired_5m": "5m 만료", "ttl_expired_1h": "1h 만료",
              "likely_server_side": "서버 쪽"}


def limit_segs(label, win):
    """5HR·7D 한 줄 — 창이 지나면 Claude Code 가 그 창을 빼므로 없는 게 정상이다."""
    if not win:
        return [(" %s " % label, ""), ("-", DM)]
    pct = int(round(num(win.get("used_percentage"))))
    segs = [(" %s " % label, ""), ("[%s]" % bar(pct, 15), tone(pct)), (" %d%%" % pct, tone(pct))]
    reset = num(win.get("resets_at"))
    if reset > 0:  # epoch 초로 적힌 절대 시각이다 — 남은 시간으로 바꾼다
        segs.append(("  R " + fmt_span(reset - NOW), DM))
    return segs


def build(d, cols):
    model = get(d, "model.display_name", "unknown")
    effort = get(d, "effort.level")
    perm = get(d, "permission_mode")
    cost = num(get(d, "cost.total_cost_usd"))
    dur = num(get(d, "cost.total_duration_ms")) / 1000
    api_dur = num(get(d, "cost.total_api_duration_ms")) / 1000
    added = int(num(get(d, "cost.total_lines_added")))
    removed = int(num(get(d, "cost.total_lines_removed")))
    ctx_pct = int(round(num(get(d, "context_window.used_percentage"))))
    ctx_size = num(get(d, "context_window.context_window_size"))
    in_tok = num(get(d, "context_window.total_input_tokens"))
    out_tok = num(get(d, "context_window.total_output_tokens"))
    cache_r = num(get(d, "context_window.current_usage.cache_read_input_tokens"))
    cache_w = num(get(d, "context_window.current_usage.cache_creation_input_tokens"))
    pc = get(d, "prompt_cache") or {}
    five = get(d, "rate_limits.five_hour")
    week = get(d, "rate_limits.seven_day")
    cwd = get(d, "workspace.current_dir") or get(d, "cwd")
    git = git_info(cwd, get(d, "session_id"))
    pr = get(d, "pr") or {}

    # effort 가 low·medium 이면 노랗게 — 2026-09-23 Opus 5.5 가 조용히 medium 으로 떨어진 일이 있었다
    model_segs = [(" ", ""), (model, BD)]
    if effort:
        model_segs.append((" " + str(effort), YL if effort in ("low", "medium") else CY))
    if get(d, "fast_mode") is True:
        model_segs.append((" fast", CY))
    if get(d, "thinking.enabled") is False:
        model_segs.append((" 생각끔", DM))
    if perm:
        model_segs.append((" [%s]" % PERM_SHORT.get(perm, perm), YL))

    # 적중 — 이번 호출: 캐시 읽기 / 입력 전체(캐시 읽기·쓰기 포함). 세션: 공식 hit_ratio
    hit = int(cache_r * 100 / in_tok) if in_tok > 0 else 0
    cache_segs = [(" 캐시 ", ""), (fmt_tok(cache_r) + "r", GR), (" " + fmt_tok(cache_w) + "w", DM),
                  ("  적중 ", ""), ("%d%%" % hit, GR)]
    if pc.get("hit_ratio") is not None:
        cache_segs += [(" · 세션 ", DM), ("%d%%" % round(num(pc["hit_ratio"]) * 100), GR)]

    if pc:
        if pc.get("warm"):
            left = num(pc.get("expires_at")) - NOW
            warm_segs = [(" 캐시 %s " % (pc.get("ttl") or ""), ""),
                         ("유지 " + fmt_span(left), YL if left < 300 else GR)]
        else:
            warm_segs = [(" 캐시 ", ""), ("식음", RD)]
            if pc.get("recache_tokens_if_cold"):
                warm_segs.append((" 재적재 " + fmt_tok(num(pc["recache_tokens_if_cold"])), DM))
        misses = int(num(pc.get("misses")))
        if misses:
            warm_segs.append(("  미스 %d" % misses, YL))
            causes = get(pc, "last_miss_cause.causes") or []
            if causes:
                warm_segs.append((" " + ",".join(MISS_CAUSE.get(c, c) for c in causes), DM))
    else:
        warm_segs = []

    time_segs = [(" " + fmt_span(dur), ""), (" (API %s)" % fmt_span(api_dur), DM)]
    if added or removed:
        time_segs += [("  +%d" % added, GR), (" -%d" % removed, RD)]

    if git:
        git_segs = [(" ", ""), (git["project"], WH), (": ", ""),
                    (git["branch"] + ("*" if git["dirty"] else ""), GR),
                    ("  미추적:%d" % git["untracked"], "")]
        if get(d, "workspace.git_worktree"):
            git_segs.append(("  wt:" + get(d, "workspace.git_worktree"), CY))
    else:
        git_segs = [(" (git 없음)", DM)]
    # PR 은 Claude Code 가 준 값이다 — 우리 git 호출이 실패해도 보인다
    if pr.get("number"):
        label = ("MR !%s" if pr.get("kind") == "mr" else "PR #%s") % pr["number"]
        git_segs.append(("  " + label, CY, pr.get("url")))
        if pr.get("review_state") in REVIEW:
            text, color = REVIEW[pr["review_state"]]
            git_segs.append((" " + text, color))

    name = get(d, "session_name")
    ops_segs = [(" " + name, CY)] if name else [(" (unnamed)", DM)]
    if get(d, "agent.name"):
        ops_segs.append(("  @" + get(d, "agent.name"), DM))
    base_segs = [(" ", ""), (">", DM), (" 워크트리 ", ""), (str(git["worktrees"] if git else 1), WH),
                 ("  ", ""), ("│", DM), ("  훅 ", ""), (str(hooks_count()), WH)]

    ctx_segs = [(" CTX ", ""), ("[%s]" % bar(ctx_pct, 15), tone(ctx_pct)), (" %d%%" % ctx_pct, tone(ctx_pct))]
    if ctx_size >= 1000000:
        ctx_segs.append((" /" + fmt_tok(ctx_size), DM))
    supply_segs = [(" 입력 ", ""), (fmt_tok(in_tok), WH), ("  출력 ", ""), (fmt_tok(out_tok), YL),
                   ("  ~$%.2f" % cost, "")]

    # 좁은 창(herdr 분할·휴대폰)에서는 상자를 버리고 두 줄로
    if cols < 60:
        w = max(20, cols - 2)
        line1 = model_segs + [("  CTX %d%%" % ctx_pct, tone(ctx_pct))]
        for label, win in (("5H", five), ("7D", week)):
            if win:
                p = int(round(num(win.get("used_percentage"))))
                line1.append(("  %s %d%%" % (label, p), tone(p)))
        line2 = (git_segs if git else []) + [("  ~$%.2f" % cost, "")] + ([("  " + name, CY)] if name else [])
        return [cell(line1, w), cell(line2, w)]

    total = min(cols - 2, 76)          # 넓으면 예전 크기(76) 그대로, 좁으면 줄인다
    lw = (total - 3) // 2
    rw = total - 3 - lw

    def div2(lc, ll, rc, rl):
        return YL + lc + ll + "─" * (lw - width(ll)) + "┬" + rl + "─" * (rw - width(rl)) + rc + R

    def div1(lc, ll, rc):
        return YL + lc + ll + "─" * (lw + 1 + rw - width(ll)) + rc + R

    def row2(l, r):
        return "│" + cell(l, lw) + YL + "│" + R + cell(r, rw) + "│"

    lines = [
        div2("┌", "─ CORE ", "┐", "─ SUPPLY "),
        row2(model_segs, supply_segs),
        row2(ctx_segs, cache_segs),
        row2(limit_segs("5HR", five), warm_segs),
        row2(limit_segs("7D ", week), time_segs),
        div1("├", "─ GIT ", "┤"),
        "│" + cell(git_segs, lw + 1 + rw) + "│",
        div2("├", "─ OPS ", "┤", "─ BASE "),
        row2(ops_segs, base_segs),
        YL + "└" + "─" * lw + "┴" + "─" * rw + "┘" + R,
    ]
    return lines


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        d = json.loads(raw) if raw.strip() else {}
        cols = int(os.environ.get("COLUMNS") or 0) or 78
        lines = build(d, cols)
    except Exception as e:  # 상태줄이 통째로 사라지는 것보다 이유 한 줄이 낫다
        lines = ["statusline 오류: %s: %s" % (type(e).__name__, e)]
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
