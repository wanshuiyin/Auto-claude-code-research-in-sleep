#!/usr/bin/env python3
"""CLI helper for searching and downloading arXiv papers.

Used by the ``arxiv`` skill (skills/arxiv/SKILL.md).

Commands
--------
search    Search arXiv and print results as JSON.
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
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

_ATOM_NS = "http://www.w3.org/2005/Atom"
_API_BASE = "http://export.arxiv.org/api/query"
_MIN_PDF_BYTES = 10_240


def _arxiv_user_agent() -> str:
    """Descriptive User-Agent for arXiv API calls.

    arXiv rate-limits the default ``Python-urllib/x.y`` agent far more
    aggressively than a named client; sending a descriptive UA (with an
    optional contact address) lands requests in arXiv's more lenient pool.
    The contact is read from ``ARIS_VERIFY_EMAIL`` — the same env var
    ``tools/research_wiki.py`` and ``tools/verify_papers.py`` already use —
    so no address is hard-coded. Falls back to a contactless UA when unset.
    """
    contact = os.environ.get("ARIS_VERIFY_EMAIL", "").strip()
    base = ("arxiv-skill/1.0 "
            "(+https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)")
    return f"{base} (mailto:{contact})" if contact else base


_NEW_STYLE_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
_OLD_STYLE_ID_RE = re.compile(r"^[A-Za-z.-]+/\d{7}(v\d+)?$")


def _normalize_id(arxiv_id: str) -> str:
    """Strip URL/version noise and return a clean arXiv ID."""
    value = arxiv_id.strip()
    if "/abs/" in value:
        value = value.split("/abs/", 1)[1]
    if value.startswith("id:"):
        value = value[3:]
    if "v" in value.split(".")[-1]:
        value = value.rsplit("v", 1)[0]
    return value


def _looks_like_arxiv_id(value: str) -> bool:
    """Return True when the input resembles a modern or legacy arXiv ID."""
    value = value.strip()
    return bool(_NEW_STYLE_ID_RE.match(value) or _OLD_STYLE_ID_RE.match(value))


def _api_url(query: str, max_results: int, start: int) -> str:
    """Build the arXiv API URL for a search query or specific ID lookup."""
    query = query.strip()
    if query.startswith("id:"):
        params = {"id_list": _normalize_id(query)}
    elif _looks_like_arxiv_id(query):
        params = {"id_list": _normalize_id(query)}
    else:
        params = {
            "search_query": query,
            "start": start,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    return f"{_API_BASE}?{urllib.parse.urlencode(params)}"


def _fetch_atom(url: str) -> ET.Element:
    """Fetch an arXiv Atom feed and return the parsed XML root.

    Sends a descriptive User-Agent (landing requests in arXiv's lenient pool)
    and retries up to 3 times on HTTP 429, transient network errors, and the
    plain-text ``Rate exceeded.`` body the API sometimes returns with 200 OK.
    Raises RuntimeError when all retries are exhausted.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _arxiv_user_agent()})
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(5 * attempt)
                continue
            raise RuntimeError(f"arXiv API fetch failed: {e}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < 3:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"arXiv API fetch failed: {e}")
        if body.strip() == b"Rate exceeded.":
            if attempt < 3:
                time.sleep(5 * attempt)
                continue
            raise RuntimeError("arXiv API rate-limited after 3 attempts")
        return ET.fromstring(body)
    # unreachable; loop either returns or raises
    raise RuntimeError("arXiv API fetch failed: exhausted retries")


def _parse_entry(entry: ET.Element) -> dict:
    """Extract structured fields from a single Atom <entry> element."""
    raw_id = entry.findtext(f"{{{_ATOM_NS}}}id", "")
    arxiv_id = _normalize_id(raw_id)
    title = (entry.findtext(f"{{{_ATOM_NS}}}title", "") or "").strip().replace("\n", " ")
    abstract = (entry.findtext(f"{{{_ATOM_NS}}}summary", "") or "").strip().replace("\n", " ")
    published = (entry.findtext(f"{{{_ATOM_NS}}}published", "") or "")[:10]
    updated = (entry.findtext(f"{{{_ATOM_NS}}}updated", "") or "")[:10]
    authors = [
        author.findtext(f"{{{_ATOM_NS}}}name", "")
        for author in entry.findall(f"{{{_ATOM_NS}}}author")
    ]
    categories = [
        category.get("term", "")
        for category in entry.findall(f"{{{_ATOM_NS}}}category")
        if category.get("term")
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
    """Search arXiv and return a list of paper dictionaries."""
    url = _api_url(query, max_results=max_results, start=start)
    root = _fetch_atom(url)
    return [_parse_entry(entry) for entry in root.findall(f"{{{_ATOM_NS}}}entry")]


def download(arxiv_id: str, output_dir: str = "papers") -> dict:
    """Download a paper PDF and return metadata about the saved file."""
    clean_id = _normalize_id(arxiv_id)
    safe_id = clean_id.replace("/", "_")

    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{safe_id}.pdf"

    if dest.exists():
        return {
            "id": clean_id,
            "path": str(dest),
            "size_kb": dest.stat().st_size // 1024,
            "skipped": True,
        }

    pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
    req = urllib.request.Request(pdf_url, headers={"User-Agent": _arxiv_user_agent()})

    data = b""
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(5 * attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < 3:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"Failed to download {pdf_url}: {exc}")
    else:
        raise RuntimeError(f"Failed to download {pdf_url} after 3 attempts")

    if len(data) < _MIN_PDF_BYTES:
        raise ValueError(
            f"Downloaded file is only {len(data)} bytes - likely an error page, not a PDF"
        )

    dest.write_bytes(data)
    return {
        "id": clean_id,
        "path": str(dest),
        "size_kb": len(data) // 1024,
        "skipped": False,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search and download arXiv papers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def _add_search_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "query",
            help="Search query or arXiv ID (bare ID or id:ARXIV_ID).",
        )
        p.add_argument(
            "--max",
            type=int,
            default=10,
            metavar="N",
            help="Maximum number of results (default: 10).",
        )
        p.add_argument(
            "--start",
            type=int,
            default=0,
            help="Start offset for pagination (default: 0).",
        )

    search_parser = subparsers.add_parser("search", help="Search arXiv papers")
    _add_search_args(search_parser)

    # Defensive aliases — models frequently hallucinate `get` / `fetch`
    # instead of `search`.  Accept them silently so the invocation succeeds
    # regardless of model quality.
    for alias in ("get", "fetch"):
        _add_search_args(subparsers.add_parser(alias, help="Alias for search"))

    download_parser = subparsers.add_parser("download", help="Download a paper PDF by arXiv ID")
    download_parser.add_argument(
        "id",
        help="arXiv paper ID, e.g. 2301.07041 or cs/0601001",
    )
    download_parser.add_argument(
        "--dir",
        default="papers",
        metavar="DIR",
        help="Output directory (default: papers).",
    )
    download_parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to sleep after download (default: 1.0).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command in ("search", "get", "fetch"):
        results = search(args.query, max_results=args.max, start=args.start)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if args.command == "download":
        result = download(args.id, output_dir=args.dir)
        if result.get("skipped"):
            print(json.dumps({**result, "message": "already exists, skipped"}, ensure_ascii=False))
        else:
            time.sleep(args.delay)
            print(json.dumps(result, ensure_ascii=False))
        return 0

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
