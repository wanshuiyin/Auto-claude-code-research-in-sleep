"""Tests for the research-wiki experiment layer — add_experiment (result-to-claim Step 5).

Closes the last freehand wiki layer. The experiment node must EXIST before
/result-to-claim adds supports/invalidates edges from it (no dangling evidence
graph). /result-to-claim is the verdict owner → it passes --update-on-exist so a
re-judge overwrites the stale verdict. Covers verdict/confidence validation, the
idea--tested_by-->exp edge, skip vs update, slug requirement, and frontmatter safety.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import research_wiki as rw  # noqa: E402


class TestExperimentLayer(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        rw.init_wiki(self.root)

    def _page(self, slug):
        return Path(self.root) / "experiments" / f"{slug}.md"

    def _edges(self):
        p = Path(self.root) / "graph" / "edges.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def test_creates_page_with_verdict_and_confidence(self):
        rw.add_experiment(self.root, "exp-001", verdict="partial", confidence="high",
                          hardware="4xH200", metrics="acc 0.71")
        fm = self._page("exp-001").read_text()
        self.assertIn("type: experiment", fm)
        self.assertIn("node_id: exp:exp-001", fm)
        self.assertIn("verdict: partial", fm)
        self.assertIn("confidence: high", fm)

    def test_invalid_verdict_rejected(self):
        for bad in ("positive", "mixed", "supported", "yes!"):
            with self.assertRaises(RuntimeError):
                rw.add_experiment(self.root, f"e-{bad}", verdict=bad)

    def test_invalid_confidence_rejected(self):
        with self.assertRaises(RuntimeError):
            rw.add_experiment(self.root, "e-c", confidence="very-high")

    def test_tested_by_edge(self):
        rw.add_experiment(self.root, "exp-002", idea="my-idea", verdict="yes")
        kinds = {(e["from"], e["type"], e["to"]) for e in self._edges()}
        self.assertIn(("idea:my-idea", "tested_by", "exp:exp-002"), kinds)

    def test_skip_on_exist_default(self):
        rw.add_experiment(self.root, "exp-003", verdict="partial")
        rw.add_experiment(self.root, "exp-003", verdict="yes")  # skip
        self.assertIn("verdict: partial", self._page("exp-003").read_text())

    def test_update_on_exist_overwrites_verdict(self):
        # the verdict owner (/result-to-claim) re-judges → must overwrite the stale verdict
        rw.add_experiment(self.root, "exp-003", verdict="partial")
        rw.add_experiment(self.root, "exp-003", verdict="yes", update_on_exist=True)
        self.assertIn("verdict: yes", self._page("exp-003").read_text())

    def test_empty_slug_rejected(self):
        with self.assertRaises(RuntimeError):
            rw.add_experiment(self.root, "   ", verdict="no")

    def test_uninitialized_wiki_raises(self):
        bare = tempfile.mkdtemp()
        with self.assertRaises(RuntimeError):
            rw.add_experiment(bare, "exp-x", verdict="no")

    def test_frontmatter_injection_neutralized(self):
        # a newline-bearing hardware/date value must not inject a second verdict line
        rw.add_experiment(self.root, "exp-inj", verdict="no",
                          hardware="gpu\nverdict: yes")
        self.assertEqual(rw._load_paper_frontmatter(self._page("exp-inj")).get("verdict"), "no")

    def test_appears_in_index(self):
        rw.add_experiment(self.root, "exp-idx", verdict="yes")
        self.assertIn("exp-idx", (Path(self.root) / "index.md").read_text())


if __name__ == "__main__":
    unittest.main()
