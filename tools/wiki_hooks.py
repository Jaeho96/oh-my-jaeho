#!/usr/bin/env python3
"""공유 LLM Wiki 훅을 Claude Code(settings.json)·Codex(hooks.json)에 등록하거나 뺀다 (2026-10-20).

  python3 tools/wiki_hooks.py            # 미리보기
  python3 tools/wiki_hooks.py --apply    # 등록 (이미 있으면 건너뜀)
  python3 tools/wiki_hooks.py --remove --apply
  python3 tools/wiki_hooks.py --sync-only --apply   # 기록 확인 훅 없이 동기화만 (예: 위임받아 일하는 맥)

넣는 것 — 세션 시작: wiki_sync.py --detach / 작업 끝: wiki_log_guard.py + wiki_sync.py --detach.
이미 있는 우리 묶음이 원하는 모양과 다르면(예: --sync-only 로 바꿀 때) 그 묶음만 원하는 모양으로 바꾼다.
기존 훅(다른 도구가 넣은 것)은 건드리지 않고 그 뒤에 묶음 하나를 덧붙인다. 우리 항목은 명령에 `/.claude/hooks/wiki_` 가 든 것이다.
묶음 단위가 아니라 훅 항목 단위로 우리 것만 빼고 맞춘다. 같은 묶음에 다른 도구의 훅이 섞여 있어도 그 훅은 남는다 (2026-10-27).
쓰기 전 원본은 ~/.omj/backups/<시각>/ 에 둔다. Codex 는 다음 시작 때 새 훅 신뢰(Trust) 승인을 한 번 묻는다.
훅 파일 자체(~/.claude/hooks/*.py 링크)는 tools/sync.py 가 건다.
"""
import argparse
import json
import os
import shutil
import sys
import time

HOME = os.path.expanduser("~")
TARGETS = {"Claude Code": os.path.join(HOME, ".claude", "settings.json"),
           "Codex": os.path.join(HOME, ".codex", "hooks.json")}
MARK = "/.claude/hooks/wiki_"
PY = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else "python3"
SYNC = {"type": "command", "command": '%s "$HOME/.claude/hooks/wiki_sync.py" --detach' % PY, "timeout": 10}
GUARD = {"type": "command", "command": '%s "$HOME/.claude/hooks/wiki_log_guard.py"' % PY, "timeout": 15}
WANT = {"SessionStart": [SYNC], "Stop": [GUARD, SYNC]}
WANT_SYNC_ONLY = {"SessionStart": [SYNC], "Stop": [SYNC]}


def is_ours(handler):
    return MARK in handler.get("command", "")


def names(handlers):
    return " + ".join(os.path.basename(h["command"].split('"')[1]) for h in handlers)


def strip_ours(groups):
    """묶음마다 우리 항목만 뺀다. 같은 묶음에 든 다른 도구의 훅은 남기고, 우리 항목만 있던 묶음은 없앤다.
    돌려주는 것: (남은 묶음, 뺀 항목 수, 첫 우리 항목이 있던 자리)."""
    rest, removed, at = [], 0, None
    for g in groups:
        handlers = g.get("hooks", [])
        keep = [h for h in handlers if not is_ours(h)]
        if len(keep) != len(handlers):
            removed += len(handlers) - len(keep)
            if at is None:
                at = len(rest)
        if len(keep) == len(handlers):
            rest.append(g)
        elif keep:
            rest.append(dict(g, hooks=keep))
    return rest, removed, at


def plan(data, remove, want=WANT):
    hooks = data.setdefault("hooks", {})
    notes = []
    for event, handlers in want.items():
        groups = hooks.get(event, [])
        rest, removed, at = strip_ours(groups)
        group = {"hooks": [dict(h) for h in handlers]}
        mine = [g for g in groups if any(is_ours(h) for h in g.get("hooks", []))]
        if remove:
            if removed:
                if rest:
                    hooks[event] = rest
                else:
                    del hooks[event]
                notes.append("%s: 위키 훅 %d개 뺌" % (event, removed))
        elif not removed:
            hooks[event] = groups + [group]
            notes.append("%s: 위키 훅 묶음 추가 (%s)" % (event, names(handlers)))
        elif len(mine) == 1 and [h.get("command") for h in mine[0].get("hooks", [])] == [h["command"] for h in handlers]:
            notes.append("%s: 이미 있음" % event)   # 우리 묶음 하나에 다른 도구의 훅이 섞이지 않은 경우
        else:                 # 모양이 다르다. 첫 우리 항목이 있던 자리에 원하는 묶음 하나만 남긴다
            rest.insert(at, group)
            hooks[event] = rest
            notes.append("%s: 위키 훅 묶음을 맞춤 (%s)" % (event, names(handlers)))
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--sync-only", action="store_true", help="기록 확인 훅 없이 동기화만")
    a = ap.parse_args()
    need = ("wiki_sync.py",) if a.sync_only else ("wiki_sync.py", "wiki_log_guard.py")
    missing = [p for p in need if not os.path.exists(os.path.join(HOME, ".claude", "hooks", p))]
    if missing and not a.remove:
        sys.exit("훅 파일이 없다: ~/.claude/hooks/%s — 먼저 tools/sync.py --apply" % ", ".join(missing))
    stamp = time.strftime("%Y%m%d%H%M%S")
    for name, path in TARGETS.items():
        if not os.path.exists(path):
            print("%s: %s 없음 — 건너뜀" % (name, path))
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        before = json.dumps(data, sort_keys=True)
        notes = plan(data, a.remove, WANT_SYNC_ONLY if a.sync_only else WANT)
        for n in notes:
            print("%s · %s" % (name, n))
        if json.dumps(data, sort_keys=True) == before or not a.apply:
            continue
        bak = os.path.join(HOME, ".omj", "backups", stamp, os.path.relpath(path, HOME))
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        shutil.copy2(path, bak)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
        print("%s · 저장 (원본 %s)" % (name, bak))
    if not a.apply:
        print("미리보기 — 바꾸려면 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
