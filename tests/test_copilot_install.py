"""Tests for install_aris_copilot.sh and smart_update_copilot.sh."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "tools" / "install_aris_copilot.sh"
UPDATE_SCRIPT = REPO_ROOT / "tools" / "smart_update_copilot.sh"
TRACE_SCRIPT = REPO_ROOT / "tools" / "save_trace.sh"


def run(
    cmd: list[str], *, cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        text=True,
        capture_output=True,
        check=check,
        env=env,
    )


def make_skill(path: Path, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(body)


def make_minimal_aris_repo(root: Path) -> Path:
    """Create a minimal ARIS repo structure with mainline skills."""
    repo = root / "aris"
    # Mainline skills (what Copilot CLI uses directly)
    make_skill(repo / "skills" / "alpha", "---\nname: alpha\ndescription: Alpha skill\nallowed-tools: Read\n---\n# alpha\n")
    make_skill(repo / "skills" / "beta", "---\nname: beta\ndescription: Beta skill\nallowed-tools: Read, Write\n---\n# beta\n")
    make_skill(repo / "skills" / "gamma", "---\nname: gamma\ndescription: Gamma skill\n---\n# gamma\n")
    # shared-references (support directory)
    (repo / "skills" / "shared-references").mkdir(parents=True, exist_ok=True)
    (repo / "skills" / "shared-references" / "reviewer-routing.md").write_text("routing\n")
    (repo / "skills" / "shared-references" / "effort-contract.md").write_text("effort\n")
    # Codex-specific packages (should be EXCLUDED from Copilot install)
    make_skill(repo / "skills" / "skills-codex" / "alpha", "# codex alpha\n")
    make_skill(repo / "skills" / "skills-codex-claude-review" / "alpha", "# codex-claude alpha\n")
    # AGENT_GUIDE.md for repo discovery
    (repo / "AGENT_GUIDE.md").write_text("# Agent Guide\n")
    return repo


def test_install_copilot_dry_run_has_no_project_writes(tmp_path: Path) -> None:
    repo = make_minimal_aris_repo(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    dry_run = run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--dry-run",
        ]
    )

    assert "(dry-run) no changes made" in dry_run.stdout
    assert not (project / ".aris").exists()
    assert not (project / ".github").exists()
    assert not (project / "AGENTS.md").exists()


def test_install_copilot_avoids_bash4_associative_arrays() -> None:
    text = INSTALL_SCRIPT.read_text()
    assert "declare -A" not in text


def test_install_copilot_creates_github_skills_symlinks(tmp_path: Path) -> None:
    """Basic install creates .github/skills/<name> symlinks to mainline skills."""
    repo = make_minimal_aris_repo(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ]
    )

    # Verify manifest
    manifest = project / ".aris" / "installed-skills-copilot.txt"
    assert manifest.exists()
    manifest_text = manifest.read_text()
    assert "repo_root" in manifest_text
    assert "installer\tinstall_aris_copilot.sh" in manifest_text

    # Verify AGENTS.md
    assert (project / "AGENTS.md").exists()
    agents_text = (project / "AGENTS.md").read_text()
    assert "ARIS Copilot CLI Skill Scope" in agents_text
    assert f"ARIS repo root: `{repo}`" in agents_text

    # Verify skill symlinks point to mainline skills/
    assert (project / ".github" / "skills" / "alpha").is_symlink()
    assert (project / ".github" / "skills" / "beta").is_symlink()
    assert (project / ".github" / "skills" / "gamma").is_symlink()
    assert (project / ".github" / "skills" / "alpha").resolve() == (repo / "skills" / "alpha")
    assert (project / ".github" / "skills" / "beta").resolve() == (repo / "skills" / "beta")

    # Verify shared-references is included
    assert (project / ".github" / "skills" / "shared-references").is_symlink()
    assert (project / ".github" / "skills" / "shared-references").resolve() == (repo / "skills" / "shared-references")

    # Verify Codex-specific packages are NOT installed
    assert not (project / ".github" / "skills" / "skills-codex").exists()
    assert not (project / ".github" / "skills" / "skills-codex-claude-review").exists()


def test_install_copilot_excludes_codex_packages(tmp_path: Path) -> None:
    """Codex-specific skill mirrors must not appear in Copilot install."""
    repo = make_minimal_aris_repo(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ]
    )

    skills_dir = project / ".github" / "skills"
    installed_names = [p.name for p in skills_dir.iterdir()]
    for codex_name in ["skills-codex", "skills-codex-claude-review", "skills-codex-gemini-review"]:
        assert codex_name not in installed_names


def test_install_copilot_reconcile_adds_and_removes(tmp_path: Path) -> None:
    """Reconcile picks up new skills and removes deleted ones."""
    repo = make_minimal_aris_repo(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    # Initial install
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ]
    )
    assert (project / ".github" / "skills" / "alpha").is_symlink()
    assert (project / ".github" / "skills" / "gamma").is_symlink()

    # Simulate upstream change: remove alpha, add delta
    (repo / "skills" / "alpha" / "SKILL.md").unlink()
    (repo / "skills" / "alpha").rmdir()
    make_skill(repo / "skills" / "delta", "---\nname: delta\ndescription: Delta\n---\n# delta\n")

    # Reconcile. #366 selective install: a plain --quiet reconcile no longer
    # silently adopts new upstream skills (that would defeat the point of the
    # new-skill confirmation gate) -- it must be requested via --add-new.
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--reconcile",
            "--add-new",
            "--quiet",
        ]
    )

    assert not (project / ".github" / "skills" / "alpha").exists()
    assert (project / ".github" / "skills" / "delta").is_symlink()
    assert (project / ".github" / "skills" / "delta").resolve() == (repo / "skills" / "delta")
    assert (project / ".github" / "skills" / "beta").is_symlink()


def test_install_copilot_uninstall_removes_managed_only(tmp_path: Path) -> None:
    """Uninstall removes only managed entries, preserves user-owned skills."""
    repo = make_minimal_aris_repo(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ]
    )

    # Add a user-owned skill
    (project / ".github" / "skills" / "my-custom-skill").mkdir(parents=True)
    (project / ".github" / "skills" / "my-custom-skill" / "SKILL.md").write_text("# mine\n")

    # Uninstall
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--uninstall",
            "--quiet",
        ]
    )

    # User skill preserved
    assert (project / ".github" / "skills" / "my-custom-skill").exists()
    # Managed skills removed
    assert not (project / ".github" / "skills" / "alpha").exists()
    assert not (project / ".github" / "skills" / "beta").exists()
    # Manifest archived
    assert (project / ".aris" / "installed-skills-copilot.txt.prev").exists()
    assert not (project / ".aris" / "installed-skills-copilot.txt").exists()
    # AGENTS.md block removed
    assert "ARIS Copilot CLI Skill Scope" not in (project / "AGENTS.md").read_text()


def test_install_copilot_uninstall_uses_manifest_repo_root(tmp_path: Path) -> None:
    """Uninstall uses repo_root from manifest, not --aris-repo flag."""
    original_repo = make_minimal_aris_repo(tmp_path / "original")
    other_repo = make_minimal_aris_repo(tmp_path / "other")
    project = tmp_path / "project"
    project.mkdir()

    # Install with original repo
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(original_repo),
            "--quiet",
        ]
    )

    alpha_link = project / ".github" / "skills" / "alpha"
    assert alpha_link.is_symlink()
    assert alpha_link.resolve() == original_repo / "skills" / "alpha"

    # Uninstall with a DIFFERENT --aris-repo (should still work via manifest repo_root)
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(other_repo),
            "--uninstall",
            "--quiet",
        ]
    )

    assert not alpha_link.exists()
    assert not (project / ".github" / "skills" / "beta").exists()


def test_install_copilot_conflict_on_real_path(tmp_path: Path) -> None:
    """Installer aborts when a real (non-symlink) path conflicts."""
    repo = make_minimal_aris_repo(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    # Pre-create a real directory that conflicts
    (project / ".github" / "skills" / "alpha").mkdir(parents=True)
    (project / ".github" / "skills" / "alpha" / "SKILL.md").write_text("# local\n")

    result = run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ],
        check=False,
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "CONFLICT" in combined or "conflict" in combined.lower()


def test_install_copilot_replace_link_resolves_conflict(tmp_path: Path) -> None:
    """--replace-link resolves a symlink conflict."""
    repo = make_minimal_aris_repo(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    # Pre-create a conflicting symlink
    (project / ".github" / "skills").mkdir(parents=True)
    (project / ".github" / "skills" / "alpha").symlink_to("/some/other/path")

    result = run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--replace-link",
            "alpha",
            "--quiet",
        ],
    )

    assert result.returncode == 0
    assert (project / ".github" / "skills" / "alpha").resolve() == (repo / "skills" / "alpha")


def test_install_copilot_reconcile_already_deleted_stale_link(tmp_path: Path) -> None:
    """Reconcile handles gracefully when a to-be-removed link is already gone."""
    repo = make_minimal_aris_repo(tmp_path)
    project = tmp_path / "project"
    project.mkdir()

    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ]
    )

    # Manually delete a managed link, then remove from upstream
    (project / ".github" / "skills" / "alpha").unlink()
    (repo / "skills" / "alpha" / "SKILL.md").unlink()
    (repo / "skills" / "alpha").rmdir()

    # Reconcile should succeed without error
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--reconcile",
            "--quiet",
        ]
    )

    manifest = (project / ".aris" / "installed-skills-copilot.txt").read_text()
    assert "\talpha\t" not in manifest


def test_smart_update_copilot_copy_install(tmp_path: Path) -> None:
    """smart_update_copilot.sh updates a copy-based install and records baselines."""
    upstream = tmp_path / "upstream"
    make_skill(upstream / "alpha", "---\nname: alpha\n---\n# alpha\n")
    make_skill(upstream / "beta", "---\nname: beta\n---\n# beta\n")
    make_skill(upstream / "gamma", "---\nname: gamma\n---\n# gamma\n")
    (upstream / "shared-references").mkdir(parents=True, exist_ok=True)
    (upstream / "shared-references" / "reviewer-routing.md").write_text("routing\n")

    local = tmp_path / "local"
    # alpha already exists locally with SAME content (up-to-date scenario is skipped)
    # Only test new installs here
    make_skill(local / "local-only", "---\nname: local-only\n---\n# keep-me\n")

    # Dry run first
    dry_run = run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--upstream",
            str(upstream),
            "--local",
            str(local),
        ]
    )
    assert dry_run.returncode == 0
    assert "Dry run complete. Use --apply to apply these changes." in dry_run.stdout

    # Apply
    result = run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--upstream",
            str(upstream),
            "--local",
            str(local),
            "--apply",
            "--add-new",  # NEW skills now require confirmation/--add-new (#366-style policy)
        ]
    )

    # New skills added
    assert (local / "alpha" / "SKILL.md").exists()
    assert (local / "beta" / "SKILL.md").exists()
    assert (local / "gamma" / "SKILL.md").exists()
    # Local-only skill preserved
    assert (local / "local-only" / "SKILL.md").exists()
    # Baseline file created with hashes for newly installed skills
    baseline_file = local / ".aris-copilot-baselines.sha256"
    assert baseline_file.exists()
    baseline_text = baseline_file.read_text()
    assert "alpha" in baseline_text
    assert "beta" in baseline_text
    assert "gamma" in baseline_text


def test_smart_update_copilot_hash_based_customization(tmp_path: Path) -> None:
    """Hash-based detection correctly identifies user-modified skills."""
    upstream_v1 = tmp_path / "upstream"
    make_skill(upstream_v1 / "alpha", "---\nname: alpha\n---\n# alpha-v1\n")
    make_skill(upstream_v1 / "beta", "---\nname: beta\n---\n# beta-v1\n")

    local = tmp_path / "local"
    local.mkdir()

    # First install: copy upstream v1 and record baselines
    run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--upstream",
            str(upstream_v1),
            "--local",
            str(local),
            "--apply",
            "--add-new",  # NEW skills now require confirmation/--add-new (#366-style policy)
        ]
    )
    assert (local / "alpha" / "SKILL.md").read_text() == "---\nname: alpha\n---\n# alpha-v1\n"

    # User customizes alpha locally
    (local / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n# alpha-v1 CUSTOMIZED\n")

    # Upstream releases v2
    (upstream_v1 / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n# alpha-v2\n")
    (upstream_v1 / "beta" / "SKILL.md").write_text("---\nname: beta\n---\n# beta-v2\n")

    # Run update: alpha should be detected as customized and skipped
    result = run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--upstream",
            str(upstream_v1),
            "--local",
            str(local),
            "--apply",
        ]
    )

    assert "Customized" in result.stdout
    assert "alpha" in result.stdout
    # alpha should NOT be updated (customized)
    assert "CUSTOMIZED" in (local / "alpha" / "SKILL.md").read_text()
    # beta should be updated (not customized)
    assert "beta-v2" in (local / "beta" / "SKILL.md").read_text()


def test_smart_update_copilot_refuses_symlink_managed(tmp_path: Path) -> None:
    """smart_update refuses to update a project managed by install_aris_copilot.sh."""
    managed_project = tmp_path / "managed"
    managed_project.mkdir()
    (managed_project / ".github" / "skills").mkdir(parents=True)
    # Create manifest to signal managed install
    (managed_project / ".aris").mkdir(parents=True)
    (managed_project / ".aris" / "installed-skills-copilot.txt").write_text(
        "version\t1\nrepo_root\t/tmp/aris\n"
    )

    refused = run(
        ["bash", str(UPDATE_SCRIPT), "--project", str(managed_project)],
        check=False,
    )

    assert refused.returncode != 0
    assert "install_aris_copilot.sh" in refused.stderr


# --- Agent profile deployment tests ---

def test_install_copilot_deploys_agents(tmp_path: Path) -> None:
    """install_aris_copilot.sh deploys .github/agents/ symlinks."""
    repo = make_minimal_aris_repo(tmp_path)
    # Ensure agent profiles exist in upstream
    repo_agents = repo / ".github" / "agents"
    repo_agents.mkdir(parents=True, exist_ok=True)
    (repo_agents / "aris-reviewer-openai.agent.md").write_text("---\nmodel: gpt-5.4\n---\n# openai\n")
    (repo_agents / "aris-reviewer-claude.agent.md").write_text("---\nmodel: claude-sonnet-4.5\n---\n# claude\n")

    project = tmp_path / "project"
    project.mkdir()

    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ]
    )

    agents_dir = project / ".github" / "agents"
    assert agents_dir.exists()
    assert (agents_dir / "aris-reviewer-openai.agent.md").is_symlink()
    assert (agents_dir / "aris-reviewer-claude.agent.md").is_symlink()
    assert (agents_dir / "aris-reviewer-openai.agent.md").resolve() == (repo_agents / "aris-reviewer-openai.agent.md")
    assert (agents_dir / "aris-reviewer-claude.agent.md").resolve() == (repo_agents / "aris-reviewer-claude.agent.md")


def test_reviewer_profiles_use_supported_frontmatter_and_explicit_models() -> None:
    for name, model in (
        ("aris-reviewer-openai.agent.md", "gpt-5.4"),
        ("aris-reviewer-claude.agent.md", "claude-sonnet-4.5"),
    ):
        text = (REPO_ROOT / ".github" / "agents" / name).read_text()
        assert f"model: {model}" in text
        assert "model_family:" not in text
        assert "tools: read" in text


def test_install_copilot_skips_symlinked_upstream_agents_directory(tmp_path: Path) -> None:
    repo = make_minimal_aris_repo(tmp_path)
    external = tmp_path / "external-agents"
    external.mkdir()
    (external / "aris-reviewer-openai.agent.md").write_text("---\nmodel: gpt-5.4\n---\n")
    (repo / ".github").mkdir()
    (repo / ".github" / "agents").symlink_to(external, target_is_directory=True)
    project = tmp_path / "project"
    project.mkdir()

    result = run(
        ["bash", str(INSTALL_SCRIPT), str(project), "--aris-repo", str(repo), "--quiet"],
        check=False,
    )

    assert result.returncode == 0
    assert "skipping symlinked upstream agents directory" in result.stderr
    assert not (project / ".github" / "agents" / "aris-reviewer-openai.agent.md").exists()


def test_smart_update_copilot_deploys_agents(tmp_path: Path) -> None:
    """smart_update_copilot.sh deploys .github/agents/ in copy-mode."""
    upstream = tmp_path / "upstream"
    make_skill(upstream / "alpha", "---\nname: alpha\n---\n# alpha\n")
    # Agent profile with a unique name so we can assert it came from this upstream
    upstream_agents = upstream.parent / ".github" / "agents"
    upstream_agents.mkdir(parents=True, exist_ok=True)
    agent_content = "---\nmodel: gpt-5.4\n---\n# openai custom-upstream-258\n"
    (upstream_agents / "aris-reviewer-openai.agent.md").write_text(agent_content)

    local = tmp_path / "local"
    local.mkdir()

    result = run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--upstream",
            str(upstream),
            "--local",
            str(local),
            "--apply",
        ]
    )
    assert result.returncode == 0

    # resolve_local_agents() with --local <path> resolves to <path>/../agents
    agents_dir = local.parent / "agents"
    deployed_agent = agents_dir / "aris-reviewer-openai.agent.md"
    assert deployed_agent.exists(), f"Agent not deployed to {deployed_agent}"
    assert deployed_agent.read_text() == agent_content, (
        f"Deployed agent content does not match custom upstream"
    )


def _make_copy_update_with_agent(tmp_path: Path) -> tuple[Path, Path, str]:
    upstream = tmp_path / "upstream"
    make_skill(upstream / "alpha", "---\nname: alpha\n---\n# alpha\n")
    upstream_agents = upstream.parent / ".github" / "agents"
    upstream_agents.mkdir(parents=True, exist_ok=True)
    content = "---\nmodel: gpt-5.4\n---\n# guarded-agent\n"
    (upstream_agents / "aris-reviewer-openai.agent.md").write_text(content)
    local = tmp_path / "local"
    local.mkdir()
    return upstream, local, content


def test_smart_update_refuses_existing_agent_symlink(tmp_path: Path) -> None:
    """An agent file symlink must never redirect an update outside the target."""
    upstream, local, _ = _make_copy_update_with_agent(tmp_path)
    agents = local.parent / "agents"
    agents.mkdir()
    external = tmp_path / "external.agent.md"
    external.write_text("do-not-touch\n")
    link = agents / "aris-reviewer-openai.agent.md"
    link.symlink_to(external)

    result = run(
        ["bash", str(UPDATE_SCRIPT), "--upstream", str(upstream), "--local", str(local), "--apply"],
        check=False,
    )

    assert result.returncode != 0
    assert "refusing symlinked agent destination" in result.stderr
    assert link.is_symlink()
    assert external.read_text() == "do-not-touch\n"


def test_smart_update_refuses_broken_agent_symlink(tmp_path: Path) -> None:
    """A broken destination symlink must not be followed or repaired by copying."""
    upstream, local, _ = _make_copy_update_with_agent(tmp_path)
    agents = local.parent / "agents"
    agents.mkdir()
    external = tmp_path / "missing-external.agent.md"
    link = agents / "aris-reviewer-openai.agent.md"
    link.symlink_to(external)

    result = run(
        ["bash", str(UPDATE_SCRIPT), "--upstream", str(upstream), "--local", str(local), "--apply"],
        check=False,
    )

    assert result.returncode != 0
    assert "refusing symlinked agent destination" in result.stderr
    assert link.is_symlink()
    assert not external.exists()


def test_smart_update_refuses_symlinked_agents_directory(tmp_path: Path) -> None:
    """A symlinked agents directory must not redirect profile deployment."""
    upstream, local, _ = _make_copy_update_with_agent(tmp_path)
    external_dir = tmp_path / "external-agents"
    external_dir.mkdir()
    (local.parent / "agents").symlink_to(external_dir, target_is_directory=True)

    result = run(
        ["bash", str(UPDATE_SCRIPT), "--upstream", str(upstream), "--local", str(local), "--apply"],
        check=False,
    )

    assert result.returncode != 0
    assert "refusing symlinked agent destination path" in result.stderr
    assert not (external_dir / "aris-reviewer-openai.agent.md").exists()


def test_smart_update_refuses_symlinked_upstream_agents_directory(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    make_skill(upstream / "alpha", "---\nname: alpha\n---\n# alpha\n")
    external = tmp_path / "external-upstream-agents"
    external.mkdir()
    (external / "aris-reviewer-openai.agent.md").write_text("---\nmodel: gpt-5.4\n---\n")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "agents").symlink_to(external, target_is_directory=True)
    local = tmp_path / "local"
    local.mkdir()

    result = run(
        ["bash", str(UPDATE_SCRIPT), "--upstream", str(upstream), "--local", str(local), "--apply"],
        check=False,
    )

    assert result.returncode != 0
    assert "refusing symlinked upstream agents directory" in result.stderr
    assert not (local.parent / "agents").exists()


def test_install_copilot_reconcile_agents(tmp_path: Path) -> None:
    """Reconcile picks up new agents and removes deleted ones."""
    repo = make_minimal_aris_repo(tmp_path)
    repo_agents = repo / ".github" / "agents"
    repo_agents.mkdir(parents=True, exist_ok=True)
    (repo_agents / "aris-reviewer-openai.agent.md").write_text("---\nmodel: gpt-5.4\n---\n# openai\n")
    (repo_agents / "aris-reviewer-claude.agent.md").write_text("---\nmodel: claude-sonnet-4.5\n---\n# claude\n")

    project = tmp_path / "project"
    project.mkdir()

    # Initial install
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ]
    )

    assert (project / ".github" / "agents" / "aris-reviewer-openai.agent.md").is_symlink()
    assert (project / ".github" / "agents" / "aris-reviewer-claude.agent.md").is_symlink()

    # Remove one agent, add a new one
    (repo_agents / "aris-reviewer-claude.agent.md").unlink()
    (repo_agents / "aris-reviewer-gemini.agent.md").write_text("---\nmodel: gemini-2.5-pro\n---\n# gemini\n")

    # Reconcile
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--reconcile",
            "--quiet",
        ]
    )

    # Removed agent should be gone
    assert not (project / ".github" / "agents" / "aris-reviewer-claude.agent.md").exists()
    # New agent should exist
    assert (project / ".github" / "agents" / "aris-reviewer-gemini.agent.md").is_symlink()
    # Existing agent should remain
    assert (project / ".github" / "agents" / "aris-reviewer-openai.agent.md").is_symlink()


def test_install_copilot_uninstall_cleans_agents(tmp_path: Path) -> None:
    """Uninstall removes managed agent symlinks."""
    repo = make_minimal_aris_repo(tmp_path)
    repo_agents = repo / ".github" / "agents"
    repo_agents.mkdir(parents=True, exist_ok=True)
    (repo_agents / "aris-reviewer-openai.agent.md").write_text("---\nmodel: gpt-5.4\n---\n# openai\n")

    project = tmp_path / "project"
    project.mkdir()

    # Install
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--quiet",
        ]
    )
    assert (project / ".github" / "agents" / "aris-reviewer-openai.agent.md").is_symlink()

    # Uninstall
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--uninstall",
            "--quiet",
        ]
    )

    assert not (project / ".github" / "agents" / "aris-reviewer-openai.agent.md").exists()


# --- Routing fail-closed tests ---

def test_routing_fail_closed_missing_executor_model(tmp_path: Path) -> None:
    """Explicit compatibility drive mode still requires its declared executor model."""
    # Verify the auto-review-loop SKILL.md contains the fail-closed language
    skill_path = REPO_ROOT / "skills" / "auto-review-loop" / "SKILL.md"
    skill_text = skill_path.read_text()

    assert "REVIEW_UNAVAILABLE" in skill_text
    assert "--executor-model" in skill_text
    # Fail-closed: missing executor-model blocks only explicit compatibility mode.
    assert "missing" in skill_text.lower() or "REVIEW_UNAVAILABLE" in skill_text


def test_routing_fail_closed_unknown_executor_family(tmp_path: Path) -> None:
    """Routing fails closed when executor_family is unknown."""
    skill_path = REPO_ROOT / "skills" / "auto-review-loop" / "SKILL.md"
    skill_text = skill_path.read_text()

    assert "executor_family" in skill_text
    assert "unknown" in skill_text


def test_copilot_prompt_templates_keep_untrusted_text_out_of_heredocs() -> None:
    """Memory, rebuttal, and round inputs are concatenated as data, not shell source."""
    skill_text = (REPO_ROOT / "skills" / "auto-review-loop" / "SKILL.md").read_text()
    routing_text = (REPO_ROOT / "skills" / "shared-references" / "reviewer-routing.md").read_text()

    for text in (skill_text, routing_text):
        assert "PROMPT_EOF" not in text
        assert 'reviewer_prompt_$$' not in text
        assert 'PROMPTFILE="$(mktemp)" || {' in text
        assert '--model "$REVIEWER_MODEL"' in text
        assert "--effort xhigh" in text
        assert "--allow-tool=read" in text
        assert 'ROUND_INPUT_FILE="review-stage/CURRENT_REVIEW_INPUTS.md"' in text
        assert 'cat -- "$ROUND_INPUT_FILE"' in text
        assert 'CHANGED_PATHS="<newline-delimited changed paths>"' not in text
        assert 'DIFF_PATH="<diff artifact path' not in text
        assert 'RESULT_PATHS="<newline-delimited result paths>"' not in text
        assert "# ARIS_ROUND2_COPILOT_BEGIN" in text
        assert "# ARIS_ROUND2_COPILOT_END" in text
    assert 'cat -- "$MEMORY_FILE"' in skill_text
    assert 'cat -- "$REBUTTAL_FILE"' in skill_text
    assert 'cat -- "$MEMORY_FILE"' in routing_text
    for text in (skill_text, routing_text):
        assert 'MEMORY_FILE="review-stage/REVIEWER_MEMORY.md"' in text
        assert 'MEMORY_FILE="REVIEWER_MEMORY.md"' not in text


def test_copilot_round2_templates_do_not_execute_malicious_path_data(tmp_path: Path) -> None:
    """Repository-controlled path bytes stay data throughout both documented shell templates."""
    documents = (
        REPO_ROOT / "skills" / "auto-review-loop" / "SKILL.md",
        REPO_ROOT / "skills" / "shared-references" / "reviewer-routing.md",
    )

    for index, document in enumerate(documents):
        text = document.read_text()
        shell = text.split("# ARIS_ROUND2_COPILOT_BEGIN", 1)[1].split(
            "# ARIS_ROUND2_COPILOT_END", 1
        )[0]

        case_dir = tmp_path / f"case-{index}"
        review_dir = case_dir / "review-stage"
        bin_dir = case_dir / "bin"
        review_dir.mkdir(parents=True)
        bin_dir.mkdir()

        marker = case_dir / "shell-injection-ran"
        malicious_inputs = (
            "Changed files (verbatim):\n"
            f'evil"; touch "{marker}"; #\n'
            f'$(touch "{marker}")\n'
            f'`touch "{marker}"`\n'
        )
        (review_dir / "REVIEWER_MEMORY.md").write_text("reviewer memory\n")
        (review_dir / "CURRENT_REVIEW_INPUTS.md").write_text(malicious_inputs)

        capture_file = case_dir / "captured-prompt.md"
        copilot = bin_dir / "copilot"
        copilot.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "while (($#)); do\n"
            "  if [[ \"$1\" == \"--prompt\" ]]; then\n"
            "    shift\n"
            "    printf '%s' \"$1\" > \"$CAPTURE_FILE\"\n"
            "    exit 0\n"
            "  fi\n"
            "  shift\n"
            "done\n"
            "exit 64\n"
        )
        copilot.chmod(0o755)

        env = os.environ.copy()
        env.update(
            {
                "CAPTURE_FILE": str(capture_file),
                "PATH": f"{bin_dir}:{env['PATH']}",
                "REVIEWER_MODEL": "gpt-5.4",
                "REVIEWER_PROFILE": "aris-reviewer-openai",
            }
        )
        run(["bash", "-eu", "-o", "pipefail", "-c", shell], cwd=case_dir, env=env)

        assert not marker.exists()
        assert malicious_inputs in capture_file.read_text()


def test_stop_gate_uses_snapshotted_state_and_executable_transition_table() -> None:
    skill_text = (REPO_ROOT / "skills" / "auto-review-loop" / "SKILL.md").read_text()

    assert "branch by `round_backend`" in skill_text
    assert "never by the forward-looking `REVIEWER_BACKEND`" in skill_text
    assert "round_requires_external_acquittal" in skill_text
    assert "tools/review_gate.py" in skill_text
    assert 'GATE_JSON=$(python3 "$REVIEW_GATE" "${GATE_ARGS[@]}")' in skill_text
    assert '--executor-model "${EXECUTOR_MODEL:-}"' in skill_text
    assert 'GATE_ARGS+=(--native-evidence "$NATIVE_EVIDENCE")' in skill_text
    assert "host_event_verified" in skill_text
    assert "both finalizers default to unavailable" in skill_text
    assert "Default Codex compatibility" in skill_text
    assert "do not turn a valid default-Codex positive verdict into `REVIEW_UNAVAILABLE`" in skill_text
    assert 'identity_assurance: caller_declared' in skill_text
    assert 'independence_verified: "unverified"' in skill_text


# --- Legacy-state resume tests ---

def test_legacy_review_state_defaults_to_codex_without_finalizer_obligation(tmp_path: Path) -> None:
    """Legacy state must not inherit Copilot-finalizer semantics."""
    state_dir = tmp_path / "review-stage"
    state_dir.mkdir()
    state_file = state_dir / "REVIEW_STATE.json"

    # Write legacy state (no reviewer_backend field)
    import json
    legacy_state = {
        "round": 2,
        "threadId": "019cd392-test-legacy",
        "status": "in_progress",
        "difficulty": "medium",
        "last_score": 5.0,
        "last_verdict": "not ready",
        "timestamp": "2026-03-13T21:00:00",
    }
    state_file.write_text(json.dumps(legacy_state))

    # Load and check
    loaded = json.loads(state_file.read_text())
    # When reviewer_backend is absent, resume should default to codex
    backend = loaded.get("reviewer_backend", "codex")
    requires_external_acquittal = loaded.get("requires_external_acquittal", False)
    assert backend == "codex", f"Legacy state missing reviewer_backend should default to codex, got: {backend}"
    assert requires_external_acquittal is False


def test_modern_review_state_has_backend_field(tmp_path: Path) -> None:
    """Modern REVIEW_STATE.json includes reviewer_backend field."""
    skill_path = REPO_ROOT / "skills" / "auto-review-loop" / "SKILL.md"
    skill_text = skill_path.read_text()

    assert "reviewer_backend" in skill_text
    assert "reviewer_profile" in skill_text
    assert "requires_external_acquittal" in skill_text
    # Verify copilot-specific fields
    assert "copilot" in skill_text.lower()


# --- Trace backward-compat tests ---

def test_save_trace_supports_new_fields(tmp_path: Path) -> None:
    """save_trace.sh accepts legacy provenance plus native evidence."""
    trace_script = REPO_ROOT / "tools" / "save_trace.sh"
    assert trace_script.exists()

    # Verify the script accepts new flags
    script_text = trace_script.read_text()
    assert "--executor)" in script_text
    assert "--requested-reviewer-model)" in script_text
    assert "--reported-reviewer-model)" in script_text
    assert "--memory-hash)" in script_text
    assert "--native-evidence)" in script_text


def test_save_trace_executor_field_not_hardcoded(tmp_path: Path) -> None:
    """save_trace.sh executor field is dynamic, not hardcoded to 'claude-code'."""
    trace_script = REPO_ROOT / "tools" / "save_trace.sh"
    script_text = trace_script.read_text()

    # The executor field should use a variable, not the literal string "claude-code"
    # in the JSON generation (it can still appear as a default)
    assert '"executor": "claude-code"' not in script_text, \
        "executor field must be dynamic (use variable, not hardcoded string)"
    # Default should be set via variable, e.g. ST_EXECUTOR or EXECUTOR
    assert 'ST_EXECUTOR' in script_text or 'EXECUTOR' in script_text


def _save_trace_request(tmp_path: Path, *extra: str) -> tuple[dict, dict, dict]:
    result = run(
        [
            "bash",
            str(TRACE_SCRIPT),
            "--skill",
            "auto-review-loop",
            "--purpose",
            "round-review",
            "--prompt",
            "review this",
            "--response",
            "ready",
            *extra,
        ],
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    run_dir = next((tmp_path / ".aris" / "traces" / "auto-review-loop").iterdir())
    request_path = next(run_dir.glob("*.request.json"))
    request = json.loads(request_path.read_text())
    # The call meta, not run.meta.json — "*.meta.json" matches both, and which one
    # comes first is directory-iteration order, which is not ours to rely on.
    meta_path = request_path.with_name(request_path.name[: -len(".request.json")] + ".meta.json")
    meta = json.loads(meta_path.read_text())
    run_meta = json.loads((run_dir / "run.meta.json").read_text())
    return request, meta, run_meta


def test_save_trace_copilot_xhigh_is_pinned(tmp_path: Path) -> None:
    request, meta, _ = _save_trace_request(
        tmp_path,
        "--backend", "copilot",
        "--model", "gpt-5.4",
        "--effort", "xhigh",
        "--executor-model", "claude-sonnet-4.5",
        "--requested-reviewer-model", "gpt-5.4",
    )

    assert request["effort"] == "xhigh"
    assert request["effort_unpinned"] is False
    assert meta["effort_unpinned"] is False


def test_save_trace_unpinned_copilot_call_remains_ineligible(tmp_path: Path) -> None:
    request, _, _ = _save_trace_request(
        tmp_path,
        "--backend", "copilot",
        "--model", "gpt-5.4",
        "--effort", "high",
        "--executor-model", "claude-sonnet-4.5",
        "--requested-reviewer-model", "gpt-5.4",
    )

    assert request["effort_unpinned"] is True


def test_save_trace_rejects_spoofed_family_and_independence(tmp_path: Path) -> None:
    """Same-family models stay same-family despite contradictory caller labels."""
    request, meta, run_meta = _save_trace_request(
        tmp_path,
        "--backend", "copilot",
        "--model", "gpt-5.4",
        "--effort", "xhigh",
        "--executor-model", "gpt-5.4",
        "--executor-family", "anthropic",
        "--requested-reviewer-model", "gpt-5.4",
        "--reviewer-family", "google",
        "--independence-verified", "true",
    )

    assert request["executor_family"] == "openai"
    assert request["reviewer_family"] == "openai"
    assert request["independence_verified"] is False
    assert meta["model_family"] == "openai"
    assert meta["independence_verified"] is False
    assert run_meta["executor_family"] == "openai"
    assert run_meta["reviewer_family"] == "openai"


def test_save_trace_records_cross_family_relation_without_claiming_attestation(tmp_path: Path) -> None:
    request, _, _ = _save_trace_request(
        tmp_path,
        "--backend", "copilot",
        "--model", "gpt-5.4",
        "--effort", "xhigh",
        "--executor-model", "claude-sonnet-4.5",
        "--executor-family", "openai",
        "--requested-reviewer-model", "gpt-5.4",
        "--reviewer-family", "anthropic",
        "--independence-verified", "false",
    )

    assert request["executor_family"] == "anthropic"
    assert request["reviewer_family"] == "openai"
    assert request["executor_model_source"] == "caller-declared"
    assert request["reviewer_model_source"] == "requested"
    assert request["family_relation"] == "different"
    assert request["independence_verified"] == "unverified"


def test_save_trace_default_codex_identity_is_advisory(tmp_path: Path) -> None:
    request, meta, run_meta = _save_trace_request(
        tmp_path,
        "--backend", "codex",
        "--model", "gpt-5.6-sol",
        "--effort", "xhigh",
    )

    for artifact in (request, meta, run_meta):
        assert artifact["executor_model"] is None
        assert artifact["executor_model_source"] == "unavailable"
        assert artifact["family_relation"] == "unknown"
        assert artifact["independence_verified"] == "unverified"


def test_save_trace_unknown_model_is_unverified(tmp_path: Path) -> None:
    request, _, _ = _save_trace_request(
        tmp_path,
        "--backend", "copilot",
        "--model", "gpt-5.4",
        "--effort", "xhigh",
        "--executor-model", "mystery-model",
        "--requested-reviewer-model", "gpt-5.4",
        "--executor-family", "anthropic",
        "--independence-verified", "true",
    )

    assert request["executor_family"] == "unknown"
    assert request["reviewer_family"] == "openai"
    assert request["independence_verified"] == "unverified"


def test_save_trace_backend_reported_model_takes_precedence(tmp_path: Path) -> None:
    request, meta, _ = _save_trace_request(
        tmp_path,
        "--backend", "copilot",
        "--model", "gpt-5.4",
        "--effort", "xhigh",
        "--executor-model", "gpt-5.4",
        "--requested-reviewer-model", "gpt-5.4",
        "--reported-reviewer-model", "claude-sonnet-4.5",
    )

    assert request["reviewer_family"] == "anthropic"
    assert meta["model_family"] == "anthropic"
    for artifact in (request, meta):
        assert artifact["reviewer_model_source"] == "backend-reported"
        assert artifact["family_relation"] == "different"
        assert artifact["independence_verified"] == "unverified"


def test_review_tracing_doc_separates_native_from_compatibility_model(tmp_path: Path) -> None:
    """Native records the resolved model; only compatibility mode pins GPT-5.4."""
    doc_path = REPO_ROOT / "skills" / "shared-references" / "review-tracing.md"
    doc_text = doc_path.read_text()

    native_start = doc_text.find("For native Copilot backend")
    compatibility_start = doc_text.find("For compatibility copilot backend")
    assert native_start >= 0
    assert compatibility_start > native_start
    native_section = doc_text[native_start:compatibility_start]
    compatibility_section = doc_text[compatibility_start:compatibility_start + 1800]
    assert '"backend": "copilot-native"' in native_section
    assert '"model": "gpt-5.4"' not in native_section
    assert '"model": "gpt-5.4"' in compatibility_section


def test_reviewer_routing_copilot_scope_consistent(tmp_path: Path) -> None:
    """The no-flag Copilot route is native while compatibility drive stays explicit."""
    doc_path = REPO_ROOT / "skills" / "shared-references" / "reviewer-routing.md"
    doc_text = doc_path.read_text()

    # Top table: "All other reviewer skills" should NOT list copilot as opt-in
    lines = doc_text.split("\n")
    for i, line in enumerate(lines):
        if "All other reviewer skills" in line:
            # The opt-in override column should not mention copilot
            # Check this line and the next few lines
            nearby = "\n".join(lines[i:i+2])
            assert "copilot" not in nearby.lower(), \
                f"All other reviewer skills should not list copilot as override. Found:\n{nearby}"
            break

    # Copilot sections say scope is /auto-review-loop only.
    copilot_section_idx = doc_text.find("Copilot CLI Custom Agent Profiles")
    assert copilot_section_idx >= 0
    copilot_section = doc_text[copilot_section_idx:copilot_section_idx + 800]
    assert "auto-review-loop" in copilot_section
    assert "only" in copilot_section.lower()
    assert "Copilot CLI Native Rubber Duck" in doc_text
    assert "copilot-native" in doc_text
    assert "two separate root" in doc_text
    assert "agent_type: rubber-duck" in doc_text
    assert "no Codex or" in doc_text and "manual finalizer" in doc_text
    assert "drive-only partial implementation" not in doc_text
    assert "not the issue's requested automatic/default" not in doc_text


def test_native_copilot_default_is_evidence_gated_end_to_end() -> None:
    skill_text = (REPO_ROOT / "skills" / "auto-review-loop" / "SKILL.md").read_text()
    trace_text = (REPO_ROOT / "skills" / "shared-references" / "review-tracing.md").read_text()
    contract_text = (REPO_ROOT / "skills" / "shared-references" / "integration-contract.md").read_text()

    assert "copilot-native" in skill_text
    assert "copilot_native_evidence.py" in skill_text
    assert "agent_type: rubber-duck" in skill_text
    assert 'GATE_ARGS+=(--native-evidence "$NATIVE_EVIDENCE")' in skill_text
    assert "no external finalizer is needed" in skill_text
    assert "Step -1 — Resolve the automatic backend" in skill_text
    assert "Do not issue a second marker/challenge here" in skill_text
    assert "COPILOT_NATIVE_<run_id>_ROUND_<round>_REVIEW" in skill_text
    assert "--replace" in skill_text and "never pass" in skill_text
    assert "validate-challenge --challenge" in skill_text
    assert "round_requires_external_acquittal=true" in skill_text
    assert "--backend copilot-native" in trace_text
    assert "host-session-event" in trace_text
    assert "`copilot_native_evidence.py` | A (gate)" in contract_text
