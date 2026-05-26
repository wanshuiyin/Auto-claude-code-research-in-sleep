import importlib.util
from io import BytesIO
from pathlib import Path

import pytest
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "research_wiki.py"


def load_module():
    spec = importlib.util.spec_from_file_location("research_wiki", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


VALID_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2510.23672v1</id>
    <title>DBLoss Test Paper</title>
    <summary>An abstract.</summary>
    <published>2025-10-27T12:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <arxiv:primary_category term="cs.LG"/>
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
    """Each call to urlopen pops one item from `responses`.
    A bytes item is returned as a FakeResponse; an Exception is raised."""
    queue = list(responses)
    calls = {"n": 0}

    def fake_urlopen(url, timeout=None):
        calls["n"] += 1
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    return calls


def test_success_first_try(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(monkeypatch, mod, [VALID_XML])

    meta = mod.fetch_arxiv_metadata("2510.23672")

    assert calls["n"] == 1
    assert meta["arxiv_id"] == "2510.23672"
    assert meta["title"] == "DBLoss Test Paper"
    assert meta["authors"] == ["Alice Smith", "Bob Jones"]
    assert meta["primary_category"] == "cs.LG"


def test_retries_on_http_429_then_succeeds(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(monkeypatch, mod, [_http_error_429(), VALID_XML])

    meta = mod.fetch_arxiv_metadata("2510.23672")

    assert calls["n"] == 2
    assert meta["title"] == "DBLoss Test Paper"


def test_retries_on_rate_exceeded_body_then_succeeds(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(monkeypatch, mod, [b"Rate exceeded.", VALID_XML])

    meta = mod.fetch_arxiv_metadata("2510.23672")

    assert calls["n"] == 2
    assert meta["title"] == "DBLoss Test Paper"


def test_raises_after_three_429s(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(
        monkeypatch, mod, [_http_error_429(), _http_error_429(), _http_error_429()]
    )

    with pytest.raises(RuntimeError, match="arXiv API fetch failed"):
        mod.fetch_arxiv_metadata("2510.23672")
    assert calls["n"] == 3


def test_raises_after_three_rate_exceeded_bodies(monkeypatch):
    mod = load_module()
    calls = _patch_urlopen(
        monkeypatch, mod, [b"Rate exceeded.", b"Rate exceeded.", b"Rate exceeded."]
    )

    with pytest.raises(RuntimeError, match="rate-limited"):
        mod.fetch_arxiv_metadata("2510.23672")
    assert calls["n"] == 3


def test_non_429_http_error_does_not_retry(monkeypatch):
    mod = load_module()
    err_500 = urllib.error.HTTPError(
        url="http://example/", code=500, msg="Server Error",
        hdrs=None, fp=BytesIO(b""),
    )
    calls = _patch_urlopen(monkeypatch, mod, [err_500])

    with pytest.raises(RuntimeError, match="arXiv API fetch failed"):
        mod.fetch_arxiv_metadata("2510.23672")
    assert calls["n"] == 1


def test_malformed_xml_raises(monkeypatch):
    mod = load_module()
    _patch_urlopen(monkeypatch, mod, [b"<not valid xml"])

    with pytest.raises(RuntimeError, match="unparseable XML"):
        mod.fetch_arxiv_metadata("2510.23672")
