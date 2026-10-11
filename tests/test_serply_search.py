import importlib.util
import io
import json
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "serply_search.py"


def load_module():
    spec = importlib.util.spec_from_file_location("serply_search", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def install_urlopen(monkeypatch, serply_search, payload):
    """Patch urlopen to return payload and record the outgoing request."""
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["request"] = request
        seen["timeout"] = timeout
        return FakeResponse(payload)

    monkeypatch.setattr(serply_search.urllib.request, "urlopen", fake_urlopen)
    return seen


def query_of(seen):
    return parse_qs(urlparse(seen["request"].full_url).query)


WEB_PAYLOAD = {
    "results": [
        {"title": "One", "link": "https://example.com/1", "description": "first"},
        {"title": "Bad", "link": "javascript:alert(1)", "description": "skip"},
        {"title": "Two", "link": "http://example.com/2", "description": None},
        {"title": None, "link": "https://example.com/3", "description": "third"},
    ]
}

SCHOLAR_PAYLOAD = {
    "results": [],
    "articles": [
        {
            "title": "A Paper",
            "link": "https://venue.org/paper",
            "description": "A Author, B Author\xa0- Venue, 2024 - venue.org",
            "author": {
                "names": "A Author, B Author",
                "authors": [{"name": "A Author"}, {"name": "B Author"}],
            },
            "extras": {"citations": {"count": "Cited by 12"}},
            "doc": {"link": "https://venue.org/paper.pdf", "type": "PDF"},
        },
        {"title": "No Link", "link": "ftp://x/y"},
    ],
}


def test_get_api_key_raises_when_missing(monkeypatch):
    serply_search = load_module()
    monkeypatch.delenv("SERPLY_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SERPLY_API_KEY"):
        serply_search._get_api_key()


def test_get_api_key_raises_when_blank(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "   ")

    with pytest.raises(RuntimeError, match="SERPLY_API_KEY"):
        serply_search._get_api_key()


def test_clamp_max_defaults_and_bounds():
    serply_search = load_module()
    assert serply_search._clamp_max(None) == 10
    assert serply_search._clamp_max(0) == 1
    assert serply_search._clamp_max(-5) == 1
    assert serply_search._clamp_max(3) == 3
    assert serply_search._clamp_max(50) == 10


def test_search_request_shape_and_headers(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    seen = install_urlopen(monkeypatch, serply_search, WEB_PAYLOAD)

    serply_search.search("rag & pipelines", max_results=5, gl="DE", recency="week")

    request = seen["request"]
    assert urlparse(request.full_url).path == "/v1/search"
    assert query_of(seen) == {
        "q": ["rag & pipelines"],
        "num": ["5"],
        "gl": ["de"],
        "tbs": ["qdr:w"],
    }
    assert request.get_header("X-api-key") == "test-key"
    assert request.get_header("User-agent") == "auto-claude-code-research-in-sleep"
    assert seen["timeout"] == serply_search._TIMEOUT_SECONDS


def test_search_omits_optional_params(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    seen = install_urlopen(monkeypatch, serply_search, WEB_PAYLOAD)

    serply_search.search("q")

    assert query_of(seen) == {"q": ["q"], "num": ["10"]}


def test_search_zero_max_clamps_to_one(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    seen = install_urlopen(monkeypatch, serply_search, WEB_PAYLOAD)

    result = serply_search.search("q", max_results=0)

    assert query_of(seen)["num"] == ["1"]
    assert result["returned"] == 1


def test_search_skips_non_http_links_and_maps_fields(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    install_urlopen(monkeypatch, serply_search, WEB_PAYLOAD)

    result = serply_search.search("q")

    assert result["mode"] == "search"
    assert result["returned"] == 3
    assert result["data"] == [
        {"title": "One", "url": "https://example.com/1", "snippet": "first"},
        {"title": "Two", "url": "http://example.com/2", "snippet": ""},
        {"title": "No Title", "url": "https://example.com/3", "snippet": "third"},
    ]


def test_search_trims_to_requested_max(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    rows = [
        {"title": str(i), "link": f"https://example.com/{i}", "description": ""}
        for i in range(11)
    ]
    install_urlopen(monkeypatch, serply_search, {"results": rows})

    result = serply_search.search("q", max_results=4)

    assert result["returned"] == 4
    assert [r["title"] for r in result["data"]] == ["0", "1", "2", "3"]


def test_search_tolerates_missing_results(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    install_urlopen(monkeypatch, serply_search, {"detail": "nothing"})

    result = serply_search.search("q")

    assert result["returned"] == 0
    assert result["data"] == []


def test_news_sends_news_vertical(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    seen = install_urlopen(monkeypatch, serply_search, WEB_PAYLOAD)

    result = serply_search.news("foundation models", recency="day")

    assert query_of(seen)["tbm"] == ["nws"]
    assert query_of(seen)["tbs"] == ["qdr:d"]
    assert result["mode"] == "news"
    assert result["returned"] == 3


def test_scholar_uses_articles_not_results(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    seen = install_urlopen(monkeypatch, serply_search, SCHOLAR_PAYLOAD)

    result = serply_search.scholar("graph neural networks", max_results=2)

    assert urlparse(seen["request"].full_url).path == "/v1/scholar"
    assert query_of(seen) == {"q": ["graph neural networks"], "num": ["2"]}
    assert result["mode"] == "scholar"
    assert result["returned"] == 1
    assert result["data"] == [
        {
            "title": "A Paper",
            "url": "https://venue.org/paper",
            "byline": "A Author, B Author - Venue, 2024 - venue.org",
            "authors": ["A Author", "B Author"],
            "cited_by": "Cited by 12",
            "pdf_url": "https://venue.org/paper.pdf",
        }
    ]


def test_scholar_handles_sparse_article(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    install_urlopen(
        monkeypatch,
        serply_search,
        {"articles": [{"title": "T", "link": "https://x.org/t", "author": "plain"}]},
    )

    result = serply_search.scholar("q")

    assert result["data"] == [{"title": "T", "url": "https://x.org/t", "byline": ""}]


def test_http_error_surfaces_detail(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "bad-key")

    def raise_401(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {},
            io.BytesIO(b'{"detail": "Invalid API key"}'),
        )

    monkeypatch.setattr(serply_search.urllib.request, "urlopen", raise_401)

    with pytest.raises(RuntimeError, match="Serply HTTP 401: Invalid API key"):
        serply_search.search("q")


def test_non_json_response_raises(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    install_urlopen(monkeypatch, serply_search, b"<html>blocked</html>")

    with pytest.raises(RuntimeError, match="non-JSON"):
        serply_search.search("q")


def test_url_error_raises_runtime_error(monkeypatch):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")

    def raise_url_error(request, timeout=None):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(serply_search.urllib.request, "urlopen", raise_url_error)

    with pytest.raises(RuntimeError, match="name resolution failed"):
        serply_search.search("q")


def test_main_search_prints_json(monkeypatch, capsys):
    serply_search = load_module()
    monkeypatch.setenv("SERPLY_API_KEY", "test-key")
    install_urlopen(monkeypatch, serply_search, WEB_PAYLOAD)

    code = serply_search.main(["search", "q", "--max", "2"])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["mode"] == "search"
    assert printed["returned"] == 2


def test_main_returns_1_on_error(monkeypatch, capsys):
    serply_search = load_module()
    monkeypatch.delenv("SERPLY_API_KEY", raising=False)

    code = serply_search.main(["scholar", "q"])

    assert code == 1
    assert "SERPLY_API_KEY" in capsys.readouterr().err


def test_parser_rejects_bad_recency():
    serply_search = load_module()
    with pytest.raises(SystemExit):
        serply_search._build_parser().parse_args(["search", "q", "--recency", "decade"])


def test_parser_scholar_has_no_geo_or_recency_flags():
    serply_search = load_module()
    with pytest.raises(SystemExit):
        serply_search._build_parser().parse_args(["scholar", "q", "--gl", "us"])
