#!/usr/bin/env python3
"""CLI helper for web search and page fetch via Keenable.

Designed to complement arXiv (preprints) and Semantic Scholar (published venues)
with **broad web search**: blog posts, documentation, project pages, news, and
papers hosted on the open web. Each search result carries a snippet of page
text; ``fetch`` returns a whole page as markdown.

Keyless by default: with no key set, requests go to Keenable's public
endpoints, which are rate-limited per IP. Set KEENABLE_API_KEY to use the
keyed endpoints with higher limits (create a key at
https://app.keenable.ai/console).

Requires
--------
Python 3 standard library only (no extra packages).

Commands
--------
search      Search the web; each result has title, URL, and a page-text snippet.
fetch       Fetch one or more URLs and return each page as markdown.

Filter flags (search)
---------------------
--site           Only results from this domain (one domain, e.g. arxiv.org)
--start-date     Only results published after this date (YYYY-MM-DD)
--end-date       Only results published before this date (YYYY-MM-DD)

Content flags (shared)
----------------------
--max-chars      Max characters of text per result
                 (default: 4000 for search, 10000 for fetch)

Examples
--------
# Basic search
python3 tools/keenable_search.py search "transformer attention mechanisms" --max 10

# One site, recent pages only
python3 tools/keenable_search.py search "diffusion distillation" --site arxiv.org \
  --start-date 2025-01-01

# Fetch pages as markdown
python3 tools/keenable_search.py fetch "https://arxiv.org/abs/2209.00796"
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_API_BASE = "https://api.keenable.ai"
_APP_TITLE = "auto-claude-code-research-in-sleep"
_USER_AGENT = "aris-keenable-search/1.0"
_DEFAULT_TIMEOUT = 30
_MAX_RESULTS_LIMIT = 50
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _api_key() -> str:
    return os.getenv("KEENABLE_API_KEY", "").strip()


def _endpoint(path: str) -> str:
    """Return the keyed endpoint when a key is set, else the keyless /public one."""
    if _api_key():
        return f"{_API_BASE}{path}"
    return f"{_API_BASE}{path}/public"


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
        "X-Keenable-Title": _APP_TITLE,
    }
    api_key = _api_key()
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return min(float(retry_after), 10.0)
        except ValueError:
            pass
    return 1.5 * (attempt + 1)


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    retries: int = 2,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """GET (payload=None) or POST JSON to Keenable and decode the JSON reply."""
    headers = _headers()
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
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
                time.sleep(_retry_delay(exc, attempt))
                last_err = exc
                continue

            message = f"HTTP {exc.code}"
            if body:
                message += f": {body[:500]}"
            if exc.code == 429 and not _api_key():
                message += " (keyless rate limit; set KEENABLE_API_KEY for higher limits)"
            raise RuntimeError(message) from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                last_err = exc
                continue
            raise RuntimeError(f"Network error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Failed to parse JSON response from Keenable API") from exc

    raise RuntimeError(f"Request failed after retries: {last_err}")


def _clip(text: Any, max_chars: int) -> str:
    """Strip and cap text at max_chars (0 or less means no cap)."""
    value = str(text or "").strip()
    if max_chars > 0 and len(value) > max_chars:
        value = value[:max_chars].rstrip()
    return value


def _normalize_date(value: Any) -> str | None:
    """Return an ISO 8601 string for a string or epoch-seconds date."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return _dt.datetime.fromtimestamp(value, tz=_dt.timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return str(value)


def _process_result(result: dict[str, Any], max_chars: int, text_field: str) -> dict[str, Any]:
    """Map one Keenable result (search hit or fetched page) to the output shape.

    Keenable returns page text in ``snippet`` (search) or ``content`` (fetch);
    ``description`` is not used because the API leaves it empty.
    """
    entry: dict[str, Any] = {
        "title": result.get("title") or "No Title",
        "url": result.get("url") or "",
    }

    published_date = _normalize_date(result.get("published_at"))
    if published_date:
        entry["published_date"] = published_date

    author = result.get("author")
    if author:
        entry["author"] = author

    text = _clip(result.get(text_field), max_chars)
    if text:
        entry[text_field] = text

    return entry


def search(
    query: str,
    max_results: int = 10,
    max_chars: int = 4000,
    site: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Search the web via Keenable and return structured results."""
    payload: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
    }
    if site:
        payload["site"] = site
    if start_date:
        payload["published_after"] = start_date
    if end_date:
        payload["published_before"] = end_date

    response = _request_json(_endpoint("/v1/search"), payload=payload)
    results = response.get("results") or []

    return {
        "command": "search",
        "query": query,
        "returned": len(results),
        "data": [_process_result(r, max_chars, "snippet") for r in results],
    }


def fetch(urls: list[str], max_chars: int = 10000) -> dict[str, Any]:
    """Fetch pages as markdown. A failed URL is reported and does not stop the rest."""
    data: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for url in urls:
        query = urllib.parse.urlencode({"url": url})
        try:
            page = _request_json(f"{_endpoint('/v1/fetch')}?{query}")
        except RuntimeError as exc:
            errors.append({"url": url, "error": str(exc)})
            continue
        entry = _process_result(page, max_chars, "content")
        if not entry["url"]:
            entry["url"] = url
        data.append(entry)

    result: dict[str, Any] = {
        "command": "fetch",
        "returned": len(data),
        "data": data,
    }
    if errors:
        result["errors"] = errors
    return result


def _max_results(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--max must be an integer, got {value!r}")
    if not 1 <= number <= _MAX_RESULTS_LIMIT:
        raise argparse.ArgumentTypeError(f"--max must be between 1 and {_MAX_RESULTS_LIMIT}")
    return number


def _date(value: str) -> str:
    if not _DATE_RE.match(value):
        raise argparse.ArgumentTypeError(f"dates must be YYYY-MM-DD, got {value!r}")
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a valid date: {value!r}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Web search and page fetch via Keenable (keyless by default).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- search ---
    search_parser = subparsers.add_parser("search", help="Search the web via Keenable")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--max", type=_max_results, default=10, metavar="N",
        help=f"Maximum number of results, 1-{_MAX_RESULTS_LIMIT} (default: 10).",
    )
    search_parser.add_argument(
        "--max-chars", type=int, default=4000, metavar="N",
        help="Max characters of snippet text per result (default: 4000).",
    )
    search_parser.add_argument(
        "--site", default=None,
        help="Only results from this domain (one domain, e.g. arxiv.org).",
    )
    search_parser.add_argument(
        "--start-date", type=_date, default=None,
        help="Only results published after this date (YYYY-MM-DD).",
    )
    search_parser.add_argument(
        "--end-date", type=_date, default=None,
        help="Only results published before this date (YYYY-MM-DD).",
    )

    # --- fetch ---
    fetch_parser = subparsers.add_parser(
        "fetch", help="Fetch pages as markdown",
    )
    fetch_parser.add_argument("urls", nargs="+", help="URLs to fetch")
    fetch_parser.add_argument(
        "--max-chars", type=int, default=10000, metavar="N",
        help="Max characters of page content per URL (default: 10000).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "search":
            result = search(
                query=args.query,
                max_results=args.max,
                max_chars=args.max_chars,
                site=args.site,
                start_date=args.start_date,
                end_date=args.end_date,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "fetch":
            result = fetch(urls=args.urls, max_chars=args.max_chars)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["data"] else 1

        raise ValueError(f"Unsupported command: {args.command}")

    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
