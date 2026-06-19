"""Tests for the research-wiki idea layer — upsert_idea (idea-creator Phase 7 write-back).

Locks the fix for "re-generated ideas not recorded": idea recording is now a
deterministic helper (not a freehand step). Covers page creation with the `outcome`
field (the one the re-ideation banlist + stats read), slug honored verbatim, outcome
validation, dedup vs --update-on-exist (so a re-gen records NEW ideas without clobbering
an enriched one), edge wiring, and that a `negative` idea lands in the query_pack banlist.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import research_wiki as rw  # noqa: E402


class TestIdeaLayer(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        rw.init_wiki(self.root)

    def _page(self, slug):
        return Path(self.root) / "ideas" / f"{slug}.md"

    def _edges(self):
        p = Path(self.root) / "graph" / "edges.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def test_creates_page_with_outcome_field(self):
        rw.upsert_idea(self.root, "distill-executor", "Distill executor into Qwen",
                       outcome="pending", thesis="train via OPD", stage="proposed")
        fm = self._page("distill-executor").read_text()
        self.assertIn("type: idea", fm)
        self.assertIn("node_id: idea:distill-executor", fm)
        self.assertIn("outcome: pending", fm)   # `outcome`, NOT `status` — banlist/stats read this
        self.assertIn("stage: proposed", fm)

    def test_slug_honored_verbatim(self):
        rw.upsert_idea(self.root, "my-idea-7", "Some idea")
        self.assertTrue(self._page("my-idea-7").is_file())

    def test_invalid_outcome_rejected(self):
        # claim/empirical words and typos must be rejected (outcome drives the banlist)
        for bad in ("verified", "supported", "done", "good"):
            with self.assertRaises(RuntimeError):
                rw.upsert_idea(self.root, f"i-{bad}", f"I {bad}", outcome=bad)

    def test_all_outcomes_accepted(self):
        for i, oc in enumerate(sorted(rw._IDEA_OUTCOMES)):
            rw.upsert_idea(self.root, f"o{i}", f"Idea {oc}", outcome=oc)
            self.assertIn(f"outcome: {oc}", self._page(f"o{i}").read_text())

    def test_dedup_skips_without_update_flag(self):
        rw.upsert_idea(self.root, "x", "X", outcome="pending")
        rw.upsert_idea(self.root, "x", "X", outcome="positive")  # should skip
        self.assertIn("outcome: pending", self._page("x").read_text())

    def test_update_on_exist_refreshes(self):
        rw.upsert_idea(self.root, "x", "X", outcome="pending")
        rw.upsert_idea(self.root, "x", "X", outcome="positive", update_on_exist=True)
        self.assertIn("outcome: positive", self._page("x").read_text())

    def test_edges_wired(self):
        rw.upsert_idea(self.root, "y", "Y", based_on=["chen2026foo"], target_gaps=["G2"])
        kinds = {(e["from"], e["type"], e["to"]) for e in self._edges()}
        self.assertIn(("idea:y", "inspired_by", "paper:chen2026foo"), kinds)
        self.assertIn(("idea:y", "addresses_gap", "gap:G2"), kinds)

    def test_uninitialized_wiki_raises(self):
        bare = tempfile.mkdtemp()  # no init → no ideas/ dir
        with self.assertRaises(RuntimeError):
            rw.upsert_idea(bare, "x", "X")

    def test_negative_idea_enters_banlist(self):
        # the user-facing point: a recorded failed idea feeds the re-ideation banlist
        rw.upsert_idea(self.root, "flop", "A flop idea", outcome="negative",
                       risks="failed because the assumption breaks")
        qp = (Path(self.root) / "query_pack.md").read_text()
        self.assertIn("Failed Ideas", qp)
        self.assertIn("A flop idea", qp)

    def test_appears_in_index(self):
        rw.upsert_idea(self.root, "idx-idea", "Indexed idea")
        self.assertIn("idx-idea", (Path(self.root) / "index.md").read_text())

    def test_body_outcome_text_not_banlisted(self):
        # A PENDING idea whose body discusses an "outcome: negative" failure mode
        # must NOT be banlisted (the reader parses frontmatter, not full text).
        rw.upsert_idea(self.root, "live-idea", "A live idea", outcome="pending",
                       risks="a risk is that outcome: negative could happen if X")
        qp = (Path(self.root) / "query_pack.md").read_text()
        self.assertNotIn("A live idea", qp.split("## Failed Ideas")[-1] if "## Failed Ideas" in qp else "")
        rw.get_stats(self.root)  # must not raise; pending idea not counted as negative

    def test_invalid_stage_rejected(self):
        with self.assertRaises(RuntimeError):
            rw.upsert_idea(self.root, "bad-stage", "X", stage="proposed\noutcome: negative")

    def test_frontmatter_injection_neutralized(self):
        # A based_on id carrying a newline + a fake outcome line must not flip the
        # parsed frontmatter outcome (quoting neutralizes the newline).
        rw.upsert_idea(self.root, "inj", "Injection probe", outcome="pending",
                       based_on=["paper:foo\noutcome: negative"])
        meta = rw._load_paper_frontmatter(self._page("inj"))
        self.assertEqual(meta.get("outcome"), "pending")


if __name__ == "__main__":
    unittest.main()
