"""korean_style_hooks.py 시험. 임시 HOME 의 Claude settings.json · Codex hooks.json 에 등록 · 재등록 · 제거하며 다른 훅이 남는지 본다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "korean_style_hooks.py"
OTHER = {"type": "command", "command": "/usr/bin/python3 \"$HOME/.claude/hooks/wiki_sync.py\" --detach", "timeout": 10}
OURS_CMD = "/.claude/hooks/korean_style_context.py"
GUARD_CMD = "/.claude/hooks/korean_style_guard.py"


class KoreanStyleHooksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / ".codex").mkdir()
        (self.home / ".claude" / "hooks").mkdir(parents=True)
        for name in ("korean_style_context.py", "korean_style_guard.py"):
            (self.home / ".claude" / "hooks" / name).write_text("", encoding="utf-8")
        self.path = self.home / ".codex" / "hooks.json"
        self.claude = self.home / ".claude" / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def run_tool(self, *args):
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=env, timeout=10)

    def commands(self, data, event):
        return [h["command"] for g in data["hooks"].get(event, []) for h in g["hooks"]]

    def test_add_again_remove_restores_original(self):
        original = {"hooks": {"SessionStart": [{"hooks": [OTHER]}], "Stop": [{"hooks": [OTHER]}]}}
        self.write(original)
        self.assertEqual(self.run_tool("--apply").returncode, 0)
        data = self.read()
        self.assertEqual(sum(OURS_CMD in c for c in self.commands(data, "SessionStart")), 1)
        self.assertEqual(sum(OURS_CMD in c for c in self.commands(data, "SubagentStart")), 1)
        self.assertEqual(self.commands(data, "Stop")[0], OTHER["command"])
        self.assertEqual(sum(GUARD_CMD in c for c in self.commands(data, "Stop")), 1)
        self.assertFalse(self.claude.exists())     # Claude settings.json 은 없으면 만들지 않는다
        before = self.path.read_text(encoding="utf-8")
        again = self.run_tool("--apply")
        self.assertIn("이미 있음", again.stdout)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        self.assertEqual(self.run_tool("--remove", "--apply").returncode, 0)
        self.assertEqual(self.read(), original)

    def test_mixed_group_keeps_other_hook(self):
        ours = {"type": "command", "command": '/usr/bin/python3 "$HOME' + OURS_CMD + '"', "timeout": 5}
        self.write({"hooks": {"SessionStart": [{"hooks": [OTHER, ours]}], "SubagentStart": [{"hooks": [ours, OTHER]}]}})
        self.assertEqual(self.run_tool("--apply").returncode, 0)
        data = self.read()
        for event in ("SessionStart", "SubagentStart"):
            cmds = self.commands(data, event)
            self.assertIn(OTHER["command"], cmds)
            self.assertEqual(sum(OURS_CMD in c for c in cmds), 1)
        self.assertEqual(self.run_tool("--remove", "--apply").returncode, 0)
        data = self.read()
        for event in ("SessionStart", "SubagentStart"):
            self.assertEqual(self.commands(data, event), [OTHER["command"]])

    def test_remove_when_absent_changes_nothing(self):
        self.write({"hooks": {"Stop": [{"hooks": [OTHER]}], "SubagentStart": []}})
        before = self.path.read_text(encoding="utf-8")
        self.assertEqual(self.run_tool("--remove", "--apply").returncode, 0)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        self.assertFalse((self.home / ".omj").exists())

    def test_claude_settings_gets_only_stop_guard(self):
        original = {"model": "x", "hooks": {"Stop": [{"hooks": [OTHER]}]}}
        self.claude.write_text(json.dumps(original), encoding="utf-8")
        self.write({"hooks": {}})
        self.assertEqual(self.run_tool("--apply").returncode, 0)
        data = json.loads(self.claude.read_text(encoding="utf-8"))
        self.assertEqual(data["model"], "x")
        self.assertEqual(set(data["hooks"]), {"Stop"})
        self.assertEqual(self.commands(data, "Stop")[0], OTHER["command"])
        self.assertEqual(sum(GUARD_CMD in c for c in self.commands(data, "Stop")), 1)
        self.assertEqual(self.run_tool("--remove", "--apply").returncode, 0)
        self.assertEqual(json.loads(self.claude.read_text(encoding="utf-8")), original)

    def test_missing_hook_file_stops(self):
        (self.home / ".claude" / "hooks" / "korean_style_context.py").unlink()
        self.write({"hooks": {}})
        p = self.run_tool("--apply")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("훅 파일이 없다", p.stderr)


if __name__ == "__main__":
    unittest.main()
