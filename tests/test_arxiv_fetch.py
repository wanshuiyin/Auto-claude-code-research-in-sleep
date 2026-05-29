"""Tests for tools/arxiv_fetch.py UA + 429 retry behavior.

Mirrors the test structure in test_research_wiki_fetch_arxiv_metadata.py
(introduced by PR #266) to keep the two helpers' rate-limit handling
verified against equivalent scenarios.
"""

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "arxiv_fetch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("arxiv_fetch", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
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
    <author><name>Bob Jones</name></author>
    <category term="cs.LG"/>
  </entry>
</feed>"""


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _http_error_429():
    return urllib.error.HTTPError(
        url="http://example/",
        code=429,
        msg="Too Many Requests",
        hdrs=None,
        fp=BytesIO(b""),
    )


def _patch_urlopen(monkeypatch, mod, responses):
    """Each call to urlopen pops one item from `responses`."""
    queue = list(responses)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    return calls


def _capture_urlopen(monkeypatch, mod, responses):
    """Like _patch_urlopen but records each Request object passed in."""
    queue = list(responses)
    seen = {"requests": []}

    def fake_urlopen(req, timeout=None):
        seen["requests"].append(req)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    return seen


# ---- search() retry behavior ---------------------------------------------

def test_search_success_first_try(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(monkeypatch, mod, [VALID_XML])

    results = mod.search("2509.14933", max_results=1)

    assert calls["n"] == 1
    assert len(results) == 1
    assert results[0]["title"] == "Test Paper"
    assert results[0]["authors"] == ["Alice Smith", "Bob Jones"]


def test_search_retries_on_http_429_then_succeeds(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(monkeypatch, mod, [_http_error_429(), VALID_XML])

    results = mod.search("2509.14933", max_results=1)

    assert calls["n"] == 2
    assert results[0]["title"] == "Test Paper"


def test_search_retries_on_urlerror_then_succeeds(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(
        monkeypatch, mod, [urllib.error.URLError("conn refused"), VALID_XML]
    )

    results = mod.search("2509.14933", max_results=1)

    assert calls["n"] == 2
    assert results[0]["title"] == "Test Paper"


def test_search_retries_on_rate_exceeded_body_then_succeeds(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(monkeypatch, mod, [b"Rate exceeded.", VALID_XML])

    results = mod.search("2509.14933", max_results=1)

    assert calls["n"] == 2
    assert results[0]["title"] == "Test Paper"


def test_search_raises_after_three_429s(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(
        monkeypatch, mod, [_http_error_429(), _http_error_429(), _http_error_429()]
    )

    with pytest.raises(RuntimeError, match="arXiv API fetch failed"):
        mod.search("2509.14933", max_results=1)
    assert calls["n"] == 3


def test_search_raises_after_three_rate_exceeded_bodies(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(
        monkeypatch, mod, [b"Rate exceeded.", b"Rate exceeded.", b"Rate exceeded."]
    )

    with pytest.raises(RuntimeError, match="rate-limited"):
        mod.search("2509.14933", max_results=1)
    assert calls["n"] == 3


def test_search_non_429_http_error_does_not_retry(monkeypatch):
    mod = load_module()
    err_500 = urllib.error.HTTPError(
        url="http://example/", code=500, msg="Server Error",
        hdrs=None, fp=BytesIO(b""),
    )
    calls = _patch_urlopen(monkeypatch, mod, [err_500])

    with pytest.raises(RuntimeError, match="arXiv API fetch failed"):
        mod.search("2509.14933", max_results=1)
    assert calls["n"] == 1


# ---- User-Agent (arXiv lenient pool) -------------------------------------

def test_search_sends_descriptive_user_agent(monkeypatch):
    mod = load_module()
    monkeypatch.delenv("ARIS_VERIFY_EMAIL", raising=False)
    seen = _capture_urlopen(monkeypatch, mod, [VALID_XML])

    mod.search("2509.14933", max_results=1)

    ua = seen["requests"][0].get_header("User-agent")
    assert ua and ua.startswith("arxiv-skill/")
    assert "Python-urllib" not in (ua or "")


def test_user_agent_includes_contact_when_env_set(monkeypatch):
    mod = load_module()
    monkeypatch.setenv("ARIS_VERIFY_EMAIL", "dev@example.org")
    seen = _capture_urlopen(monkeypatch, mod, [VALID_XML])

    mod.search("2509.14933", max_results=1)

    ua = seen["requests"][0].get_header("User-agent")
    assert "mailto:dev@example.org" in ua


def test_user_agent_no_contact_when_env_unset(monkeypatch):
    mod = load_module()
    monkeypatch.delenv("ARIS_VERIFY_EMAIL", raising=False)
    seen = _capture_urlopen(monkeypatch, mod, [VALID_XML])

    mod.search("2509.14933", max_results=1)

    ua = seen["requests"][0].get_header("User-agent")
    assert "mailto:" not in (ua or "")


# ---- download() retry behavior -------------------------------------------

_FAKE_PDF = b"%PDF-1.4\n" + b"x" * 20_000  # > _MIN_PDF_BYTES


def test_download_retries_on_429_then_succeeds(monkeypatch, tmp_path):
    mod = load_module()
    calls = _patch_urlopen(monkeypatch, mod, [_http_error_429(), _FAKE_PDF])

    result = mod.download("2509.14933", output_dir=str(tmp_path))

    assert calls["n"] == 2
    assert result["skipped"] is False
    assert Path(result["path"]).exists()


def test_download_raises_after_three_429s(monkeypatch, tmp_path):
    mod = load_module()
    calls = _patch_urlopen(
        monkeypatch, mod, [_http_error_429(), _http_error_429(), _http_error_429()]
    )

    with pytest.raises(urllib.error.HTTPError):
        mod.download("2509.14933", output_dir=str(tmp_path))
    assert calls["n"] == 3
