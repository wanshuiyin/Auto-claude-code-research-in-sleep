#!/usr/bin/env python3
"""CLI helper for searching and downloading arXiv papers.

Used by the ``arxiv`` skill (skills/arxiv/SKILL.md).

Commands
--------
search  Search arXiv and print results as JSON.
download  Download a paper PDF by arXiv ID.

Examples
--------
python3 tools/arxiv_fetch.py search "attention mechanism" --max 10
python3 tools/arxiv_fetch.py search "id:2301.07041" --max 1
python3 tools/arxiv_fetch.py download 2301.07041 --dir papers
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

_ATOM_NS = "http://www.w3.org/2005/Atom"
_API_BASE = "http://export.arxiv.org/api/query"
_USER_AGENT = "arxiv-skill/1.0 (github.com/wanshuiyin/Auto-claude-code-research-in-sleep)"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _parse_entry(entry: ET.Element) -> dict:
    """Extract structured fields from a single Atom <entry> element."""
    raw_id = entry.findtext(f"{{{_ATOM_NS}}}id", "")
    arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id
    # Strip version suffix (e.g. "2301.07041v2" -> "2301.07041")
    if "v" in arxiv_id.split(".")[-1]:
        arxiv_id = arxiv_id.rsplit("v", 1)[0]

    title = (entry.findtext(f"{{{_ATOM_NS}}}title", "") or "").strip().replace("\n", " ")
    abstract = (entry.findtext(f"{{{_ATOM_NS}}}summary", "") or "").strip().replace("\n", " ")
    published = (entry.findtext(f"{{{_ATOM_NS}}}published", "") or "")[:10]
    updated = (entry.findtext(f"{{{_ATOM_NS}}}updated", "") or "")[:10]

    authors = [
        a.findtext(f"{{{_ATOM_NS}}}name", "")
        for a in entry.findall(f"{{{_ATOM_NS}}}author")
    ]
    categories = [
        c.get("term", "")
        for c in entry.findall(f"{{{_ATOM_NS}}}category")
        if c.get("term")
    ]

    return {
        "id": arxiv_id,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "published": published,
        "updated": updated,
        "categories": categories,
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def search(query: str, max_results: int = 10, start: int = 0) -> list[dict]:
    """Search arXiv and return a list of paper dicts."""
    params = urllib.parse.urlencode({
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{_API_BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())
    return [_parse_entry(e) for e in root.findall(f"{{{_ATOM_NS}}}entry")]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download(arxiv_id: str, output_dir: str = "papers") -> dict:
    """Download a paper PDF.  Returns a result dict with 'path' and 'size_kb'."""
    # Normalise ID: replace slashes with underscores for filenames
    safe_id = arxiv_id.replace("/", "_")
    # Strip version suffix for the filename
    if "v" in safe_id.split(".")[-1]:
        safe_id = safe_id.rsplit("v", 1)[0]

    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{safe_id}.pdf"

    if dest.exists():
        return {"id": arxiv_id, "path": str(dest), "size_kb": dest.stat().st_size // 1024, "skipped": True}

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    req = urllib.request.Request(pdf_url, headers={"User-Agent": _USER_AGENT})

    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 1:
                time.sleep(5)
                continue
            raise
    else:
        raise RuntimeError(f"Failed to download {pdf_url} after retries")

    if len(data) < 10_240:
        raise ValueError(
            f"Downloaded file is only {len(data)} bytes — likely an error page, not a PDF"
        )

    dest.write_bytes(data)
    return {"id": arxiv_id, "path": str(dest), "size_kb": len(data) // 1024, "skipped": False}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search and download arXiv papers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="Search arXiv papers")
    sp.add_argument("query", help="Search query or id:ARXIV_ID for a specific paper")
    sp.add_argument("--max", type=int, default=10, metavar="N", help="Max results (default: 10)")
    sp.add_argument("--start", type=int, default=0, help="Start offset (default: 0)")

    dp = sub.add_parser("download", help="Download a paper PDF by arXiv ID")
    dp.add_argument("id", help="arXiv paper ID, e.g. 2301.07041 or cs/0601001")
    dp.add_argument("--dir", default="papers", metavar="DIR", help="Output directory (default: papers)")
    dp.add_argument("--delay", type=float, default=1.0,
                    help="Seconds to sleep after download (default: 1.0)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "search":
        results = search(args.query, max_results=args.max, start=args.start)
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif args.command == "download":
        result = download(args.id, output_dir=args.dir)
        if result.get("skipped"):
            print(json.dumps({**result, "message": "already exists, skipped"}, ensure_ascii=False))
        else:
            time.sleep(args.delay)
            print(json.dumps(result, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
