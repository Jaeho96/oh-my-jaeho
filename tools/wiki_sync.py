#!/usr/bin/env python3
"""공유 LLM Wiki 폴더를 git 원격과 맞춘다 (2026-10-20).

1) 바뀐 파일을 커밋 2) 원격을 rebase 로 받기 3) 올리기.
위키는 「새 파일 추가」가 대부분이라 충돌이 드물다. 충돌·실패면 되돌려 두고(rebase 중단) 위키 폴더의 `.sync-error` 에
사유를 적고 macOS 알림을 띄운 뒤 다음 회차에 다시 한다. 성공하면 `.sync-error` 를 지운다.
올리기가 실패하면 5 · 20 · 60초 쉬며 다시 받고 올린다. GitHub 500 · DNS 같은 일시 오류는 안 올린 커밋이
WIKI_SYNC_STUCK_MIN 분(기본 30)보다 오래 쌓였을 때만 알린다(2026-11-04).

부르는 곳: Claude Code·Codex 의 SessionStart·Stop 훅(`--detach`). launchd 는 쓰지 않는다 — macOS 개인정보 보호가
백그라운드 작업의 ~/Documents 접근을 막는다(2026-10-20 실측 「Operation not permitted」). 훅은 터미널의 권한을 물려받는다.
--detach: 뒤에서 돌고 바로 `{}` 를 내고 끝난다(세션을 기다리게 하지 않는다).
바뀐 게 없고 마지막 성공이 WIKI_SYNC_MIN_GAP 초(기본 120) 안이면 받기도 건너뛴다.

환경 변수: WIKI_DIR(기본 ~/Documents/Obsidian Vault/LLM Wiki) · WIKI_HOST(커밋에 적을 기기 이름, 기본 LocalHostName)
Python 3.9 에서도 돈다.
"""
import datetime
import fcntl
import os
import re
import subprocess
import sys
import time

WIKI = os.path.expanduser(os.environ.get("WIKI_DIR", "~/Documents/Obsidian Vault/LLM Wiki"))
OMJ = os.path.expanduser("~/.omj")
LOG = os.path.join(OMJ, "wiki-sync.log")
ERR = os.path.join(WIKI, ".sync-error")
GIT = "/usr/bin/git" if os.path.exists("/usr/bin/git") else "git"
LAST_OK = os.path.join(OMJ, "wiki-sync.last")
MIN_GAP = int(os.environ.get("WIKI_SYNC_MIN_GAP", "120"))
# 올리기 실패 뒤 다시 받고 올리기 전에 쉬는 초. 뒤에서 도니 세션은 기다리지 않는다.
RETRY_WAITS = [float(x) for x in os.environ.get("WIKI_SYNC_RETRY_WAITS", "5,20,60").split(",") if x.strip()]
# 일시 오류(GitHub 500 · DNS · 끊김)는 안 올린 커밋이 이 분보다 오래됐을 때만 알린다. 다음 회차가 어차피 다시 한다.
STUCK_MIN = float(os.environ.get("WIKI_SYNC_STUCK_MIN", "30"))
# 인증(403) · 권한 · 규칙 위반은 사람이 손봐야 하니 넣지 않는다.
TRANSIENT = re.compile(r"Internal Server Error|Bad Gateway|Service Unavailable|(?:HTTP|returned error:) 50[0-4]|"
                       r"Could not resolve host|Failed to connect|timed out|Connection reset|early EOF", re.I)


def git(*args):
    p = subprocess.run([GIT, "-C", WIKI] + list(args), capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def host():
    for cmd in (["scutil", "--get", "LocalHostName"], ["hostname", "-s"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
            if out:
                return out
        except OSError:
            pass
    return "unknown"


def log(line):
    os.makedirs(OMJ, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG, encoding="utf-8") as f:
            old = f.readlines()[-499:]
    except OSError:
        old = []
    with open(LOG, "w", encoding="utf-8") as f:
        f.writelines(old + ["%s %s\n" % (stamp, line)])


def reason(detail):
    """git 출력에서 이유가 담긴 줄을 고른다. 「failed to push some refs」는 결과일 뿐 이유가 아니다(2026-11-04)."""
    lines = [l.strip() for l in (detail or "").splitlines() if l.strip()]
    lines = [l for l in lines if "failed to push some refs" not in l and not l.startswith("To ")] or lines
    for key in ("[rejected]", "[remote rejected]", "GH0", "remote: error", "fatal:", "error:", "Error"):
        for l in lines:
            if key in l:
                return l
    return lines[-1] if lines else "사유 없음"


def flat(detail):
    return " / ".join(l.strip() for l in (detail or "").splitlines() if l.strip())[-600:]


def unpushed_age_min():
    """안 올린 커밋 중 가장 오래된 것의 나이(분). 없으면 0."""
    rc, out = git("log", "@{u}..HEAD", "--format=%ct")
    stamps = [int(x) for x in out.split()] if rc == 0 and out else []
    return (time.time() - min(stamps)) / 60 if stamps else 0


def fail(what, detail):
    msg = "%s 실패 — %s" % (what, reason(detail))
    with open(ERR, "w", encoding="utf-8") as f:
        f.write("%s\n%s\n\n%s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), msg, detail[-2000:]))
    # 일시 오류는 막힌 지 STUCK_MIN 분이 안 됐으면 알리지 않는다(2026-11-04, GitHub 500 으로 알림이 연달아 뜸)
    quiet = TRANSIENT.search(detail or "") and unpushed_age_min() < STUCK_MIN
    log("%s %s | %s" % ("WARN" if quiet else "ERROR", msg, flat(detail)))   # .sync-error 는 성공하면 지워지니 전체 출력은 로그에
    if not quiet and not os.environ.get("WIKI_SYNC_QUIET"):
        try:
            subprocess.run(["osascript", "-e", 'display notification "%s" with title "LLM Wiki 동기화"'
                            % msg.replace('"', "'")[:180]], capture_output=True)
        except OSError:
            pass
    return 1


def sync():
    if not os.path.isdir(os.path.join(WIKI, ".git")):
        return fail("준비", "git 저장소가 아니다: %s" % WIKI)
    if os.path.isdir(os.path.join(WIKI, ".git", "rebase-merge")) or os.path.isdir(os.path.join(WIKI, ".git", "rebase-apply")):
        git("rebase", "--abort")
    git("add", "-A")
    rc, _ = git("diff", "--cached", "--quiet")
    _, unpushed = git("rev-list", "--count", "@{u}..HEAD")
    if (rc == 0 and unpushed.strip() in ("", "0") and os.path.exists(LAST_OK)
            and os.path.getmtime(LAST_OK) > datetime.datetime.now().timestamp() - MIN_GAP):
        return 0              # 바뀐 것도, 안 올린 커밋도 없고 방금 받았다 — 손으로 만든 커밋은 건너뛰지 않는다(2026-10-20)
    if rc != 0:
        _, names = git("diff", "--cached", "--name-only")
        n = len([x for x in names.splitlines() if x])
        rc, out = git("commit", "-q", "-m", "wiki: %s %s · %d개" % (
            os.environ.get("WIKI_HOST") or host(), datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), n))
        if rc != 0:
            return fail("커밋", out)
    rc, out = git("pull", "--rebase", "--autostash", "-q")
    if rc != 0:
        git("rebase", "--abort")
        return fail("받기(충돌일 수 있음)", out)
    rc, ahead = git("rev-list", "--count", "@{u}..HEAD")
    if rc == 0 and ahead.strip() not in ("", "0"):
        rc, out = git("push", "-q")
        # 2026-11-04 GitHub 이 몇 분씩 「remote rejected … Internal Server Error」를 내다 저절로 풀렸다 — 쉬었다 다시 받고 올린다
        for n, wait in enumerate(RETRY_WAITS, 1):
            if rc == 0:
                break
            log("WARN 올리기 실패, %g초 뒤 다시(%d/%d) | %s" % (wait, n, len(RETRY_WAITS), flat(out)))
            time.sleep(wait)
            rc2, out2 = git("pull", "--rebase", "--autostash", "-q")
            if rc2 != 0:
                git("rebase", "--abort")
                return fail("받기(충돌일 수 있음)", out2)
            rc, out = git("push", "-q")
        if rc != 0:
            return fail("올리기", out)
    if os.path.exists(ERR):
        os.remove(ERR)
    with open(LAST_OK, "w") as f:
        f.write(datetime.datetime.now().isoformat())
    log("ok")
    return 0


def locked_sync():
    os.makedirs(OMJ, exist_ok=True)
    with open(os.path.join(OMJ, "wiki-sync.lock"), "a+") as lk:
        try:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0          # 다른 세션의 동기화가 돌고 있다
        return sync()


def main():
    if "--detach" not in sys.argv:
        return locked_sync()
    print("{}", flush=True)   # 훅 출력 — 아무 지시도 하지 않는다
    if os.fork() > 0:
        return 0
    os.setsid()
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):      # 훅 실행기가 파이프 끝을 기다리지 않게
        os.dup2(null, fd)
    try:
        rc = locked_sync()
    except Exception as e:    # 뒤에서 죽으면 아무도 모른다 — 기록은 남긴다
        log("ERROR 예외 %r" % (e,))
        rc = 1
    os._exit(rc)


if __name__ == "__main__":
    sys.exit(main())
