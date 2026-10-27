#!/usr/bin/env python3
"""한국어 문체 지침 훅을 Codex(hooks.json)에 등록하거나 뺀다 (2026-10-27).

  python3 tools/korean_style_hooks.py            # 미리보기
  python3 tools/korean_style_hooks.py --apply    # 등록 (이미 있으면 건너뜀)
  python3 tools/korean_style_hooks.py --remove --apply

Claude Code 는 rules/korean-style*.md 를 ~/.claude/rules 링크로 읽으니(tools/sync.py) 여기서 다루지 않는다.
Codex 에는 세션 시작(startup · clear · compact)과 하위 에이전트 시작에 hooks/korean_style_context.py 를 건다.
훅의 표준 출력이 개발자 문맥으로 들어간다. 지침이 기본 한도(약 2,500토큰)보다 길어서 additionalContextLimit 을 준다.
우리 항목은 명령에 `/.claude/hooks/korean_style_` 가 든 훅이다. 묶음 단위가 아니라 훅 항목 단위로 우리 것만 빼고 더한다.
같은 묶음에 다른 도구의 훅이 섞여 있어도 그 훅은 남는다.
쓰기 전 원본은 ~/.omj/backups/<시각>/ 에 둔다. Codex 는 새 훅을 /hooks 에서 신뢰(Trust)해야 돌린다.
훅 파일 자체(~/.claude/hooks/korean_style_context.py 링크)는 tools/sync.py 가 건다.
"""
import argparse
import json
import os
import shutil
import sys
import time

HOME = os.path.expanduser("~")
TARGET = os.path.join(HOME, ".codex", "hooks.json")
MARK = "/.claude/hooks/korean_style_"
PY = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else "python3"
HANDLER = {"type": "command", "command": '%s "$HOME/.claude/hooks/korean_style_context.py"' % PY,
           "timeout": 5, "additionalContextLimit": 20000}
# resume 은 넣지 않는다. 이어 받은 대화에 처음 넣은 지침이 남는지는 문서에 없다(미확인). natural-korean 도 같은 선택이다.
WANT = {"SessionStart": {"matcher": "^(startup|clear|compact)$", "hooks": [HANDLER]},
        "SubagentStart": {"hooks": [HANDLER]}}


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


def plan(data, remove):
    hooks = data.setdefault("hooks", {})
    notes = []
    for event, group in WANT.items():
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
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args()
    if not a.remove and not os.path.exists(os.path.join(HOME, ".claude", "hooks", "korean_style_context.py")):
        sys.exit("훅 파일이 없다: ~/.claude/hooks/korean_style_context.py. 먼저 tools/sync.py --apply 를 돌린다")
    if os.path.exists(TARGET):
        with open(TARGET, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    before = json.dumps(data, sort_keys=True)
    for n in plan(data, a.remove):
        print("Codex · %s" % n)
    if json.dumps(data, sort_keys=True) == before or not a.apply:
        if not a.apply:
            print("미리보기. 바꾸려면 --apply")
        return 0
    if os.path.exists(TARGET):
        bak = os.path.join(HOME, ".omj", "backups", time.strftime("%Y%m%d%H%M%S"), os.path.relpath(TARGET, HOME))
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        shutil.copy2(TARGET, bak)
        print("Codex · 원본 %s" % bak)
    tmp = TARGET + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, TARGET)
    print("Codex · 저장 %s%s" % (TARGET, "" if a.remove else " (다음 Codex 시작 때 /hooks 에서 신뢰 승인)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
