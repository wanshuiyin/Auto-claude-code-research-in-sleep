"""Exercise the Gemini reviewer's HTTP request without calling a model."""
import io
import json
import runpy
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("override", "expected_model", "config"),
    [
        (None, "gemini-3.8-flash", {}),
        ("models/gemini-3.8-flash", "gemini-3.8-flash", {}),
        ("gemini-2.5-flash", "gemini-2.5-flash", {"temperature": 0.2}),
    ],
)
def test_api_model_and_sampling(monkeypatch, override, expected_model, config):
    monkeypatch.delenv("GEMINI_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_REVIEW_API_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test")
    bridge = runpy.run_path(str(ROOT / "mcp-servers/gemini-review/server.py"))

    def respond(request, timeout):
        assert request.full_url.endswith(f"/models/{expected_model}:generateContent")
        body = json.loads(request.data)
        assert body.get("generationConfig", {}) == config
        assert body["contents"] == [{"role": "user", "parts": [{"text": "Review this."}]}]
        return io.BytesIO(b'{"candidates":[{"content":{"parts":[{"text":"Reviewed."}]}}]}')

    monkeypatch.setattr(urllib.request, "urlopen", respond)
    result, error = bridge["run_gemini_api_review"](
        "Review this.", history=[], model=override, system="", image_paths=[]
    )
    assert error is None
    assert result["response"] == "Reviewed."
