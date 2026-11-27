import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "semantic_scholar_fetch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("semantic_scholar_fetch", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_request_json_retries_after_a_read_timeout(monkeypatch):
    semantic_scholar_fetch = load_module()
    monkeypatch.setattr(semantic_scholar_fetch.time, "sleep", lambda seconds: None)
    attempts = []

    def fake_urlopen(req, timeout=None):
        attempts.append(req.full_url)
        if len(attempts) == 1:
            raise TimeoutError("timed out")
        return FakeResponse({"data": []})

    monkeypatch.setattr(semantic_scholar_fetch.urllib.request, "urlopen", fake_urlopen)

    assert semantic_scholar_fetch._request_json("https://api.semanticscholar.org/graph/v1/paper/search") == {
        "data": []
    }
    assert len(attempts) == 2
