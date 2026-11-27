import argparse
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
MODULE_PATH = ROOT / "tools" / "outcrawl_search.py"
SKILLS = (
    ROOT / "skills" / "outcrawl-search" / "SKILL.md",
    ROOT / "skills" / "skills-codex" / "outcrawl-search" / "SKILL.md",
)


@pytest.mark.parametrize("layout", ["global_pointer", "project_link", "explicit", "manifest"])
def test_codex_skill_resolves_helper_in_installed_layouts(tmp_path, layout):
    """Execute the documented shell resolver without touching the real home."""
    skill = (ROOT / "skills/skills-codex/outcrawl-search/SKILL.md").read_text()
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
        (repo / "tools/outcrawl_search.py").write_text(f"print({name!r})\n")
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
        ["bash", "-eu", "-c", block + '\npython3 "$OUTCRAWL_FETCHER"'],
        cwd=project, env=env, capture_output=True, text=True,
    )
    expected = {"global_pointer": "pointer", "project_link": "linked"}.get(layout, layout)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def load_module():
    spec = importlib.util.spec_from_file_location("outcrawl_search", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        # bytes are replayed as-is, to simulate a malformed body
        self._raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def capture_urlopen(monkeypatch, module, *payloads):
    """Patch urlopen to record each request and answer with the next payload."""
    calls = []
    answers = iter(payloads)

    def fake_urlopen(req, timeout=None):
        calls.append((req, timeout))
        answer = next(answers)
        if isinstance(answer, BaseException):
            raise answer
        return FakeResponse(answer)

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    return calls


def http_error(code, payload):
    body = io.BytesIO(json.dumps(payload).encode("utf-8"))
    return urllib.error.HTTPError("https://api.outcrawl.ai/v1/search", code, "error", {}, body)


def test_search_posts_payload_and_normalizes_hits(monkeypatch):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", " test-key ")
    calls = capture_urlopen(
        monkeypatch,
        outcrawl_search,
        {
            "hits": [
                {"url": "https://arxiv.org/abs/2211.17192", "title": "Paper", "snippet": "text", "rank": 1},
                {"url": "https://example.com/b", "title": None, "rank": 2},
                {"title": "no url"},
                "not a dict",
            ],
            "usage": {"credits": "1"},
        },
    )

    result = outcrawl_search.search("speculative decoding", max_results=5, site="arxiv.org")

    req, timeout = calls[0]
    assert req.full_url == "https://api.outcrawl.ai/v1/search"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer test-key"
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("User-agent") == outcrawl_search.USER_AGENT
    assert json.loads(req.data) == {"query": "speculative decoding site:arxiv.org", "limit": 5}
    assert timeout == 60.0
    assert result == {
        "mode": "search",
        "query": "speculative decoding site:arxiv.org",
        "returned": 2,
        "data": [
            {"title": "Paper", "url": "https://arxiv.org/abs/2211.17192", "snippet": "text"},
            {"title": "No Title", "url": "https://example.com/b", "snippet": ""},
        ],
        "usage": {"credits": "1"},
    }


def test_search_without_site_sends_the_query_unchanged(monkeypatch):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    calls = capture_urlopen(monkeypatch, outcrawl_search, {"hits": []})

    result = outcrawl_search.search("q")

    assert json.loads(calls[0][0].data) == {"query": "q", "limit": 10}
    assert result["returned"] == 0
    assert "usage" not in result


def test_search_warns_when_response_has_no_hits_list(monkeypatch, capsys):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    capture_urlopen(monkeypatch, outcrawl_search, {"unexpected": True})

    assert outcrawl_search.search("q")["returned"] == 0
    assert "no hits list" in capsys.readouterr().err


def test_missing_key_is_an_account_error_before_any_request(monkeypatch):
    outcrawl_search = load_module()
    monkeypatch.delenv("OUTCRAWL_API_KEY", raising=False)
    calls = capture_urlopen(monkeypatch, outcrawl_search)

    with pytest.raises(outcrawl_search.AccountError, match="OUTCRAWL_API_KEY is not set"):
        outcrawl_search.search("q")
    assert calls == []


@pytest.mark.parametrize(
    ("code", "error_type", "needle"),
    [
        (401, "AccountError", "Invalid OUTCRAWL_API_KEY"),
        (402, "AccountError", "credits exhausted"),
        (429, "AccountError", "rate limit"),
        (500, "RuntimeError", r"\(HTTP 500\): boom"),
    ],
)
def test_http_errors_become_actionable_messages(monkeypatch, code, error_type, needle):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    capture_urlopen(monkeypatch, outcrawl_search, http_error(code, {"message": "boom"}))

    expected = getattr(outcrawl_search, error_type, RuntimeError)
    with pytest.raises(expected, match=needle) as excinfo:
        outcrawl_search.search("q")
    assert isinstance(excinfo.value, outcrawl_search.AccountError) == (error_type == "AccountError")


def test_read_timeout_becomes_runtime_error(monkeypatch):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    capture_urlopen(monkeypatch, outcrawl_search, TimeoutError("read timed out"))

    with pytest.raises(RuntimeError, match="Could not reach the Outcrawl API"):
        outcrawl_search.search("q")


def test_non_json_response_is_an_error(monkeypatch):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    capture_urlopen(monkeypatch, outcrawl_search, b"<html>")

    with pytest.raises(RuntimeError, match="non-JSON"):
        outcrawl_search.search("q")


def test_scrape_returns_markdown_and_truncates(monkeypatch):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    calls = capture_urlopen(
        monkeypatch,
        outcrawl_search,
        {
            "url": "https://example.com/a",
            "statusCode": 200,
            "markdown": "# A\n\n" + "x" * 50,
            "metadata": {"title": "Page A"},
        },
    )

    result = outcrawl_search.scrape(["https://example.com/a"], max_chars=10)

    req, timeout = calls[0]
    assert req.full_url == "https://api.outcrawl.ai/v1/scrape"
    assert json.loads(req.data) == {
        "url": "https://example.com/a",
        "formats": ["markdown"],
        "onlyMainContent": True,
    }
    assert timeout == 90.0
    assert result == {
        "mode": "scrape",
        "returned": 1,
        "data": [
            {
                "url": "https://example.com/a",
                "title": "Page A",
                "markdown": "# A\n\nxxxxx",
                "markdown_truncated": True,
            }
        ],
    }


def test_scrape_full_page_sends_only_main_content_false(monkeypatch):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    calls = capture_urlopen(monkeypatch, outcrawl_search, {"markdown": "ok"})

    outcrawl_search.scrape(["https://example.com"], main_content_only=False)

    assert json.loads(calls[0][0].data)["onlyMainContent"] is False


def test_scrape_reports_per_url_errors_and_keeps_going(monkeypatch):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    capture_urlopen(
        monkeypatch,
        outcrawl_search,
        {"url": "https://example.com/missing", "statusCode": 404},
        http_error(500, {"message": "render failed"}),
        {"url": "https://example.com/good", "markdown": "ok", "metadata": {}},
    )

    result = outcrawl_search.scrape(
        ["https://example.com/missing", "https://example.com/broken", "https://example.com/good"]
    )

    assert result["returned"] == 1
    assert result["data"] == [
        {"url": "https://example.com/missing", "error": "Page returned HTTP 404"},
        {"url": "https://example.com/broken", "error": "Outcrawl API error (HTTP 500): render failed"},
        {"url": "https://example.com/good", "title": "No Title", "markdown": "ok"},
    ]


@pytest.mark.parametrize("code", [401, 402, 429])
def test_scrape_stops_batch_on_account_errors(monkeypatch, code):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    calls = capture_urlopen(monkeypatch, outcrawl_search, http_error(code, {}))

    result = outcrawl_search.scrape(["https://example.com/1", "https://example.com/2"])

    assert len(calls) == 1
    assert result["returned"] == 0
    assert result["data"][1] == {
        "url": "https://example.com/2",
        "error": "Skipped: an earlier request failed with an account error.",
    }


def test_main_without_key_exits_1_with_message(monkeypatch, capsys):
    outcrawl_search = load_module()
    monkeypatch.delenv("OUTCRAWL_API_KEY", raising=False)

    assert outcrawl_search.main(["search", "q"]) == 1
    assert "OUTCRAWL_API_KEY is not set" in capsys.readouterr().err


def test_main_prints_json_and_exits_nonzero_when_all_scrapes_fail(monkeypatch, capsys):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    capture_urlopen(monkeypatch, outcrawl_search, {"statusCode": 500})

    assert outcrawl_search.main(["scrape", "https://example.com"]) == 1
    assert json.loads(capsys.readouterr().out)["returned"] == 0


def test_main_search_error_goes_to_stderr(monkeypatch, capsys):
    outcrawl_search = load_module()
    monkeypatch.setenv("OUTCRAWL_API_KEY", "k")
    capture_urlopen(monkeypatch, outcrawl_search, http_error(429, {}))

    assert outcrawl_search.main(["search", "q"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "rate limit" in captured.err


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "q", "--max", "0"],
        ["search", "q", "--max", "21"],
        ["search", "q", "--site", " "],
        ["scrape", "--max-chars", "0", "https://example.com"],
    ],
)
def test_parser_rejects_out_of_range_values(argv):
    outcrawl_search = load_module()
    with pytest.raises(SystemExit) as excinfo:
        outcrawl_search._build_parser().parse_args(argv)
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com", "https://example.com/$(id)", "https://example.com/a b", "https://x/`y`"],
)
def test_parser_rejects_unsafe_scrape_urls(url):
    outcrawl_search = load_module()
    with pytest.raises(SystemExit):
        outcrawl_search._build_parser().parse_args(["scrape", url])


def test_parser_normalizes_site_and_accepts_query_after_double_dash():
    outcrawl_search = load_module()
    args = outcrawl_search._build_parser().parse_args(
        ["search", "--site", "https://ArXiv.org/abs", "--", "-leading dash"]
    )
    assert args.site == "arxiv.org"
    assert args.query == "-leading dash"


def test_parser_defaults_match_skill_constants():
    outcrawl_search = load_module()
    parser = outcrawl_search._build_parser()
    search_args = parser.parse_args(["search", "q"])
    scrape_args = parser.parse_args(["scrape", "https://example.com"])
    for skill in SKILLS:
        text = skill.read_text()
        assert f"**MAX_RESULTS = {search_args.max}**" in text
        assert f"**MAX_CHARS = {scrape_args.max_chars}**" in text


def test_every_flag_named_in_the_skills_is_accepted_by_the_parser():
    outcrawl_search = load_module()
    parser = outcrawl_search._build_parser()
    subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    help_text = "".join(sub.format_help() for sub in subparsers.choices.values())
    for skill in SKILLS:
        text = skill.read_text()
        helper_lines = [line for line in text.splitlines() if '"$OUTCRAWL_FETCHER"' in line or line.startswith("  --")]
        flags = set(re.findall(r"`(--[a-z][a-z-]+)`", text))
        flags |= set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", "\n".join(helper_lines)))
        assert {"--max", "--site", "--max-chars", "--full-page"} <= flags
        for flag in flags:
            assert flag in help_text, f"{skill}: {flag}"


def test_skill_files_reference_helper_and_untrusted_content_rule():
    for skill in SKILLS:
        text = skill.read_text()
        assert "outcrawl_search.py" in text
        assert "untrusted" in text
        assert "Evidence boundary:" in text
