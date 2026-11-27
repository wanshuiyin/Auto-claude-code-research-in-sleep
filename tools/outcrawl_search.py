#!/usr/bin/env python3
"""CLI helper for web search and page scraping via Outcrawl.

Complements arXiv, Semantic Scholar and OpenAlex with **broad web search**
(title, URL and snippet per result): blog posts, documentation, project
pages, technical reports. Also scrapes a known URL to markdown through a
real browser, which is useful for reading a paper page, a README or a docs
page that needs JavaScript to render.

Requires
--------
Python standard library only. Set OUTCRAWL_API_KEY (the free tier includes
1,000 credits a month).

Commands
--------
search    Search the web (title, URL, snippet per result).
scrape    Fetch one or more URLs as markdown.

Examples
--------
# Top 10 web results
python3 tools/outcrawl_search.py search "KV cache compression long context" --max 10

# Restrict results to one site
python3 tools/outcrawl_search.py search "mixture of experts routing" --site arxiv.org

# Scrape known URLs
python3 tools/outcrawl_search.py scrape "https://arxiv.org/abs/2211.17192"
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

API_BASE = "https://api.outcrawl.ai/v1"
KEY_URL = "https://outcrawl.ai/sign-in"
# api.outcrawl.ai refuses the default Python-urllib user agent.
USER_AGENT = "aris-outcrawl-search"
MAX_RESULTS = 20


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value}")
    return number


def _result_count(value: str) -> int:
    number = _positive_int(value)
    if number > MAX_RESULTS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_RESULTS}, got {value}")
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
    return os.getenv("OUTCRAWL_API_KEY", "").strip()


def _hostname(item: str) -> str:
    """Reduce "https://user@ArXiv.org:443/abs?x=1" to "arxiv.org"."""
    host = item.strip().lower().split("://", 1)[-1]
    for sep in "/?#":
        host = host.split(sep, 1)[0]
    return host.rsplit("@", 1)[-1].split(":", 1)[0].strip(".")


def _site(value: str) -> str:
    """argparse type for --site: one hostname."""
    host = _hostname(value)
    if not host or any(ch.isspace() for ch in host):
        raise argparse.ArgumentTypeError(f"not a valid domain: {value!r}")
    return host


def _error_message(status: int, body: Any) -> str:
    """Turn an HTTP error from Outcrawl into one actionable line."""
    detail = None
    if isinstance(body, dict):
        detail = body.get("message") or body.get("error")
        if isinstance(detail, dict):
            detail = detail.get("message")
    if status == 401:
        return f"Invalid OUTCRAWL_API_KEY. Get a key from: {KEY_URL}"
    if status == 402:
        return f"Outcrawl credits exhausted for this API key. {detail or ''}".strip()
    if status == 429:
        return f"Outcrawl rate limit reached, retry shortly. {detail or ''}".strip()
    return f"Outcrawl API error (HTTP {status}): {detail or 'no details'}"


def _post(endpoint: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    """POST a JSON payload to the Outcrawl API and return the parsed body."""
    api_key = _api_key()
    if not api_key:
        raise AccountError(f"OUTCRAWL_API_KEY is not set. Get a key from: {KEY_URL}")

    request = urllib.request.Request(
        f"{API_BASE}/{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
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
        raise error(_error_message(exc.code, body)) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the Outcrawl API: {exc.reason}") from None
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        # Read timeouts and connection resets are not wrapped in URLError.
        raise RuntimeError(f"Could not reach the Outcrawl API: {exc}") from None

    try:
        body = json.loads(raw)
    except ValueError:
        raise RuntimeError("Outcrawl returned a non-JSON response.") from None
    if not isinstance(body, dict):
        raise RuntimeError("Outcrawl returned an unexpected response.")
    return body


def _truncate(entry: dict[str, Any], markdown: Any, max_chars: int) -> None:
    if isinstance(markdown, str) and markdown:
        entry["markdown"] = markdown[:max_chars]
        if len(markdown) > max_chars:
            entry["markdown_truncated"] = True


def search(
    query: str,
    max_results: int = 10,
    site: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Search the web via Outcrawl and return structured results."""
    full_query = f"{query} site:{site}" if site else query
    body = _post("search", {"query": full_query, "limit": max_results}, timeout)
    hits = body.get("hits")
    if not isinstance(hits, list):
        print("Warning: Outcrawl response has no hits list; returning 0 results.", file=sys.stderr)
        hits = []

    results = []
    for hit in hits:
        if not isinstance(hit, dict) or not hit.get("url"):
            continue
        results.append({
            "title": hit.get("title") or "No Title",
            "url": hit["url"],
            "snippet": hit.get("snippet") or "",
        })

    output: dict[str, Any] = {
        "mode": "search",
        "query": full_query,
        "returned": len(results),
        "data": results[:max_results],
    }
    if isinstance(body.get("usage"), dict):
        output["usage"] = body["usage"]
    return output


def _scrape_one(
    url: str, max_chars: int, main_content_only: bool, timeout: float
) -> dict[str, Any]:
    body = _post(
        "scrape",
        {"url": url, "formats": ["markdown"], "onlyMainContent": main_content_only},
        timeout,
    )
    status = body.get("statusCode")
    if isinstance(status, int) and status >= 400:
        raise RuntimeError(f"Page returned HTTP {status}")
    metadata = body.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    entry: dict[str, Any] = {
        "url": body.get("url") or url,
        "title": metadata.get("title") or "No Title",
    }
    _truncate(entry, body.get("markdown"), max_chars)
    return entry


def scrape(
    urls: list[str],
    max_chars: int = 20000,
    main_content_only: bool = True,
    timeout: float = 90.0,
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
        description="Web search and page scraping via Outcrawl.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search the web via Outcrawl")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--max", type=_result_count, default=10, metavar="N",
        help=f"Maximum number of results, 1-{MAX_RESULTS} (default: 10).",
    )
    search_parser.add_argument(
        "--site", type=_site, default=None, metavar="DOMAIN",
        help="Restrict results to one domain (added to the query as site:DOMAIN).",
    )

    scrape_parser = subparsers.add_parser("scrape", help="Fetch URLs as markdown")
    scrape_parser.add_argument(
        "urls", nargs="+", type=_scrape_url,
        help="Plain http(s) URLs to scrape; no spaces, quotes, backticks, $ or \\.",
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


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not _api_key():
        print(f"Error: OUTCRAWL_API_KEY is not set. Get a key from: {KEY_URL}", file=sys.stderr)
        return 1

    try:
        if args.command == "search":
            result = search(query=args.query, max_results=args.max, site=args.site)
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
