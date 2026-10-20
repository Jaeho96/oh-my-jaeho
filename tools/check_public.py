#!/usr/bin/env python3
"""공개 레포에 올라가면 안 되는 값을 찾는다. 하나라도 있으면 종료코드 1.

검사 대상: git 이 추적하거나 커밋하려는 파일(없으면 레포 전체). *.local.* 와 이 파일은 뺀다.
기본 패턴(토큰·이메일·Slack/Notion ID·홈 절대 경로)에 더해, 회사·사람 이름처럼 나만 아는 낱말은
private-terms.local.txt(한 줄에 하나, 커밋 안 됨)에 적어 두면 함께 찾는다.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

PATTERNS = {
    "홈 절대 경로": r"/Users/[^/\s\"'<]+/|/home/[^/\s\"'<]+/",
    "이메일": r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
    "Slack ID": r"\b[CUW](?=[A-Z0-9]*\d)[A-Z0-9]{8,11}\b",
    "Notion·UUID ID": r"\b[0-9a-f]{32}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    "토큰": r"xox[abprs]-[\w-]+|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w+|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----",
}
ALLOW = [r"noreply@", r"@example\.(com|org)", r"you@"]


def files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=REPO, capture_output=True, text=True, check=True).stdout.split("\n")
        paths = [REPO / f for f in out if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = [p for p in REPO.rglob("*") if ".git" not in p.parts]
    return [p for p in paths if p.is_file() and not p.is_symlink() and ".local." not in p.name and p.resolve() != SELF]


def main() -> int:
    pats = dict(PATTERNS)
    terms = REPO / "private-terms.local.txt"
    if terms.exists():
        words = [w.strip() for w in terms.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
        if words:
            pats["비공개 낱말"] = "|".join(re.escape(w) for w in words)
    compiled = {k: re.compile(v) for k, v in pats.items()}
    allow = re.compile("|".join(ALLOW))
    hits = 0
    for p in files():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for kind, rx in compiled.items():
                for m in rx.finditer(line):
                    if allow.search(m.group(0)):
                        continue
                    hits += 1
                    print(f"{p.relative_to(REPO)}:{n}: [{kind}] {m.group(0)[:60]}")
    if not terms.exists():
        print("(참고) private-terms.local.txt 가 없어 회사·사람 이름은 검사하지 않았다.")
    print(f"\n{'통과' if not hits else f'{hits}건 — 공개 전에 고칠 것'}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
