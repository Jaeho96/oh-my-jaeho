"""korean_style_context.py 시험. 링크로 불러도 레포 지침을 찾고, 길면 자르고, 원본이 없어도 조용히 끝나는지 본다."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = HERE / "korean_style_context.py"


def run(path, **env):
    full = dict(os.environ, **env)
    p = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, env=full, timeout=10)
    return p.returncode, p.stdout


class KoreanStyleHookTests(unittest.TestCase):
    def test_prints_both_rule_files(self):
        code, out = run(HOOK)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("아래는 사용자가 정한 한국어 문체 지침이다."))
        self.assertIn("# 한국어로 쓰기", out)
        self.assertIn("# 토스 테크니컬 라이팅 가이드", out)

    def test_follows_symlink_to_repo(self):
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "korean_style_context.py"
            link.symlink_to(HOOK)
            code, out = run(link)
        self.assertEqual(code, 0)
        self.assertIn("# 한국어로 쓰기", out)

    def test_truncates_long_output(self):
        code, out = run(HOOK, KOREAN_STYLE_MAX_BYTES="300")
        self.assertEqual(code, 0)
        self.assertIn("지침이 길어서 여기서 잘랐다", out)
        self.assertLess(len(out.encode("utf-8")), 600)

    def test_missing_rules_prints_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "hooks").mkdir()
            copy = Path(d) / "hooks" / "korean_style_context.py"
            copy.write_text(HOOK.read_text(encoding="utf-8"), encoding="utf-8")
            code, out = run(copy)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
