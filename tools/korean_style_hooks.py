#!/usr/bin/env python3
"""한국어 문체 훅을 Claude Code(settings.json) · Codex(hooks.json)에 등록하거나 뺀다 (2026-10-27).

  python3 tools/korean_style_hooks.py            # 미리보기
  python3 tools/korean_style_hooks.py --apply    # 등록 (이미 있으면 건너뜀)
  python3 tools/korean_style_hooks.py --remove --apply

넣는 것
- Codex 세션 시작(startup · clear · compact)과 하위 에이전트 시작: hooks/korean_style_context.py 가 지침 본문을 개발자 문맥으로 넣는다.
  Claude Code 는 rules/korean-style*.md 를 ~/.claude/rules 링크로 읽으니(tools/sync.py) 이 훅이 필요 없다.
  지침이 기본 한도(약 2,500토큰)보다 길어서 additionalContextLimit 을 준다.
- Claude Code · Codex 작업 끝(Stop): hooks/korean_style_guard.py 가 기계로 판정할 수 있는 문체 위반을 한 번 되돌린다.
우리 항목은 명령에 `/.claude/hooks/korean_style_` 가 든 훅이다. 묶음 단위가 아니라 훅 항목 단위로 우리 것만 빼고 더한다.
같은 묶음에 다른 도구의 훅이 섞여 있어도 그 훅은 남는다.
Claude settings.json 이 없으면 건너뛰고(만들지 않음), Codex hooks.json 이 없으면 새로 만든다.
쓰기 전 원본은 ~/.omj/backups/<시각>/ 에 둔다. Codex 는 새 훅을 /hooks 에서 신뢰(Trust)해야 돌린다.
훅 파일 자체(~/.claude/hooks/korean_style_*.py 링크)는 tools/sync.py 가 건다.
"""
import argparse
import json
import os
import shutil
import sys
import time

HOME = os.path.expanduser("~")
MARK = "/.claude/hooks/korean_style_"
PY = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else "python3"
CONTEXT = {"type": "command", "command": '%s "$HOME/.claude/hooks/korean_style_context.py"' % PY,
           "timeout": 5, "additionalContextLimit": 20000}
GUARD = {"type": "command", "command": '%s "$HOME/.claude/hooks/korean_style_guard.py"' % PY, "timeout": 15}
# resume 은 넣지 않는다. 이어 받은 대화에 처음 넣은 지침이 남는지는 문서에 없다(미확인). natural-korean 도 같은 선택이다.
TARGETS = [
    ("Claude Code", os.path.join(HOME, ".claude", "settings.json"), False,
     {"Stop": {"hooks": [GUARD]}}),
    ("Codex", os.path.join(HOME, ".codex", "hooks.json"), True,
     {"SessionStart": {"matcher": "^(startup|clear|compact)$", "hooks": [CONTEXT]},
      "SubagentStart": {"hooks": [CONTEXT]},
      "Stop": {"hooks": [GUARD]}}),
]
HOOK_FILES = ("korean_style_context.py", "korean_style_guard.py")


def strip_ours(groups):
    """묶음마다 우리 항목만 뺀다. 같은 묶음에 든 다른 훅은 그대로 두고, 우리 항목만 있던 묶음은 없앤다."""
    rest, removed = [], 0
    for g in groups:
        handlers = g.get("hooks", [])
        keep = [h for h in handlers if MARK not in h.get("command", "")]
        removed += len(handlers) - len(keep)
        if len(keep) == len(handlers):
            rest.append(g)
        elif keep:
            rest.append(dict(g, hooks=keep))
    return rest, removed


def plan(data, want, remove):
    hooks = dict(data.get("hooks") or {})
    notes = []
    for event, group in want.items():
        groups = hooks.get(event, [])
        rest, removed = strip_ours(groups)
        if remove:
            if removed:
                if rest:
                    hooks[event] = rest
                else:
                    del hooks[event]
                notes.append("%s: 문체 훅 %d개 뺌" % (event, removed))
        elif removed == 1 and group in groups:
            notes.append("%s: 이미 있음" % event)
        else:
            hooks[event] = rest + [json.loads(json.dumps(group))]
            notes.append("%s: 문체 훅 묶음 %s" % (event, "맞춤" if removed else "추가"))
    if hooks != (data.get("hooks") or {}):
        data["hooks"] = hooks
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()
    missing = [f for f in HOOK_FILES if not os.path.exists(os.path.join(HOME, ".claude", "hooks", f))]
    if missing and not a.remove:
        sys.exit("훅 파일이 없다: ~/.claude/hooks/%s. 먼저 tools/sync.py --apply 를 돌린다" % ", ".join(missing))
    stamp = time.strftime("%Y%m%d%H%M%S")
    for name, path, create, want in TARGETS:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        elif create:
            data = {}
        else:
            print("%s · %s 없음. 건너뜀" % (name, path))
            continue
        before = json.dumps(data, sort_keys=True)
        for n in plan(data, want, a.remove):
            print("%s · %s" % (name, n))
        if json.dumps(data, sort_keys=True) == before or not a.apply:
            continue
        if os.path.exists(path):
            bak = os.path.join(HOME, ".omj", "backups", stamp, os.path.relpath(path, HOME))
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            shutil.copy2(path, bak)
            print("%s · 원본 %s" % (name, bak))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
        trust = " (다음 Codex 시작 때 /hooks 에서 신뢰 승인)" if name == "Codex" and not a.remove else ""
        print("%s · 저장 %s%s" % (name, path, trust))
    if not a.apply:
        print("미리보기. 바꾸려면 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
