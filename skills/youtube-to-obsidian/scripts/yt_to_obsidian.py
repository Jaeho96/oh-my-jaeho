#!/usr/bin/env python3
"""
유튜브 채널 영상 자막 → Obsidian 볼트 적재

사용법:
    python3 yt_to_obsidian.py                  # 새 영상만 처리 (증분)
    python3 yt_to_obsidian.py --limit 5        # 최대 5개
    python3 yt_to_obsidian.py --all            # 상태 무시하고 전체 재처리
    python3 yt_to_obsidian.py --dry-run        # 목록만 확인
    python3 yt_to_obsidian.py --verbose        # 오류 전문 출력
    python3 yt_to_obsidian.py --cookies-from-browser chrome   # 멤버십 영상 포함

필요: brew install yt-dlp
"""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────
CHANNEL_URL = "https://www.youtube.com/@codingpe/videos"

# 볼트 루트 — 반드시 실존해야 함. 없으면 만들지 않고 즉시 종료한다.
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT", str(Path.home() / "Documents/Obsidian Vault")))

# 볼트 루트 기준 상대 경로. 채널명 폴더는 실행 시 자동으로 붙는다.
VAULT_SUBPATH = os.environ.get("YT_VAULT_SUBPATH", "나의 지식그래프/기술지식/유튜브")

# 자막 선택 우선순위. '-orig'(원본 자동자막)를 번역 트랙보다 앞에 둔다.
#   ko-orig : 한국어 원본 자동자막
#   ko      : 한국어 번역 트랙 (원본이 영어인 영상이면 기계번역)
PREFER_LANGS = ["ko-orig", "en-orig", "ko", "en"]

TAGS = ["유튜브", "자막"]
DEFAULT_LIMIT = 20

# 자막이 아직 없는 영상 재시도 정책 (자동자막은 업로드 후 수 시간 뒤 생성됨)
RETRY_AFTER_DAYS = 3
MAX_TRIES = 5

# 요청 간 대기 (초). YouTube 자막 엔드포인트는 429를 잘 던진다.
SLEEP_BETWEEN_VIDEOS = 2.0

# ── 요약 (--summarize) ───────────────────────────────────────
# 로컬 claude CLI 를 헤드리스로 호출한다. 별도 API 키가 필요 없다.
CLAUDE_BIN = str(Path.home() / ".local/bin/claude")
SUMMARY_MODEL = "claude-sonnet-5-5"
# Sonnet 5.5 는 settings.json 의 top-level effortLevel 을 따르지 않으니 명시한다. 정리는 원문
# 길이만큼 출력하는 작업이라 높은 effort 는 과하다. --disallowed-tools 가 가변 인자라 그 앞에 둔다.
SUMMARY_EFFORT = "medium"

# 이 문구가 그대로 남아 있는 노트만 채운다.
# 사람이 직접 쓴 요약은 절대 덮어쓰지 않는다.
SUMMARY_PLACEHOLDER = "_(직접 작성하거나 LLM으로 채우는 영역)_"
CLEAN_PLACEHOLDER = "_(원문 정리 전 — `--clean` 으로 채워집니다)_"

# 정리본은 요약과 달리 '입력 길이만큼' 출력이 나온다. 실측 자막은 중앙값 3.5천 자,
# 최대 8.4만 자라 긴 영상은 한 번에 뱉을 수 없다. 청크로 잘라 이어붙인다.
CLEAN_CHUNK_CHARS = 6_000
CLEAN_TIMEOUT = 600

# 프롬프트에 넣을 자막 최대 길이. 초과분은 잘라내고 그 사실을 알린다.
SUMMARY_MAX_CHARS = 60_000
# 요약도 정리와 같은 600초로 둔다. 300초에서는 6천 자 정리본 요약이 간헐적으로
# 타임아웃됐다 — 호출 자체는 정상인데 제한만 짧았다.
SUMMARY_TIMEOUT = 600
# ─────────────────────────────────────────────────────────────

VERBOSE = False


def log_err(msg: str) -> None:
    if VERBOSE:
        print(msg, file=sys.stderr)


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """yt-dlp 실행. check=False면 non-zero도 그대로 반환한다."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(
            f"명령 실패 (exit {p.returncode}): {' '.join(cmd)}\n{p.stderr.strip()}"
        )
    return p


def yt_base(cookies: str | None) -> list[str]:
    base = ["yt-dlp", "--no-warnings", "--socket-timeout", "30",
            "--retries", "3", "--sleep-requests", "1"]
    if cookies:
        base += ["--cookies-from-browser", cookies]
    return base


def list_channel_videos(url: str, cookies: str | None) -> list[dict]:
    """
    채널 영상 목록 조회.

    --ignore-errors 를 쓰지 않는다: 개별 오류를 무시하면 부분/빈 목록이
    성공처럼 보이고, 그 상태로 "처리 대상 0개"라며 정상 종료해버린다.
    """
    p = run(yt_base(cookies) + [
        "--flat-playlist", "--print", "%(id)s\t%(title)s", url,
    ])

    videos, malformed = [], 0
    for line in p.stdout.strip().splitlines():
        if "\t" not in line:
            malformed += 1
            continue
        vid, title = line.split("\t", 1)
        vid, title = vid.strip(), title.strip()
        if not vid or vid == "NA":
            malformed += 1
            continue
        videos.append({"id": vid, "title": title})

    if malformed:
        print(f"  ⚠️  형식이 어긋난 줄 {malformed}개 무시됨")
    if not videos:
        raise RuntimeError("채널 목록이 비어 있습니다. URL 또는 네트워크를 확인하세요.")
    return videos


def resolve_channel_dir_local(parent: Path, want: str | None) -> Path:
    """
    디스크에서 채널 폴더를 찾는다. 네트워크를 쓰지 않는다.

    --summarize 는 로컬 노트만 다루므로 YouTube 왕복이 필요 없다.
    채널 조회를 거치게 하면 네트워크 장애·채널명 변경·429 때문에
    디스크에 있는 노트를 요약하지 못하게 된다.
    """
    if want:
        d = parent / safe_filename(want)
        if not d.is_dir():
            raise RuntimeError(f"채널 폴더가 없습니다: {d}")
        return d
    if not parent.is_dir():
        raise RuntimeError(f"폴더가 없습니다: {parent}\n  먼저 적재를 실행하세요.")

    dirs = sorted(p for p in parent.iterdir() if p.is_dir())
    if not dirs:
        raise RuntimeError(f"채널 폴더가 없습니다: {parent}\n  먼저 적재를 실행하세요.")
    if len(dirs) > 1:
        names = "\n".join(f"    - {d.name}" for d in dirs)
        raise RuntimeError(
            f"채널 폴더가 여러 개입니다. --channel-dir 로 지정하세요:\n{names}")
    return dirs[0]


def resolve_channel_name(url: str, cookies: str | None) -> str:
    """
    채널명 조회. --flat-playlist 에서는 %(channel)s 가 NA 로 나오므로
    playlist 메타데이터 필드를 쓴다.
    """
    p = run(yt_base(cookies) + [
        "--flat-playlist", "--playlist-items", "1",
        "--print", "%(playlist_channel,playlist_uploader,channel,uploader|)s", url,
    ], check=False)

    # check=False 로 두면서 stderr 를 버리면, 네트워크 장애·429·쿠키 오류·잘못된
    # URL 이 전부 "채널명을 확인할 수 없습니다" 한 줄로 뭉개진다. 채널 모드의
    # 첫 단계라 여기서 원인을 감추면 그 뒤 진단이 전부 막힌다.
    if p.returncode != 0:
        err = p.stderr.strip()
        log_err(f"채널 조회 실패 (exit {p.returncode}):\n{err}")
        first = next((l for l in err.splitlines() if l.strip()), "원인 불명")
        raise RuntimeError(
            f"채널 조회 실패: {first[:300]}"
            + ("" if VERBOSE else "\n  전문을 보려면 --verbose 를 붙이세요.")
        )

    name = (p.stdout.strip().splitlines() or [""])[0].strip()
    if not name or name == "NA":
        log_err(f"채널명 필드가 비어 있음. stdout={p.stdout[:200]!r}\n"
                f"stderr={p.stderr.strip()[:500]}")
        raise RuntimeError(f"채널명을 확인할 수 없습니다 (URL 확인 필요): {url}")
    return name


# ─────────────────────────────────────────────────────────────
# VTT 파싱
# ─────────────────────────────────────────────────────────────

# WebVTT 큐 태그만 제거한다. 임의의 <...> 를 전부 지우면
# "<T> for generics" 처럼 실제로 발화된 텍스트가 사라진다.
_TIMING_TAG = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d{3}>")
_CUE_TAG = re.compile(r"</?(?:c|v|i|b|u|ruby|rt|lang)(?:[.\s][^>]*)?>", re.IGNORECASE)

_META_PREFIXES = (
    "WEBVTT", "Kind:", "Language:", "NOTE", "STYLE", "REGION",
    "Region:", "X-TIMESTAMP-MAP",
)


def parse_vtt(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    lines: list[str] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith(_META_PREFIXES):
            continue
        if "-->" in line:
            continue
        if line.isdigit():
            continue

        line = _TIMING_TAG.sub("", line)
        line = _CUE_TAG.sub("", line)
        line = html.unescape(line)          # &amp; &quot; &lt; &nbsp; 등
        line = line.replace(" ", " ").strip()
        if line:
            lines.append(line)

    # 롤링 자막 중복 제거.
    #   - 완전히 같은 줄이 이어지면 버린다.
    #   - 직전 줄이 현재 줄의 접두사인 경우만 '이어붙기'로 보고 대체하는데,
    #     "네" → "네 그렇습니다" 같은 정상 발화까지 삼키지 않도록
    #     직전 줄이 충분히 길 때만 적용한다.
    MIN_ROLL_PREFIX = 10

    deduped: list[str] = []
    for line in lines:
        if deduped and line == deduped[-1]:
            continue
        prev = deduped[-1] if deduped else ""
        if (prev and len(prev) >= MIN_ROLL_PREFIX
                and line.startswith(prev) and len(line) > len(prev)):
            deduped[-1] = line
            continue
        deduped.append(line)

    return re.sub(r"\s+", " ", " ".join(deduped)).strip()


# ─────────────────────────────────────────────────────────────
# 자막 취득
# ─────────────────────────────────────────────────────────────

MEMBERS_ONLY = re.compile(r"members[- ]only|available to this channel's members", re.I)


def choose_sub_lang(meta: dict) -> tuple[str, bool] | None:
    """
    받을 자막 트랙 하나를 고른다. -> (lang, is_manual) 또는 None

    수동 자막을 최우선으로 하고, 없으면 자동자막 중 PREFER_LANGS 순서를 따른다.
    번역 트랙(ko)보다 원본(ko-orig)이 먼저 오도록 PREFER_LANGS 를 구성해 둔다.
    """
    manual = meta.get("subtitles") or {}
    auto = meta.get("automatic_captions") or {}

    for lang in PREFER_LANGS:
        if lang in manual:
            return lang, True
    for lang in PREFER_LANGS:
        if lang in auto:
            return lang, False

    # PREFER_LANGS 에 없더라도 원본 자동자막이 있으면 그걸 쓴다.
    for lang in auto:
        if lang.endswith("-orig"):
            return lang, False
    return None


def fetch_meta(vid: str, cookies: str | None) -> dict:
    """
    메타데이터만 조회한다. -> {"status": "ok", "meta": …}
                            | {"status": "unavailable", "reason": …}

    자막 다운로드와 분리해 둔다. 두 가지 이유가 있다.
      1) 이미 처리한 영상의 자막을 다시 받지 않으려면 채널·상태를 먼저 알아야 한다.
      2) 자막이 없을 때도 채널을 알아야 '올바른 채널'의 보류 기록을 남길 수 있다.
    """
    url = f"https://www.youtube.com/watch?v={vid}"
    p = run(yt_base(cookies) + ["--skip-download", "--dump-json", url], check=False)
    if p.returncode != 0:
        err = p.stderr.strip()
        log_err(f"[{vid}] 메타 조회 실패:\n{err}")
        if MEMBERS_ONLY.search(err):
            return {"status": "unavailable", "reason": "멤버십 전용"}
        raise RuntimeError(err)
    return {"status": "ok", "meta": json.loads(p.stdout.strip().splitlines()[0])}


def fetch_subs(vid: str, meta: dict, workdir: Path, cookies: str | None) -> dict:
    """
    자막을 내려받는다. -> {"status": "ok", "vtt":…, "lang":…, "is_manual":…}
                        | {"status": "no_subs", "reason": …}

    언어는 하나만 요청한다. 여러 언어를 한 번에 요청하면 그중 하나가 429 를
    맞는 순간 yt-dlp 가 non-zero 로 끝나서, 이미 받은 자막까지 버려진다.
    성공 판정은 exit code 가 아니라 .vtt 존재로 한다.
    """
    chosen = choose_sub_lang(meta)
    if chosen is None:
        return {"status": "no_subs", "reason": "자막 트랙 없음"}
    lang, is_manual = chosen

    # --no-simulate 필수: --dump-json 은 simulate 를 켜므로 --write-subs 가 무시된다.
    sub_flag = "--write-subs" if is_manual else "--write-auto-subs"
    p = run(yt_base(cookies) + [
        "--skip-download", "--no-simulate",
        sub_flag, "--sub-langs", lang,
        "--sub-format", "vtt", "--convert-subs", "vtt",
        "-o", str(workdir / "%(id)s.%(ext)s"),
        f"https://www.youtube.com/watch?v={vid}",
    ], check=False)

    found = sorted(workdir.glob(f"{vid}.*.vtt"))
    if not found:
        log_err(f"[{vid}] 자막 다운로드 실패 (exit {p.returncode}):\n{p.stderr.strip()}")
        return {"status": "no_subs", "reason": f"자막 다운로드 실패 ({lang})"}
    if p.returncode != 0:
        log_err(f"[{vid}] exit {p.returncode} 였지만 자막은 확보됨: {found[0].name}")

    return {"status": "ok", "vtt": found[0], "lang": lang, "is_manual": is_manual}


# ─────────────────────────────────────────────────────────────
# 노트 생성
# ─────────────────────────────────────────────────────────────

def y(value) -> str:
    """
    YAML 스칼라 안전 직렬화.
    JSON 문자열은 유효한 YAML 큰따옴표 스칼라이므로, 따옴표·역슬래시·개행이
    모두 이스케이프된다. 제목으로 프론트매터 키를 주입하는 것도 막힌다.
    """
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def safe_filename(title: str) -> str:
    name = re.sub(r'[\\/:*?"<>|#\[\]^]', "", title)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80] or "untitled"


def safe_wikilink(text: str) -> str:
    """[[...]] 안에서 링크를 깨뜨리는 문자 제거."""
    return re.sub(r"[\[\]|#^]", "", str(text)).strip() or "unknown"


def build_note(meta: dict, transcript: str, lang: str, is_manual: bool,
               created: str | None) -> str:
    vid = meta["id"]
    title = meta.get("title") or vid
    upload = meta.get("upload_date") or ""
    pub = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else ""
    channel = meta.get("channel") or meta.get("uploader") or ""
    dur = meta.get("duration") or 0
    duration = f"{dur // 3600:02d}:{dur % 3600 // 60:02d}:{dur % 60:02d}"
    url = f"https://www.youtube.com/watch?v={vid}"
    today = date.today().isoformat()

    tag_lines = "\n".join(f"  - {t}" for t in TAGS)

    words = transcript.split()
    chunks = [" ".join(words[i:i + 120]) for i in range(0, len(words), 120)]
    body = "\n\n".join(chunks) if chunks else "_자막 내용 없음_"

    return f"""---
title: {y(title)}
created: {created or today}
updated: {today}
published: {pub}
kind: youtube-transcript
channel: {y(channel)}
video_id: {vid}
url: {url}
duration: {duration}
lang: {lang}
caption_source: {"manual" if is_manual else "auto"}
tags:
{tag_lines}
source: {y(url)}
---

# {title}

> [!info]
> 채널: {channel} · 업로드: {pub or "미상"} · 길이: {duration}
> 원본: [YouTube에서 보기]({url})

> [!warning]
> 자동 추출한 원문 자막입니다({"수동" if is_manual else "자동"} · `{lang}`).
> 구두점과 오탈자가 정제되지 않았으니 인용 시 원본 영상을 확인하세요.

---

## 요약

{SUMMARY_PLACEHOLDER}

---

## 정리본

{CLEAN_PLACEHOLDER}

---

## 자막 원문

{body}

---

# Related Notes

- [[{safe_wikilink(channel)}]]
"""


def existing_created(path: Path) -> str | None:
    """재적재 시 최초 created 값을 보존한다."""
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:15]:
            if line.startswith("created:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


# ─────────────────────────────────────────────────────────────
# 요약 채우기
# ─────────────────────────────────────────────────────────────

# 요약 다음 섹션은 정리본이지만, 정리본 섹션이 아직 없는 구버전 노트도 받아준다.
_SUMMARY_BLOCK = re.compile(
    r"(## 요약\n\n)(.*?)(\n\n---\n\n## (?:정리본|자막 원문))", re.DOTALL)
_CLEAN_BLOCK = re.compile(r"(## 정리본\n\n)(.*?)(\n\n---\n\n## 자막 원문)", re.DOTALL)
_TRANSCRIPT_BLOCK = re.compile(r"## 자막 원문\n\n(.*?)\n\n---\n\n# Related Notes", re.DOTALL)
_UPDATED_LINE = re.compile(r"^updated: .*$", re.MULTILINE)
_FENCE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)

SUMMARY_PROMPT = """\
아래는 기술 유튜브 영상의 자동 생성 자막 원문이다. 이것을 Obsidian 학습 노트의
'요약' 섹션으로 정리하라.

제약:
- 자막은 자동 생성이라 구두점이 없고 오탈자·인식 오류가 있다. 문맥으로 보정해 읽어라.
- 자막에 없는 내용을 추측해 채우지 마라. 근거가 약하면 그 항목을 생략하라.
- 출력은 마크다운 본문만. 인사말·서두·"요약하겠습니다" 같은 말 금지.
- 최상위 제목(#)이나 '## 요약' 헤딩을 다시 쓰지 마라. 아래 구조로 바로 시작하라.

구조:
**핵심**
- 영상의 논지를 3~5개 불릿으로. 각 불릿은 한 문장.

**다룬 개념**
- `용어` — 영상에서 설명한 방식대로 한 줄 설명. 4~8개.

**실무 적용**
- 바로 써먹을 수 있는 판단·절차를 1~3개. 영상에 근거가 없으면 이 섹션 전체를 생략.

---
영상 제목: {title}
채널: {channel}
길이: {duration}
---

{transcript}
"""


def summarize_transcript(title: str, channel: str, duration: str,
                         transcript: str) -> str:
    """claude CLI 를 헤드리스로 호출해 요약 마크다운을 받는다."""
    truncated = len(transcript) > SUMMARY_MAX_CHARS
    body = transcript[:SUMMARY_MAX_CHARS]
    if truncated:
        body += "\n\n[이 뒤는 길이 제한으로 잘렸다. 잘린 부분은 요약에 반영하지 마라.]"

    prompt = SUMMARY_PROMPT.format(
        title=title, channel=channel, duration=duration, transcript=body)

    p = subprocess.run(
        [CLAUDE_BIN, "-p", "--model", SUMMARY_MODEL, "--effort", SUMMARY_EFFORT,
         "--disallowed-tools", "Bash", "Read", "Write", "Edit", "WebFetch", "WebSearch"],
        input=prompt, capture_output=True, text=True, timeout=SUMMARY_TIMEOUT,
    )
    if p.returncode != 0:
        raise RuntimeError(f"claude 호출 실패 (exit {p.returncode}): {p.stderr.strip()}")

    out = p.stdout.strip()
    m = _FENCE.match(out)              # 코드펜스로 감싸 오는 경우 벗긴다
    if m:
        out = m.group(1).strip()
    if len(out) < 40:
        raise RuntimeError(f"요약이 비었거나 너무 짧습니다: {out[:80]!r}")

    out = sanitize_llm_output(out)

    if truncated:
        out += ("\n\n> [!note]\n> 자막이 길어 앞부분 "
                f"{SUMMARY_MAX_CHARS:,}자만 요약에 사용했습니다.")
    return out


def read_frontmatter(text: str) -> dict:
    fm = {}
    for line in text.splitlines()[1:25]:
        if line == "---":
            break
        if ": " in line:
            k, v = line.split(": ", 1)
            fm[k.strip()] = v.strip().strip('"')
    return fm


def write_note_atomic(path: Path, text: str) -> None:
    """임시파일 + rename. 중간에 끊겨도 원본 노트가 깨지지 않는다."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".note-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


CLEAN_PROMPT = """\
아래는 기술 유튜브 영상의 자동 생성 자막 조각이다. 읽을 수 있는 글로 손봐라.

해야 할 것:
- 문장을 끊고 구두점을 넣어라.
- 문단을 나눠라. 화제가 바뀌는 지점에서 빈 줄로 구분한다.
- 음성 인식 오류가 명백한 단어는 문맥에 맞게 고쳐라.
  (기술 용어·영문 약어가 한글로 잘못 적힌 경우가 많다)
- 의미 없는 말버릇("어", "음", "그", "인제")은 덜어내라.

절대 하지 말 것:
- 요약하지 마라. 내용을 줄이거나 생략하지 마라. 분량이 원문과 비슷해야 한다.
- 원문에 없는 내용을 보태지 마라.
- 확신이 없는 고유명사·숫자는 그대로 두어라. 추측해서 바꾸지 마라.
- 마크다운 헤딩(#), 구분선(---), 목록 기호를 새로 만들지 마라. 문단 글로만 써라.
- 인사말·설명·"정리하면" 같은 말 없이, 손본 본문만 출력하라.

{position}
아래는 이 영상에 대해 '확실히 아는' 정보다. 자막이 이것을 잘못 받아 적었으면
(예: 채널명·발표자 이름이 엉뚱한 단어로 인식된 경우) 이 표기로 고쳐라.
영상 제목: {title}
채널명: {channel}
---

{chunk}
"""


def call_claude(prompt: str, timeout: int) -> str:
    p = subprocess.run(
        [CLAUDE_BIN, "-p", "--model", SUMMARY_MODEL, "--effort", SUMMARY_EFFORT,
         "--disallowed-tools", "Bash", "Read", "Write", "Edit", "WebFetch", "WebSearch"],
        input=prompt, capture_output=True, text=True, timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError(f"claude 호출 실패 (exit {p.returncode}): {p.stderr.strip()}")
    out = p.stdout.strip()
    m = _FENCE.match(out)
    if m:
        out = m.group(1).strip()
    return out


_HRULE = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$\n?", re.MULTILINE)


def sanitize_llm_output(out: str) -> str:
    """
    모델 출력을 노트에 넣기 전에 손본다.

    자막은 신뢰할 수 없는 외부 텍스트이고 프롬프트에 그대로 들어가므로,
    모델이 유도되어 노트 구조를 흉내 낼 수 있다. 다만 위험도가 다르다.

    - 구조 헤딩은 **거부**한다. 섹션 정규식이 '첫' 매치를 잡기 때문에
      가짜 헤딩이 들어가면 이후 추출 지점이 통째로 어긋난다.
    - 단독 구분선은 **제거만** 한다. 섹션 종결 패턴은 `---` 뒤에 헤딩이
      따라와야 성립하므로 단독 `---` 은 구조를 깨지 않는다. 이것 때문에
      원문 길이만큼 나온 정리 결과를 통째로 버리는 건 손해가 더 크다.
    """
    for bad in ("## 요약", "## 정리본", "## 자막 원문", "# Related Notes"):
        if bad in out:
            raise RuntimeError(f"출력에 노트 구조 헤딩이 섞여 있습니다: {bad!r}")

    cleaned, n = _HRULE.subn("", out)
    if n:
        log_err(f"  (단독 구분선 {n}개 제거)")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def chunk_text(text: str, size: int) -> list[str]:
    """공백 경계에서 잘라 청크로 나눈다."""
    words, chunks, cur, n = text.split(), [], [], 0
    for w in words:
        if n + len(w) + 1 > size and cur:
            chunks.append(" ".join(cur))
            cur, n = [], 0
        cur.append(w)
        n += len(w) + 1
    if cur:
        chunks.append(" ".join(cur))
    return chunks or [""]


def clean_transcript(title: str, channel: str, transcript: str) -> str:
    """자막 원문을 읽을 수 있는 글로 손본다. 길면 청크로 나눠 처리한다."""
    chunks = chunk_text(transcript, CLEAN_CHUNK_CHARS)
    out_parts = []
    for i, ch in enumerate(chunks, 1):
        pos = (f"(전체 {len(chunks)}조각 중 {i}번째 조각이다. "
               f"앞뒤가 잘려 있을 수 있으니 이 조각만 손보고, "
               f"도입·마무리 문구를 새로 지어내지 마라.)"
               if len(chunks) > 1 else "")
        part = call_claude(
            CLEAN_PROMPT.format(position=pos, title=title, channel=channel, chunk=ch),
            CLEAN_TIMEOUT)
        part = sanitize_llm_output(part)
        if len(part) < len(ch) * 0.4:
            raise RuntimeError(
                f"{i}번째 조각이 과도하게 줄었습니다 "
                f"({len(ch):,}자 → {len(part):,}자). 요약해버린 것으로 보입니다.")
        out_parts.append(part)
    return "\n\n".join(out_parts)


def ensure_clean_section(text: str) -> str:
    """
    '## 정리본' 섹션이 없는 구버전 노트에 자리를 만들어 준다.
    이미 있으면 그대로 둔다.
    """
    if "## 정리본\n" in text:
        return text
    marker = "\n\n---\n\n## 자막 원문\n"
    i = text.find(marker)
    if i == -1:
        return text
    ins = f"\n\n---\n\n## 정리본\n\n{CLEAN_PLACEHOLDER}"
    return text[:i] + ins + text[i:]


def fill_clean(path: Path) -> str:
    """
    노트의 '## 정리본'을 채운다. -> "filled" | "skip" | "malformed"

    플레이스홀더가 그대로인 노트만 건드린다. 사람이 손본 정리본은 보존한다.
    """
    text = ensure_clean_section(path.read_text(encoding="utf-8"))

    cm = _CLEAN_BLOCK.search(text)
    tm = _TRANSCRIPT_BLOCK.search(text)
    if not cm or not tm:
        return "malformed"
    if cm.group(2).strip() != CLEAN_PLACEHOLDER:
        return "skip"

    fm = read_frontmatter(text)
    cleaned = clean_transcript(
        fm.get("title", path.stem), fm.get("channel", ""), tm.group(1))

    new = text[:cm.start(2)] + cleaned + text[cm.end(2):]
    write_note_atomic(path, bump_updated(new))
    return "filled"


def bump_updated(text: str) -> str:
    """
    프론트매터 블록 '안'의 updated: 만 갱신한다.

    노트 전체에 정규식을 걸면, 프론트매터에 updated: 가 없는 손으로 고친
    노트에서 본문·자막의 'updated: …' 로 보이는 줄이 대신 치환된다.
    """
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    head, rest = text[:end + 1], text[end + 1:]
    head2, n = _UPDATED_LINE.subn(
        f"updated: {date.today().isoformat()}", head, count=1)
    return head2 + rest if n else text


def fill_summary(path: Path) -> str:
    """
    노트 하나의 요약을 채운다. -> "filled" | "skip" (이미 작성됨) | "malformed"

    플레이스홀더가 그대로인 노트만 건드린다. 사람이 쓴 요약은 보존한다.
    """
    text = path.read_text(encoding="utf-8")

    sm = _SUMMARY_BLOCK.search(text)
    tm = _TRANSCRIPT_BLOCK.search(text)
    if not sm or not tm:
        return "malformed"
    if sm.group(2).strip() != SUMMARY_PLACEHOLDER:
        return "skip"

    fm = read_frontmatter(text)

    # 요약은 '정리본'을 근거로 만든다. 원문 자막은 구두점이 없고 인식 오류가
    # 섞여 있어 그대로 요약하면 오류가 그대로 굳는다. 정리본이 비어 있으면
    # 여기서 먼저 채운다 — 정리 없이 요약만 만드는 경로는 두지 않는다.
    cm = _CLEAN_BLOCK.search(text)
    if not cm or cm.group(2).strip() == CLEAN_PLACEHOLDER:
        r = fill_clean(path)
        if r == "malformed":
            return "malformed"
        text = path.read_text(encoding="utf-8")
        sm = _SUMMARY_BLOCK.search(text)
        cm = _CLEAN_BLOCK.search(text)
        if not sm or not cm:
            return "malformed"

    summary = summarize_transcript(
        fm.get("title", path.stem), fm.get("channel", ""),
        fm.get("duration", ""), cm.group(2),
    )

    new = text[:sm.start(2)] + summary + text[sm.end(2):]
    write_note_atomic(path, bump_updated(new))
    return "filled"


def needs_clean(text: str) -> bool:
    """
    정리본 섹션이 아예 없거나(구버전 노트) 플레이스홀더면 정리 대상.

    단 **자막 노트가 아닌 파일은 제외한다.** 채널 폴더에는 허브 노트
    (`kind: channel-hub`)처럼 `## 자막 원문` 이 없는 파일도 있고, 그런 파일은
    정리본 섹션이 없다는 이유만으로 대상에 잡혀 목록·집계를 오염시킨다.
    """
    if not _TRANSCRIPT_BLOCK.search(text):
        return False
    cm = _CLEAN_BLOCK.search(text)
    return cm is None or cm.group(2).strip() == CLEAN_PLACEHOLDER


def run_pass(vault_dir: Path, limit: int, dry_run: bool, label: str,
             pending_of, filler) -> int:
    notes = sorted(vault_dir.glob("*.md"))
    if not notes:
        print(f"노트가 없습니다: {vault_dir}")
        return 1

    pending = [n for n in notes if pending_of(n.read_text(encoding="utf-8"))]
    print(f"노트 {len(notes)}개 중 {label} 필요 {len(pending)}개")
    targets = pending[:limit]

    if dry_run:
        for n in targets:
            print(f"  - {n.name}")
        return 0

    filled = skipped = failed = 0
    for i, n in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {n.name[:60]}", end=" ... ", flush=True)
        try:
            r = filler(n)
            if r == "filled":
                filled += 1
                print(f"{label} 완료")
            elif r == "skip":
                skipped += 1
                print("이미 작성됨, 보존")
            else:
                skipped += 1
                print("구조가 달라 건너뜀")
        except subprocess.TimeoutExpired:
            failed += 1
            print("실패: 시간 초과")
        except Exception as e:
            failed += 1
            m = str(e).strip().splitlines()
            print(f"실패: {m[0][:120] if m else e}")
            log_err(f"[{n.name}] 전문:\n{e}")

    print(f"\n완료 — {label} {filled} / 건너뜀 {skipped} / 실패 {failed}")
    return 0


def clean_pass(vault_dir: Path, limit: int, dry_run: bool) -> int:
    return run_pass(vault_dir, limit, dry_run, "정리", needs_clean, fill_clean)


def summarize_pass(vault_dir: Path, limit: int, dry_run: bool) -> int:
    notes = sorted(vault_dir.glob("*.md"))
    if not notes:
        print(f"노트가 없습니다: {vault_dir}")
        return 1

    pending = []
    for n in notes:
        head = n.read_text(encoding="utf-8")
        if SUMMARY_PLACEHOLDER in head:
            pending.append(n)

    print(f"노트 {len(notes)}개 중 요약 필요 {len(pending)}개")
    targets = pending[:limit]

    if dry_run:
        for n in targets:
            print(f"  - {n.name}")
        return 0

    filled = skipped = failed = 0
    for i, n in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {n.name[:60]}", end=" ... ", flush=True)
        try:
            r = fill_summary(n)
            if r == "filled":
                filled += 1
                print("요약 채움")
            elif r == "skip":
                skipped += 1
                print("이미 작성됨, 보존")
            else:
                skipped += 1
                print("구조가 달라 건너뜀")
        except subprocess.TimeoutExpired:
            failed += 1
            print(f"실패: {SUMMARY_TIMEOUT}초 초과")
        except Exception as e:
            failed += 1
            msg = str(e).strip().splitlines()
            print(f"실패: {msg[0][:120] if msg else e}")
            log_err(f"[{n.name}] 전문:\n{e}")

    print(f"\n완료 — 요약 {filled} / 건너뜀 {skipped} / 실패 {failed}")
    return 0


# ─────────────────────────────────────────────────────────────
# 상태 관리
# ─────────────────────────────────────────────────────────────

def load_state(state_file: Path) -> dict:
    """
    손상된 상태파일을 조용히 버리지 않는다. 빈 set 으로 넘어가면
    전체를 미처리로 보고 기존 노트를 다시 덮어쓰게 된다.
    """
    if not state_file.exists():
        return {"version": 2, "done": {}, "deferred": {}}
    text = state_file.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"상태파일이 손상되었습니다: {state_file}\n"
            f"  {e}\n"
            f"  내용을 확인해 직접 고치거나, --reset-state 로 기록을 버리고 시작하세요."
        ) from e

    if isinstance(data, list):          # v1 형식 (ID 배열) 마이그레이션
        return {"version": 2, "done": {v: "" for v in data}, "deferred": {}}
    data.setdefault("done", {})
    data.setdefault("deferred", {})
    return data


def save_state(state_file: Path, state: dict) -> None:
    """임시파일 + rename 으로 원자적 저장. 중간에 끊겨도 깨지지 않는다."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=state_file.parent, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, state_file)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def should_retry(entry: dict) -> bool:
    if entry.get("tries", 0) >= MAX_TRIES:
        return False
    last = entry.get("last_try") or ""
    try:
        return date.fromisoformat(last) <= date.today() - timedelta(days=RETRY_AFTER_DAYS)
    except ValueError:
        return True


def defer(state: dict, vid: str, reason: str) -> None:
    e = state["deferred"].get(vid, {"tries": 0})
    e["tries"] = e.get("tries", 0) + 1
    e["reason"] = reason
    e["last_try"] = date.today().isoformat()
    state["deferred"][vid] = e


# ─────────────────────────────────────────────────────────────

_VID_RE = re.compile(r"(?:v=|/shorts/|/live/|/embed/|youtu\.be/)([A-Za-z0-9_-]{11})")


def extract_video_id(s: str) -> str | None:
    """youtube.com/watch?v=, youtu.be/, /shorts/, /live/, 순수 ID 를 모두 받는다."""
    s = s.strip()
    m = _VID_RE.search(s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[A-Za-z0-9_-]{11}", s) else None


def write_note(meta: dict, transcript: str, lang: str, is_manual: bool,
               vault_dir: Path, fallback_title: str) -> Path:
    upload = meta.get("upload_date") or ""
    prefix = f"{upload}_" if len(upload) == 8 else ""
    # 파일명은 메타데이터 제목을 쓴다. --flat-playlist 목록의 제목은 로케일에
    # 따라 영어로 오는 경우가 있어 노트 본문과 어긋난다. video_id 를 붙여야
    # 제목이 80자에서 잘려 겹치는 영상끼리 서로를 덮어쓰지 않는다.
    fname = safe_filename(meta.get("title") or fallback_title)
    out = vault_dir / f"{prefix}{fname}_{meta['id']}.md"
    vault_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build_note(meta, transcript, lang, is_manual, existing_created(out)),
        encoding="utf-8",
    )
    return out


class StateCache:
    """
    채널 폴더별 상태파일을 캐시한다.
    링크 모드에서는 한 번 실행에 여러 채널이 섞일 수 있다.
    """

    def __init__(self, reset: bool) -> None:
        self.reset = reset
        self._m: dict[Path, dict] = {}

    def get(self, vault_dir: Path) -> dict:
        if vault_dir not in self._m:
            self._m[vault_dir] = (
                {"version": 2, "done": {}, "deferred": {}} if self.reset
                else load_state(vault_dir / ".processed.json")
            )
        return self._m[vault_dir]

    def save_all(self) -> None:
        # is_dir() 로 걸러선 안 된다. 노트가 하나도 안 써진 새 채널(전부 멤버십
        # 전용인 경우 등)은 폴더가 없어서 보류 기록이 통째로 유실되고,
        # RETRY_AFTER_DAYS·MAX_TRIES 가 무력화된다. save_state() 가 부모를 만든다.
        for d, st in self._m.items():
            save_state(d / ".processed.json", st)

    @property
    def dirs(self) -> list[Path]:
        return list(self._m)


def process_video(vid: str, fallback_title: str, workdir: Path,
                  cookies: str | None, parent: Path, cache: StateCache,
                  force: bool, known_dir: Path | None) -> tuple[str, Path | None, str]:
    """영상 하나를 적재한다. -> (status, vault_dir, 메시지)"""
    m = fetch_meta(vid, cookies)
    if m["status"] != "ok":
        # 메타 조회 자체가 막히면(멤버십 전용 등) 채널을 알 수 없다.
        # 채널 모드는 폴더를 미리 알고 있으므로 그때만 보류를 기록한다.
        if known_dir is not None:
            defer(cache.get(known_dir), vid, m["reason"])
        return m["status"], known_dir, m["reason"]

    meta = m["meta"]
    channel = meta.get("channel") or meta.get("uploader") or "unknown"
    vault_dir = known_dir or (parent / safe_filename(channel))
    state = cache.get(vault_dir)

    # 자막을 받기 '전에' 판정한다. 뒤에서 하면 이미 처리한 영상도 매번
    # 메타에 이어 자막까지 다시 내려받게 된다.
    if not force and vid in state["done"]:
        return "already", vault_dir, "이미 처리됨, 건너뜀"

    s = fetch_subs(vid, meta, workdir, cookies)
    if s["status"] != "ok":
        # 메타가 있으므로 채널을 알고, 올바른 채널에 보류를 남길 수 있다.
        defer(state, vid, s["reason"])
        return s["status"], vault_dir, s["reason"]

    transcript = parse_vtt(s["vtt"])
    if len(transcript) < 50:
        defer(state, vid, "자막 너무 짧음")
        return "no_subs", vault_dir, "자막 너무 짧음"

    write_note(meta, transcript, s["lang"], s["is_manual"],
               vault_dir, fallback_title)
    state["done"][vid] = date.today().isoformat()
    state["deferred"].pop(vid, None)
    return "ok", vault_dir, f"저장 ({len(transcript):,}자, {s['lang']})"


def main() -> int:
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", nargs="+", metavar="LINK",
                    help="영상 링크(또는 ID) 하나 이상. 채널 폴더는 자동 판별")
    ap.add_argument("--channel", default=CHANNEL_URL, metavar="URL",
                    help="채널 URL (기본값은 스크립트 상단 CHANNEL_URL)")
    ap.add_argument("--channel-dir", dest="channel_dir", default=None, metavar="NAME",
                    help="--summarize 시 대상 채널 폴더명")
    # 적재 후 정리·요약은 기본값이다. 원문만 받고 싶을 때만 --no-summarize 로 끈다.
    ap.add_argument("--and-summarize", dest="and_summarize", action="store_true",
                    default=True,
                    help="(기본값) 적재 직후 정리·요약까지 이어서 실행")
    ap.add_argument("--no-summarize", dest="and_summarize", action="store_false",
                    help="적재만 하고 정리·요약은 건너뛴다 "
                         "(대량 적재처럼 비용을 나중에 결정하고 싶을 때)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--all", action="store_true",
                    help="이미 처리한 것도 다시 처리 (기록은 보존)")
    ap.add_argument("--reset-state", action="store_true",
                    help="처리 기록을 버리고 처음부터 (되돌릴 수 없음)")
    ap.add_argument("--dry-run", action="store_true", help="목록만 출력")
    ap.add_argument("--clean", action="store_true",
                    help="적재 대신, 자막 원문을 읽을 수 있게 손봐 '## 정리본'을 채운다")
    ap.add_argument("--summarize", action="store_true",
                    help="적재 대신 '## 요약'을 채운다 "
                         "(정리본이 비어 있으면 정리를 먼저 수행)")
    ap.add_argument("--verbose", action="store_true", help="오류 전문 출력")
    ap.add_argument("--cookies-from-browser", dest="cookies", default=None,
                    metavar="BROWSER",
                    help="브라우저 세션 사용 (chrome/safari/firefox). 멤버십 영상용")
    args = ap.parse_args()
    VERBOSE = args.verbose

    # 볼트 루트가 없으면 절대 만들지 않는다.
    # mkdir(parents=True) 로 오타 경로를 새로 만들면 노트가 볼트 밖에 쌓인다.
    if not VAULT_ROOT.is_dir():
        print(f"❌ 볼트 루트가 없습니다: {VAULT_ROOT}", file=sys.stderr)
        return 1
    parent = VAULT_ROOT / VAULT_SUBPATH
    if not parent.parent.is_dir():
        print(f"❌ 상위 폴더가 없습니다: {parent.parent}", file=sys.stderr)
        return 1

    # ── 정리 / 요약 전용 모드 ──
    # 로컬 노트만 다루므로 yt-dlp·YouTube 왕복이 전혀 없어야 한다.
    # (claude CLI 호출은 있다 — Anthropic 쪽 네트워크는 사용한다)
    if args.clean or args.summarize:
        if not Path(CLAUDE_BIN).exists():
            print(f"❌ claude CLI 가 없습니다: {CLAUDE_BIN}", file=sys.stderr)
            return 1
        try:
            vault_dir = resolve_channel_dir_local(parent, args.channel_dir)
        except RuntimeError as e:
            print(f"❌ {e}", file=sys.stderr)
            return 1
        print(f"대상: {vault_dir}")
        if args.clean:
            rc = clean_pass(vault_dir, args.limit, args.dry_run)
            if rc or not args.summarize:
                return rc
        return summarize_pass(vault_dir, args.limit, args.dry_run)

    if not shutil.which("yt-dlp"):
        print("❌ yt-dlp 가 없습니다.  brew install yt-dlp", file=sys.stderr)
        return 1

    # --all 은 '다시 처리'일 뿐 '기록 삭제'가 아니다. 빈 상태로 시작하면
    # 루프의 저장이 기존 기록을 이번 회차 몇 건으로 덮어써서, 다음 실행이
    # 전체를 재다운로드하게 된다. 기록을 버리는 것은 --reset-state 뿐이다.
    cache = StateCache(args.reset_state)
    known_dir: Path | None = None
    ok = skipped = failed = already = 0

    try:
        if args.url:
            # ── 링크 모드: 채널 폴더는 영상 메타데이터로 판별 ──
            targets = []
            for raw in args.url:
                vid = extract_video_id(raw)
                if vid is None:
                    print(f"❌ 영상 ID를 찾을 수 없습니다: {raw}", file=sys.stderr)
                    return 1
                targets.append({"id": vid, "title": vid})
            print(f"링크 {len(targets)}개")
        else:
            # ── 채널 모드 ──
            # flush 필수: 파이프에서 stdout 은 블록 버퍼링이라, 뒤이어 stderr 로
            # 나가는 오류가 이 줄보다 먼저 찍혀 원인 파악을 방해한다.
            print(f"채널 조회 중: {args.channel}", flush=True)
            channel_name = resolve_channel_name(args.channel, args.cookies)
            known_dir = parent / safe_filename(channel_name)
            print(f"  채널: {channel_name}")
            print(f"  저장 위치: {known_dir}")

            videos = list_channel_videos(args.channel, args.cookies)
            print(f"  전체 {len(videos)}개")

            state = cache.get(known_dir)
            done, deferred = state["done"], state["deferred"]
            targets = []
            for v in videos:
                vid = v["id"]
                if not args.all:
                    if vid in done:
                        continue
                    if vid in deferred and not should_retry(deferred[vid]):
                        continue
                targets.append(v)
            targets = targets[: args.limit]
            print(f"  처리 대상 {len(targets)}개 "
                  f"(완료 {len(done)} / 보류 {len(deferred)})")
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        for t in targets:
            print(f"  - {t['id']}  {t['title']}")
        return 0
    if not targets:
        print("처리할 영상이 없습니다.")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for i, t in enumerate(targets, 1):
            vid = t["id"]
            print(f"[{i}/{len(targets)}] {t['title'][:50]}", end=" ... ", flush=True)
            try:
                status, _vdir, msg = process_video(
                    vid, t["title"], workdir, args.cookies, parent,
                    cache, args.all, known_dir,
                )
                print(msg)
                if status == "ok":
                    ok += 1
                elif status == "already":
                    # '이미 처리됨'은 보류(재시도 대상)가 아니다. 같이 세면
                    # 없는 보류 사유를 찾아보라고 안내하게 된다.
                    already += 1
                else:
                    skipped += 1
            except Exception as e:
                # 실패는 done 에 넣지 않는다 — 다음 실행에서 다시 시도해야 한다.
                failed += 1
                m = str(e).strip().splitlines()
                print(f"실패: {m[0][:120] if m else e}")
                log_err(f"[{vid}] 전문:\n{e}")
            finally:
                cache.save_all()
                if i < len(targets):
                    time.sleep(SLEEP_BETWEEN_VIDEOS)

    parts = [f"저장 {ok}"]
    if already:
        parts.append(f"이미 처리 {already}")
    parts += [f"보류 {skipped}", f"실패 {failed}"]
    print("\n완료 — " + " / ".join(parts))
    for d in cache.dirs:
        print(f"위치: {d}")
    if skipped and not VERBOSE:
        print("보류 사유를 보려면 --verbose 를 붙이세요.")

    # 이미 처리된 노트라도 정리·요약이 비어 있을 수 있으므로 already 도 포함한다.
    if args.and_summarize and (ok or already):
        if not Path(CLAUDE_BIN).exists():
            print(f"⚠️  claude CLI 가 없어 정리·요약은 건너뜁니다: {CLAUDE_BIN}")
            return 0
        # 순서를 지킨다: 원문 → 정리 → 요약.
        # 요약은 정리본을 근거로 만들어야 하므로 정리가 먼저다.
        for d in cache.dirs:
            if d.is_dir():
                print(f"\n── 정리: {d.name} ──")
                clean_pass(d, args.limit, False)
                print(f"\n── 요약: {d.name} ──")
                summarize_pass(d, args.limit, False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
