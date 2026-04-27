#!/usr/bin/env python3
"""CLI helper for AI-powered web search via Exa.

Designed to complement arXiv (preprints) and Semantic Scholar (published venues)
with **broad web search**: blog posts, documentation, company pages, news, and
research papers — all with built-in content extraction.

Requires
--------
pip install exa-py

Commands
--------
search          Search the web and optionally retrieve content.
find-similar    Find pages similar to a given URL.
get-contents    Retrieve content for specific URLs.

Filter flags (search)
---------------------
--type           Search type: auto (default), neural, fast, instant
--category       Focus area: "company", "research paper", "news",
                 "personal site", "financial report", "people"
--include-domains  Only include results from these domains (comma-separated)
--exclude-domains  Exclude results from these domains (comma-separated)
--include-text   Required text in page (comma-separated phrases)
--exclude-text   Prohibited text in page (comma-separated phrases)
--start-date     Only results published after this ISO 8601 date
--end-date       Only results published before this ISO 8601 date
--location       Two-letter ISO country code for localized results

Content flags (shared)
----------------------
--content        Content mode: highlights (default), text, summary, none
--max-chars      Max characters for content extraction (default: 4000)

Examples
--------
# Basic search with highlights
python3 tools/exa_search.py search "transformer attention mechanisms" --max 10

# Research papers with full text
python3 tools/exa_search.py search "semantic communication" --category "research paper" \
  --content text --max-chars 8000

# Recent news about a topic
python3 tools/exa_search.py search "foundation models" --category news \
  --start-date 2025-01-01

# Domain-restricted search
python3 tools/exa_search.py search "RAG pipeline" --include-domains "arxiv.org,huggingface.co"

# Find similar pages to a URL
python3 tools/exa_search.py find-similar "https://arxiv.org/abs/2301.07041" --max 5

# Get content for specific URLs
python3 tools/exa_search.py get-contents "https://example.com/page1" "https://example.com/page2"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

_INSTALL_MESSAGE = "exa-py not found. Install it with: pip install exa-py"


def _get_client() -> Any:
    """Create and return an Exa client with the integration tracking header."""
    api_key = os.getenv("EXA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "EXA_API_KEY environment variable is required. "
            "Get your key from: https://exa.ai"
        )

    try:
        from exa_py import Exa
    except ImportError:
        raise RuntimeError(_INSTALL_MESSAGE)

    client = Exa(api_key=api_key)
    client.headers["x-exa-integration"] = "auto-claude-code-research-in-sleep"
    return client


def _parse_list(value: str | None) -> list[str] | None:
    """Split a comma-separated string into a list, or return None."""
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _build_content_kwargs(content_mode: str, max_chars: int) -> dict[str, Any]:
    """Build content retrieval kwargs for Exa search_and_contents."""
    if content_mode == "none":
        return {}
    if content_mode == "highlights":
        return {"highlights": {"max_characters": max_chars}}
    if content_mode == "text":
        return {"text": {"max_characters": max_chars}}
    if content_mode == "summary":
        return {"summary": True}
    return {"highlights": {"max_characters": max_chars}}


def _process_result(result: Any, content_mode: str) -> dict[str, Any]:
    """Extract structured fields from a single Exa result object."""
    entry: dict[str, Any] = {
        "title": getattr(result, "title", None) or "No Title",
        "url": getattr(result, "url", None) or "",
    }

    published_date = getattr(result, "published_date", None)
    if published_date:
        entry["published_date"] = published_date

    author = getattr(result, "author", None)
    if author:
        entry["author"] = author

    if content_mode == "highlights":
        highlights = getattr(result, "highlights", None)
        if highlights:
            entry["highlights"] = highlights
    elif content_mode == "text":
        text = getattr(result, "text", None)
        if text:
            entry["text"] = text
    elif content_mode == "summary":
        summary = getattr(result, "summary", None)
        if summary:
            entry["summary"] = summary

    return entry


def search(
    query: str,
    max_results: int = 10,
    search_type: str = "auto",
    content_mode: str = "highlights",
    max_chars: int = 4000,
    category: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    include_text: list[str] | None = None,
    exclude_text: list[str] | None = None,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
    user_location: str | None = None,
) -> dict[str, Any]:
    """Search the web via Exa and return structured results."""
    client = _get_client()

    kwargs: dict[str, Any] = {
        "query": query,
        "num_results": max_results,
        "type": search_type,
    }

    kwargs.update(_build_content_kwargs(content_mode, max_chars))

    if category:
        kwargs["category"] = category
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains
    if include_text:
        kwargs["include_text"] = include_text
    if exclude_text:
        kwargs["exclude_text"] = exclude_text
    if start_published_date:
        kwargs["start_published_date"] = start_published_date
    if end_published_date:
        kwargs["end_published_date"] = end_published_date
    if user_location:
        kwargs["user_location"] = user_location

    response = client.search_and_contents(**kwargs)

    return {
        "mode": "search",
        "query": query,
        "type": search_type,
        "returned": len(response.results),
        "data": [_process_result(r, content_mode) for r in response.results],
    }


def find_similar(
    url: str,
    max_results: int = 10,
    content_mode: str = "highlights",
    max_chars: int = 4000,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
) -> dict[str, Any]:
    """Find pages similar to a given URL."""
    client = _get_client()

    kwargs: dict[str, Any] = {
        "url": url,
        "num_results": max_results,
    }

    kwargs.update(_build_content_kwargs(content_mode, max_chars))

    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains
    if start_published_date:
        kwargs["start_published_date"] = start_published_date
    if end_published_date:
        kwargs["end_published_date"] = end_published_date

    response = client.find_similar_and_contents(**kwargs)

    return {
        "mode": "find-similar",
        "url": url,
        "returned": len(response.results),
        "data": [_process_result(r, content_mode) for r in response.results],
    }


def get_contents(
    urls: list[str],
    content_mode: str = "text",
    max_chars: int = 10000,
) -> dict[str, Any]:
    """Retrieve content for specific URLs."""
    client = _get_client()

    kwargs: dict[str, Any] = {"ids": urls}
    kwargs.update(_build_content_kwargs(content_mode, max_chars))

    response = client.get_contents(**kwargs)

    return {
        "mode": "get-contents",
        "returned": len(response.results),
        "data": [_process_result(r, content_mode) for r in response.results],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI-powered web search via Exa.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- search ---
    search_parser = subparsers.add_parser("search", help="Search the web via Exa")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--max", type=int, default=10, metavar="N",
        help="Maximum number of results (default: 10).",
    )
    search_parser.add_argument(
        "--type", default="auto", dest="search_type",
        choices=("auto", "neural", "fast", "instant"),
        help="Search type (default: auto).",
    )
    search_parser.add_argument(
        "--content", default="highlights", dest="content_mode",
        choices=("highlights", "text", "summary", "none"),
        help="Content retrieval mode (default: highlights).",
    )
    search_parser.add_argument(
        "--max-chars", type=int, default=4000, metavar="N",
        help="Max characters for content extraction (default: 4000).",
    )
    search_parser.add_argument(
        "--category", default=None,
        help='Category filter: "company", "research paper", "news", '
             '"personal site", "financial report", "people".',
    )
    search_parser.add_argument(
        "--include-domains", default=None,
        help="Comma-separated domains to include.",
    )
    search_parser.add_argument(
        "--exclude-domains", default=None,
        help="Comma-separated domains to exclude.",
    )
    search_parser.add_argument(
        "--include-text", default=None,
        help="Comma-separated phrases that must appear in page.",
    )
    search_parser.add_argument(
        "--exclude-text", default=None,
        help="Comma-separated phrases to exclude from results.",
    )
    search_parser.add_argument(
        "--start-date", default=None,
        help="Only results published after this date (ISO 8601).",
    )
    search_parser.add_argument(
        "--end-date", default=None,
        help="Only results published before this date (ISO 8601).",
    )
    search_parser.add_argument(
        "--location", default=None,
        help="Two-letter ISO country code for localized results.",
    )

    # --- find-similar ---
    similar_parser = subparsers.add_parser(
        "find-similar", help="Find pages similar to a URL",
    )
    similar_parser.add_argument("url", help="URL to find similar pages for")
    similar_parser.add_argument(
        "--max", type=int, default=10, metavar="N",
        help="Maximum number of results (default: 10).",
    )
    similar_parser.add_argument(
        "--content", default="highlights", dest="content_mode",
        choices=("highlights", "text", "summary", "none"),
        help="Content retrieval mode (default: highlights).",
    )
    similar_parser.add_argument(
        "--max-chars", type=int, default=4000, metavar="N",
        help="Max characters for content extraction (default: 4000).",
    )
    similar_parser.add_argument(
        "--include-domains", default=None,
        help="Comma-separated domains to include.",
    )
    similar_parser.add_argument(
        "--exclude-domains", default=None,
        help="Comma-separated domains to exclude.",
    )
    similar_parser.add_argument(
        "--start-date", default=None,
        help="Only results published after this date (ISO 8601).",
    )
    similar_parser.add_argument(
        "--end-date", default=None,
        help="Only results published before this date (ISO 8601).",
    )

    # --- get-contents ---
    contents_parser = subparsers.add_parser(
        "get-contents", help="Retrieve content for specific URLs",
    )
    contents_parser.add_argument("urls", nargs="+", help="URLs to fetch content for")
    contents_parser.add_argument(
        "--content", default="text", dest="content_mode",
        choices=("highlights", "text", "summary", "none"),
        help="Content retrieval mode (default: text).",
    )
    contents_parser.add_argument(
        "--max-chars", type=int, default=10000, metavar="N",
        help="Max characters for content extraction (default: 10000).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "search":
            result = search(
                query=args.query,
                max_results=args.max,
                search_type=args.search_type,
                content_mode=args.content_mode,
                max_chars=args.max_chars,
                category=args.category,
                include_domains=_parse_list(args.include_domains),
                exclude_domains=_parse_list(args.exclude_domains),
                include_text=_parse_list(args.include_text),
                exclude_text=_parse_list(args.exclude_text),
                start_published_date=args.start_date,
                end_published_date=args.end_date,
                user_location=args.location,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "find-similar":
            result = find_similar(
                url=args.url,
                max_results=args.max,
                content_mode=args.content_mode,
                max_chars=args.max_chars,
                include_domains=_parse_list(args.include_domains),
                exclude_domains=_parse_list(args.exclude_domains),
                start_published_date=args.start_date,
                end_published_date=args.end_date,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "get-contents":
            result = get_contents(
                urls=args.urls,
                content_mode=args.content_mode,
                max_chars=args.max_chars,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        raise ValueError(f"Unsupported command: {args.command}")

    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
