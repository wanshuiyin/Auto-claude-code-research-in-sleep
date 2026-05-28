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


# ---- User-Agent (arXiv lenient pool) -------------------------------------

BATCH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2510.23672v1</id>
    <title>First Paper</title>
    <summary>Abstract one.</summary>
    <published>2025-10-27T12:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <arxiv:primary_category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2402.14992v2</id>
    <title>Second Paper</title>
    <summary>Abstract two.</summary>
    <published>2024-02-22T12:00:00Z</published>
    <author><name>Bob Jones</name></author>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
</feed>"""


def _capture_urlopen(monkeypatch, mod, responses):
    """Like _patch_urlopen but records each Request object passed to urlopen."""
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


def test_sends_descriptive_user_agent(monkeypatch):
    mod = load_module()
    monkeypatch.delenv("ARIS_VERIFY_EMAIL", raising=False)
    seen = _capture_urlopen(monkeypatch, mod, [VALID_XML])

    mod.fetch_arxiv_metadata("2510.23672")

    req = seen["requests"][0]
    ua = req.get_header("User-agent")  # urllib normalizes header key casing
    assert ua and ua.startswith("ARIS-research-wiki/")
    assert "Python-urllib" not in (ua or "")


def test_user_agent_includes_contact_when_env_set(monkeypatch):
    mod = load_module()
    monkeypatch.setenv("ARIS_VERIFY_EMAIL", "dev@example.org")
    seen = _capture_urlopen(monkeypatch, mod, [VALID_XML])

    mod.fetch_arxiv_metadata("2510.23672")

    ua = seen["requests"][0].get_header("User-agent")
    assert "mailto:dev@example.org" in ua


# ---- Batch id_list fetch -------------------------------------------------

def test_batch_fetch_one_request_many_entries(monkeypatch):
    mod = load_module()
    seen = _capture_urlopen(monkeypatch, mod, [BATCH_XML])

    out = mod.fetch_arxiv_metadata_batch(["2510.23672", "2402.14992"])

    # single network call for both ids
    assert len(seen["requests"]) == 1
    # id_list carried both ids, comma-joined
    assert "2510.23672,2402.14992" in seen["requests"][0].full_url
    # max_results set to the id count so >10 ids are not silently truncated
    assert "max_results=2" in seen["requests"][0].full_url
    # keyed by normalized id, version stripped
    assert set(out) == {"2510.23672", "2402.14992"}
    assert out["2510.23672"]["title"] == "First Paper"
    assert out["2402.14992"]["authors"] == ["Bob Jones"]


def test_batch_fetch_empty_input_no_request(monkeypatch):
    mod = load_module()
    seen = _capture_urlopen(monkeypatch, mod, [])

    assert mod.fetch_arxiv_metadata_batch([]) == {}
    assert len(seen["requests"]) == 0
