#!/usr/bin/env python3
"""config.toml(+config.local.toml)에 적힌 스킬·규칙을 각 도구의 설정 폴더에 심볼릭 링크로 배포한다.

- 기본은 미리보기. --apply 를 줘야 바꾼다.
- 자기가 만든 링크만 ~/.omj/state.json 에 적고, 설정에서 빠진 것만 지운다.
- 같은 자리에 원래 파일·폴더가 있으면 건너뛰고 「충돌」로 알린다. --backup-existing 이면 옮기고 링크를 건다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE = Path.home() / ".omj" / "state.json"


def load_config() -> dict:
    cfg = tomllib.loads((REPO / "config.toml").read_text(encoding="utf-8"))
    local = REPO / "config.local.toml"
    if local.exists():
        over = tomllib.loads(local.read_text(encoding="utf-8"))
        for section, values in over.items():
            if isinstance(values, list):  # [[files]] 같은 배열은 통째로 바꾼다
                cfg[section] = values
                continue
            base = cfg.setdefault(section, {})
            items = list(base.get("items", []))
            for name in values.get("add", []):
                if name not in items:
                    items.append(name)
            items = [n for n in items if n not in values.get("remove", [])]
            base.update({k: v for k, v in values.items() if k not in ("add", "remove")})
            if "items" not in values:
                base["items"] = items
    return cfg


def desired_links(cfg: dict) -> tuple[list[tuple[Path, Path]], list[str]]:
    """(배포 위치, 레포 원본) 목록과 경고를 돌려준다."""
    t = cfg.get("targets", {})
    claude = Path(os.path.expanduser(t.get("claude_home", "~/.claude")))
    agents = Path(os.path.expanduser(t.get("agents_home", "~/.agents")))
    links, warns = [], []

    sk = cfg.get("skills", {})
    for name in sk.get("items", []):
        src = REPO / "skills" / name
        if not (src / "SKILL.md").exists():
            warns.append(f"스킬 원본 없음: skills/{name}/SKILL.md")
            continue
        for p in sk.get("platforms", ["claude"]):
            if p == "claude":
                links.append((claude / "skills" / name, src))
            elif p == "codex":
                links.append((agents / "skills" / name, src))
            else:
                warns.append(f"모르는 플랫폼: {p} (skills/{name})")

    ru = cfg.get("rules", {})
    for name in ru.get("items", []):
        src = REPO / "rules" / f"{name}.md"
        if not src.exists():
            warns.append(f"규칙 원본 없음: rules/{name}.md")
            continue
        for p in ru.get("platforms", ["claude"]):
            if p == "claude":
                links.append((claude / "rules" / f"{name}.md", src))
            else:
                warns.append(f"규칙은 아직 {p} 배포를 지원하지 않음 (rules/{name})")

    for f in cfg.get("files", []):
        src = REPO / f.get("src", "")
        if not f.get("src") or not f.get("dest") or not src.exists():
            warns.append(f"파일 항목이 잘못됨: {f}")
            continue
        links.append((Path(os.path.expanduser(f["dest"])), src))
    return links, warns


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"links": {}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="실제로 바꾼다(없으면 미리보기)")
    ap.add_argument("--backup-existing", action="store_true", help="충돌하는 원래 파일·폴더를 옮기고 링크를 건다")
    args = ap.parse_args()

    cfg = load_config()
    want, warns = desired_links(cfg)
    state = load_state()
    owned: dict[str, str] = state.get("links", {})
    stamp = time.strftime("%Y%m%d%H%M%S")
    plan: list[tuple[str, str]] = []
    conflicts = 0

    for dest, src in want:
        key = str(dest)
        if dest.is_symlink():
            if Path(os.readlink(dest)) == src:
                plan.append(("그대로", key))
                owned[key] = str(src)
                continue
            if key in owned:
                plan.append(("다시 연결", f"{key} → {src}"))
            else:
                plan.append(("충돌(남의 링크)", f"{key} → {os.readlink(dest)}"))
                conflicts += 1
                continue
        elif dest.exists():
            if not args.backup_existing:
                plan.append(("충돌(원래 있음)", key))
                conflicts += 1
                continue
            plan.append(("옮기고 연결", f"{key} → {key}.omj-backup-{stamp}"))
        else:
            plan.append(("새로 연결", f"{key} → {src}"))
        if args.apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                dest.unlink()
            elif dest.exists():
                dest.rename(dest.with_name(f"{dest.name}.omj-backup-{stamp}"))
            dest.symlink_to(src)
        owned[key] = str(src)

    wanted = {str(d) for d, _ in want}
    for key, src in list(owned.items()):
        if key in wanted:
            continue
        p = Path(key)
        if p.is_symlink() and os.readlink(p) == src:
            plan.append(("정리(설정에서 빠짐)", key))
            if args.apply:
                p.unlink()
        else:
            plan.append(("기록만 지움(이미 바뀜)", key))
        del owned[key]

    for w in warns:
        print(f"[경고] {w}")
    for action, what in plan:
        print(f"{action:<16} {what}")
    print(f"\n{'적용함' if args.apply else '미리보기 — 바꾸려면 --apply'} · 충돌 {conflicts}건")

    if args.apply:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"links": owned}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if conflicts and args.apply else 0


if __name__ == "__main__":
    sys.exit(main())
