"""wiki_log_guard.py 회귀 시험 — 가짜 대화 기록으로 Claude Code·Codex 둘 다 본다."""
import json
import os
import subprocess
import sys
import tempfile
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


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.env = dict(os.environ, WIKI_GUARD_STATE=str(self.dir / "state.json"), HOME=str(self.dir))

    def run_hook(self, rows, codex=False, active=False, session="s1"):
        path = self.dir / ("%s.jsonl" % session)
        head = [{"type": "session_meta", "payload": {}}] if codex else []
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

    def test_heredoc_log_counts(self):
        rows = self.edits() + [claude_line("tool", name="Bash", input={"command": "cat > \"%s/x.md\" <<'EOF'" % RAW})]
        self.assertEqual(self.run_hook(rows), {})

    def test_reading_raw_is_not_a_log(self):
        rows = self.edits() + [claude_line("tool", name="Bash", input={"command": "cat \"%s/old.md\"" % RAW})]
        self.assertEqual(self.run_hook(rows).get("decision"), "block")

    def test_few_reads_pass_many_calls_block(self):
        reads = [claude_line("prompt", text="찾아줘")] + [claude_line("tool", name="Read", input={"file_path": "/a"})] * 3
        self.assertEqual(self.run_hook(reads, session="r1"), {})
        many = [claude_line("prompt", text="조사해줘")] + [claude_line("tool", name="Read", input={"file_path": "/a"})] * 8
        self.assertEqual(self.run_hook(many, session="r2").get("decision"), "block")

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

    def test_broken_input_passes(self):
        p = subprocess.run([sys.executable, str(HERE / "wiki_log_guard.py")], env=self.env, capture_output=True, text=True,
                           input="not json")
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, {}))


if __name__ == "__main__":
    unittest.main()
