"""arXiv-id dedup in ingest_paper must match the whole id.

A 4-digit `YYMM.NNNN` is a prefix of the 5-digit ids that share its `YYMM`, so
an unanchored match takes a truncated id for the paper it was cut from.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import research_wiki as rw  # noqa: E402

LOST_IN_THE_MIDDLE = {
    "arxiv_id": "2307.03172",
    "title": "Lost in the Middle: How Language Models Use Long Contexts",
    "authors": ["Nelson F. Liu", "Kevin Lin"],
    "year": 2023,
    "venue": "arXiv",
}


def _wiki_with_one_paper(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "research-wiki"
    rw.init_wiki(str(root))
    page = rw.ingest_paper(str(root), arxiv_id="2307.03172", prefetched_meta=dict(LOST_IN_THE_MIDDLE))
    return root, page


def test_truncated_id_does_not_match_existing_page(tmp_path: Path) -> None:
    root, page = _wiki_with_one_paper(tmp_path)

    assert rw._find_existing_page_by_arxiv(root, "2307.03172") == page
    assert rw._find_existing_page_by_arxiv(root, "2307.0317") is None


def test_url_reference_matches_whole_id_with_optional_version(tmp_path: Path) -> None:
    root = tmp_path / "research-wiki"
    rw.init_wiki(str(root))
    page = root / "papers" / "hand_written.md"
    page.write_text("# Notes\n\nSee https://arxiv.org/abs/2307.03172v2\n", encoding="utf-8")

    assert rw._find_existing_page_by_arxiv(root, "2307.03172") == page
    assert rw._find_existing_page_by_arxiv(root, "2307.0317") is None


def test_update_on_exist_with_truncated_id_leaves_the_real_page_alone(tmp_path: Path, monkeypatch) -> None:
    root, page = _wiki_with_one_paper(tmp_path)
    before = page.read_text(encoding="utf-8")

    def no_entry(aid: str, timeout: float = 15.0) -> dict:
        raise RuntimeError(f"arXiv API returned no entry for {aid}")

    monkeypatch.setattr(rw, "fetch_arxiv_metadata", no_entry)
    other = rw.ingest_paper(
        str(root), arxiv_id="2307.0317", title="Some Other Paper",
        authors=["A. Nobody"], year=2023, update_on_exist=True,
    )

    assert other != page
    assert page.read_text(encoding="utf-8") == before
