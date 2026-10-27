"""korean_style_guard.py 시험. 가짜 Claude Code 대화 기록과 Codex rollout 으로 잡을 것 · 넘길 것을 본다."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "korean_style_guard.py"
DASH = "—"
HANGUL_ESCAPE = "\\" + "u" + "ac00"       # 파일에 그대로 쓰면 깨지는 꼴. 시험 파일에는 조각으로 둔다


def prompt(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def answer(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def tool(name, tool_id=None, **inp):
    item = {"type": "tool_use", "name": name, "input": inp}
    if tool_id:
        item["id"] = tool_id
    return {"type": "assistant", "message": {"content": [item]}}


def result(tool_id, **res):
    """Claude Code 가 도구 결과 줄에 남기는 toolUseResult(Edit 은 originalFile · structuredPatch)."""
    return {"type": "user", "toolUseResult": res,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}]}}


def js_string(text):
    return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def codex_meta(cwd="/repo"):
    return {"type": "session_meta", "payload": {"id": "s", "cwd": cwd}}


def codex_turn():
    return {"type": "event_msg", "payload": {"type": "task_started"}}


def codex_answer(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                 "content": [{"type": "output_text", "text": text}]}}


def codex_exec(js):
    return {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "input": js}}


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.state = self.dir / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_guard(self, entries, session="s1", active=False):
        path = self.dir / ("%s.jsonl" % session)
        path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n", encoding="utf-8")
        data = {"session_id": session, "transcript_path": str(path), "stop_hook_active": active}
        env = dict(os.environ, STYLE_GUARD_STATE=str(self.state))
        p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(data), capture_output=True,
                           text=True, env=env, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def assertBlocked(self, out, *words):
        self.assertEqual(out.get("decision"), "block", out)
        for w in words:
            self.assertIn(w, out["reason"])

    def test_bold_attached_to_korean_in_answer(self):
        self.assertBlocked(self.run_guard([prompt("해 줘"), answer("결과는 **굵게**가 붙었습니다.")]), "답: 굵게")

    def test_code_backtick_and_quote_are_skipped(self):
        text = "`a %s b` 와 `**굵게**는` 은 코드다.\n```\nx %s y\n```\n> 인용 %s 원문\n끝났습니다." % (DASH, DASH, DASH)
        self.assertEqual(self.run_guard([prompt("해 줘"), answer(text)]), {})

    def test_only_current_turn(self):
        out = self.run_guard([prompt("하나"), answer("앞 턴 %s 줄표" % DASH), prompt("둘"), answer("깨끗한 답입니다.")])
        self.assertEqual(out, {})

    def test_markdown_file_dash(self):
        out = self.run_guard([prompt("써 줘"), tool("Write", file_path="/x/notes.md", content="제목 %s 부제" % DASH),
                              answer("썼습니다.")])
        self.assertBlocked(out, "파일 notes.md: 줄표")

    def test_edit_checks_only_new_text(self):
        out = self.run_guard([prompt("고쳐 줘"), tool("Edit", file_path="/x/a.md", old_string="옛 %s 글" % DASH,
                                                       new_string="새 글"), answer("고쳤습니다.")])
        self.assertEqual(out, {})

    def test_vocabulary_word_and_exceptions(self):
        self.assertBlocked(self.run_guard([prompt("써"), tool("Write", file_path="/x/a.md", content="고아 노트를 정리")]),
                           "쓰지 않는 단어")
        mention = "금지어 「고아」와 줄표(%s), 예문 「제목 %s 부제」는 언급이다." % (DASH, DASH)
        self.assertEqual(self.run_guard([prompt("써"), answer(mention)], session="s2"), {})
        self.assertEqual(self.run_guard([prompt("써"), answer("배우 고아성이 나온다.")], session="s3"), {})
        rules = tool("Write", file_path="/repo/rules/vocabulary.md", content="| 고아 | 미해결 링크 | **굵게**는 %s" % DASH)
        self.assertEqual(self.run_guard([prompt("써"), rules], session="s4"), {})

    def test_hangul_escape_in_any_file(self):
        out = self.run_guard([prompt("써"), tool("Write", file_path="/x/a.json", content='{"t": "%s"}' % HANGUL_ESCAPE)])
        self.assertBlocked(out, "파일 a.json: 한글 이스케이프")
        other = "\\" + "u2014"                # 한글이 아닌 이스케이프는 넘긴다
        self.assertEqual(self.run_guard([prompt("써"), tool("Write", file_path="/x/b.py", content=other)], session="s2"), {})

    def test_commit_credit_line(self):
        cmd = "git commit -F - <<'EOF'\nfix: 고친다\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nEOF"
        self.assertBlocked(self.run_guard([prompt("커밋"), tool("Bash", command=cmd)]), "커밋 메시지: Claude 표기")

    def test_once_per_user_turn(self):
        entries = [prompt("해"), answer("결과 %s 이렇다" % DASH)]
        # 다른 Stop 훅이 되돌린 뒤(stop_hook_active)라도 이 훅이 아직 묻지 않았으면 본다
        self.assertBlocked(self.run_guard(entries, active=True), "줄표")
        # 한 번 되돌린 뒤에는 같은 지시 안에서 다시 묻지 않는다(설명에 또 줄표가 있어도)
        self.assertEqual(self.run_guard(entries + [answer("인용 %s 이라 그대로 둡니다." % DASH)], active=True), {})
        self.assertEqual(self.run_guard(entries + [answer("또 %s" % DASH)]), {})
        # 새 지시가 오면 다시 본다
        self.assertBlocked(self.run_guard(entries + [prompt("다음"), answer("새 %s 글" % DASH)]), "줄표")

    def test_scheduled_session_passes(self):
        self.assertEqual(self.run_guard([prompt("<scheduled-task name='x'>"), answer("a %s b" % DASH)]), {})

    def test_codex_answer_and_patch(self):
        self.assertBlocked(self.run_guard([codex_meta(), codex_turn(), codex_answer("끝 %s 났다" % DASH)]), "답: 줄표")
        js = 'text(await tools.apply_patch("*** Begin Patch\\n*** Add File: /x/notes.md\\n+**굵게**를 썼다\\n*** End Patch"))'
        self.assertBlocked(self.run_guard([codex_meta(), codex_turn(), codex_exec(js)], session="c2"),
                           "파일 notes.md: 굵게")

    def test_codex_previous_turn_is_ignored(self):
        out = self.run_guard([codex_meta(), codex_turn(), codex_answer("앞 %s 턴" % DASH), codex_turn(),
                              codex_answer("깨끗합니다.")])
        self.assertEqual(out, {})

    def test_edit_inside_existing_code_block_passes(self):
        doc = self.dir / "doc.md"
        doc.write_text('설명입니다.\n\n```python\nexample = "a %s b"\n```\n' % DASH, encoding="utf-8")
        out = self.run_guard([prompt("고쳐"), tool("Edit", file_path=str(doc), old_string="x",
                                                   new_string='example = "a %s b"' % DASH)])
        self.assertEqual(out, {})

    def test_edit_outside_code_block_is_checked_in_file(self):
        doc = self.dir / "doc.md"
        doc.write_text("```\ncode\n```\n제목 %s 부제\n" % DASH, encoding="utf-8")
        out = self.run_guard([prompt("고쳐"), tool("Edit", file_path=str(doc), old_string="x", new_string="제목 %s 부제" % DASH)])
        self.assertBlocked(out, "파일 doc.md: 줄표")

    def test_git_C_commit_message_is_checked(self):
        cmd = 'git -C /repo commit -m "feat: 기능 %s 고친다"' % DASH
        self.assertBlocked(self.run_guard([prompt("커밋"), tool("Bash", command=cmd)]), "커밋 메시지: 줄표")

    def test_other_command_after_commit_is_not_message(self):
        cmd = "git commit -m \"fix: 정상\" && python3 -c 'print(\"고아 %s\")'" % DASH
        self.assertEqual(self.run_guard([prompt("커밋"), tool("Bash", command=cmd)]), {})

    def test_cat_heredoc_message_is_checked(self):
        cmd = ("git commit -m \"$(cat <<'EOF'\nfix: 고친다\n\nCo-Authored-By: Claude <noreply@anthropic.com>\nEOF\n)\"\n"
               "git log -1")
        self.assertBlocked(self.run_guard([prompt("커밋"), tool("Bash", command=cmd)]), "커밋 메시지: Claude 표기")

    def test_message_file_relative_to_C(self):
        (self.dir / "msg.txt").write_text("fix: 줄표 %s 있음\n" % DASH, encoding="utf-8")
        cmd = "git -C %s commit -F msg.txt" % self.dir
        self.assertBlocked(self.run_guard([prompt("커밋"), tool("Bash", command=cmd)]), "커밋 메시지: 줄표")

    def test_codex_exec_commit(self):
        js = 'text(await tools.exec_command({cmd:"git -C /r commit -m \\"x %s y\\""}))' % DASH
        self.assertBlocked(self.run_guard([codex_meta(), codex_turn(), codex_exec(js)]), "커밋 메시지: 줄표")
        js2 = 'text(await tools.exec_command({cmd:"git status && echo 고아"}))'
        self.assertEqual(self.run_guard([codex_meta(), codex_turn(), codex_exec(js2)], session="c2"), {})

    def test_escape_range_in_code_passes(self):
        a, b = "\\" + "u" + "ac00", "\\" + "u" + "d7a3"
        out = self.run_guard([prompt("써"), tool("Write", file_path="/x/k.py", content="re.compile('[%s-%s]+')" % (a, b))])
        self.assertEqual(out, {})

    def test_edit_location_from_original_file(self):
        doc = self.dir / "doc.md"
        line = "x %s y" % DASH
        orig = "```\n%s\n```\n옛 문장\n" % line            # 같은 글이 코드 예문에 먼저 있고, 고친 곳은 본문
        doc.write_text(orig.replace("옛 문장", line), encoding="utf-8")
        out = self.run_guard([prompt("고쳐"), tool("Edit", "t1", file_path=str(doc), old_string="옛 문장", new_string=line),
                              result("t1", originalFile=orig, oldString="옛 문장", newString=line, structuredPatch=[])])
        self.assertBlocked(out, "파일 doc.md: 줄표")
        orig2 = "%s\n```\n옛 코드\n```\n" % line            # 같은 글이 본문에 먼저 있고, 고친 곳은 코드 안
        doc.write_text(orig2.replace("옛 코드", line), encoding="utf-8")
        out = self.run_guard([prompt("고쳐"), tool("Edit", "t2", file_path=str(doc), old_string="옛 코드", new_string=line),
                              result("t2", originalFile=orig2, oldString="옛 코드", newString=line, structuredPatch=[])],
                             session="s2")
        self.assertEqual(out, {})

    def test_edit_location_from_structured_patch(self):
        doc = self.dir / "doc.md"
        line = "x %s y" % DASH
        doc.write_text("```\n%s\n```\n%s\n" % (line, line), encoding="utf-8")
        prose = [{"oldStart": 4, "oldLines": 1, "newStart": 4, "newLines": 1, "lines": ["-옛", "+" + line]}]
        code = [{"oldStart": 2, "oldLines": 1, "newStart": 2, "newLines": 1, "lines": ["-옛", "+" + line]}]
        out = self.run_guard([prompt("고쳐"), tool("Edit", "t1", file_path=str(doc), old_string="옛", new_string=line),
                              result("t1", originalFile=None, structuredPatch=prose)])
        self.assertBlocked(out, "파일 doc.md: 줄표")
        out = self.run_guard([prompt("고쳐"), tool("Edit", "t2", file_path=str(doc), old_string="옛", new_string=line),
                              result("t2", originalFile=None, structuredPatch=code)], session="s2")
        self.assertEqual(out, {})

    def test_codex_patch_hunk_location(self):
        doc = self.dir / "doc.md"
        line = "x %s y" % DASH
        doc.write_text("```\n%s\n```\n\n제목\n%s\n" % (line, line), encoding="utf-8")
        prose = "*** Begin Patch\n*** Update File: %s\n@@\n 제목\n+%s\n*** End Patch" % (doc, line)
        out = self.run_guard([codex_meta(), codex_turn(), codex_exec("text(await tools.apply_patch(%s))" % js_string(prose))])
        self.assertBlocked(out, "파일 doc.md: 줄표")
        doc.write_text("제목\n%s\n```\n%s\n```\n" % (line, line), encoding="utf-8")
        code = "*** Begin Patch\n*** Update File: %s\n@@\n ```\n+%s\n ```\n*** End Patch" % (doc, line)
        out = self.run_guard([codex_meta(), codex_turn(), codex_exec("text(await tools.apply_patch(%s))" % js_string(code))],
                             session="c2")
        self.assertEqual(out, {})

    def test_codex_workdir_and_claude_cd(self):
        other = self.dir / "other"
        other.mkdir()
        (other / "msg.txt").write_text("fix: 줄표 %s 있음\n" % DASH, encoding="utf-8")
        js = "text(await tools.exec_command({cmd: %s, workdir: %s}))" % (js_string("git commit -F msg.txt"), js_string(str(other)))
        self.assertBlocked(self.run_guard([codex_meta("/repo"), codex_turn(), codex_exec(js)]), "커밋 메시지: 줄표")
        cmd = "cd %s && git commit -F msg.txt" % other
        self.assertBlocked(self.run_guard([prompt("커밋"), tool("Bash", command=cmd)], session="s2"), "커밋 메시지: 줄표")


if __name__ == "__main__":
    unittest.main()
