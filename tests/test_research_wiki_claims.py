"""Tests for the research-wiki claim layer — add_claim (the PROVE/JUDGE ledger).

Covers: page creation with the PROOF-axis status, slug honored verbatim, the
status validator (empirical "supported"/"invalidated" must be REJECTED — they are
a separate axis carried by edges, not the claim's status field), the new `unproven`
proof-gap status, dedup vs --update-on-exist, edge wiring, and the uninitialized-wiki
guard. These lock the Option-A design: claim `status` = proof axis only.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import research_wiki as rw  # noqa: E402


class TestClaimLayer(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        rw.init_wiki(self.root)

    def _page(self, slug):
        return Path(self.root) / "claims" / f"{slug}.md"

    def _edges(self):
        p = Path(self.root) / "graph" / "edges.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def test_creates_page_with_proof_status_and_provenance(self):
        rw.add_claim(self.root, "thm-main-ub", "Main upper bound",
                     status="verified", provenance=".aris/traces/proof-checker/r1",
                     statement="X <= Y")
        fm = self._page("thm-main-ub").read_text()
        self.assertIn("node_type: claim", fm)
        self.assertIn("node_id: claim:thm-main-ub", fm)
        self.assertIn("status: verified", fm)
        self.assertIn(".aris/traces/proof-checker/r1", fm)

    def test_slug_honored_verbatim(self):
        rw.add_claim(self.root, "b1-sieve-lb", "Sieve lower bound", status="unproven")
        self.assertTrue(self._page("b1-sieve-lb").is_file())

    def test_empirical_status_rejected(self):
        # The crux of the design: experiment outcomes are NOT claim statuses.
        for bad in ("supported", "partial", "invalidated", "yes", "no"):
            with self.assertRaises(RuntimeError):
                rw.add_claim(self.root, f"c-{bad}", f"C {bad}", status=bad)

    def test_unproven_is_valid(self):
        rw.add_claim(self.root, "thm-gap", "Has an open gap", status="unproven")
        self.assertIn("status: unproven", self._page("thm-gap").read_text())

    def test_all_proof_statuses_accepted(self):
        for i, st in enumerate(sorted(rw._CLAIM_STATUSES)):
            rw.add_claim(self.root, f"s{i}", f"Claim {st}", status=st)
            self.assertIn(f"status: {st}", self._page(f"s{i}").read_text())

    def test_dedup_skips_without_update_flag(self):
        rw.add_claim(self.root, "thm-x", "X", status="drafted")
        rw.add_claim(self.root, "thm-x", "X", status="verified")  # should skip
        self.assertIn("status: drafted", self._page("thm-x").read_text())

    def test_update_on_exist_refreshes_status(self):
        rw.add_claim(self.root, "thm-x", "X", status="unproven")
        rw.add_claim(self.root, "thm-x", "X", status="verified", update_on_exist=True)
        self.assertIn("status: verified", self._page("thm-x").read_text())

    def test_edges_wired(self):
        rw.add_claim(self.root, "thm-y", "Y", status="verified",
                     uses=["paper:foo2024"], depends_on=["thm-x"], refutes=["thm-z"])
        kinds = {(e["from"], e["type"], e["to"]) for e in self._edges()}
        self.assertIn(("claim:thm-y", "uses", "paper:foo2024"), kinds)
        self.assertIn(("claim:thm-y", "depends_on", "claim:thm-x"), kinds)
        self.assertIn(("claim:thm-y", "refutes", "claim:thm-z"), kinds)

    def test_uninitialized_wiki_raises(self):
        bare = tempfile.mkdtemp()  # no init → no claims/ dir
        with self.assertRaises(RuntimeError):
            rw.add_claim(bare, "thm-x", "X", status="drafted")

    def test_appears_in_index(self):
        rw.add_claim(self.root, "thm-idx", "Indexed claim", status="verified")
        idx = (Path(self.root) / "index.md")
        self.assertTrue(idx.is_file())
        self.assertIn("thm-idx", idx.read_text())


if __name__ == "__main__":
    unittest.main()
