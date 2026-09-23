"""Tests for HTTP 406 handling and verification fallbacks.

export.arxiv.org has been observed answering 406 (empty body) to Python's
urllib while `requests`/`curl` succeed on the same URL. These tests cover:

- arxiv_fetch._fetch_atom and research_wiki._arxiv_api_get re-issue the
  request through the fallback transport on 406;
- verify_papers never turns a refusal (401/403/406) into ``unverified``:
  arXiv ids fall back to DataCite DOIs, titles fall back to OpenAlex, and the
  reported ``method`` names the source that actually verified the paper.
"""

import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path

import pytest
import urllib.error


ROOT = Path(__file__).resolve().parents[1]


def load_tool(filename, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


VALID_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2509.14933v1</id>
    <title>Test Paper</title>
    <summary>An abstract.</summary>
    <published>2025-09-18T12:00:00Z</published>
    <updated>2025-09-18T12:00:00Z</updated>
    <author><name>Alice Smith</name></author>
    <category term="cs.LG"/>
  </entry>
</feed>"""


def _http_error(code):
    return urllib.error.HTTPError(url="https://example/", code=code, msg="err", hdrs=None,
                                  fp=BytesIO(b""))


def _urlopen_always(monkeypatch, mod, exc):
    def fake_urlopen(req, timeout=None):
        raise exc

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)


# ── transport fallback on 406 ────────────────────────────────────────────────

def test_arxiv_fetch_406_uses_fallback(monkeypatch):
    mod = load_tool("arxiv_fetch.py", "arxiv_fetch_406")
    _urlopen_always(monkeypatch, mod, _http_error(406))
    seen = []
    monkeypatch.setattr(mod, "_fallback_get",
                        lambda url, headers, timeout: seen.append((url, headers)) or VALID_XML)
    results = mod.search("attention", max_results=1)
    assert results and results[0]["title"] == "Test Paper"
    assert seen[0][0].startswith("https://export.arxiv.org/")
    assert "User-Agent" in seen[0][1]


def test_arxiv_fetch_406_without_fallback_raises(monkeypatch):
    mod = load_tool("arxiv_fetch.py", "arxiv_fetch_406b")
    _urlopen_always(monkeypatch, mod, _http_error(406))
    monkeypatch.setattr(mod, "_fallback_get", lambda *a: None)
    with pytest.raises(RuntimeError, match="406"):
        mod.search("attention", max_results=1)


def test_arxiv_fetch_other_4xx_still_fatal(monkeypatch):
    mod = load_tool("arxiv_fetch.py", "arxiv_fetch_400")
    _urlopen_always(monkeypatch, mod, _http_error(400))
    called = []
    monkeypatch.setattr(mod, "_fallback_get", lambda *a: called.append(1))
    with pytest.raises(RuntimeError):
        mod.search("attention", max_results=1)
    assert not called


def test_research_wiki_406_uses_fallback(monkeypatch):
    mod = load_tool("research_wiki.py", "research_wiki_406")
    _urlopen_always(monkeypatch, mod, _http_error(406))
    monkeypatch.setattr(mod, "_arxiv_fallback_get", lambda url, headers, timeout: VALID_XML)
    assert mod._arxiv_api_get("https://export.arxiv.org/api/query?id_list=x", "x") == VALID_XML


# ── verify_papers: refusals are not "not found" ─────────────────────────────

class Router:
    """Fake verify_papers.http_get: maps URL prefixes to (status, body)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, headers=None, timeout=30):
        self.calls.append(url)
        for prefix, result in self.routes.items():
            if url.startswith(prefix):
                return result
        raise AssertionError(f"unexpected URL {url}")


def _vp(monkeypatch, routes):
    mod = load_tool("verify_papers.py", f"verify_papers_{len(routes)}_{id(routes)}")
    router = Router(routes)
    monkeypatch.setattr(mod, "http_get", router)
    return mod, router


def _run(mod, papers):
    inputs = [mod.PaperInput(**p) for p in papers]
    return mod.verify_papers(inputs, arxiv_batch_size=40, fuzzy_threshold=0.6,
                             user_email="x@y", cache=None)


OPENALEX_HIT = json.dumps({"results": [{
    "title": "The wisdom of crowds for visual search",
    "doi": "https://doi.org/10.1073/pnas.1610732114"}]})


def test_arxiv_refusal_falls_back_to_datacite(monkeypatch):
    mod, router = _vp(monkeypatch, {
        "https://export.arxiv.org": (406, None),
        "https://api.datacite.org/dois/10.48550/arxiv.2109.14187": (200, "{}"),
    })
    (res,) = _run(mod, [{"id": "p1", "arxiv_id": "2109.14187"}])
    assert res.status == "verified" and res.method == "datacite"


def test_arxiv_refusal_and_datacite_404_is_unverified(monkeypatch):
    mod, _ = _vp(monkeypatch, {
        "https://export.arxiv.org": (406, None),
        "https://api.datacite.org": (404, None),
    })
    (res,) = _run(mod, [{"id": "p1", "arxiv_id": "9999.99999"}])
    assert res.status == "unverified"


def test_arxiv_refusal_and_datacite_refusal_is_pending(monkeypatch):
    mod, _ = _vp(monkeypatch, {
        "https://export.arxiv.org": (406, None),
        "https://api.datacite.org": (403, None),
    })
    (res,) = _run(mod, [{"id": "p1", "arxiv_id": "2109.14187"}])
    assert res.status == "verify_pending"


def test_arxiv_ok_keeps_arxiv_method(monkeypatch):
    body = '<feed><entry><id>http://arxiv.org/abs/2109.14187v2</id></entry></feed>'
    mod, router = _vp(monkeypatch, {"https://export.arxiv.org": (200, body)})
    (res,) = _run(mod, [{"id": "p1", "arxiv_id": "2109.14187"}])
    assert res.status == "verified" and res.method == "arxiv"
    assert not any("datacite" in u for u in router.calls)


def test_s2_refusal_falls_back_to_openalex(monkeypatch):
    mod, _ = _vp(monkeypatch, {
        "https://api.semanticscholar.org": (403, None),
        "https://api.openalex.org": (200, OPENALEX_HIT),
    })
    (res,) = _run(mod, [{"id": "p1", "title": "The wisdom of crowds for visual search"}])
    assert res.status == "verified" and res.method == "openalex"
    assert res.identifiers["doi"] == "10.1073/pnas.1610732114"


def test_s2_refusal_and_openalex_down_is_pending(monkeypatch):
    mod, _ = _vp(monkeypatch, {
        "https://api.semanticscholar.org": (403, None),
        "https://api.openalex.org": (503, None),
    })
    (res,) = _run(mod, [{"id": "p1", "title": "Some real but unindexed paper"}])
    assert res.status == "verify_pending"


def test_s2_clean_miss_stays_unverified(monkeypatch):
    mod, router = _vp(monkeypatch, {
        "https://api.semanticscholar.org": (200, json.dumps({"data": []})),
    })
    (res,) = _run(mod, [{"id": "p1", "title": "A fabricated paper title about nothing"}])
    assert res.status == "unverified"
    assert not any("openalex" in u for u in router.calls)


def test_s2_api_key_header_sent(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "k123")
    mod = load_tool("verify_papers.py", "verify_papers_key")
    seen = {}

    def fake(url, headers=None, timeout=30):
        seen["headers"] = headers
        return 200, json.dumps({"data": []})

    monkeypatch.setattr(mod, "http_get", fake)
    mod.verify_title_s2("Any title here", 0.6)
    assert seen["headers"].get("x-api-key") == "k123"


def test_http_get_406_uses_fallback(monkeypatch):
    mod = load_tool("verify_papers.py", "verify_papers_http")
    _urlopen_always(monkeypatch, mod, _http_error(406))
    monkeypatch.setattr(mod, "_fallback_get", lambda url, headers, timeout: b"<feed/>")
    assert mod.http_get("https://export.arxiv.org/api/query?id_list=x") == (200, "<feed/>")
