#!/usr/bin/env python3
"""CLI helper for Google web, news and Google Scholar search via Serply.

Designed to complement arXiv (preprints) and Semantic Scholar (published venues)
with **Google coverage**: the regular Google web index, Google News, and Google
Scholar (papers, citations and authors across publishers).

Requires
--------
SERPLY_API_KEY environment variable (https://serply.io). Standard library only,
no SDK to install.

Commands
--------
search          Google web search.
news            Google News results (same shape as search).
scholar         Google Scholar search (papers with authors and citation text).

Filter flags
------------
--max            Maximum number of results (1-10, Serply returns one page).
--gl             Two-letter country code for localized results (search, news).
--recency        day, week, month or year (search, news).

Examples
--------
# Google web search
python3 tools/serply_search.py search "transformer attention mechanisms" --max 10

# Restrict to one site with a search operator
python3 tools/serply_search.py search "site:arxiv.org semantic communication"

# Papers via Google Scholar
python3 tools/serply_search.py scholar "diffusion models for protein design" --max 5

# Last week of news
python3 tools/serply_search.py news "foundation models" --recency week
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_BASE_URL = "https://api.serply.io/v1"
_USER_AGENT = "auto-claude-code-research-in-sleep"
_MAX_RESULTS_CAP = 10
_TIMEOUT_SECONDS = 30
_RECENCY_TO_TBS = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}


def _get_api_key() -> str:
    api_key = os.getenv("SERPLY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "SERPLY_API_KEY environment variable is required. "
            "Get your key from: https://serply.io"
        )
    return api_key


def _clamp_max(value: int | None) -> int:
    """Clamp the result count into 1..10 (Serply returns a single page)."""
    if value is None:
        return _MAX_RESULTS_CAP
    return max(1, min(int(value), _MAX_RESULTS_CAP))


def _is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.lower().startswith(("http://", "https://"))


def _request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET a Serply endpoint and return the decoded JSON object."""
    api_key = _get_api_key()
    query = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}
    )
    request = urllib.request.Request(
        f"{_BASE_URL}/{path}?{query}",
        headers={
            "X-Api-Key": api_key,
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            if isinstance(payload, dict):
                detail = str(payload.get("detail") or "")
        except (ValueError, OSError):
            pass
        raise RuntimeError(
            f"Serply HTTP {exc.code}" + (f": {detail}" if detail else "")
        ) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Serply request failed: {exc.reason}") from None

    try:
        data = json.loads(body)
    except ValueError:
        raise RuntimeError("Serply returned a non-JSON response") from None
    if not isinstance(data, dict):
        raise RuntimeError("Serply returned an unexpected response shape")
    return data


def _web_params(
    query: str, max_results: int | None, gl: str | None, recency: str | None
) -> dict[str, Any]:
    params: dict[str, Any] = {"q": query, "num": _clamp_max(max_results)}
    if gl:
        params["gl"] = gl.strip().lower()
    if recency:
        params["tbs"] = _RECENCY_TO_TBS[recency]
    return params


def _process_web_result(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict) or not _is_http_url(row.get("link")):
        return None
    return {
        "title": row.get("title") or "No Title",
        "url": row["link"],
        "snippet": row.get("description") or "",
    }


def _process_scholar_result(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict) or not _is_http_url(row.get("link")):
        return None
    entry: dict[str, Any] = {
        "title": row.get("title") or "No Title",
        "url": row["link"],
        # Scholar's description is the byline: authors - venue, year - publisher.
        "byline": (row.get("description") or "").replace("\xa0", " "),
    }
    author = row.get("author")
    if isinstance(author, dict):
        names = [
            a.get("name")
            for a in (author.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        if names:
            entry["authors"] = names
    extras = row.get("extras")
    if isinstance(extras, dict):
        citations = extras.get("citations")
        if isinstance(citations, dict) and citations.get("count"):
            entry["cited_by"] = citations["count"]
    doc = row.get("doc")
    if isinstance(doc, dict) and _is_http_url(doc.get("link")):
        entry["pdf_url"] = doc["link"]
    return entry


def _package(
    mode: str, query: str, rows: Any, process: Any, max_results: int | None
) -> dict[str, Any]:
    limit = _clamp_max(max_results)
    data = [
        entry
        for entry in (process(row) for row in (rows if isinstance(rows, list) else []))
        if entry is not None
    ][:limit]
    return {"mode": mode, "query": query, "returned": len(data), "data": data}


def search(
    query: str,
    max_results: int | None = None,
    gl: str | None = None,
    recency: str | None = None,
) -> dict[str, Any]:
    """Google web search via Serply."""
    response = _request("search", _web_params(query, max_results, gl, recency))
    return _package(
        "search", query, response.get("results"), _process_web_result, max_results
    )


def news(
    query: str,
    max_results: int | None = None,
    gl: str | None = None,
    recency: str | None = None,
) -> dict[str, Any]:
    """Google News results via the search endpoint (tbm=nws)."""
    params = _web_params(query, max_results, gl, recency)
    params["tbm"] = "nws"
    response = _request("search", params)
    return _package(
        "news", query, response.get("results"), _process_web_result, max_results
    )


def scholar(query: str, max_results: int | None = None) -> dict[str, Any]:
    """Google Scholar search via Serply."""
    response = _request(
        "scholar", {"q": query, "num": _clamp_max(max_results)}
    )
    return _package(
        "scholar", query, response.get("articles"), _process_scholar_result, max_results
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Google web, news and Scholar search via Serply.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("search", "Google web search"),
        ("news", "Google News results"),
        ("scholar", "Google Scholar search"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("query", help="Search query")
        sub.add_argument(
            "--max", type=int, default=10, metavar="N",
            help="Maximum number of results, 1-10 (default: 10).",
        )
        if name != "scholar":
            sub.add_argument(
                "--gl", default=None,
                help="Two-letter country code for localized results.",
            )
            sub.add_argument(
                "--recency", default=None, choices=tuple(_RECENCY_TO_TBS),
                help="Only results from the last day, week, month or year.",
            )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "search":
            result = search(args.query, args.max, args.gl, args.recency)
        elif args.command == "news":
            result = news(args.query, args.max, args.gl, args.recency)
        elif args.command == "scholar":
            result = scholar(args.query, args.max)
        else:
            raise ValueError(f"Unsupported command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
