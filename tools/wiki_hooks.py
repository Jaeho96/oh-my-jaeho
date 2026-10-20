#!/usr/bin/env python3
"""공유 LLM Wiki 훅을 Claude Code(settings.json)·Codex(hooks.json)에 등록하거나 뺀다 (2026-10-20).

  python3 tools/wiki_hooks.py            # 미리보기
  python3 tools/wiki_hooks.py --apply    # 등록 (이미 있으면 건너뜀)
  python3 tools/wiki_hooks.py --remove --apply

넣는 것 — 세션 시작: wiki_sync.py --detach / 작업 끝: wiki_log_guard.py + wiki_sync.py --detach.
기존 훅(다른 도구가 넣은 것)은 건드리지 않고 그 뒤에 묶음 하나를 덧붙인다. 우리 항목은 명령에 `/.claude/hooks/wiki_` 가 든 것이다.
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


def ours(group):
    return any(MARK in h.get("command", "") for h in group.get("hooks", []))


def plan(data, remove):
    hooks = data.setdefault("hooks", {})
    notes = []
    for event, handlers in WANT.items():
        groups = hooks.setdefault(event, [])
        mine = [g for g in groups if ours(g)]
        if remove:
            if mine:
                hooks[event] = [g for g in groups if not ours(g)]
                notes.append("%s: 위키 훅 묶음 %d개 뺌" % (event, len(mine)))
        elif not mine:
            groups.append({"hooks": [dict(h) for h in handlers]})
            notes.append("%s: 위키 훅 묶음 추가 (%s)" % (event, " + ".join(os.path.basename(h["command"].split('"')[1]) for h in handlers)))
        else:
            notes.append("%s: 이미 있음" % event)
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()
    missing = [p for p in ("wiki_sync.py", "wiki_log_guard.py") if not os.path.exists(os.path.join(HOME, ".claude", "hooks", p))]
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
        notes = plan(data, a.remove)
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
