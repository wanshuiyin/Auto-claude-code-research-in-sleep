import http.client
import importlib.util
import io
import json
import os
import re
import subprocess
import urllib.error
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "keenable_search.py"


@pytest.mark.parametrize("layout", ["global_pointer", "project_link", "explicit", "manifest"])
def test_codex_skill_resolves_helper_in_installed_layouts(tmp_path, layout):
    """Execute the documented shell resolver without touching the real home."""
    skill = (ROOT / "skills/skills-codex/keenable-search/SKILL.md").read_text()
    step = skill.split("### Step 2: Locate Script", 1)[1]
    block = re.search(r"```bash\n(.*?)```", step, re.S).group(1)
    fixture_home = tmp_path / "fixture home"
    project = tmp_path / "project"
    project.mkdir()
    (fixture_home / ".aris").mkdir(parents=True)
    repositories = {}
    for name in ("pointer", "explicit", "manifest", "linked"):
        repo = tmp_path / name
        (repo / "tools").mkdir(parents=True)
        (repo / "tools/keenable_search.py").write_text(f"print({name!r})\n")
        repositories[name] = repo
    env = dict(os.environ)
    env.pop("ARIS_REPO", None)
    (project / ".aris").mkdir()
    if layout != "project_link":
        (fixture_home / ".aris/repo").write_text(str(repositories["pointer"]) + "\n")
    if layout in ("explicit", "manifest"):
        (project / ".aris/installed-skills-codex.txt").write_text(
            f"repo_root\t{repositories['manifest']}\n"
        )
    if layout in ("explicit", "project_link"):
        (project / ".aris/tools").symlink_to(repositories["linked"] / "tools")
    if layout == "explicit":
        env["ARIS_REPO"] = str(repositories["explicit"])
    # Substitute home references in the snippet; preserve HOME and CODEX_HOME.
    block = block.replace("$HOME", str(fixture_home))
    block = block.replace("~/.codex", f'"{fixture_home}/.codex"')
    result = subprocess.run(
        ["bash", "-eu", "-c", block + '\npython3 "$KEENABLE_FETCHER"'],
        cwd=project, env=env, capture_output=True, text=True,
    )
    expected = {"global_pointer": "pointer", "project_link": "linked"}.get(layout, layout)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def load_module():
    spec = importlib.util.spec_from_file_location("keenable_search", MODULE_PATH)
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


def capture_urlopen(monkeypatch, module, payload):
    """Patch urlopen to record each request and answer with payload."""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        return FakeResponse(payload)

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_keyless_by_default_uses_public_endpoints(monkeypatch):
    keenable_search = load_module()
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)

    assert keenable_search._endpoint("/v1/search") == "https://api.keenable.ai/v1/search/public"
    assert keenable_search._endpoint("/v1/fetch") == "https://api.keenable.ai/v1/fetch/public"
    headers = keenable_search._headers()
    assert headers["X-Keenable-Title"] == "auto-claude-code-research-in-sleep"
    assert "X-API-Key" not in headers


def test_api_key_switches_to_keyed_endpoints(monkeypatch):
    keenable_search = load_module()
    monkeypatch.setenv("KEENABLE_API_KEY", " test-key ")

    assert keenable_search._endpoint("/v1/search") == "https://api.keenable.ai/v1/search"
    assert keenable_search._endpoint("/v1/fetch") == "https://api.keenable.ai/v1/fetch"
    headers = keenable_search._headers()
    assert headers["X-API-Key"] == "test-key"
    assert headers["X-Keenable-Title"] == "auto-claude-code-research-in-sleep"


def test_process_result_maps_snippet_and_ignores_description():
    keenable_search = load_module()
    entry = keenable_search._process_result(
        {
            "title": "Test Paper",
            "url": "https://example.com/paper",
            "description": "",
            "snippet": "  Page text from the result.\nSecond line.  ",
            "published_at": "2025-01-15T00:00:00Z",
            "acquired_at": "2026-09-03T17:20:45Z",
        },
        4000,
        "snippet",
    )

    assert entry == {
        "title": "Test Paper",
        "url": "https://example.com/paper",
        "published_date": "2025-01-15T00:00:00Z",
        "snippet": "Page text from the result.\nSecond line.",
    }


def test_process_result_caps_text_at_max_chars():
    keenable_search = load_module()
    entry = keenable_search._process_result(
        {"title": "T", "url": "https://example.com", "snippet": "x" * 5000}, 100, "snippet"
    )
    assert len(entry["snippet"]) == 100


def test_process_result_missing_optional_fields():
    keenable_search = load_module()
    entry = keenable_search._process_result({"title": None, "url": None}, 4000, "snippet")

    assert entry["title"] == "No Title"
    assert entry["url"] == ""
    assert "published_date" not in entry
    assert "author" not in entry
    assert "snippet" not in entry


def test_process_result_converts_epoch_published_at():
    keenable_search = load_module()
    entry = keenable_search._process_result(
        {
            "title": "Fetched",
            "url": "https://arxiv.org/abs/2209.00796",
            "content": "# Title",
            "author": "Ling Yang",
            "published_at": 1662076800,
        },
        10000,
        "content",
    )

    assert entry["published_date"] == "2022-09-02T00:00:00+00:00"
    assert entry["author"] == "Ling Yang"
    assert entry["content"] == "# Title"


def test_search_posts_payload_with_filters(monkeypatch):
    keenable_search = load_module()
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)
    calls = capture_urlopen(
        monkeypatch,
        keenable_search,
        {"results": [{"title": "Result 1", "url": "https://example.com/1", "snippet": "text 1"}]},
    )

    result = keenable_search.search(
        query="test query",
        max_results=5,
        site="arxiv.org",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    req = calls[0]
    assert req.full_url == "https://api.keenable.ai/v1/search/public"
    assert req.get_method() == "POST"
    assert json.loads(req.data) == {
        "query": "test query",
        "max_results": 5,
        "site": "arxiv.org",
        "published_after": "2025-01-01",
        "published_before": "2025-12-31",
    }
    assert req.get_header("X-keenable-title") == "auto-claude-code-research-in-sleep"
    assert result["command"] == "search"
    assert result["returned"] == 1
    assert result["data"][0]["snippet"] == "text 1"


def test_search_omits_unset_filters(monkeypatch):
    keenable_search = load_module()
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)
    calls = capture_urlopen(monkeypatch, keenable_search, {"results": []})

    result = keenable_search.search(query="q")

    assert json.loads(calls[0].data) == {"query": "q", "max_results": 10}
    assert result["returned"] == 0
    assert result["data"] == []


def test_search_with_key_sends_header_to_keyed_endpoint(monkeypatch):
    keenable_search = load_module()
    monkeypatch.setenv("KEENABLE_API_KEY", "test-key")
    calls = capture_urlopen(monkeypatch, keenable_search, {"results": []})

    keenable_search.search(query="q")

    assert calls[0].full_url == "https://api.keenable.ai/v1/search"
    assert calls[0].get_header("X-api-key") == "test-key"


def test_fetch_gets_each_url_as_markdown(monkeypatch):
    keenable_search = load_module()
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)
    calls = capture_urlopen(
        monkeypatch,
        keenable_search,
        {"url": "https://example.com/a", "title": "A", "content": "# A\n\nbody", "description": ""},
    )

    result = keenable_search.fetch(["https://example.com/a?x=1&y=2"])

    assert calls[0].get_method() == "GET"
    assert calls[0].full_url == (
        "https://api.keenable.ai/v1/fetch/public?url=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1%26y%3D2"
    )
    assert result["command"] == "fetch"
    assert result["returned"] == 1
    assert result["data"][0]["content"] == "# A\n\nbody"
    assert "errors" not in result


def test_fetch_reports_failed_urls_and_keeps_going(monkeypatch):
    keenable_search = load_module()

    def fake_request_json(url, **kwargs):
        if "bad" in url:
            raise RuntimeError("HTTP 422: could not fetch")
        return {"url": "https://example.com/good", "title": "Good", "content": "ok"}

    monkeypatch.setattr(keenable_search, "_request_json", fake_request_json)

    result = keenable_search.fetch(["https://example.com/bad", "https://example.com/good"])

    assert result["returned"] == 1
    assert result["data"][0]["title"] == "Good"
    assert result["errors"] == [{"url": "https://example.com/bad", "error": "HTTP 422: could not fetch"}]


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timed out"),
        http.client.RemoteDisconnected("Remote end closed connection without response"),
        ConnectionResetError(104, "Connection reset by peer"),
    ],
    ids=["read-timeout", "remote-disconnected", "connection-reset"],
)
def test_fetch_retries_and_reports_a_network_error_urllib_does_not_wrap(monkeypatch, error):
    keenable_search = load_module()
    monkeypatch.setattr(keenable_search.time, "sleep", lambda seconds: None)
    attempts = []

    def fake_urlopen(req, timeout=None):
        if "slow" in req.full_url:
            attempts.append(req.full_url)
            raise error
        return FakeResponse({"url": "https://example.com/good", "title": "Good", "content": "ok"})

    monkeypatch.setattr(keenable_search.urllib.request, "urlopen", fake_urlopen)

    result = keenable_search.fetch(["https://example.com/good", "https://example.com/slow"])

    assert len(attempts) == 3
    assert result["returned"] == 1
    assert result["data"][0]["title"] == "Good"
    assert result["errors"] == [{"url": "https://example.com/slow", "error": f"Network error: {error}"}]


def test_rate_limit_error_points_to_api_key(monkeypatch):
    keenable_search = load_module()
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b'{"detail":"rate limited"}')
        )

    monkeypatch.setattr(keenable_search.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="KEENABLE_API_KEY"):
        keenable_search._request_json("https://api.keenable.ai/v1/search/public", payload={}, retries=0)


def test_cli_parser_builds_help_without_traceback():
    keenable_search = load_module()
    help_text = keenable_search._build_parser().format_help()

    assert "search" in help_text
    assert "fetch" in help_text


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "q", "--max", "0"],
        ["search", "q", "--max", "51"],
        ["search", "q", "--start-date", "2025-1-1"],
        ["search", "q", "--end-date", "2025-02-30"],
    ],
)
def test_cli_rejects_out_of_range_arguments(argv):
    keenable_search = load_module()
    with pytest.raises(SystemExit):
        keenable_search._build_parser().parse_args(argv)


def test_main_search_outputs_json(monkeypatch, capsys):
    keenable_search = load_module()
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)
    capture_urlopen(
        monkeypatch,
        keenable_search,
        {"query": "q", "results": [{"title": "Result 1", "url": "https://example.com/1", "snippet": "s"}]},
    )

    exit_code = keenable_search.main(["search", "test query", "--max", "5"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert set(output) == {"command", "query", "returned", "data"}
    assert output["command"] == "search"
    assert len(output["data"]) == 1


def test_main_fetch_exits_nonzero_when_every_url_fails(monkeypatch, capsys):
    keenable_search = load_module()

    def fake_request_json(url, **kwargs):
        raise RuntimeError("HTTP 404")

    monkeypatch.setattr(keenable_search, "_request_json", fake_request_json)

    assert keenable_search.main(["fetch", "https://example.com/missing"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["errors"][0]["url"] == "https://example.com/missing"
