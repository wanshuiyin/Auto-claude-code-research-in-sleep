"""Tests for tools/verify_papers.py transient-failure handling.

export.arxiv.org returns 406 Not Acceptable intermittently, while a missing ID
is a plain 200 with zero results. Classifying 406 as a permanent 4xx made
`_verify_arxiv_batch_with_retry` mark every ID in the batch — including papers
that really exist — as "unverified", i.e. a false fabrication signal.
"""

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "verify_papers.py"

REAL_ID = "1706.03762"
MISSING_ID = "2609.99999"

FOUND_FEED = (
    "<feed><entry><id>http://arxiv.org/abs/1706.03762v7</id></entry></feed>"
)
EMPTY_FEED = "<feed><opensearch:totalResults>0</opensearch:totalResults></feed>"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_papers", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register before exec: the module's dataclasses resolve their annotations
    # through sys.modules (same pattern as test_review_gate.py).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _patch_http_get(monkeypatch, mod, responses):
    """Each call to http_get pops one (status, body) pair from `responses`."""
    queue = list(responses)
    calls = {"n": 0}

    def fake_http_get(url, headers=None, timeout=30):
        calls["n"] += 1
        return queue.pop(0)

    monkeypatch.setattr(mod, "http_get", fake_http_get)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    return calls


# ---- is_transient ---------------------------------------------------------

def test_is_transient_covers_arxiv_rate_limit_codes():
    mod = load_module()

    assert mod.is_transient(406)  # intermittent on export.arxiv.org
    assert mod.is_transient(408)
    assert mod.is_transient(429)
    assert mod.is_transient(503)
    assert mod.is_transient(-1)  # network failure


def test_is_transient_excludes_real_client_errors():
    mod = load_module()

    assert not mod.is_transient(200)
    assert not mod.is_transient(400)
    assert not mod.is_transient(404)


# ---- batch verification --------------------------------------------------

def test_batch_retries_on_406_then_verifies(monkeypatch):
    mod = load_module()
    calls = _patch_http_get(
        monkeypatch, mod, [(406, None), (406, None), (200, FOUND_FEED)]
    )

    result = mod._verify_arxiv_batch_with_retry([REAL_ID, MISSING_ID])

    assert calls["n"] == 3
    assert result == {REAL_ID: "verified", MISSING_ID: "unverified"}


def test_missing_id_is_unverified_on_a_clean_200(monkeypatch):
    """A nonexistent ID is 200 + zero results, not an HTTP error."""
    mod = load_module()
    _patch_http_get(monkeypatch, mod, [(200, EMPTY_FEED)])

    result = mod._verify_arxiv_batch_with_retry([MISSING_ID])

    assert result == {MISSING_ID: "unverified"}


def test_persistent_406_reports_pending_not_unverified(monkeypatch):
    """Exhausted retries must not claim a real paper does not exist."""
    mod = load_module()
    _patch_http_get(monkeypatch, mod, [(406, None)] * 3)

    result = mod._verify_arxiv_batch_with_retry([REAL_ID])

    assert result == {REAL_ID: "verify_pending"}


def test_non_transient_4xx_still_short_circuits(monkeypatch):
    """A malformed query (400) is permanent — no retries."""
    mod = load_module()
    calls = _patch_http_get(monkeypatch, mod, [(400, None)])

    result = mod._verify_arxiv_batch_with_retry([REAL_ID])

    assert calls["n"] == 1
    assert result == {REAL_ID: "unverified"}


# ── refusals, the curl transport, and the pending cache ─────────────────────

def _counting_http_get(monkeypatch, mod, status, body=None):
    calls = {"n": 0}

    def fake_http_get(url, headers=None, timeout=30):
        calls["n"] += 1
        return status, body

    monkeypatch.setattr(mod, "http_get", fake_http_get)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    return calls


def test_persistent_406_does_not_split_the_batch(monkeypatch):
    """arXiv refusing the client answers every sub-batch the same way."""
    mod = load_module()
    calls = _counting_http_get(monkeypatch, mod, 406)
    batch = [f"2401.{i:05d}" for i in range(40)]

    out = mod._verify_arxiv_batch_with_retry(batch)

    assert calls["n"] == 3
    assert set(out.values()) == {"verify_pending"}


def test_refusals_are_pending_in_every_layer(monkeypatch):
    mod = load_module()
    for status in (401, 403):
        _counting_http_get(monkeypatch, mod, status)
        assert set(mod._verify_arxiv_batch_with_retry(["1706.03762"]).values()) == {"verify_pending"}
        assert mod.verify_doi("10.1000/x", "a@b.c") == "verify_pending"
        assert mod.verify_title_s2("Attention Is All You Need", 0.7) == ("verify_pending", None)


def test_http_get_rescues_406_through_curl(monkeypatch):
    import urllib.error
    from io import BytesIO
    mod = load_module()

    def refuse(req, timeout=30):
        raise urllib.error.HTTPError(url="http://x/", code=406, msg="Not Acceptable", hdrs=None, fp=BytesIO(b""))

    monkeypatch.setattr(mod.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(mod, "_curl_get", lambda url, headers, timeout: b"<feed/>")
    assert mod.http_get("https://export.arxiv.org/api/query?id_list=1") == (200, "<feed/>")

    monkeypatch.setattr(mod, "_curl_get", lambda url, headers, timeout: None)
    assert mod.http_get("https://export.arxiv.org/api/query?id_list=1") == (406, None)


def test_cached_pending_is_asked_again(monkeypatch):
    """A verify_pending written during an outage must not answer for the next 30 days."""
    mod = load_module()
    feed = "<feed><entry><id>http://arxiv.org/abs/1706.03762v7</id></entry></feed>"
    calls = _counting_http_get(monkeypatch, mod, 200, feed)
    cache = {"arxiv:1706.03762": {"status": "verify_pending", "reason": "arxiv_verify_pending", "ts": 0}}
    paper = mod.PaperInput(id="p1", arxiv_id="1706.03762")

    (result,) = mod.verify_papers([paper], arxiv_batch_size=40, fuzzy_threshold=0.6,
                                  user_email="a@b.c", cache=cache)

    assert calls["n"] == 1
    assert result.status == "verified"
    assert cache["arxiv:1706.03762"]["status"] == "verified"


# ── matching returned entries to requested IDs ──────────────────────────

def test_truncated_id_is_not_verified_by_its_longer_sibling(monkeypatch):
    """`2501.1234` is a strict prefix of `2501.12345`; the feed entry for the
    real 5-digit paper must not vouch for the (nonexistent) 4-digit one."""
    mod = load_module()
    feed = "<feed><entry><id>http://arxiv.org/abs/2501.12345v1</id></entry></feed>"
    _patch_http_get(monkeypatch, mod, [(200, feed)])

    result = mod._verify_arxiv_batch_with_retry(["2501.1234", "2501.12345"])

    assert result == {"2501.1234": "unverified", "2501.12345": "verified"}


def test_returned_entry_matches_versioned_and_legacy_ids(monkeypatch):
    mod = load_module()
    feed = (
        "<feed>"
        "<entry><id>http://arxiv.org/abs/1706.03762v7</id></entry>"
        "<entry><id>http://arxiv.org/abs/cs/0601001v1</id></entry>"
        "<entry><id>http://arxiv.org/abs/2501.12345</id></entry>"
        "</feed>"
    )
    _patch_http_get(monkeypatch, mod, [(200, feed)])

    result = mod._verify_arxiv_batch_with_retry(["1706.03762v5", "cs/0601001", "2501.12345"])

    assert result == {"1706.03762v5": "verified", "cs/0601001": "verified", "2501.12345": "verified"}
