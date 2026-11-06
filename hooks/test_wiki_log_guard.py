"""wiki_log_guard.py 회귀 시험 — 가짜 대화 기록으로 Claude Code·Codex 둘 다 본다."""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = "~/Documents/Obsidian Vault/LLM Wiki/raw"


def claude_line(kind, **kw):
    if kind == "prompt":
        return {"type": "user", "message": {"role": "user", "content": kw["text"]}}
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": kw["name"], "input": kw.get("input", {})}]}}


def codex_line(name, text):
    return {"type": "response_item", "payload": {"type": "custom_tool_call", "name": name, "input": text}}


def codex_task(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                 "content": [{"type": "input_text", "text": text}]}}


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def claude_call(call_id, name, inp, start, end):
    """시각이 붙은 도구 호출과 그 결과 — 실제 대화 기록처럼 두 줄이다."""
    return [{"type": "assistant", "timestamp": iso(start),
             "message": {"content": [{"type": "tool_use", "id": call_id, "name": name, "input": inp}]}},
            {"type": "user", "timestamp": iso(end),
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": ""}]}}]


def codex_call(call_id, name, text, start, end):
    return [{"type": "response_item", "timestamp": iso(start),
             "payload": {"type": "custom_tool_call", "name": name, "input": text, "call_id": call_id}},
            {"type": "response_item", "timestamp": iso(end),
             "payload": {"type": "custom_tool_call_output", "call_id": call_id, "output": ""}}]


REVIEW_TASK = "<task>\nRun a stop-gate review of the previous Claude turn.\nOnly review the work from the previous Claude turn.\n"


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.env = dict(os.environ, WIKI_GUARD_STATE=str(self.dir / "state.json"), HOME=str(self.dir))

    def run_hook(self, rows, codex=False, active=False, session="s1", meta=None):
        path = self.dir / ("%s.jsonl" % session)
        head = [{"type": "session_meta", "payload": meta or {}}] if codex else []
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in head + rows) + "\n", encoding="utf-8")
        p = subprocess.run([sys.executable, str(HERE / "wiki_log_guard.py")], env=self.env, capture_output=True, text=True,
                           input=json.dumps({"session_id": session, "transcript_path": str(path), "stop_hook_active": active}))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def edits(self):
        return [claude_line("prompt", text="고쳐줘"), claude_line("tool", name="Edit", input={"file_path": "/repo/a.py"})]

    def test_edit_without_log_blocks(self):
        out = self.run_hook(self.edits())
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("LLM Wiki/raw", out["reason"])

    def test_log_after_edit_passes(self):
        rows = self.edits() + [claude_line("tool", name="Write", input={"file_path": os.path.expanduser(RAW) + "/x.md"})]
        self.assertEqual(self.run_hook(rows), {})

    def test_memory_only_write_passes(self):
        # 2026-11-06: 사용자 지적을 자동 메모리에 적기만 한 턴을 막았다
        mem = os.path.expanduser("~/.claude/projects/-repo/memory/feedback-x.md")
        rows = [claude_line("prompt", text="그렇게 부르지 마"),
                claude_line("tool", name="Write", input={"file_path": mem}),
                claude_line("tool", name="Bash", input={"command": "echo '- x' >> \"%s\"" % os.path.join(os.path.dirname(mem), "MEMORY.md")})]
        self.assertEqual(self.run_hook(rows), {})

    def test_memory_write_with_real_edit_still_blocks(self):
        mem = os.path.expanduser("~/.claude/projects/-repo/memory/feedback-x.md")
        rows = self.edits() + [claude_line("tool", name="Write", input={"file_path": mem})]
        self.assertEqual(self.run_hook(rows).get("decision"), "block")

    def test_heredoc_log_counts(self):
        rows = self.edits() + [claude_line("tool", name="Bash", input={"command": "cat > \"%s/x.md\" <<'EOF'" % RAW})]
        self.assertEqual(self.run_hook(rows), {})

    def test_reading_raw_is_not_a_log(self):
        rows = self.edits() + [claude_line("tool", name="Bash", input={"command": "cat \"%s/old.md\"" % RAW})]
        self.assertEqual(self.run_hook(rows).get("decision"), "block")

    def test_reads_only_ask_from_twenty_calls(self):
        # 파일을 고치지 않은 턴은 도구 호출 20회부터 묻는다(2026-10-29, 8 → 20)
        reads = [claude_line("prompt", text="찾아줘")] + [claude_line("tool", name="Read", input={"file_path": "/a"})] * 19
        self.assertEqual(self.run_hook(reads, session="r1"), {})
        many = [claude_line("prompt", text="조사해줘")] + [claude_line("tool", name="Read", input={"file_path": "/a"})] * 20
        self.assertEqual(self.run_hook(many, session="r2").get("decision"), "block")

    def test_codex_stop_review_passes(self):
        patch = codex_line("exec", 'tools.apply_patch("*** Begin Patch\\n*** Update File: /repo/a.py")')
        claude = {"originator": "Claude Code"}
        self.assertEqual(self.run_hook([codex_task(REVIEW_TASK), patch], codex=True, session="v1", meta=claude), {})
        # 같은 플러그인으로 맡긴 작업(검토 프롬프트 없음)은 그대로 묻는다
        self.assertEqual(self.run_hook([codex_task("고쳐줘"), patch], codex=True, session="v2", meta=claude).get("decision"),
                         "block")
        # 사용자가 연 Codex 세션은 검토 문구가 있어도 묻는다
        mine = {"originator": "codex_cli_rs"}
        self.assertEqual(self.run_hook([codex_task(REVIEW_TASK), patch], codex=True, session="v3", meta=mine).get("decision"),
                         "block")
        # 맡긴 작업이 검토 문구가 든 파일을 고쳐도 검토 세션으로 보지 않는다
        quoted = codex_line("exec", 'tools.apply_patch("*** Update File: /repo/hook.py\\n+%s")' % REVIEW_TASK.splitlines()[1])
        rows = [codex_task("훅 고쳐줘. 검토 프롬프트는 %s 로 시작한다" % REVIEW_TASK.splitlines()[1]), quoted]
        self.assertEqual(self.run_hook(rows, codex=True, session="v4", meta=claude).get("decision"), "block")

    def test_scheduled_session_passes(self):
        rows = [claude_line("prompt", text='<scheduled-task name="cc-gap-check">')] + self.edits()[1:]
        self.assertEqual(self.run_hook(rows), {})

    def test_active_continuation_passes(self):
        self.assertEqual(self.run_hook(self.edits(), active=True), {})

    def test_asks_once_per_batch(self):
        self.assertEqual(self.run_hook(self.edits()).get("decision"), "block")
        self.assertEqual(self.run_hook(self.edits()), {})                       # 같은 묶음 — 다시 묻지 않는다
        more = self.edits() + [claude_line("tool", name="Edit", input={"file_path": "/repo/b.py"})]
        self.assertEqual(self.run_hook(more).get("decision"), "block")          # 새로 고친 뒤에는 다시 묻는다

    def test_codex_patch_blocks_and_log_passes(self):
        patch = codex_line("exec", 'tools.apply_patch("*** Begin Patch\\n*** Update File: /repo/a.py")')
        self.assertEqual(self.run_hook([patch], codex=True, session="c1").get("decision"), "block")
        log = codex_line("exec", 'tools.apply_patch("*** Add File: %s/y.md")' % RAW)
        self.assertEqual(self.run_hook([patch, log], codex=True, session="c2"), {})

    def write_raw(self, minutes_ahead, saved_hours_ago=0):
        raw = self.dir / "Documents/Obsidian Vault/LLM Wiki/raw"
        raw.mkdir(parents=True, exist_ok=True)
        saved = datetime.datetime.now() - datetime.timedelta(hours=saved_hours_ago)
        stamp = saved + datetime.timedelta(minutes=minutes_ahead)
        path = raw / ("%s-claude-code-t-abcd.md" % stamp.strftime("%Y%m%dT%H%M%S"))
        path.write_text("---\n---\n", encoding="utf-8")
        os.utime(path, (saved.timestamp(), saved.timestamp()))
        return claude_line("tool", name="Write", input={"file_path": str(path)})

    def test_old_misnamed_log_is_left_alone(self):
        # 이미 올라가 링크가 걸렸을 옛 기록은 이름을 바꾸라고 하지 않는다
        self.assertEqual(self.run_hook(self.edits() + [self.write_raw(30, saved_hours_ago=24)]), {})

    def test_only_logs_after_last_check(self):
        old = self.edits() + [self.write_raw(30)]
        self.assertEqual(self.run_hook(old, session="k1").get("decision"), "block")
        later = old + [claude_line("tool", name="Write", input={"file_path": os.path.expanduser(RAW) + "/x.md"})]
        self.assertEqual(self.run_hook(later, session="k1"), {})              # 앞서 본 기록은 다시 보지 않는다

    def test_name_ahead_of_save_blocks_once(self):
        rows = self.edits() + [self.write_raw(30)]
        out = self.run_hook(rows)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("파일명 시각", out["reason"])
        self.assertNotIn("기록이 아직 없다", out["reason"])                     # 기록은 남겼다
        self.assertEqual(self.run_hook(rows), {})                               # 같은 파일은 다시 묻지 않는다

    def test_name_at_save_time_passes(self):
        self.assertEqual(self.run_hook(self.edits() + [self.write_raw(-1)]), {})

    # ── 경로를 어떻게 적었든, 이 세션의 도구가 도는 동안 raw 기록이 생겼으면 센다 ──
    # 명령 글자에 "LLM Wiki/raw/" 가 그대로 있어야만 세던 탓에 같은 일이 다섯 번 났다
    # (2026-10-22 · 10-29 · 11-02). 글자 맞추기를 넓히는 대신, 도구 호출이 시작해서 결과가
    # 돌아오기까지의 시간 안에 raw 파일이 바뀌었는지 본다. 시간으로 이 세션에 묶이므로
    # 다른 세션이나 다른 맥이 쓴 기록은 세지 않는다.

    def raw_file(self, name_at, saved_at):
        raw = self.dir / "Documents/Obsidian Vault/LLM Wiki/raw"
        raw.mkdir(parents=True, exist_ok=True)
        path = raw / ("%s-claude-code-t-%x.md" % (time.strftime("%Y%m%dT%H%M%S", time.localtime(name_at)), int(saved_at)))
        path.write_text("---\n---\n", encoding="utf-8")
        os.utime(path, (saved_at, saved_at))
        return path

    def test_log_written_with_wiki_variable_counts(self):
        # 2026-11-02: W=".../LLM Wiki" 로 두고 "$W/raw/…" 로 썼다
        now = time.time()
        self.raw_file(now - 10, now - 10)
        cmd = 'W="$HOME/Documents/Obsidian Vault/LLM Wiki"; F="$W/raw/$(date +%Y%m%dT%H%M%S)-claude-code-x.md"; cat > "$F"'
        self.assertEqual(self.run_hook(self.edits() + claude_call("t1", "Bash", {"command": cmd}, now - 11, now - 9)), {})

    def test_log_written_with_raw_variable_counts(self):
        # 2026-10-29: W=".../LLM Wiki/raw" 로 두고 "$W/…" 로 썼다 (끝 슬래시가 없다)
        now = time.time()
        self.raw_file(now - 10, now - 10)
        cmd = 'W="$HOME/Documents/Obsidian Vault/LLM Wiki/raw"; cat > "$W/${TS}-claude-code-x.md"'
        self.assertEqual(self.run_hook(self.edits() + claude_call("t1", "Bash", {"command": cmd}, now - 11, now - 9)), {})

    def test_listing_old_logs_is_not_a_log(self):
        now = time.time()
        self.raw_file(now - 3600, now - 3600)
        cmd = 'W="$HOME/Documents/Obsidian Vault/LLM Wiki"; ls "$W/raw/" | tail -3'
        rows = self.edits() + claude_call("t1", "Bash", {"command": cmd}, now - 11, now - 9)
        self.assertEqual(self.run_hook(rows).get("decision"), "block")

    def test_other_writer_during_unrelated_call_is_not_counted(self):
        # 오래 도는 명령(예: codex exec) 동안 다른 세션이 기록을 써도 내 기록이 아니다
        now = time.time()
        self.raw_file(now - 10, now - 10)
        rows = self.edits() + claude_call("t1", "Bash", {"command": "sleep 5; echo done"}, now - 15, now - 5)
        self.assertEqual(self.run_hook(rows).get("decision"), "block")

    def test_log_saved_outside_the_call_is_not_counted(self):
        # raw 를 언급한 호출이라도, 그 호출이 끝난 뒤 다른 쪽이 쓴 기록은 세지 않는다
        now = time.time()
        self.raw_file(now - 2, now - 2)
        cmd = 'W="$HOME/Documents/Obsidian Vault/LLM Wiki"; cat "$W/raw/old.md"'
        rows = self.edits() + claude_call("t1", "Bash", {"command": cmd}, now - 30, now - 29)
        self.assertEqual(self.run_hook(rows).get("decision"), "block")

    def test_codex_log_written_with_variable_counts(self):
        now = time.time()
        self.raw_file(now - 10, now - 10)
        patch = codex_line("exec", 'tools.apply_patch("*** Begin Patch\\n*** Update File: /repo/a.py")')
        cmd = 'exec_command("W=\\"$HOME/Documents/Obsidian Vault/LLM Wiki\\"; cat > \\"$W/raw/x.md\\"")'
        rows = [patch] + codex_call("c1", "exec", cmd, now - 11, now - 9)
        self.assertEqual(self.run_hook(rows, codex=True, session="cv"), {})

    def test_time_matched_log_still_gets_name_check(self):
        # 시간으로 찾은 기록도 파일명 시각 검사를 받는다 — 이름이 명령 글자에 없어도
        now = time.time()
        self.raw_file(now + 1800, now - 10)
        cmd = 'W="$HOME/Documents/Obsidian Vault/LLM Wiki"; cat > "$W/raw/$TS-claude-code-x.md"'
        out = self.run_hook(self.edits() + claude_call("t1", "Bash", {"command": cmd}, now - 11, now - 9))
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("파일명 시각", out["reason"])
        self.assertNotIn("기록이 아직 없다", out["reason"])

    def test_broken_input_passes(self):
        p = subprocess.run([sys.executable, str(HERE / "wiki_log_guard.py")], env=self.env, capture_output=True, text=True,
                           input="not json")
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, {}))


if __name__ == "__main__":
    unittest.main()
