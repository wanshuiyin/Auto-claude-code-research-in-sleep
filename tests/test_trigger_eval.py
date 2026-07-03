#!/usr/bin/env python3
"""Unit tests for tools/meta_opt/trigger_eval.py — the pure stream-parse /
classify / aggregate logic. No live `claude` subprocess is invoked (the probe
layer is I/O and not unit-tested here); these lock the grading semantics that
turn a raw stream into a trigger/confusion/miss verdict.

Run: python3 tests/test_trigger_eval.py   (also pytest-compatible)
"""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "trigger_eval", REPO / "tools" / "meta_opt" / "trigger_eval.py")
TE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TE)


def _assistant_event(content_blocks):
    return json.dumps({"type": "assistant", "message": {"content": content_blocks}})


def _skill_use(skill_name):
    return {"type": "tool_use", "name": "Skill", "input": {"skill": skill_name}}


def _read_use(path):
    return {"type": "tool_use", "name": "Read", "input": {"file_path": path}}


class ParseStreamTest(unittest.TestCase):
    def test_extracts_tool_uses_across_lines(self):
        stream = "\n".join([
            json.dumps({"type": "system", "subtype": "init"}),
            _assistant_event([{"type": "text", "text": "ok"}, _skill_use("check-gpu")]),
            "not json noise on stderr",
            json.dumps({"type": "result", "subtype": "success"}),
        ])
        uses = TE.parse_stream_tool_uses(stream)
        self.assertEqual(uses, [("Skill", {"skill": "check-gpu"})])

    def test_skips_malformed_and_non_assistant(self):
        stream = "\n".join(["", "{bad json", json.dumps({"type": "user"}),
                            _assistant_event([_read_use("/x/skills/foo/SKILL.md")])])
        self.assertEqual(TE.parse_stream_tool_uses(stream),
                         [("Read", {"file_path": "/x/skills/foo/SKILL.md"})])


class ClassifyTest(unittest.TestCase):
    def test_skill_call_for_target_is_trigger(self):
        out, detail = TE.classify([("Skill", {"skill": "check-gpu"})], "check-gpu")
        self.assertEqual(out, "trigger")
        self.assertEqual(detail, "check-gpu")

    def test_plugin_namespaced_target_matches_on_tail_but_is_tagged(self):
        out, detail = TE.classify([("Skill", {"skill": "myplugin:check-gpu"})], "check-gpu")
        self.assertEqual(out, "trigger")
        # namespaced match must be surfaced distinctly, not silently == exact
        self.assertIn("namespaced", detail)
        self.assertIn("myplugin:check-gpu", detail)

    def test_namespaced_target_does_not_tail_match(self):
        # if the TARGET itself is namespaced, don't fuzzy-tail-match a bare id
        out, _ = TE.classify([("Skill", {"skill": "check-gpu"})], "plug:check-gpu")
        self.assertEqual(out, "confusion")

    def test_different_skill_is_confusion_with_name(self):
        out, detail = TE.classify([("Skill", {"skill": "vast-gpu"})], "check-gpu")
        self.assertEqual(out, "confusion")
        self.assertEqual(detail, "vast-gpu")

    def test_reading_target_skill_md_is_trigger(self):
        out, _ = TE.classify(
            [("Read", {"file_path": "/home/u/.claude/skills/research-lit/SKILL.md"})],
            "research-lit")
        self.assertEqual(out, "trigger")

    def test_no_skill_engagement_is_miss(self):
        out, _ = TE.classify([("Bash", {"command": "ls"})], "check-gpu")
        self.assertEqual(out, "miss")
        self.assertEqual(TE.classify([], "check-gpu")[0], "miss")

    def test_first_skill_call_decides(self):
        # a confusion followed by the correct skill still counts as confusion:
        # the model reached for the wrong skill first.
        out, detail = TE.classify(
            [("Skill", {"skill": "vast-gpu"}), ("Skill", {"skill": "check-gpu"})],
            "check-gpu")
        self.assertEqual((out, detail), ("confusion", "vast-gpu"))


class AggregateTest(unittest.TestCase):
    def test_rate_excludes_errors_from_denominator(self):
        recs = [
            {"skill": "s", "query": "q1", "outcome": "trigger", "detail": "s"},
            {"skill": "s", "query": "q1", "outcome": "miss", "detail": ""},
            {"skill": "s", "query": "q2", "outcome": "confusion", "detail": "other"},
            {"skill": "s", "query": "q2", "outcome": "error", "detail": "boom"},
        ]
        agg = TE.aggregate(recs)["s"]
        # graded = 3 (error excluded); triggers = 1 → 0.333
        self.assertEqual(agg["trigger_rate"], 0.333)
        self.assertEqual(agg["probes"], 4)
        self.assertEqual(agg["errors"], 1)
        self.assertEqual(agg["confusions"], {"other": 1})

    def test_all_errors_gives_none_rate_not_zerodiv(self):
        recs = [{"skill": "s", "query": "q", "outcome": "error", "detail": "x"}]
        self.assertIsNone(TE.aggregate(recs)["s"]["trigger_rate"])


class StreamErrorTest(unittest.TestCase):
    def test_max_turns_termination_is_NOT_a_real_error(self):
        # the probe deliberately caps at 1 turn; error_max_turns is the expected
        # successful ending, not a failure — must be gradeable.
        stream = "\n".join([
            _assistant_event([_skill_use("check-gpu")]),
            json.dumps({"type": "result", "is_error": True, "subtype": "error_max_turns"}),
        ])
        self.assertFalse(TE._stream_real_error(stream))
        self.assertTrue(TE._stream_has_assistant(stream))

    def test_genuine_error_subtype_is_detected(self):
        stream = json.dumps({"type": "result", "is_error": True,
                             "subtype": "error_during_execution"})
        self.assertTrue(TE._stream_real_error(stream))

    def test_clean_success_result_is_not_error(self):
        stream = "\n".join([
            _assistant_event([_skill_use("check-gpu")]),
            json.dumps({"type": "result", "subtype": "success", "is_error": False}),
        ])
        self.assertFalse(TE._stream_real_error(stream))
        self.assertTrue(TE._stream_has_assistant(stream))

    def test_no_assistant_turn_detected(self):
        stream = "\n".join([json.dumps({"type": "system", "subtype": "init"}),
                            json.dumps({"type": "result", "subtype": "success"})])
        self.assertFalse(TE._stream_has_assistant(stream))


class DenyToolsTest(unittest.TestCase):
    def test_stateful_tools_are_denied(self):
        # the safety invariant: side-effecting tools are on the deny list
        for t in ("Bash", "Write", "Edit"):
            self.assertIn(t, TE._DENY_TOOLS)
        # the tools we SCORE on must NOT be denied (or we'd never see a trigger)
        for t in ("Skill", "Read"):
            self.assertNotIn(t, TE._DENY_TOOLS)


class SampleEvalFileTest(unittest.TestCase):
    def test_sample_file_is_valid_and_well_formed(self):
        data = json.loads(
            (REPO / "tools" / "meta_opt" / "trigger_evals.sample.json").read_text())
        skills = {k: v for k, v in data.items() if not k.startswith("_")}
        self.assertTrue(skills)
        for name, queries in skills.items():
            self.assertIsInstance(queries, list, name)
            self.assertTrue(queries, f"{name} has no queries")
            for q in queries:
                self.assertIsInstance(q, str)
                self.assertTrue(q.strip())


if __name__ == "__main__":
    unittest.main()
