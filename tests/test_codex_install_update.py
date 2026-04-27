from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "tools" / "install_aris_codex.sh"
UPDATE_SCRIPT = REPO_ROOT / "tools" / "smart_update_codex.sh"


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
    repo = root / "aris"
    make_skill(repo / "skills" / "skills-codex" / "alpha", "# alpha\n")
    make_skill(repo / "skills" / "skills-codex" / "beta", "# beta-base\n")
    (repo / "skills" / "skills-codex" / "shared-references").mkdir(parents=True, exist_ok=True)
    (repo / "skills" / "skills-codex" / "shared-references" / "reviewer-routing.md").write_text("base\n")
    make_skill(repo / "skills" / "skills-codex-claude-review" / "beta", "# beta-claude-overlay\n")
    make_skill(repo / "skills" / "skills-codex-gemini-review" / "beta", "# beta-gemini-overlay\n")
    return repo


def test_install_aris_codex_dry_run_has_no_project_writes(tmp_path: Path) -> None:
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
    assert not (project / ".agents").exists()
    assert not (project / "AGENTS.md").exists()


def test_install_aris_codex_avoids_bash4_associative_arrays() -> None:
    text = INSTALL_SCRIPT.read_text()
    assert "declare -A" not in text


def test_install_aris_codex_reconcile_and_uninstall(tmp_path: Path) -> None:
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

    manifest = project / ".aris" / "installed-skills-codex.txt"
    assert manifest.exists()
    assert (project / "AGENTS.md").exists()
    agents_text = (project / "AGENTS.md").read_text()
    assert "ARIS Codex Skill Scope" in agents_text
    assert f"ARIS repo root: `{repo}`" in agents_text
    assert "repo_root" in agents_text
    assert '$1=="repo_root"{print $2; exit}' in agents_text
    assert "$1==repo_root" not in agents_text
    assert (project / ".agents" / "skills" / "alpha").is_symlink()
    assert (project / ".agents" / "skills" / "beta").resolve() == (repo / "skills" / "skills-codex" / "beta")

    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--reconcile",
            "--with-claude-review-overlay",
            "--quiet",
        ]
    )
    assert (project / ".agents" / "skills" / "beta").resolve() == (
        repo / "skills" / "skills-codex-claude-review" / "beta"
    )

    (repo / "skills" / "skills-codex" / "alpha").rename(repo / "skills" / "skills-codex" / "alpha-removed")
    make_skill(repo / "skills" / "skills-codex" / "gamma", "# gamma\n")
    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(repo),
            "--reconcile",
            "--with-claude-review-overlay",
            "--quiet",
        ]
    )
    assert not (project / ".agents" / "skills" / "alpha").exists()
    assert (project / ".agents" / "skills" / "gamma").is_symlink()

    (project / ".agents" / "skills" / "local-only").mkdir(parents=True)
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
    assert (project / ".agents" / "skills" / "local-only").exists()
    assert not (project / ".agents" / "skills" / "beta").exists()
    assert (project / ".aris" / "installed-skills-codex.txt.prev").exists()
    assert "ARIS Codex Skill Scope" not in (project / "AGENTS.md").read_text()


def test_install_aris_codex_uninstall_uses_manifest_repo_root(tmp_path: Path) -> None:
    original_repo = make_minimal_aris_repo(tmp_path / "original")
    other_repo = make_minimal_aris_repo(tmp_path / "other")
    project = tmp_path / "project"
    project.mkdir()

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

    alpha_link = project / ".agents" / "skills" / "alpha"
    assert alpha_link.is_symlink()
    assert alpha_link.resolve() == original_repo / "skills" / "skills-codex" / "alpha"

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
    assert not (project / ".agents" / "skills" / "beta").exists()
    assert not (project / ".agents" / "skills" / "shared-references").exists()
    assert not (project / ".aris" / "installed-skills-codex.txt").exists()
    assert (project / ".aris" / "installed-skills-codex.txt.prev").exists()


def test_install_aris_codex_reconcile_removes_stale_links_from_manifest_repo(tmp_path: Path) -> None:
    original_repo = make_minimal_aris_repo(tmp_path / "original")
    new_repo = make_minimal_aris_repo(tmp_path / "new")
    (new_repo / "skills" / "skills-codex" / "alpha").rename(
        new_repo / "skills" / "skills-codex" / "alpha-removed"
    )
    make_skill(new_repo / "skills" / "skills-codex" / "gamma", "# gamma\n")
    project = tmp_path / "project"
    project.mkdir()

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

    alpha_link = project / ".agents" / "skills" / "alpha"
    beta_link = project / ".agents" / "skills" / "beta"
    assert alpha_link.is_symlink()
    assert alpha_link.resolve() == original_repo / "skills" / "skills-codex" / "alpha"

    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(new_repo),
            "--reconcile",
            "--quiet",
        ]
    )

    assert not alpha_link.exists()
    assert beta_link.resolve() == new_repo / "skills" / "skills-codex" / "beta"
    assert (project / ".agents" / "skills" / "gamma").resolve() == (
        new_repo / "skills" / "skills-codex" / "gamma"
    )
    manifest = (project / ".aris" / "installed-skills-codex.txt").read_text()
    assert "\talpha\t" not in manifest
    assert f"repo_root\t{new_repo}" in manifest


def test_install_aris_codex_reconcile_accepts_already_deleted_stale_link(tmp_path: Path) -> None:
    original_repo = make_minimal_aris_repo(tmp_path / "original")
    new_repo = make_minimal_aris_repo(tmp_path / "new")
    (new_repo / "skills" / "skills-codex" / "alpha").rename(
        new_repo / "skills" / "skills-codex" / "alpha-removed"
    )
    project = tmp_path / "project"
    project.mkdir()

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

    alpha_link = project / ".agents" / "skills" / "alpha"
    assert alpha_link.is_symlink()
    alpha_link.unlink()

    run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            str(project),
            "--aris-repo",
            str(new_repo),
            "--reconcile",
            "--quiet",
        ]
    )

    manifest = (project / ".aris" / "installed-skills-codex.txt").read_text()
    assert "\talpha\t" not in manifest


def test_smart_update_codex_copy_install_and_symlink_refusal(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    make_skill(upstream / "alpha", "# alpha-v2\n")
    make_skill(upstream / "beta", "# beta\n")
    make_skill(upstream / "gamma", "../shared-references/integration-contract.md\n")
    (upstream / "shared-references").mkdir(parents=True, exist_ok=True)
    (upstream / "shared-references" / "reviewer-routing.md").write_text("new\n")
    (upstream / "shared-references" / "integration-contract.md").write_text("integration\n")

    local = tmp_path / "local"
    make_skill(local / "alpha", "# alpha-v1\n")
    (local / "shared-references").mkdir(parents=True, exist_ok=True)
    (local / "shared-references" / "reviewer-routing.md").write_text("old\n")
    make_skill(local / "local-only", "# keep-me\n")

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
    assert "Safe update: 0" in dry_run.stdout
    assert "New: 2" in dry_run.stdout
    assert "Needs merge: 2" in dry_run.stdout
    assert "New shared references: 1" in dry_run.stdout
    assert "shared-references/integration-contract.md" in dry_run.stdout
    assert "Local only: 1" in dry_run.stdout
    assert not (local / "shared-references" / "integration-contract.md").exists()

    run(
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
    assert "# alpha-v1" in (local / "alpha" / "SKILL.md").read_text()
    assert (local / "beta" / "SKILL.md").exists()
    assert (local / "gamma" / "SKILL.md").exists()
    assert (local / "shared-references" / "integration-contract.md").read_text() == "integration\n"
    assert (local / "shared-references" / "reviewer-routing.md").read_text() == "old\n"
    assert (local / "local-only" / "SKILL.md").exists()

    managed_project = tmp_path / "managed-project"
    (managed_project / ".agents" / "skills").mkdir(parents=True)
    (managed_project / ".agents" / "skills" / "auto-review-loop").symlink_to(
        REPO_ROOT / "skills" / "skills-codex" / "auto-review-loop"
    )
    refused = run(
        ["bash", str(UPDATE_SCRIPT), "--project", str(managed_project)],
        check=False,
    )
    assert refused.returncode != 0
    assert "install_aris_codex.sh" in refused.stderr


def test_smart_update_codex_local_uses_default_upstream(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()

    dry_run = run(["bash", str(UPDATE_SCRIPT), "--local", str(local)])

    assert dry_run.returncode == 0
    assert f"Upstream: {REPO_ROOT / 'skills' / 'skills-codex'}" in dry_run.stdout
    assert f"Local:    {local}" in dry_run.stdout


def test_smart_update_codex_allows_unrelated_symlinked_skills(tmp_path: Path) -> None:
    local = tmp_path / "local"
    third_party = tmp_path / "third-party-skill"
    local.mkdir()
    make_skill(third_party, "# third-party\n")
    (local / "third-party").symlink_to(third_party)

    dry_run = run(["bash", str(UPDATE_SCRIPT), "--local", str(local)])

    assert dry_run.returncode == 0
    assert "third-party" in dry_run.stdout


def test_smart_update_codex_refuses_aris_symlinked_skills(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()
    (local / "auto-review-loop").symlink_to(
        REPO_ROOT / "skills" / "skills-codex" / "auto-review-loop"
    )

    refused = run(["bash", str(UPDATE_SCRIPT), "--local", str(local)], check=False)

    assert refused.returncode != 0
    assert "symlink-managed ARIS entry 'auto-review-loop'" in refused.stderr


def test_smart_update_codex_ignores_local_only_shared_reference_failures(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    make_skill(upstream / "alpha", "# alpha\n")
    (upstream / "shared-references").mkdir(parents=True, exist_ok=True)

    local = tmp_path / "local"
    local.mkdir()
    make_skill(local / "local-only", "../shared-references/local-contract.md\n")

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
    assert (local / "alpha" / "SKILL.md").exists()
    assert (local / "local-only" / "SKILL.md").exists()


def test_smart_update_codex_local_respects_overlay(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()

    run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--local",
            str(local),
            "--overlay",
            "claude-review",
            "--apply",
        ]
    )

    installed = (local / "auto-review-loop" / "SKILL.md").read_text()
    overlay = (
        REPO_ROOT
        / "skills"
        / "skills-codex-claude-review"
        / "auto-review-loop"
        / "SKILL.md"
    ).read_text()
    base = (REPO_ROOT / "skills" / "skills-codex" / "auto-review-loop" / "SKILL.md").read_text()

    assert installed == overlay
    assert installed != base


def test_smart_update_codex_overlay_updates_existing_base_copy(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()
    base_skill = REPO_ROOT / "skills" / "skills-codex" / "auto-review-loop"
    overlay_skill = (
        REPO_ROOT
        / "skills"
        / "skills-codex-claude-review"
        / "auto-review-loop"
    )

    run(["cp", "-a", str(base_skill), str(local / "auto-review-loop")])

    dry_run = run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--local",
            str(local),
            "--overlay",
            "claude-review",
        ]
    )
    assert "Safe update: 1" in dry_run.stdout
    assert "  auto-review-loop" in dry_run.stdout

    run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--local",
            str(local),
            "--overlay",
            "claude-review",
            "--apply",
        ]
    )

    assert (local / "auto-review-loop" / "SKILL.md").read_text() == (
        overlay_skill / "SKILL.md"
    ).read_text()


def test_smart_update_codex_overlay_preserves_custom_local_copy(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()
    base_skill = REPO_ROOT / "skills" / "skills-codex" / "auto-review-loop"

    run(["cp", "-a", str(base_skill), str(local / "auto-review-loop")])
    custom_text = (local / "auto-review-loop" / "SKILL.md").read_text() + "\n<!-- local customization -->\n"
    (local / "auto-review-loop" / "SKILL.md").write_text(custom_text)

    result = run(
        [
            "bash",
            str(UPDATE_SCRIPT),
            "--local",
            str(local),
            "--overlay",
            "claude-review",
            "--apply",
        ]
    )

    assert "Needs merge: 1" in result.stdout
    assert (local / "auto-review-loop" / "SKILL.md").read_text() == custom_text
