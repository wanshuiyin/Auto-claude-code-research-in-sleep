import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "xquik_search.py"


def load_module():
    spec = importlib.util.spec_from_file_location("xquik_search", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


def test_search_encodes_query_bounds_limit_and_sends_key(monkeypatch):
    xquik = load_module()
    captured = {}

    def open_request(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response({"tweets": [], "has_next_page": False, "next_cursor": ""})

    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")
    result = xquik.search("asyncio + timeout", 8, "Top", opener=open_request)

    request = captured["request"]
    query = parse_qs(urlparse(request.full_url).query)
    assert query == {"q": ["asyncio + timeout"], "limit": ["8"], "queryType": ["Top"]}
    assert request.get_header("X-api-key") == "test-secret"
    assert request.get_header("Accept") == "application/json"
    assert captured["timeout"] == 20
    assert result["returned"] == 0


@pytest.mark.parametrize("limit", [0, 21])
def test_search_rejects_unbounded_limits(monkeypatch, limit):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")

    with pytest.raises(ValueError, match="between 1 and 20"):
        xquik.search("query", limit)


def test_search_rejects_empty_query(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")

    with pytest.raises(ValueError, match="query is required"):
        xquik.search("  ")


def test_search_rejects_oversized_query(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")

    with pytest.raises(ValueError, match="at most 512 characters"):
        xquik.search("x" * 513)


def test_search_rejects_unknown_query_type(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")

    with pytest.raises(ValueError, match="Latest or Top"):
        xquik.search("query", query_type="Popular")


def test_search_requires_api_key(monkeypatch):
    xquik = load_module()
    monkeypatch.delenv("XQUIK_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="XQUIK_API_KEY"):
        xquik.search("query")


def test_search_normalizes_public_discussion_fields(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")
    payload = {
        "tweets": [
            {
                "id": "123",
                "text": "The fix works on Python 3.12.",
                "createdAt": "2026-08-20T10:00:00Z",
                "likeCount": 9,
                "retweetCount": 2,
                "replyCount": 1,
                "quoteCount": 0,
                "viewCount": 350,
                "bookmarkCount": 4,
                "author": {"username": "maintainer", "name": "Maintainer"},
            }
        ],
        "has_next_page": True,
        "next_cursor": "next-page",
    }

    result = xquik.search("python fix", opener=lambda *_args, **_kwargs: Response(payload))

    assert result == {
        "query": "python fix",
        "query_type": "Latest",
        "returned": 1,
        "has_next_page": True,
        "next_cursor": "next-page",
        "tweets": [
            {
                "id": "123",
                "text": "The fix works on Python 3.12.",
                "url": "https://x.com/maintainer/status/123",
                "created_at": "2026-08-20T10:00:00Z",
                "author": {"username": "maintainer", "name": "Maintainer"},
                "engagement": {
                    "likes": 9,
                    "reposts": 2,
                    "replies": 1,
                    "quotes": 0,
                    "views": 350,
                    "bookmarks": 4,
                },
            }
        ],
    }


def test_search_caps_unexpected_extra_results(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")
    payload = {
        "tweets": [{"id": str(index), "text": "post"} for index in range(5)],
        "has_next_page": False,
        "next_cursor": "",
    }

    result = xquik.search("query", 2, opener=lambda *_args, **_kwargs: Response(payload))

    assert result["returned"] == 2
    assert [tweet["id"] for tweet in result["tweets"]] == ["0", "1"]


def test_search_omits_unavailable_fields_and_malformed_tweets(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")
    payload = {
        "tweets": [
            {"id": "123", "text": "No optional fields."},
            {"id": "456"},
            {"id": 789, "text": "Non-string identifier."},
        ],
        "has_next_page": False,
        "next_cursor": "",
    }

    result = xquik.search("query", opener=lambda *_args, **_kwargs: Response(payload))

    assert result["returned"] == 1
    assert result["tweets"] == [{"id": "123", "text": "No optional fields."}]


def test_search_rejects_oversized_response(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")

    class OversizedResponse(Response):
        def __init__(self):
            self.payload = b"x" * (xquik.MAX_RESPONSE_BYTES + 1)

    with pytest.raises(RuntimeError, match="exceeded the 2 MiB limit"):
        xquik.search("query", opener=lambda *_args, **_kwargs: OversizedResponse())


def test_search_rejects_unsafe_generated_urls(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")
    payload = {
        "tweets": [
            {
                "id": "not-numeric",
                "text": "Post",
                "url": "https://x.com/example/status/not-numeric",
                "author": {"username": "../escape", "name": "Example"},
            }
        ]
    }

    result = xquik.search("query", opener=lambda *_args, **_kwargs: Response(payload))

    assert result["tweets"] == [
        {
            "id": "not-numeric",
            "text": "Post",
            "author": {"username": "../escape", "name": "Example"},
        }
    ]


def test_search_rejects_malformed_response(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")

    class InvalidResponse(Response):
        def __init__(self):
            self.payload = b"not-json"

    with pytest.raises(RuntimeError, match="invalid JSON"):
        xquik.search("query", opener=lambda *_args, **_kwargs: InvalidResponse())


def test_search_reports_http_status_without_response_body_or_secret(monkeypatch):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")

    def fail(request, timeout):
        raise HTTPError(request.full_url, 429, "rate limit", {}, io.BytesIO(b"test-secret"))

    with pytest.raises(RuntimeError) as error:
        xquik.search("query", opener=fail)

    assert str(error.value) == "Xquik search failed with HTTP 429."
    assert "test-secret" not in str(error.value)


def test_main_prints_json_without_api_key(monkeypatch, capsys):
    xquik = load_module()
    monkeypatch.setenv("XQUIK_API_KEY", "test-secret")
    monkeypatch.setattr(
        xquik,
        "search",
        lambda *_args, **_kwargs: {
            "query": "query",
            "query_type": "Latest",
            "returned": 0,
            "has_next_page": False,
            "next_cursor": "",
            "tweets": [],
        },
    )

    assert xquik.main(["query", "--max", "5"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["query"] == "query"
    assert "test-secret" not in output.out
    assert output.err == ""
