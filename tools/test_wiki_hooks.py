"""wiki_hooks.py 시험. 임시 HOME 의 Claude settings.json · Codex hooks.json 에 등록 · 재등록 · 전환 · 제거하며 다른 훅이 남는지 본다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "wiki_hooks.py"
OTHER = {"type": "command", "command": "node \"$HOME/other/stop-gate.mjs\"", "timeout": 30}
GUARD_CMD = "/.claude/hooks/wiki_log_guard.py"
SYNC_CMD = "/.claude/hooks/wiki_sync.py"


class WikiHooksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / ".codex").mkdir()
        (self.home / ".claude" / "hooks").mkdir(parents=True)
        for name in ("wiki_sync.py", "wiki_log_guard.py"):
            (self.home / ".claude" / "hooks" / name).write_text("", encoding="utf-8")
        self.claude = self.home / ".claude" / "settings.json"
        self.codex = self.home / ".codex" / "hooks.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def run_tool(self, *args):
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=env, timeout=10)

    def commands(self, data, event):
        return [h["command"] for g in data["hooks"].get(event, []) for h in g["hooks"]]

    def test_add_again_remove_restores_original(self):
        original = {"model": "x", "hooks": {"Stop": [{"hooks": [OTHER]}]}}
        for path in (self.claude, self.codex):
            self.write(path, original)
        self.assertEqual(self.run_tool("--apply").returncode, 0)
        for path in (self.claude, self.codex):
            data = self.read(path)
            self.assertEqual(self.commands(data, "Stop")[0], OTHER["command"])
            self.assertTrue(any(GUARD_CMD in c for c in self.commands(data, "Stop")))
            self.assertTrue(any(SYNC_CMD in c for c in self.commands(data, "SessionStart")))
        before = [p.read_text(encoding="utf-8") for p in (self.claude, self.codex)]
        again = self.run_tool("--apply")
        self.assertEqual(again.stdout.count("이미 있음"), 4)
        self.assertEqual([p.read_text(encoding="utf-8") for p in (self.claude, self.codex)], before)
        self.assertEqual(self.run_tool("--remove", "--apply").returncode, 0)
        for path in (self.claude, self.codex):
            self.assertEqual(self.read(path), original)

    def test_mixed_group_keeps_other_hook(self):
        guard = {"type": "command", "command": '/usr/bin/python3 "$HOME' + GUARD_CMD + '"', "timeout": 15}
        self.write(self.claude, {"hooks": {"Stop": [{"hooks": [OTHER, guard]}]}})
        self.write(self.codex, {"hooks": {}})
        self.assertEqual(self.run_tool("--apply").returncode, 0)
        cmds = self.commands(self.read(self.claude), "Stop")
        self.assertIn(OTHER["command"], cmds)
        self.assertEqual(sum(GUARD_CMD in c for c in cmds), 1)
        self.assertEqual(self.run_tool("--remove", "--apply").returncode, 0)
        self.assertEqual(self.commands(self.read(self.claude), "Stop"), [OTHER["command"]])

    def test_sync_only_switch_keeps_position_and_other_hooks(self):
        self.write(self.claude, {"hooks": {"Stop": [{"hooks": [OTHER]}]}})
        self.write(self.codex, {"hooks": {}})
        self.assertEqual(self.run_tool("--apply").returncode, 0)
        self.assertEqual(self.run_tool("--sync-only", "--apply").returncode, 0)
        cmds = self.commands(self.read(self.claude), "Stop")
        self.assertEqual(cmds[0], OTHER["command"])
        self.assertFalse(any(GUARD_CMD in c for c in cmds))
        self.assertEqual(sum(SYNC_CMD in c for c in cmds), 1)

    def test_remove_when_absent_changes_nothing(self):
        data = {"hooks": {"Stop": [{"hooks": [OTHER]}]}}
        for path in (self.claude, self.codex):
            self.write(path, data)
        before = [p.read_text(encoding="utf-8") for p in (self.claude, self.codex)]
        self.assertEqual(self.run_tool("--remove", "--apply").returncode, 0)
        self.assertEqual([p.read_text(encoding="utf-8") for p in (self.claude, self.codex)], before)


if __name__ == "__main__":
    unittest.main()
