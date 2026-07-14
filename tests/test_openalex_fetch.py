import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

# openalex_fetch treats `requests` as an optional dependency (it prints an
# install hint instead of hard-crashing); CI installs only pytest, so skip
# this module there rather than fail on the missing import.
pytest.importorskip("requests")


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "openalex_fetch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("openalex_fetch", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, openalex_fetch, payload=None, status_code=200):
        self._openalex_fetch = openalex_fetch
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            response = SimpleNamespace(status_code=self.status_code)
            raise self._openalex_fetch.requests.exceptions.HTTPError(
                f"HTTP {self.status_code}", response=response
            )

    def json(self):
        return self._payload


def test_reconstruct_abstract_orders_inverted_index_positions():
    openalex_fetch = load_module()

    abstract = openalex_fetch.OpenAlexClient()._reconstruct_abstract(
        {"models": [1], "are": [2], "useful": [0, 3]}
    )

    assert abstract == "useful models are useful"


def test_parse_work_handles_missing_location_and_normalizes_metadata():
    openalex_fetch = load_module()
    client = openalex_fetch.OpenAlexClient()

    parsed = client._parse_work(
        {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1234/example",
            "display_name": "A test work",
            "authorships": [
                {"author": {"display_name": "Ada Lovelace"}},
                {"author": {}},
            ],
            "primary_location": None,
            "open_access": {"oa_status": "gold", "oa_url": "https://example.test/pdf"},
            "abstract_inverted_index": {"Test": [0], "abstract.": [1]},
            "topics": [{"display_name": "Topic A"}],
            "keywords": [{"display_name": "Keyword A"}],
            "publication_year": 2025,
            "cited_by_count": 3,
            "type": "article",
            "language": "en",
        }
    )

    assert parsed["openalex_id"] == "W123"
    assert parsed["doi"] == "10.1234/example"
    assert parsed["title"] == "A test work"
    assert parsed["authors"] == ["Ada Lovelace", "Unknown"]
    assert parsed["author_count"] == 2
    assert parsed["venue"] == "Unknown"
    assert parsed["abstract"] == "Test abstract."
    assert parsed["topics"] == ["Topic A"]
    assert parsed["keywords"] == ["Keyword A"]


def test_search_works_builds_filters_and_caps_page_size(monkeypatch):
    openalex_fetch = load_module()
    client = openalex_fetch.OpenAlexClient(api_key="test-key")
    captured = {}

    def fake_get(url, params, timeout):
        captured.update(url=url, params=params, timeout=timeout)
        return FakeResponse(openalex_fetch, {"results": []})

    monkeypatch.setattr(client.session, "get", fake_get)

    assert client.search_works(
        "agent memory",
        max_results=250,
        publication_year="2020-2023",
        work_type="article",
        open_access=True,
        min_citations=10,
        sort="cited_by_count:desc",
    ) == []

    assert captured["url"] == "https://api.openalex.org/works"
    assert captured["timeout"] == 30
    params = captured["params"]
    assert params["search"] == "agent memory"
    assert params["per_page"] == 200
    assert params["sort"] == "cited_by_count:desc"
    assert set(params["filter"].split(",")) == {
        "publication_year:2020-2023",
        "type:article",
        "is_oa:true",
        "cited_by_count:>10",
    }
    assert params["api_key"] == "test-key"


def test_search_works_surfaces_rate_limit_error(monkeypatch, capsys):
    openalex_fetch = load_module()
    client = openalex_fetch.OpenAlexClient()

    def fake_get(url, params, timeout):
        return FakeResponse(openalex_fetch, status_code=429)

    monkeypatch.setattr(client.session, "get", fake_get)

    with pytest.raises(openalex_fetch.requests.exceptions.HTTPError):
        client.search_works("rate limited")

    assert "Rate limit exceeded" in capsys.readouterr().err
