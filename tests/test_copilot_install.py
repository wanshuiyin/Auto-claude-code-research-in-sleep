"""Tests for install_aris_copilot.sh and smart_update_copilot.sh."""
from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "tools" / "install_aris_copilot.sh"
UPDATE_SCRIPT = REPO_ROOT / "tools" / "smart_update_copilot.sh"


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
    assert "Run with --apply" in dry_run.stdout

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
