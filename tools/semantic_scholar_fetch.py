#!/usr/bin/env python3
"""CLI helper for fetching Semantic Scholar papers.

Designed to complement arxiv_fetch.py: arXiv handles preprints, this tool
handles **published venue papers** (IEEE, ACM, Springer, etc.) with rich
metadata (citations, venue, fieldsOfStudy, TLDR).

Commands
--------
search       Relevance search for papers (offset pagination, max 100).
search-bulk  Bulk search with token-based pagination (max 1000).
paper        Fetch one paper by Semantic Scholar paper ID, DOI, CorpusId, ArXiv ID, etc.

Filter flags (shared by search and search-bulk)
-----------------------------------------------
--fields-of-study   e.g. "Computer Science,Engineering"
--publication-types  e.g. "JournalArticle", "Conference", "Review"
--min-citations      e.g. 10
--year               e.g. "2020-", "2020-2024"
--venue              exact venue name, e.g. "IEEE Transactions on Signal Processing"
--open-access        only papers with a public PDF

Examples
--------
# Search for journal articles with >= 10 citations (best combo for quality filtering)
python3 tools/semantic_scholar_fetch.py search "semantic communication" --max 10 \
  --publication-types JournalArticle --min-citations 10

# CS/Engineering papers from 2022 onward
python3 tools/semantic_scholar_fetch.py search "semantic communication" --max 10 \
  --fields-of-study "Computer Science,Engineering" --year "2022-"

# Bulk search sorted by citation count, CS only
python3 tools/semantic_scholar_fetch.py search-bulk "semantic communication" --max 50 \
  --sort citationCount:desc --fields-of-study "Computer Science" --year "2020-"

# Fetch a single paper by DOI or arXiv ID
python3 tools/semantic_scholar_fetch.py paper "10.1109/JSAC.2021.3126077"
python3 tools/semantic_scholar_fetch.py paper "ARXIV:2006.10685"

# NOTE: --venue requires exact venue name (e.g. "IEEE Transactions on Signal Processing"),
# not partial match like "IEEE". Prefer --publication-types + --fields-of-study instead.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_API_BASE = "https://api.semanticscholar.org/graph/v1"
_USER_AGENT = "s2-fetch/1.1"
_DEFAULT_TIMEOUT = 30

# Good default for relevance search / single-paper fetch
_DEFAULT_FIELDS = (
    "paperId,title,abstract,year,venue,publicationVenue,publicationTypes,"
    "publicationDate,url,openAccessPdf,authors,externalIds,citationCount,"
    "referenceCount,fieldsOfStudy,s2FieldsOfStudy,tldr"
)

# Bulk search is intended for basic paper data; keep defaults conservative
_DEFAULT_BULK_FIELDS = (
    "paperId,title,abstract,year,venue,publicationDate,url,authors,"
    "externalIds,citationCount,referenceCount,fieldsOfStudy"
)


def _headers() -> dict[str, str]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    }
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _request_json(url: str, *, retries: int = 2, timeout: int = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=_headers())
    last_err: Exception | None = None

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                last_err = exc
                continue

            message = f"HTTP {exc.code}"
            if body:
                message += f": {body}"
            raise RuntimeError(message) from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                last_err = exc
                continue
            raise RuntimeError(f"Network error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Failed to parse JSON response from Semantic Scholar API") from exc

    raise RuntimeError(f"Request failed after retries: {last_err}")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("\n", " ")
    return text or None


def _parse_author(author: dict[str, Any]) -> dict[str, Any]:
    return {
        "authorId": author.get("authorId"),
        "name": _clean_text(author.get("name")),
    }


def _parse_publication_venue(pub_venue: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pub_venue:
        return None
    return {
        "id": pub_venue.get("id"),
        "name": _clean_text(pub_venue.get("name")),
        "type": _clean_text(pub_venue.get("type")),
        "issn": _clean_text(pub_venue.get("issn")),
        "url": _clean_text(pub_venue.get("url")),
    }


def _parse_paper(paper: dict[str, Any]) -> dict[str, Any]:
    authors = paper.get("authors") or []
    return {
        "paperId": paper.get("paperId"),
        "title": _clean_text(paper.get("title")),
        "abstract": _clean_text(paper.get("abstract")),
        "year": paper.get("year"),
        "venue": _clean_text(paper.get("venue")),
        "publicationVenue": _parse_publication_venue(paper.get("publicationVenue")),
        "publicationTypes": paper.get("publicationTypes"),
        "publicationDate": _clean_text(paper.get("publicationDate")),
        "url": _clean_text(paper.get("url")),
        "openAccessPdf": paper.get("openAccessPdf"),
        "authors": [_parse_author(a) for a in authors],
        "externalIds": paper.get("externalIds"),
        "citationCount": paper.get("citationCount"),
        "referenceCount": paper.get("referenceCount"),
        "fieldsOfStudy": paper.get("fieldsOfStudy"),
        "s2FieldsOfStudy": paper.get("s2FieldsOfStudy"),
        "tldr": paper.get("tldr"),
    }


def search(
    query: str,
    max_results: int = 10,
    offset: int = 0,
    fields: str = _DEFAULT_FIELDS,
    fields_of_study: str | None = None,
    venue: str | None = None,
    year: str | None = None,
    min_citation_count: int | None = None,
    publication_types: str | None = None,
    open_access_pdf: bool = False,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "query": query,
        "limit": max_results,
        "offset": offset,
        "fields": fields,
    }
    if fields_of_study:
        params["fieldsOfStudy"] = fields_of_study
    if venue:
        params["venue"] = venue
    if year:
        params["year"] = year
    if min_citation_count is not None:
        params["minCitationCount"] = min_citation_count
    if publication_types:
        params["publicationTypes"] = publication_types
    if open_access_pdf:
        params["openAccessPdf"] = ""
    url = f"{_API_BASE}/paper/search?{urllib.parse.urlencode(params)}"
    payload = _request_json(url)

    data = payload.get("data") or []
    return {
        "mode": "search",
        "total": payload.get("total"),
        "offset": offset,
        "next_offset": offset + len(data),
        "data": [_parse_paper(item) for item in data],
    }


def search_bulk(
    query: str,
    max_results: int = 100,
    token: str | None = None,
    fields: str = _DEFAULT_BULK_FIELDS,
    sort: str | None = None,
    fields_of_study: str | None = None,
    venue: str | None = None,
    year: str | None = None,
    min_citation_count: int | None = None,
    publication_types: str | None = None,
    open_access_pdf: bool = False,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "query": query,
        "limit": max_results,
        "fields": fields,
    }
    if token:
        params["token"] = token
    if sort:
        params["sort"] = sort
    if fields_of_study:
        params["fieldsOfStudy"] = fields_of_study
    if venue:
        params["venue"] = venue
    if year:
        params["year"] = year
    if min_citation_count is not None:
        params["minCitationCount"] = min_citation_count
    if publication_types:
        params["publicationTypes"] = publication_types
    if open_access_pdf:
        params["openAccessPdf"] = ""

    url = f"{_API_BASE}/paper/search/bulk?{urllib.parse.urlencode(params)}"
    payload = _request_json(url)

    data = payload.get("data") or []
    return {
        "mode": "search-bulk",
        "token": payload.get("token"),
        "returned": len(data),
        "sort": sort,
        "data": [_parse_paper(item) for item in data],
    }


def get_paper(paper_id: str, fields: str = _DEFAULT_FIELDS) -> dict[str, Any]:
    encoded_id = urllib.parse.quote(paper_id, safe="")
    params = {"fields": fields}
    url = f"{_API_BASE}/paper/{encoded_id}?{urllib.parse.urlencode(params)}"
    payload = _request_json(url)
    return _parse_paper(payload)


def _add_filter_args(parser: argparse.ArgumentParser) -> None:
    """Add shared filtering arguments to a search sub-parser."""
    parser.add_argument(
        "--fields-of-study",
        default=None,
        help="Comma-separated fields of study filter, e.g. 'Computer Science,Engineering'.",
    )
    parser.add_argument(
        "--venue",
        default=None,
        help="Comma-separated venue filter, e.g. 'IEEE,ACM' or 'Nature'.",
    )
    parser.add_argument(
        "--year",
        default=None,
        help="Year or range, e.g. '2023', '2020-2024', '2020-', '-2023'.",
    )
    parser.add_argument(
        "--min-citations",
        type=int,
        default=None,
        metavar="N",
        help="Minimum citation count filter.",
    )
    parser.add_argument(
        "--publication-types",
        default=None,
        help="Comma-separated types: JournalArticle,Conference,Review,etc.",
    )
    parser.add_argument(
        "--open-access",
        action="store_true",
        default=False,
        help="Only return papers with a public PDF.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search and fetch papers from Semantic Scholar.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Relevance search for papers")
    search_parser.add_argument("query", help="Keyword query")
    search_parser.add_argument(
        "--max",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of results to return (default: 10).",
    )
    search_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Offset for pagination (default: 0).",
    )
    search_parser.add_argument(
        "--fields",
        default=_DEFAULT_FIELDS,
        help="Comma-separated response fields to request.",
    )
    _add_filter_args(search_parser)

    bulk_parser = subparsers.add_parser(
        "search-bulk",
        help="Bulk search for papers with token-based pagination",
    )
    bulk_parser.add_argument("query", help="Keyword query")
    bulk_parser.add_argument(
        "--max",
        type=int,
        default=100,
        metavar="N",
        help="Maximum number of results to return in this page (default: 100).",
    )
    bulk_parser.add_argument(
        "--token",
        default=None,
        help="Continuation token returned by a previous bulk search page.",
    )
    bulk_parser.add_argument(
        "--sort",
        default=None,
        help="Optional sort for bulk search, e.g. publicationDate:desc or citationCount:desc",
    )
    bulk_parser.add_argument(
        "--fields",
        default=_DEFAULT_BULK_FIELDS,
        help="Comma-separated response fields to request.",
    )
    _add_filter_args(bulk_parser)

    paper_parser = subparsers.add_parser("paper", help="Fetch one paper by ID")
    paper_parser.add_argument(
        "id",
        help=(
            "Semantic Scholar paper ID, DOI, CorpusId:..., ARXIV:..., PMID:..., MAG:..., ACL:..., etc."
        ),
    )
    paper_parser.add_argument(
        "--fields",
        default=_DEFAULT_FIELDS,
        help="Comma-separated response fields to request.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "search":
            result = search(
                query=args.query,
                max_results=args.max,
                offset=args.offset,
                fields=args.fields,
                fields_of_study=args.fields_of_study,
                venue=args.venue,
                year=args.year,
                min_citation_count=args.min_citations,
                publication_types=args.publication_types,
                open_access_pdf=args.open_access,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "search-bulk":
            result = search_bulk(
                query=args.query,
                max_results=args.max,
                token=args.token,
                fields=args.fields,
                sort=args.sort,
                fields_of_study=args.fields_of_study,
                venue=args.venue,
                year=args.year,
                min_citation_count=args.min_citations,
                publication_types=args.publication_types,
                open_access_pdf=args.open_access,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "paper":
            result = get_paper(
                paper_id=args.id,
                fields=args.fields,
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