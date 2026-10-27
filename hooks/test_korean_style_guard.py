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

    def put(self, name, content):
        """도구가 쓴 결과처럼 파일을 만든다. 훅은 Stop 때의 파일을 읽는다."""
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)

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
        path = self.put("notes.md", "제목 %s 부제" % DASH)
        out = self.run_guard([prompt("써 줘"), tool("Write", file_path=path, content="제목 %s 부제" % DASH),
                              answer("썼습니다.")])
        self.assertBlocked(out, "파일 notes.md: 줄표")

    def test_edit_checks_only_new_text(self):
        out = self.run_guard([prompt("고쳐 줘"), tool("Edit", file_path="/x/a.md", old_string="옛 %s 글" % DASH,
                                                       new_string="새 글"), answer("고쳤습니다.")])
        self.assertEqual(out, {})

    def test_vocabulary_word_and_exceptions(self):
        path = self.put("a.md", "고아 노트를 정리")
        self.assertBlocked(self.run_guard([prompt("써"), tool("Write", file_path=path, content="고아 노트를 정리")]),
                           "쓰지 않는 단어")
        mention = "금지어 「고아」와 줄표(%s), 예문 「제목 %s 부제」는 언급이다." % (DASH, DASH)
        self.assertEqual(self.run_guard([prompt("써"), answer(mention)], session="s2"), {})
        self.assertEqual(self.run_guard([prompt("써"), answer("배우 고아성이 나온다.")], session="s3"), {})
        rules = tool("Write", file_path="/repo/rules/vocabulary.md", content="| 고아 | 미해결 링크 | **굵게**는 %s" % DASH)
        self.assertEqual(self.run_guard([prompt("써"), rules], session="s4"), {})

    def test_hangul_escape_in_any_file(self):
        path = self.put("a.json", '{"t": "%s"}' % HANGUL_ESCAPE)
        out = self.run_guard([prompt("써"), tool("Write", file_path=path, content='{"t": "%s"}' % HANGUL_ESCAPE)])
        self.assertBlocked(out, "파일 a.json: 한글 이스케이프")
        other = "\\" + "u2014"                # 한글이 아닌 이스케이프는 넘긴다
        path = self.put("b.py", other)
        self.assertEqual(self.run_guard([prompt("써"), tool("Write", file_path=path, content=other)], session="s2"), {})

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
        notes = self.put("notes.md", "**굵게**를 썼다\n")
        js = 'text(await tools.apply_patch("*** Begin Patch\\n*** Add File: %s\\n+**굵게**를 썼다\\n*** End Patch"))' % notes
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
        path = self.put("k.py", "re.compile('[%s-%s]+')" % (a, b))
        out = self.run_guard([prompt("써"), tool("Write", file_path=path, content="re.compile('[%s-%s]+')" % (a, b))])
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

    def test_fixed_later_in_same_turn_passes(self):
        doc = self.dir / "doc.md"
        bad, good = "문장 %s 수정" % DASH, "문장 수정"
        doc.write_text(good + "\n", encoding="utf-8")
        out = self.run_guard([prompt("고쳐"),
                              tool("Edit", "t1", file_path=str(doc), old_string="문장 옛", new_string=bad),
                              result("t1", originalFile="문장 옛\n", oldString="문장 옛", newString=bad, structuredPatch=[]),
                              tool("Edit", "t2", file_path=str(doc), old_string=bad, new_string=good),
                              result("t2", originalFile=bad + "\n", oldString=bad, newString=good, structuredPatch=[])])
        self.assertEqual(out, {})
        out = self.run_guard([prompt("써"), tool("Write", file_path=str(doc), content=bad + "\n"),
                              tool("Edit", file_path=str(doc), old_string=bad, new_string=good)], session="s2")
        self.assertEqual(out, {})

    def test_untouched_part_of_changed_line_passes(self):
        doc = self.dir / "doc.md"
        line = "기존 %s 문장 새말" % DASH
        doc.write_text(line + "\n", encoding="utf-8")
        patch = [{"oldStart": 1, "oldLines": 1, "newStart": 1, "newLines": 1,
                  "lines": ["-기존 %s 문장 옛말" % DASH, "+" + line]}]
        out = self.run_guard([prompt("고쳐"), tool("Edit", "t1", file_path=str(doc), old_string="옛말", new_string="새말"),
                              result("t1", originalFile=None, structuredPatch=patch)])
        self.assertEqual(out, {})
        old = "기존 %s 문장 옛말" % DASH                     # Edit 는 앞뒤 글까지 함께 넘기는 일이 많다
        out = self.run_guard([prompt("고쳐"), tool("Edit", "t2", file_path=str(doc), old_string=old, new_string=line),
                              result("t2", originalFile=old + "\n", oldString=old, newString=line, structuredPatch=[])],
                             session="s2")
        self.assertEqual(out, {})
        doc.write_text("제목 %s 부제\n" % DASH, encoding="utf-8")   # 새로 넣은 줄표는 잡는다
        out = self.run_guard([prompt("고쳐"), tool("Edit", "t3", file_path=str(doc), old_string="제목 부제",
                                                    new_string="제목 %s 부제" % DASH),
                              result("t3", originalFile="제목 부제\n", oldString="제목 부제",
                                     newString="제목 %s 부제" % DASH, structuredPatch=[])], session="s3")
        self.assertBlocked(out, "파일 doc.md: 줄표")

    def test_codex_partial_line_change(self):
        doc = self.dir / "doc.md"
        doc.write_text("기존 %s 문장 새말\n" % DASH, encoding="utf-8")
        patch = "*** Begin Patch\n*** Update File: %s\n@@\n-기존 %s 문장 옛말\n+기존 %s 문장 새말\n*** End Patch" % (doc, DASH, DASH)
        out = self.run_guard([codex_meta(), codex_turn(), codex_exec("text(await tools.apply_patch(%s))" % js_string(patch))])
        self.assertEqual(out, {})
        doc.write_text("제목 %s 부제\n" % DASH, encoding="utf-8")
        patch = "*** Begin Patch\n*** Update File: %s\n@@\n-제목 부제\n+제목 %s 부제\n*** End Patch" % (doc, DASH)
        out = self.run_guard([codex_meta(), codex_turn(), codex_exec("text(await tools.apply_patch(%s))" % js_string(patch))],
                             session="c2")
        self.assertBlocked(out, "파일 doc.md: 줄표")

    def test_dash_kept_after_later_edit_on_same_line(self):
        doc = self.dir / "doc.md"
        doc.write_text("제목 %s 부제 새말\n" % DASH, encoding="utf-8")
        first = ("제목 부제 옛말", "제목 %s 부제 옛말" % DASH)
        second = ("옛말", "새말")
        with_orig = [prompt("고쳐"),
                     tool("Edit", "t1", file_path=str(doc), old_string=first[0], new_string=first[1]),
                     result("t1", originalFile=first[0] + "\n", oldString=first[0], newString=first[1], structuredPatch=[]),
                     tool("Edit", "t2", file_path=str(doc), old_string=second[0], new_string=second[1]),
                     result("t2", originalFile=first[1] + "\n", oldString=second[0], newString=second[1], structuredPatch=[])]
        self.assertBlocked(self.run_guard(with_orig), "파일 doc.md: 줄표")
        without = [prompt("고쳐"), tool("Edit", file_path=str(doc), old_string=first[0], new_string=first[1]),
                   tool("Edit", file_path=str(doc), old_string=second[0], new_string=second[1])]
        self.assertBlocked(self.run_guard(without, session="s2"), "파일 doc.md: 줄표")

    def test_write_update_checks_only_changed_lines(self):
        doc = self.dir / "doc.md"
        old_dash = "옛 줄 %s 그대로" % DASH
        doc.write_text(old_dash + "\n새 줄\n", encoding="utf-8")
        patch = [{"oldStart": 1, "oldLines": 1, "newStart": 1, "newLines": 2, "lines": [" " + old_dash, "+새 줄"]}]
        out = self.run_guard([prompt("써"), tool("Write", "t1", file_path=str(doc), content=old_dash + "\n새 줄\n"),
                              result("t1", type="update", content=old_dash + "\n새 줄\n", structuredPatch=patch, originalFile=None)])
        self.assertEqual(out, {})

    def test_codex_same_block_in_prose_and_code(self):
        doc = self.dir / "doc.md"
        line = "x %s y" % DASH
        doc.write_text("%s\n```\n%s\n```\n" % (line, line), encoding="utf-8")     # 본문의 줄은 원래 있던 글
        patch = "*** Begin Patch\n*** Update File: %s\n@@\n-옛 코드\n+%s\n*** End Patch" % (doc, line)
        out = self.run_guard([codex_meta(), codex_turn(), codex_exec("text(await tools.apply_patch(%s))" % js_string(patch))])
        self.assertEqual(out, {})

    def test_line_added_then_deleted_in_same_turn(self):
        doc = self.dir / "doc.md"
        doc.write_text("제목\n", encoding="utf-8")
        bad = "\n덧붙인 %s 줄" % DASH
        no_results = [prompt("고쳐"), tool("Edit", file_path=str(doc), old_string="제목", new_string="제목" + bad),
                      tool("Edit", file_path=str(doc), old_string=bad, new_string="")]
        self.assertEqual(self.run_guard(no_results), {})
        with_results = [prompt("고쳐"),
                        tool("Edit", "t1", file_path=str(doc), old_string="제목", new_string="제목" + bad),
                        result("t1", originalFile="제목\n", structuredPatch=[]),
                        tool("Edit", "t2", file_path=str(doc), old_string=bad, new_string=""),
                        result("t2", originalFile="제목" + bad + "\n", structuredPatch=[])]
        self.assertEqual(self.run_guard(with_results, session="s2"), {})

    def test_code_edit_with_unplaced_deletion(self):
        doc = self.dir / "doc.md"
        line = "x %s y" % DASH
        doc.write_text("```\n%s\n```\n" % line, encoding="utf-8")     # 제목 줄은 지웠다
        out = self.run_guard([prompt("코드를 고치고 제목을 지워 줘"),
                              tool("Edit", file_path=str(doc), old_string="x old y", new_string=line),
                              tool("Edit", file_path=str(doc), old_string="제목\n", new_string="")])
        self.assertEqual(out, {})

    def test_fallback_keeps_file_context(self):
        doc = self.dir / "doc.md"
        line = "x %s y" % DASH
        doc.write_text("```\n%s\n```\n" % line, encoding="utf-8")
        # 되돌릴 수 없는 기록(새 글이 지금 파일에 없는 수정이 뒤에 있다)이어도 코드 블록 안 글은 문장으로 보지 않는다
        out = self.run_guard([prompt("고쳐"), tool("Edit", file_path=str(doc), old_string="x old y", new_string=line),
                              tool("Edit", file_path=str(doc), old_string="없는 글", new_string="사라진 글")])
        self.assertEqual(out, {})
        doc.write_text("본문 %s 끝\n" % DASH, encoding="utf-8")
        out = self.run_guard([prompt("고쳐"), tool("Edit", file_path=str(doc), old_string="본문 끝", new_string="본문 %s 끝" % DASH),
                              tool("Edit", file_path=str(doc), old_string="없는 글", new_string="사라진 글")], session="s2")
        self.assertBlocked(out, "파일 doc.md: 줄표")

    def test_replace_all_without_result_keeps_existing_text(self):
        doc = self.dir / "doc.md"
        line = "A %s B" % DASH
        doc.write_text("%s\n```\n%s\n```\n" % (line, line), encoding="utf-8")   # 본문 줄은 원래 있던 글
        out = self.run_guard([prompt("고쳐"), tool("Edit", file_path=str(doc), old_string="X", new_string=line, replace_all=True)])
        self.assertEqual(out, {})

    def test_exact_original_file_wins_over_unplaced_later_edit(self):
        doc = self.dir / "doc.md"
        bad = "기존 %s 글" % DASH
        orig = bad + "\n옛\nX\n"
        after = bad + "\n" + bad + "\nX\n"
        doc.write_text(bad + "\n새 글\nY\n", encoding="utf-8")
        out = self.run_guard([prompt("고쳐"),
                              tool("Edit", "a", file_path=str(doc), old_string="옛", new_string=bad),
                              result("a", originalFile=orig),
                              tool("Edit", "b", file_path=str(doc), old_string=bad + "\nX", new_string="새 글\nX"),
                              result("b", originalFile=after),
                              tool("Edit", "c", file_path=str(doc), old_string="X", new_string="Y", replace_all=True)])
        self.assertEqual(out, {})

    def test_partial_base_when_early_edit_is_unplaced(self):
        doc = self.dir / "doc.md"
        doc.write_text("```\nx %s y\n```\n본문 %s 끝\n" % (DASH, DASH), encoding="utf-8")
        # 앞 수정(코드 안)은 결과가 없고 replace_all 이라 되돌리지 못한다. 뒤 수정(본문 줄표)은 originalFile 이 있다
        out = self.run_guard([prompt("고쳐"),
                              tool("Edit", file_path=str(doc), old_string="x old y", new_string="x %s y" % DASH, replace_all=True),
                              tool("Edit", "t2", file_path=str(doc), old_string="본문 끝", new_string="본문 %s 끝" % DASH),
                              result("t2", originalFile="```\nx %s y\n```\n본문 끝\n" % DASH)])
        self.assertBlocked(out, "파일 doc.md: 줄표")
        self.assertNotIn("x %s y" % DASH, out["reason"])

    def test_codex_unplaced_patch_checks_each_added_line(self):
        doc = self.dir / "doc.md"
        doc.write_text("머리\n새 %s 줄\n가운데\n기존 %s 문장 새말\n" % (DASH, DASH), encoding="utf-8")
        # 첫 줄 문맥이 지금 파일과 달라(뒤에 셸로 바꿈) 덩어리를 되돌릴 수 없다
        patch = ("*** Begin Patch\n*** Update File: %s\n@@\n 옛 머리\n+새 %s 줄\n 가운데\n-기존 %s 문장 옛말\n+기존 %s 문장 새말\n*** End Patch"
                 % (doc, DASH, DASH, DASH))
        out = self.run_guard([codex_meta(), codex_turn(), codex_exec("text(await tools.apply_patch(%s))" % js_string(patch))])
        self.assertBlocked(out, "파일 doc.md: 줄표")
        self.assertIn("새 %s 줄" % DASH, out["reason"])
        self.assertNotIn("문장 새말", out["reason"])

    def test_repeated_lines_do_not_misalign_diff(self):
        doc = self.dir / "doc.md"
        orig = "기존 %s 글\n\na\n기존 %s 글\n" % (DASH, DASH)
        mid = orig.replace("a", "C")
        final = mid.replace("\nC\n", "a\n")
        doc.write_text(final, encoding="utf-8")
        out = self.run_guard([prompt("본문 수정"),
                              tool("Edit", "e1", file_path=str(doc), old_string="a", new_string="C", replace_all=True),
                              tool("Edit", "e2", file_path=str(doc), old_string="\nC\n", new_string="a\n"),
                              result("e2", originalFile=mid)])
        self.assertEqual(out, {})

    def test_write_without_result_then_edit_keeps_written_dash(self):
        doc = self.dir / "doc.md"
        doc.write_text("제목 %s 부제\n새\n" % DASH, encoding="utf-8")
        out = self.run_guard([prompt("새 문서를 쓰고 끝줄을 고쳐"),
                              tool("Write", "w", file_path=str(doc), content="제목 %s 부제\n옛\n" % DASH),
                              tool("Edit", "e", file_path=str(doc), old_string="옛", new_string="새")])
        self.assertBlocked(out, "파일 doc.md: 줄표")

    def test_moved_line_is_not_new_text(self):
        doc = self.dir / "doc.md"
        line = "기존 %s 글" % DASH
        orig = "C\n\n%s\n%s\nC\n\nb" % (line, line)
        final = "C\n%s\n\n%s\nC\n\nb" % (line, line)      # 빈 줄의 자리만 옮겼다
        doc.write_text(final, encoding="utf-8")
        out = self.run_guard([prompt("줄 정리"), tool("Edit", "e", file_path=str(doc), old_string="x", new_string="y"),
                              result("e", originalFile=orig)])
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
