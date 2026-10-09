#!/usr/bin/env python3
"""CLI helper for web search and page scraping via Firecrawl.

Complements arXiv, Semantic Scholar and OpenAlex with **broad web search
that returns full-page markdown**: blog posts, documentation, project pages,
technical reports and PDFs. Also scrapes a known URL (HTML or PDF) to
markdown, which is useful for reading a paper, a README or a docs page.

Requires
--------
Python standard library only. Set FIRECRAWL_API_KEY.

Commands
--------
search    Search the web, optionally with page markdown for each result.
scrape    Fetch one or more URLs as markdown.

Examples
--------
# Search and read the top pages in one call
python3 tools/firecrawl_search.py search "KV cache compression long context" --max 5

# Results only (title, URL, description), no page content
python3 tools/firecrawl_search.py search "speculative decoding" --max 10 --content none

# PDFs from the past year, restricted to a few hosts
python3 tools/firecrawl_search.py search "mixture of experts routing" --category pdf \
  --tbs qdr:y --include-domains "arxiv.org,openreview.net"

# Scrape known URLs (HTML or PDF)
python3 tools/firecrawl_search.py scrape "https://arxiv.org/abs/2211.17192"
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://api.firecrawl.dev/v2"
ORIGIN = "aris"
KEY_URL = "https://www.firecrawl.dev/app/api-keys"


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value}")
    return number


def _result_count(value: str) -> int:
    number = _positive_int(value)
    if number > 100:
        raise argparse.ArgumentTypeError(f"must be between 1 and 100, got {value}")
    return number


# Plain http(s) URLs only: no whitespace, quotes, backticks, "$" or backslashes.
SCRAPE_URL_RE = re.compile(r"^https?://[^\s'\"`$\\]+$")


class AccountError(RuntimeError):
    """HTTP 401/402/429: the key or account is the problem, not the URL."""


def _scrape_url(value: str) -> str:
    """argparse type for scrape URLs."""
    if not SCRAPE_URL_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"not a plain http(s) URL: {value!r}")
    return value


def _api_key() -> str:
    return os.getenv("FIRECRAWL_API_KEY", "").strip()


def _hostname(item: str) -> str:
    """Reduce "https://user@ArXiv.org:443/abs?x=1" to "arxiv.org"."""
    host = item.strip().lower().split("://", 1)[-1]
    for sep in "/?#":
        host = host.split(sep, 1)[0]
    return host.rsplit("@", 1)[-1].split(":", 1)[0].strip(".")


def _parse_domains(value: str | None) -> list[str] | None:
    """Split a comma-separated domain list and keep lowercase hostnames only."""
    if value is None:
        return None
    hosts = (_hostname(item) for item in value.split(","))
    return [host for host in hosts if host]


def _domain_list(value: str) -> list[str]:
    """argparse type for --include-domains / --exclude-domains."""
    hosts = _parse_domains(value)
    if not hosts:
        raise argparse.ArgumentTypeError(f"no valid domain in {value!r}")
    return hosts


def _error_message(status: int, body: Any, has_key: bool) -> str:
    """Turn an HTTP error from Firecrawl into one actionable line."""
    detail = body.get("error") if isinstance(body, dict) else None
    if not has_key and status in (401, 402, 429):
        return (
            "This request needs an API key, or the daily limit for requests without one "
            f"was reached. Set FIRECRAWL_API_KEY. Get a key from: {KEY_URL}"
        )
    if status == 401:
        return f"Invalid FIRECRAWL_API_KEY. Get a key from: {KEY_URL}"
    if status == 402:
        return f"Firecrawl credits exhausted for this API key. {detail or ''}".strip()
    if status == 429:
        return f"Firecrawl rate limit reached, retry shortly. {detail or ''}".strip()
    return f"Firecrawl API error (HTTP {status}): {detail or 'no details'}"


def _post(endpoint: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    """POST a JSON payload to the Firecrawl API and return the parsed body."""
    api_key = _api_key()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        f"{API_BASE}/{endpoint}",
        data=json.dumps({**payload, "origin": ORIGIN}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read() or b"{}")
        except (ValueError, OSError, http.client.HTTPException):
            body = None
        error = AccountError if exc.code in (401, 402, 429) else RuntimeError
        raise error(_error_message(exc.code, body, bool(api_key))) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the Firecrawl API: {exc.reason}") from None
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        # Read timeouts and connection resets are not wrapped in URLError.
        raise RuntimeError(f"Could not reach the Firecrawl API: {exc}") from None

    try:
        body = json.loads(raw)
    except ValueError:
        raise RuntimeError("Firecrawl returned a non-JSON response.") from None
    # Some failures (e.g. DNS errors on scrape) come back as HTTP 200 with success: false.
    if not isinstance(body, dict) or not body.get("success", False):
        detail = body.get("error") if isinstance(body, dict) else None
        raise RuntimeError(f"Firecrawl request failed: {detail or 'unknown error'}")
    return body


def _truncate(entry: dict[str, Any], markdown: Any, max_chars: int) -> None:
    if isinstance(markdown, str) and markdown:
        entry["markdown"] = markdown[:max_chars]
        if len(markdown) > max_chars:
            entry["markdown_truncated"] = True


def search(
    query: str,
    max_results: int = 5,
    content_mode: str = "markdown",
    max_chars: int = 4000,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    category: str | None = None,
    tbs: str | None = None,
    country: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Search the web via Firecrawl and return structured results."""
    payload: dict[str, Any] = {
        "query": query,
        "limit": max_results,
        # Same server-side budget as scrape, so the server stops before the client does.
        "timeout": int(timeout * 1000),
    }
    if content_mode == "markdown":
        payload["scrapeOptions"] = {"formats": ["markdown"], "onlyMainContent": True}
    if include_domains:
        payload["includeDomains"] = include_domains
    if exclude_domains:
        payload["excludeDomains"] = exclude_domains
    if category:
        payload["categories"] = [{"type": category}]
    if tbs:
        payload["tbs"] = tbs
    if country:
        payload["country"] = country

    body = _post("search", payload, timeout + 30)
    data = body.get("data")
    hits = data.get("web") if isinstance(data, dict) else None
    if not isinstance(hits, list):
        print("Warning: Firecrawl response has no data.web list; returning 0 results.", file=sys.stderr)
        hits = []

    results = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        entry: dict[str, Any] = {
            "title": hit.get("title") or "No Title",
            "url": hit.get("url") or "",
            "description": hit.get("description") or "",
        }
        if hit.get("category"):
            entry["category"] = hit["category"]
        metadata = hit.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        status = metadata.get("statusCode")
        if metadata.get("error") or (isinstance(status, int) and status >= 400):
            entry["scrape_error"] = metadata.get("error") or f"Page returned HTTP {status}"
        else:
            _truncate(entry, hit.get("markdown"), max_chars)
        results.append(entry)

    output: dict[str, Any] = {
        "mode": "search",
        "query": query,
        "returned": len(results),
        "data": results,
    }
    warnings = body.get("warnings") or ([body["warning"]] if body.get("warning") else [])
    if warnings:
        output["warnings"] = warnings
    return output


def _scrape_one(
    url: str, max_chars: int, main_content_only: bool, timeout: float
) -> dict[str, Any]:
    body = _post(
        "scrape",
        {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": main_content_only,
            # Large PDFs can take longer than the 60 s server default.
            "timeout": int(timeout * 1000),
        },
        timeout + 30,
    )
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Firecrawl returned no page data.")
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    status = metadata.get("statusCode")
    if isinstance(status, int) and status >= 400:
        raise RuntimeError(f"Page returned HTTP {status}")
    entry: dict[str, Any] = {
        "url": metadata.get("sourceURL") or url,
        "title": metadata.get("title") or "No Title",
    }
    _truncate(entry, data.get("markdown"), max_chars)
    return entry


def scrape(
    urls: list[str],
    max_chars: int = 20000,
    main_content_only: bool = True,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Fetch URLs as markdown. Per-URL failures are reported, not raised."""
    results = []
    for index, url in enumerate(urls):
        try:
            results.append(_scrape_one(url, max_chars, main_content_only, timeout))
        except AccountError as exc:
            # Key, credit or rate-limit problems apply to every URL, so stop here.
            results.append({"url": url, "error": str(exc)})
            results.extend(
                {"url": rest, "error": "Skipped: an earlier request failed with an account error."}
                for rest in urls[index + 1:]
            )
            break
        except RuntimeError as exc:
            results.append({"url": url, "error": str(exc)})
        except Exception as exc:  # one bad response must not drop the pages already fetched
            results.append({"url": url, "error": f"Unexpected error: {exc!r}"})

    return {
        "mode": "scrape",
        "returned": sum(1 for r in results if "error" not in r),
        "data": results,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Web search and page scraping via Firecrawl.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search the web via Firecrawl")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--max", type=_result_count, default=5, metavar="N",
        help="Maximum number of results, 1-100 (default: 5).",
    )
    search_parser.add_argument(
        "--content", default="markdown", dest="content_mode", choices=("markdown", "none"),
        help="markdown: page content for each result (default); none: title, URL, description.",
    )
    search_parser.add_argument(
        "--max-chars", type=_positive_int, default=4000, metavar="N",
        help="Max markdown characters kept per result (default: 4000).",
    )
    search_parser.add_argument(
        "--include-domains", type=_domain_list, default=None, metavar="DOMAINS",
        help="Comma-separated domains to include (hostnames; scheme, port and path are dropped).",
    )
    search_parser.add_argument(
        "--exclude-domains", type=_domain_list, default=None, metavar="DOMAINS",
        help="Comma-separated domains to exclude. Cannot be combined with --include-domains.",
    )
    search_parser.add_argument(
        "--category", default=None, choices=("pdf", "developer"),
        help="pdf: PDF documents only; developer: code repositories, issues and docs.",
    )
    search_parser.add_argument(
        "--tbs", default=None,
        help="Time filter: qdr:h, qdr:d, qdr:w, qdr:m, qdr:y, "
             "cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY, or sbd:1 to sort by date.",
    )
    search_parser.add_argument(
        "--country", default=None, help="ISO country code for localized results (e.g. US, DE).",
    )

    scrape_parser = subparsers.add_parser("scrape", help="Fetch URLs as markdown")
    scrape_parser.add_argument(
        "urls", nargs="+", type=_scrape_url,
        help="Plain http(s) URLs to scrape (HTML or PDF); no spaces, quotes, backticks, $ or \\.",
    )
    scrape_parser.add_argument(
        "--max-chars", type=_positive_int, default=20000, metavar="N",
        help="Max markdown characters kept per page (default: 20000).",
    )
    scrape_parser.add_argument(
        "--full-page", action="store_true",
        help="Keep navigation, headers and footers instead of the main content only.",
    )

    return parser


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "search" and args.include_domains and args.exclude_domains:
        parser.error("--include-domains and --exclude-domains cannot be combined.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not _api_key():
        print(
            "Note: FIRECRAWL_API_KEY is not set.",
            file=sys.stderr,
        )

    try:
        if args.command == "search":
            result = search(
                query=args.query,
                max_results=args.max,
                content_mode=args.content_mode,
                max_chars=args.max_chars,
                include_domains=args.include_domains,
                exclude_domains=args.exclude_domains,
                category=args.category,
                tbs=args.tbs,
                country=args.country,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "scrape":
            result = scrape(
                urls=args.urls,
                max_chars=args.max_chars,
                main_content_only=not args.full_page,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["returned"] else 1

        raise ValueError(f"Unsupported command: {args.command}")

    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
