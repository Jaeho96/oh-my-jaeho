#!/usr/bin/env python3
"""Codex 세션과 하위 에이전트가 시작할 때 한국어 문체 지침을 개발자 문맥으로 넣는 훅 (SessionStart · SubagentStart).

Claude Code 는 같은 파일을 ~/.claude/rules 링크로 읽는다. Codex 는 그 폴더를 모르니 이 훅이 본문을 출력한다.
Codex 는 훅의 표준 출력을 개발자 문맥으로 넣는다(learn.chatgpt.com/docs/hooks).
- 원본은 이 레포의 rules/korean-style.md 와 rules/korean-style-toss.md 다. 링크를 따라가 레포 위치를 찾는다.
- 지침 본문만 바뀌면 훅 정의는 그대로라 Codex 신뢰를 다시 받지 않아도 된다.
- MAX_BYTES 를 넘으면 자르고 그렇다고 적는다. hooks.json 의 additionalContextLimit 보다 작게 둔다.
- Claude Code 가 codex 플러그인으로 띄운 Codex 세션(rollout 첫 줄 originator 「Claude Code」)에는 넣지 않는다.
  거의 다 턴 끝마다 도는 종료 검토이고, 그 답은 Claude 가 읽는 판정이다. 매번 지침 전문이 들어가면 검토가 무거워진다.
  세션 시작 때 rollout 에는 첫 줄만 있어 검토 프롬프트로는 가려낼 수 없다. 최근 30일 이런 세션 526개 중 525개가
  종료 검토였다(2026-10-29 확인).
- 오류가 나면 아무것도 출력하지 않고 끝낸다. 훅 고장이 세션 시작을 막으면 안 된다.
Python 3.9 에서도 돈다(Codex 가 시스템 python3 로 부른다).
"""
import json
import os
import sys

FILES = ("korean-style.md", "korean-style-toss.md")
MAX_BYTES = int(os.environ.get("KOREAN_STYLE_MAX_BYTES", "60000"))
HEAD = "아래는 사용자가 정한 한국어 문체 지침이다. 사용자가 읽는 한국어 글을 쓸 때 따른다.\n\n"


def from_claude_code():
    """훅 입력(표준 입력)의 transcript_path 첫 줄 originator 가 「Claude Code」면 참. 손으로 돌릴 때(터미널)는 읽지 않는다."""
    if sys.stdin.isatty():
        return False
    try:
        path = json.loads(sys.stdin.read() or "{}").get("transcript_path")
        with open(path, encoding="utf-8", errors="replace") as f:
            return json.loads(f.readline()).get("payload", {}).get("originator") == "Claude Code"
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def main():
    if from_claude_code():
        return
    rules = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "rules")
    parts = []
    for name in FILES:
        path = os.path.join(rules, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                parts.append(f.read().strip())
    if not parts:
        return
    text = HEAD + "\n\n".join(parts) + "\n"
    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        text = data[:MAX_BYTES].decode("utf-8", "ignore") + "\n\n(지침이 길어서 여기서 잘랐다. 전문은 " + rules + ")\n"
    sys.stdout.write(text)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
