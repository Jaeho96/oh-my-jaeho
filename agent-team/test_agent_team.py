"""agent-team 회귀 시험 — 가짜 codex 를 PATH 앞에 두고 실행기·보드 수집기를 본다."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board  # noqa: E402

FAKE_CODEX = """#!/bin/sh
# 가짜 codex: exec 이면 이벤트 몇 줄을 찍고 끝난다. app-server 면 아무 답도 하지 않고 기다린다.
if [ "$1" = "exec" ]; then
  echo '{"type":"thread.started","thread_id":"t-1"}'
  echo '{"type":"turn.started"}'
  echo '{"type":"item.completed","item":{"type":"agent_message","text":"끝"}}'
  echo '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}}'
  exit ${FAKE_EXIT:-0}
fi
if [ "$1" = "app-server" ]; then sleep 30; fi
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        bindir = self.dir / "bin"
        bindir.mkdir()
        fake = bindir / "codex"
        fake.write_text(FAKE_CODEX)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, PATH="%s:%s" % (bindir, os.environ["PATH"]))
        self.runs = self.dir / "runs"

    def run_team(self, *extra, env=None):
        args = [sys.executable, str(HERE / "run_team.py"), "--name", "t", "--cwd", str(self.dir),
                "--task", "x", "--runs", str(self.runs)] + list(extra)
        return subprocess.run(args, env=env or self.env, capture_output=True, text=True, timeout=60)


class RunTeamTests(Base):
    def test_foreground_records_exit_code_and_private_files(self):
        p = self.run_team()
        self.assertEqual(p.returncode, 0, p.stderr)
        metas = list(self.runs.glob("*.meta.json"))
        self.assertEqual(len(metas), 1)
        meta = json.loads(metas[0].read_text())
        self.assertEqual(meta["exit_code"], 0)
        self.assertIsNotNone(meta["finished"])
        self.assertEqual(stat.S_IMODE(self.runs.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(metas[0].stat().st_mode), 0o600)

    def test_background_supervisor_records_failure(self):
        env = dict(self.env, FAKE_EXIT="3")
        p = self.run_team("--background", env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        deadline = time.time() + 20
        meta = {}
        while time.time() < deadline:
            metas = list(self.runs.glob("*.meta.json"))
            meta = json.loads(metas[0].read_text()) if metas else {}
            if meta.get("finished"):
                break
            time.sleep(0.2)
        self.assertEqual(meta.get("exit_code"), 3)          # 백그라운드도 종료 코드가 남는다

    def test_same_name_twice_does_not_overwrite(self):
        self.run_team()
        self.run_team()
        metas = sorted(self.runs.glob("*.meta.json"))
        self.assertEqual(len(metas), 2)
        # 같은 초에 시작해도 겹치지 않게 이름 끝에 임의 접미사가 붙는다(시각만 다르면 이 시험은 우연히 통과하므로 직접 본다)
        for m in metas:
            self.assertRegex(json.loads(m.read_text())["name"], r"-t-[0-9a-f]{4}$")

    def test_name_with_path_separator_is_rejected(self):
        args = [sys.executable, str(HERE / "run_team.py"), "--name", "../x", "--cwd", str(self.dir),
                "--task", "x", "--runs", str(self.runs)]
        p = subprocess.run(args, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(self.runs.exists())

    def test_missing_codex_is_recorded_as_error(self):
        env = dict(self.env, PATH="/usr/bin:/bin")
        self.run_team(env=env)
        meta = json.loads(next(self.runs.glob("*.meta.json")).read_text())
        self.assertIsNone(meta["exit_code"])
        self.assertIn("시작 실패", meta["error"])


class BoardTests(Base):
    def test_run_state_prefers_exit_code(self):
        r = {"last_terminal": "completed", "events": 3, "updated": board.now_iso()}
        self.assertEqual(board.run_state({"exit_code": 1}, r), "error")
        self.assertEqual(board.run_state({"exit_code": 0}, {"last_terminal": "failed"}), "done")
        self.assertEqual(board.run_state({"pid": 999999}, r), "stale")     # 감시 프로세스가 없는데 결과도 없다
        self.assertEqual(board.run_state({}, {"events": 0}), "unknown")   # 빈 기록을 「실행 중」으로 보지 않는다

    def test_summarize_events_flags_unknown_and_uses_last_terminal(self):
        p = self.dir / "e.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in [
            {"type": "thread.started", "thread_id": "t"}, {"type": "turn.completed"},
            {"type": "turn.failed"}, {"type": "run.finished"}, [], "x"]))
        s = board.summarize_events(str(p))
        self.assertEqual(s["last_terminal"], "failed")
        self.assertIn("run.finished", s["unknown"])

    def test_collect_runs_survives_broken_meta(self):
        self.runs.mkdir()
        (self.runs / "a.meta.json").write_text("{broken")
        (self.runs / "b.meta.json").write_text(json.dumps({"exit_code": 0}))
        runs, _ = board.collect_runs(str(self.runs), board.Rollouts(str(self.dir / "sessions")))
        self.assertEqual(len(runs), 2)

    def test_rollout_team_tree(self):
        day = self.dir / "sessions" / time.strftime("%Y/%m/%d")
        day.mkdir(parents=True)

        def rollout(name, meta, events):
            lines = [{"timestamp": "2026-10-23T09:00:00Z", "type": "session_meta", "payload": meta}] + events
            (day / ("rollout-%s.jsonl" % name)).write_text("\n".join(json.dumps(x) for x in lines))

        rollout("m", {"id": "M"}, [{"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": "합침"}}])
        rollout("c", {"id": "C", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "M", "agent_role": "explorer",
                                                                          "agent_nickname": "Huygens"}}}},
                [{"type": "turn_context", "payload": {"model": "gpt-6-luna", "effort": "medium"}},
                 {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 5}}}},
                 {"type": "event_msg", "payload": {"type": "task_started"}}])
        team = board.Rollouts(str(self.dir / "sessions")).team("M", time.time() - 3600)
        self.assertEqual(team["last_message"], "합침")
        self.assertEqual(len(team["children"]), 1)
        child = team["children"][0]
        self.assertEqual((child["role"], child["nickname"], child["state"], child["models"]),
                         ("explorer", "Huygens", "running", ["gpt-6-luna"]))
        self.assertEqual(board.team_totals(team)["total_tokens"], 5)

    def test_app_server_silence_times_out(self):
        old = os.environ["PATH"]
        os.environ["PATH"] = self.env["PATH"]
        try:
            ct = board.CodexThreads()
            t0 = time.monotonic()
            with self.assertRaises(RuntimeError):
                ct._start_timeout = 1
                ct.proc = None
                orig = ct._request
                ct._request = lambda m, p, timeout=15: orig(m, p, timeout=1)
                ct.list(limit=1)
            self.assertLess(time.monotonic() - t0, 5)                # 답 없는 app-server 에 매달리지 않는다
        finally:
            os.environ["PATH"] = old
            ct._close()

    def test_non_loopback_needs_flag(self):
        self.assertTrue(board.is_loopback("127.0.0.1"))
        self.assertTrue(board.is_loopback("localhost"))
        self.assertFalse(board.is_loopback("0.0.0.0"))
        p = subprocess.run([sys.executable, str(HERE / "board.py"), "--host", "0.0.0.0", "--port", "0"],
                           capture_output=True, text=True, timeout=15)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--allow-remote", p.stderr)

    def test_server_token_sse_and_static_guard(self):
        import socket
        import urllib.request
        import urllib.error
        dist = self.dir / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<!doctype html><title>보드</title>")
        (self.dir / "secret.txt").write_text("비밀")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = dict(self.env, HOME=str(self.dir))
        p = subprocess.Popen([sys.executable, str(HERE / "board.py"), "--port", str(port), "--token", "tok",
                              "--web-dist", str(dist), "--sessions", str(self.dir / "s"), "--claude", str(self.dir / "c"),
                              "--runs", str(self.runs), "--wiki", str(self.dir / "w")],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(p.kill)
        base = "http://127.0.0.1:%d" % port
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)

        def code(path):
            try:
                return urllib.request.urlopen(base + path, timeout=3).getcode()
            except urllib.error.HTTPError as e:
                return e.code

        self.assertEqual(code("/api/state"), 401)                             # 토큰 없으면 막힌다
        self.assertEqual(code("/api/state?t=wrong"), 401)
        self.assertEqual(code("/api/state?t=tok"), 200)
        self.assertEqual(code("/../secret.txt"), 404)                         # 빌드 폴더 밖은 못 나간다
        self.assertEqual(code("/%2e%2e/secret.txt"), 404)
        self.assertIn("보드", urllib.request.urlopen(base + "/", timeout=3).read().decode())
        with urllib.request.urlopen(base + "/events?t=tok", timeout=5) as r:
            self.assertEqual(r.headers.get("Content-Type"), "text/event-stream; charset=utf-8")
            first = r.readline().decode()
        self.assertEqual(first.strip(), "event: state")                      # 연결하자마자 상태 한 번

    def test_parse_machines(self):
        self.assertEqual(board.parse_machines("work mac=유휴 맥북, other"), [("work mac", "유휴 맥북"), ("other", "other")])


if __name__ == "__main__":
    unittest.main()
