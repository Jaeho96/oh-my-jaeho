#!/usr/bin/env python3
"""이 기기에 공유 LLM Wiki 저장소를 준비한다 — 없으면 clone, 있으면 원격이 맞는지 확인한다.

  python3 tools/wiki_setup.py --repo https://github.com/<계정>/<저장소>.git [--dir <위키 폴더>] [--blocks] [--apply]

기본은 미리보기. 이미 있는 위키 폴더가 git 저장소가 아니면 덮지 않고 멈춘다(손으로 합친다).
--blocks: 위키의 templates/agent-instructions-block.md 를 ~/.claude/CLAUDE.md · ~/.codex/AGENTS.md 에 넣는다.
          SHARED-LLM-WIKI 마커 블록이 이미 있으면 건드리지 않고 다른지만 알린다(원본은 .bak-<시각> 으로 남김).
동기화 자체는 Claude Code·Codex 훅이 tools/wiki_sync.py --detach 로 한다(세션 시작·작업 끝). launchd 는 쓰지 않는다 —
macOS 개인정보 보호가 백그라운드 작업의 ~/Documents 접근을 막는다(2026-10-20 실측).
"""
import argparse
import os
import subprocess
import sys
import time


def norm(url):
    url = url.rstrip("/")
    return url[:-4] if url.endswith(".git") else url


START, END = "<!-- SHARED-LLM-WIKI:START -->", "<!-- SHARED-LLM-WIKI:END -->"


def install_blocks(wiki, apply):
    src = os.path.join(wiki, "templates", "agent-instructions-block.md")
    if not os.path.exists(src):
        print("지침 블록 원본 없음:", src)
        return 1
    with open(src, encoding="utf-8") as f:
        block = f.read().strip() + "\n"
    for path in (os.path.expanduser("~/.claude/CLAUDE.md"), os.path.expanduser("~/.codex/AGENTS.md")):
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if START in text:
            cur = text[text.index(START):text.index(END) + len(END)].strip() + "\n"
            print("%s: 블록 있음%s" % (path, "" if cur == block else " — 원본과 다르다(손으로 확인)"))
            continue
        print(("넣음  " if apply else "예정 넣음  ") + path)
        if apply:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if text:
                with open(path + ".bak-" + time.strftime("%Y%m%d%H%M%S"), "w", encoding="utf-8") as f:
                    f.write(text)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.rstrip("\n") + ("\n\n" if text else "") + block)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dir", default="~/Documents/Obsidian Vault/LLM Wiki")
    ap.add_argument("--blocks", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    wiki = os.path.expanduser(a.dir)

    if os.path.isdir(os.path.join(wiki, ".git")):
        origin = subprocess.run(["git", "-C", wiki, "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
        if norm(origin) != norm(a.repo):
            sys.exit("위키 저장소의 origin(%s)이 --repo 와 다르다 — 손으로 확인한다" % (origin or "없음"))
        print("위키 저장소 있음 · origin 일치 —", wiki)
    elif os.path.exists(wiki) and os.listdir(wiki):
        sys.exit("위키 폴더가 이미 있는데 git 저장소가 아니다: %s — 내용을 옮긴 뒤 다시 한다" % wiki)
    else:
        print(("clone  " if a.apply else "예정 clone  ") + "%s → %s" % (a.repo, wiki))
        if a.apply:
            os.makedirs(os.path.dirname(wiki), exist_ok=True)
            if subprocess.run(["git", "clone", a.repo, wiki]).returncode:
                sys.exit("clone 실패")
    if a.blocks and (a.apply or os.path.isdir(wiki)):
        install_blocks(wiki, a.apply)
    if not a.apply:
        print("미리보기 — 하려면 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
