"""The Claude Code plugin packaging (.claude-plugin/ + commands/setup.md).

Pins what a plugin install depends on: the marketplace exposes one plugin
named `aris` rooted at the repo, the manifest carries no pinned version (so
updates follow the source), and /aris:setup registers the codex-exec bridge
from the plugin directory under the server name the skills hardcode.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_marketplace_exposes_aris_at_repo_root():
    m = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert m["name"] == "aris"
    (plugin,) = m["plugins"]
    assert plugin["name"] == "aris" and plugin["source"] == "./"


def test_plugin_manifest_has_no_pinned_version():
    p = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert p["name"] == "aris"
    assert "version" not in p, "a pinned version would freeze plugin users until it is bumped"


def test_setup_registers_the_bridge_under_the_hardcoded_server_name():
    text = (REPO / "commands" / "setup.md").read_text()
    assert 'claude mcp add codex -s user -- python3 "${CLAUDE_PLUGIN_ROOT}/mcp-servers/codex-exec/server.py"' in text
    assert "~/.aris/repo" in text
    assert (REPO / "mcp-servers" / "codex-exec" / "server.py").is_file()


def test_codex_manifest_points_at_the_codex_mirror():
    # Codex CLI prefers .codex-plugin/plugin.json and must get the spawn_agent
    # mirror, never the mainline skills that call mcp__codex__codex
    p = json.loads((REPO / ".codex-plugin" / "plugin.json").read_text())
    assert p["name"] == "aris"
    assert p["skills"] == "./skills/skills-codex/"
    assert "version" not in p
