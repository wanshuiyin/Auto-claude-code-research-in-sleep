#!/usr/bin/env python3
"""Run one bounded public X search for the web-debug-search skill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SEARCH_URL = "https://xquik.com/api/v1/x/tweets/search"
MAX_RESULTS = 20
TIMEOUT_SECONDS = 20
Opener = Callable[..., Any]


def _api_key() -> str:
    key = os.getenv("XQUIK_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "XQUIK_API_KEY is required. Create a key at https://xquik.com and export it first."
        )
    return key


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"max results must be between 1 and {MAX_RESULTS}")


def _validate_query(query: str) -> None:
    if not query.strip():
        raise ValueError("query is required")


def _request(query: str, limit: int, query_type: str) -> Request:
    params = urlencode({"q": query, "limit": limit, "queryType": query_type})
    return Request(
        f"{SEARCH_URL}?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "aris-web-debug-search/1.0",
            "x-api-key": _api_key(),
        },
    )


def _author(tweet: dict[str, Any]) -> dict[str, str]:
    source = tweet.get("author")
    if not isinstance(source, dict):
        return {}
    return {
        field: value
        for field in ("username", "name")
        if isinstance((value := source.get(field)), str) and value
    }


def _tweet_url(tweet: dict[str, Any], author: dict[str, str]) -> str:
    supplied = tweet.get("url")
    if isinstance(supplied, str) and supplied.startswith("https://x.com/"):
        return supplied
    tweet_id = tweet.get("id")
    username = author.get("username")
    if isinstance(tweet_id, str) and username:
        return f"https://x.com/{username}/status/{tweet_id}"
    return ""


def _normalize_tweet(tweet: dict[str, Any]) -> dict[str, Any]:
    author = _author(tweet)
    return {
        "id": tweet.get("id", ""),
        "text": tweet.get("text", ""),
        "url": _tweet_url(tweet, author),
        "created_at": tweet.get("createdAt", ""),
        "author": author,
        "engagement": {
            "likes": tweet.get("likeCount", 0),
            "reposts": tweet.get("retweetCount", 0),
            "replies": tweet.get("replyCount", 0),
            "quotes": tweet.get("quoteCount", 0),
            "views": tweet.get("viewCount", 0),
            "bookmarks": tweet.get("bookmarkCount", 0),
        },
    }


def _decode(payload: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Xquik returned invalid JSON.") from error
    if not isinstance(decoded, dict) or not isinstance(decoded.get("tweets"), list):
        raise RuntimeError("Xquik returned an unexpected response shape.")
    return decoded


def search(
    query: str,
    max_results: int = 10,
    query_type: str = "Latest",
    *,
    opener: Opener = urlopen,
) -> dict[str, Any]:
    """Search one page and return stable fields for discovery review."""
    _validate_query(query)
    _validate_limit(max_results)
    request = _request(query, max_results, query_type)
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            payload = _decode(response.read())
    except HTTPError as error:
        raise RuntimeError(f"Xquik search failed with HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError("Xquik search failed. Check the network connection.") from error

    tweets = [
        _normalize_tweet(tweet)
        for tweet in payload["tweets"][:max_results]
        if isinstance(tweet, dict)
    ]
    return {
        "query": query,
        "query_type": query_type,
        "returned": len(tweets),
        "has_next_page": payload.get("has_next_page") is True,
        "next_cursor": payload.get("next_cursor", ""),
        "tweets": tweets,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Public X discussion search query")
    parser.add_argument("--max", type=int, default=10, dest="max_results")
    parser.add_argument("--query-type", choices=("Latest", "Top"), default="Latest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = search(args.query, args.max_results, args.query_type)
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
