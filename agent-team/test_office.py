"""office.py 회귀 시험 — 가짜 Codex 세션 기록·Claude 대화 기록으로 상태와 팀 묶음을 본다."""
import json
import os
import re
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import office  # noqa: E402

NOW = time.time()


def stamp(sec_ago):
    return datetime.fromtimestamp(NOW - sec_ago, timezone.utc).isoformat().replace("+00:00", "Z")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.codex = self.root / "codex"
        self.claude = self.root / "claude"
        self.day = self.codex / datetime.fromtimestamp(NOW).strftime("%Y/%m/%d")
        self.day.mkdir(parents=True)
        (self.claude / "-proj").mkdir(parents=True)

    def write(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")

    def registry(self, **kw):
        reg = office.Registry(str(self.codex), str(self.claude), **kw)
        reg.refresh(NOW)
        return reg

    def codex_team(self):
        self.write(self.day / "rollout-a-M.jsonl", [
            {"timestamp": stamp(300), "type": "session_meta", "payload": {"id": "M", "source": "exec", "cwd": "/w/repo"}},
            {"timestamp": stamp(299), "type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "high"}},
            {"timestamp": stamp(298), "type": "event_msg", "payload": {"type": "task_started"}},
            {"timestamp": stamp(290), "type": "response_item", "payload": {"type": "function_call", "name": "wait_agent", "call_id": "w1"}},
        ])
        self.write(self.day / "rollout-b-C.jsonl", [
            {"timestamp": stamp(280), "type": "session_meta", "payload": {"id": "C", "parent_thread_id": "M",
             "source": {"subagent": {"thread_spawn": {"parent_thread_id": "M", "agent_role": "explorer", "agent_nickname": "Huygens"}}}}},
            {"timestamp": stamp(270), "type": "event_msg", "payload": {"type": "task_started"}},
            {"timestamp": stamp(20), "type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "call_id": "x1",
             "input": 'const r = await tools.exec_command({cmd:"rg -n token board.py"});'}},
            {"timestamp": stamp(19), "type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"input_tokens": 47000, "output_tokens": 500}, "model_context_window": 475000,
                "total_token_usage": {"total_tokens": 99000, "output_tokens": 3000}}}},
        ])


class ParserTests(unittest.TestCase):
    def test_classify_command(self):
        self.assertEqual(office.classify_command("rg -n foo src"), (office.READING, "rg"))
        self.assertEqual(office.classify_command("git log --oneline -3"), (office.READING, "git log"))
        self.assertEqual(office.classify_command("git commit -m x"), (office.TYPING, "git commit"))
        self.assertEqual(office.classify_command("sed -i s/a/b/ f"), (office.TYPING, "sed -i"))
        self.assertEqual(office.classify_command("TOKEN=abc python3 run.py"), (office.TYPING, "python3"))

    def test_command_text_is_never_shown(self):
        mode, label = office.classify_claude_tool("Bash", {"command": "curl -H 'Authorization: Bearer SECRET' x"})
        self.assertNotIn("SECRET", label)                     # 명령 전체가 아니라 첫 단어만
        mode, label = office.classify_claude_tool("Bash", {"command": "ls", "description": "폴더 보기"})
        self.assertEqual((mode, label), (office.READING, "폴더 보기"))

    def test_prompt_title_skips_injected_blocks(self):
        self.assertIsNone(office.prompt_title("# AGENTS.md instructions for /x"))
        self.assertIsNone(office.prompt_title("<environment_context>…"))
        self.assertEqual(office.prompt_title("<task>\nRun a stop-gate review"), "Run a stop-gate review")

    def test_claude_end_turn_waits_for_input(self):
        t = office.AgentTrack("s", "claude")
        t.apply(office.parse_claude_line({"type": "assistant", "message": {"stop_reason": "end_turn", "content": []}}), NOW)
        self.assertEqual(t.status(NOW, 600)[0], office.WAITING)

    def test_tail_reader_reads_only_new_complete_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl"
            p.write_text('{"a":1}\n{"b":')
            r = office.TailReader(str(p))
            self.assertEqual(r.read_new(), [{"a": 1}])            # 덜 쓰인 줄은 기다린다
            with open(p, "a") as f:
                f.write('2}\n{"c":3}\n')
            self.assertEqual(r.read_new(), [{"b": 2}, {"c": 3}])
            self.assertEqual(r.read_new(), [])

    def test_tail_reader_skips_cut_first_line_on_big_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl"
            p.write_text("\n".join(json.dumps({"i": i, "pad": "x" * 50}) for i in range(100)) + "\n")
            got = office.TailReader(str(p), initial_bytes=500).read_new()
            self.assertTrue(got and got[-1]["i"] == 99)
            self.assertTrue(all("pad" in g for g in got))       # 잘린 첫 줄이 깨진 값으로 들어오지 않는다


class RegistryTests(Fixture):
    def test_codex_team_tree_and_states(self):
        self.codex_team()
        o = office.build_office(self.registry(), NOW, local_label="L")
        team = o["rooms"][0]["teams"][0]
        self.assertEqual(team["lead"]["status"], office.TEAM)                  # 매니저는 팀을 기다린다
        child = team["members"][0]
        self.assertEqual((child["role"], child["nickname"], child["status"]), ("explorer", "Huygens", office.READING))
        self.assertEqual(child["activity"], "rg")
        self.assertEqual(child["context"]["pct"], 10.0)                        # (47000+500)/475000

    def test_stalled_after_silence(self):
        self.codex_team()
        o = office.build_office(self.registry(stall_sec=10), NOW + 60, local_label="L")
        child = o["rooms"][0]["teams"][0]["members"][0]
        self.assertEqual(child["status"], office.STALLED)

    def test_exec_subagent_done_after_task_complete(self):
        self.codex_team()
        with open(self.day / "rollout-b-C.jsonl", "a") as f:
            f.write(json.dumps({"timestamp": stamp(5), "type": "event_msg",
                                "payload": {"type": "task_complete", "last_agent_message": "보고"}}) + "\n")
        o = office.build_office(self.registry(), NOW, local_label="L")
        child = o["rooms"][0]["teams"][0]["members"][0]
        self.assertEqual((child["status"], child["lastMessage"]), (office.DONE, "보고"))

    def test_claude_session_with_subagent(self):
        sess = self.claude / "-proj" / "S1.jsonl"
        self.write(sess, [
            {"type": "ai-title", "aiTitle": "integrate-tools"},
            {"timestamp": stamp(30), "type": "assistant", "cwd": "/w/proj", "message": {"model": "claude-x", "stop_reason": "tool_use",
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 99990, "output_tokens": 0},
             "content": [{"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "/w/proj/app.ts"}}]}},
        ])
        self.write(self.claude / "-proj" / "S1" / "subagents" / "agent-a1.jsonl", [
            {"timestamp": stamp(10), "type": "assistant", "message": {"stop_reason": "tool_use",
             "content": [{"type": "tool_use", "id": "g1", "name": "Grep", "input": {}}]}}])
        (self.claude / "-proj" / "S1" / "subagents" / "agent-a1.meta.json").write_text(
            json.dumps({"agentType": "Explore", "description": "찾기", "finished": False}))
        o = office.build_office(self.registry(), NOW, local_label="L")
        team = o["rooms"][0]["teams"][0]
        self.assertEqual((team["lead"]["title"], team["lead"]["status"], team["lead"]["activity"]),
                         ("integrate-tools", office.TYPING, "Edit app.ts"))
        self.assertEqual(team["lead"]["context"]["pct"], 50.0)                 # 100000/200000
        self.assertEqual((team["members"][0]["role"], team["members"][0]["status"]), ("Explore", office.READING))
        self.assertIsNone(team["lead"]["lastMessage"])                        # Claude 대화 내용은 싣지 않는다

    def test_herdr_blocked_marks_permission(self):
        sess = self.claude / "-proj" / "S2.jsonl"
        self.write(sess, [{"timestamp": stamp(5), "type": "assistant", "cwd": "/w/proj",
                           "message": {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "rm x"}}]}}])
        sessions = {"local": [{"agent": "claude", "status": "blocked", "cwd": "/w/proj"}], "remote": {}}
        o = office.build_office(self.registry(), NOW, sessions=sessions, local_label="L")
        self.assertEqual(o["rooms"][0]["teams"][0]["lead"]["status"], office.PERMISSION)

    def test_hide_pattern_counts_lonely_reviews(self):
        self.write(self.day / "rollout-r-R.jsonl", [
            {"timestamp": stamp(60), "type": "session_meta", "payload": {"id": "R", "source": "vscode"}},
            {"timestamp": stamp(59), "type": "response_item", "payload": {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "<task>\nRun a stop-gate review of x"}]}}])
        o = office.build_office(self.registry(), NOW, local_label="L", hide_re=re.compile("^Run a stop-gate review"))
        self.assertEqual((len(o["rooms"][0]["teams"]), o["rooms"][0]["hidden"]), (0, 1))

    def test_remote_room_from_herdr(self):
        sessions = {"local": [], "remote": {"Sub Mac": [{"agent": "codex", "status": "working", "pane": "w1:p2", "title": "t"}]}}
        o = office.build_office(self.registry(), NOW, sessions=sessions, local_label="L")
        self.assertEqual(o["rooms"][1]["teams"][0]["lead"]["status"], office.TYPING)


if __name__ == "__main__":
    unittest.main()

class StatusChangedAtTests(unittest.TestCase):
    def test_status_clock_changes_only_when_status_changes(self):
        track = office.AgentTrack('demo', 'codex')
        track.apply([('turn_start', {})], 1000)
        self.assertEqual(track.snapshot(1001, 600)['statusChangedAt'], office.iso(1000))
        track.apply([('context', {'used': 200})], 1010)
        self.assertEqual(track.snapshot(1011, 600)['statusChangedAt'], office.iso(1000))
        track.apply([('turn_end', {'awaiting_input': True})], 1020)
        self.assertEqual(track.snapshot(1021, 600)['statusChangedAt'], office.iso(1020))
        self.assertEqual(track.snapshot(1030, 600)['statusChangedAt'], office.iso(1020))

    def test_stalled_clock_uses_threshold_and_does_not_reset(self):
        track = office.AgentTrack('demo', 'codex')
        track.apply([('turn_start', {})], 1000)
        self.assertEqual(track.snapshot(1700, 600)['statusChangedAt'], office.iso(1600))
        self.assertEqual(track.snapshot(1800, 600)['statusChangedAt'], office.iso(1600))


class ReviewFixTests(Fixture):
    """2026-10-26 결함 검토에서 확인한 것들."""

    def test_assignment_value_never_becomes_label(self):
        # 소문자 · 숫자가 섞인 변수 이름도 값까지 버린다(전에는 이름표가 'API_TOKEN2=secret-value' 였다)
        mode, label = office.classify_command("API_TOKEN2=secret-value curl https://x")
        self.assertEqual((mode, label), (office.TYPING, "curl"))
        self.assertNotIn("secret", office.classify_command("myKey_1=s3cret rg x")[1])

    def test_cd_prefix_and_write_like_flags(self):
        c = office.classify_command
        self.assertEqual(c("cd /repo && rg x"), (office.READING, "rg"))
        self.assertEqual(c("git branch"), (office.READING, "git branch"))
        self.assertEqual(c("git branch -a --list"), (office.READING, "git branch"))
        self.assertEqual(c("git branch -D work"), (office.TYPING, "git branch"))
        self.assertEqual(c("git branch new-name"), (office.TYPING, "git branch"))
        self.assertEqual(c("sed -i.bak s/a/b/ f"), (office.TYPING, "sed -i"))
        self.assertEqual(c("find . -name '*.pyc' -delete"), (office.TYPING, "find"))
        self.assertEqual(c("find . -name '*.py'"), (office.READING, "find"))

    def test_lead_final_message_is_not_shown(self):
        # README: 대화 내용은 싣지 않고 Codex 하위 에이전트 보고문만 예외다
        self.codex_team()
        with open(self.day / "rollout-a-M.jsonl", "a") as f:
            f.write(json.dumps({"timestamp": stamp(4), "type": "event_msg",
                                "payload": {"type": "task_complete", "last_agent_message": "리더 최종 답변"}}) + "\n")
        with open(self.day / "rollout-b-C.jsonl", "a") as f:
            f.write(json.dumps({"timestamp": stamp(5), "type": "event_msg",
                                "payload": {"type": "task_complete", "last_agent_message": "하위 보고"}}) + "\n")
        team = office.build_office(self.registry(), NOW, local_label="L")["rooms"][0]["teams"][0]
        self.assertIsNone(team["lead"]["lastMessage"])
        self.assertEqual(team["members"][0]["lastMessage"], "하위 보고")

    def test_one_bad_file_does_not_stop_the_office(self):
        self.codex_team()
        (self.day / "rollout-z-bad.jsonl").write_text('{"type":"session_meta","payload":["bad"]}\n"str"\n')
        (self.day / "rollout-y-str.jsonl").write_text('"just a string"\n')
        reg = self.registry()
        o = office.build_office(reg, NOW, local_label="L")
        ids = [t["lead"]["id"] for t in o["rooms"][0]["teams"]]
        self.assertIn("M", ids)                                          # 멀쩡한 팀은 그대로 보인다

    def test_session_started_days_ago_is_found(self):
        old = self.codex / datetime.fromtimestamp(NOW - 3 * 86400).strftime("%Y/%m/%d")
        self.write(old / "rollout-old-O.jsonl", [
            {"timestamp": stamp(3 * 86400), "type": "session_meta", "payload": {"id": "O", "source": "cli", "cwd": "/w/old"}},
            {"timestamp": stamp(30), "type": "event_msg", "payload": {"type": "task_started"}},
        ])
        os.utime(old / "rollout-old-O.jsonl", (NOW - 30, NOW - 30))       # 지금도 쓰고 있다
        o = office.build_office(self.registry(), NOW, local_label="L")
        self.assertIn("O", [t["lead"]["id"] for t in o["rooms"][0]["teams"]])

    def test_remote_room_keeps_last_list_and_shows_error(self):
        sessions = {"local": [], "remote": {"M": [{"pane": "r1", "agent": "codex", "status": "idle"}]},
                    "remote_errors": {"M": "연결 실패"}}
        o = office.build_office(self.registry(), NOW, sessions=sessions, local_label="L")
        room = next(r for r in o["rooms"] if r["label"] == "M")
        self.assertEqual((len(room["teams"]), room["error"]), (1, "연결 실패"))
