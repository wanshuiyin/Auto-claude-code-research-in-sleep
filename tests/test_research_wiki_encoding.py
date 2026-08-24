"""The wiki is UTF-8 on every platform (issue #385).

Before this was fixed, most file ops in research_wiki.py inherited the platform
default encoding. On a cp936 (Chinese Windows) locale that wrote the wiki in GBK:
the directory could not be shared with collaborators on other platforms, and
rebuild_index crashed the moment any external tool rewrote a file as UTF-8.

These tests reproduce the reported failure — non-ASCII content written, then read
back — rather than probing exotic encodings.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import research_wiki as rw  # noqa: E402

NON_ASCII = "中文证据 · café ✓"


class TestWikiEncoding(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        rw.init_wiki(self.root)

    def test_non_ascii_edge_evidence_is_written_as_utf8(self):
        rw.add_edge(self.root, "paper:a", "paper:b", "extends", evidence=NON_ASCII)
        raw = (Path(self.root) / "graph" / "edges.jsonl").read_bytes()
        # Decodes as UTF-8 (would raise on a GBK-written file) and survives the trip.
        record = json.loads(raw.decode("utf-8").strip().split("\n")[-1])
        self.assertEqual(record["evidence"], NON_ASCII)

    def test_rebuild_index_reads_a_utf8_wiki(self):
        rw.add_edge(self.root, "paper:a", "paper:b", "extends", evidence=NON_ASCII)
        # The reported crash: UnicodeDecodeError under a non-UTF-8 default locale.
        rw.rebuild_index(self.root)


class TestSlugifyKeepsNonAsciiLetters(unittest.TestCase):
    """Non-ASCII titles used to collapse to `<year>_untitled`, so a second paper
    by the same author in the same year was silently dropped as a duplicate."""

    def test_two_chinese_papers_get_distinct_slugs(self):
        a = rw.slugify("扩散语言模型的表征视角", "张三", 2026)
        b = rw.slugify("图神经网络的可解释性研究", "张三", 2026)
        self.assertNotEqual(a, b)
        self.assertNotIn("untitled", a)

    def test_ascii_titles_slugify_exactly_as_before(self):
        # Locking the pre-existing behavior: these strings must not drift.
        self.assertEqual(
            rw.slugify("Attention Is All You Need", "Vaswani", 2017),
            "vaswani2017_attention_all_you",
        )
        self.assertEqual(
            rw.slugify("BERT: Pre-training of Deep Bidirectional Transformers", "Devlin", 2019),
            "devlin2019_bert_pretraining_deep",
        )

    def test_second_chinese_paper_is_actually_ingested(self):
        root = tempfile.mkdtemp()
        rw.init_wiki(root)
        rw.ingest_paper(root, title="扩散语言模型的表征视角", authors="张三", year=2026)
        rw.ingest_paper(root, title="图神经网络的可解释性研究", authors="张三", year=2026)
        pages = list((Path(root) / "papers").glob("*.md"))
        self.assertEqual(len(pages), 2)


if __name__ == "__main__":
    unittest.main()
