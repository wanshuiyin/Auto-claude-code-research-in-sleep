"""Tests for the deterministic evidence gate used by /idea-discovery."""

import sys
import tempfile
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import idea_discovery_gate as gate  # noqa: E402
import run_state  # noqa: E402


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _complete_run(root: Path, run_id: str = "idea-run") -> None:
    run_state.start_run(root, run_id, list(gate.REQUIRED_PHASES))
    _write(
        root,
        "idea-stage/IDEA_REPORT.md",
        """# Idea Discovery Report

## Literature Landscape

## Ranked Ideas

## Novelty Verification

## External Critical Review
""",
    )
    _write(root, "refine-logs/FINAL_PROPOSAL.md", "# Final Proposal\n")
    artifacts = {
        "research-lit": "idea-stage/IDEA_REPORT.md#literature-landscape",
        "idea-creator": "idea-stage/IDEA_REPORT.md#ranked-ideas",
        "novelty-check": "idea-stage/IDEA_REPORT.md#novelty-verification",
        "research-review": "idea-stage/IDEA_REPORT.md#external-critical-review",
        "research-refine-pipeline": "refine-logs/FINAL_PROPOSAL.md",
    }
    for phase, artifact in artifacts.items():
        run_state.set_status(root, run_id, phase, "done", artifact=artifact)


def test_gate_accepts_complete_evidence_and_records_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "PASS"
        state = run_state.load_run(root, "idea-run")
        assert state["gates"][gate.GATE_NAME]["verdict"] == "PASS"
        # The gate proves execution evidence only — it must NOT upgrade the
        # semantic phases to `accepted` (resumable-runs.md: done-but-not-
        # accepted marks a stage whose own audit is still pending).
        assert all(phase["status"] == "done" for phase in state["phases"])
        report = (root / "idea-stage/IDEA_REPORT.md").read_text(encoding="utf-8")
        assert "## Evidence Gate" in report
        assert "**Status:** PASS" in report


def test_gate_blocks_missing_phase_and_writes_visible_report_section():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_state.start_run(root, "idea-run", ["research-lit"])
        _write(root, "idea-stage/IDEA_REPORT.md", "# Idea Discovery Report\n")
        run_state.set_status(
            root,
            "idea-run",
            "research-lit",
            "done",
            artifact="idea-stage/IDEA_REPORT.md",
        )

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "BLOCKED"
        assert "idea-creator evidence missing (phase not recorded)" in result.reasons
        state = run_state.load_run(root, "idea-run")
        assert state["gates"][gate.GATE_NAME]["verdict"] == "BLOCKED"
        report = (root / "idea-stage/IDEA_REPORT.md").read_text(encoding="utf-8")
        assert "BLOCKED: idea-creator evidence missing (phase not recorded)" in report


def test_gate_blocks_missing_report_section_without_duplicate_gate_block():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        report_path = root / "idea-stage/IDEA_REPORT.md"
        report_path.write_text("# Idea Discovery Report\n## Literature Landscape\n", encoding="utf-8")

        first = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")
        second = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert first.verdict == second.verdict == "BLOCKED"
        report = report_path.read_text(encoding="utf-8")
        assert report.count(gate.START_MARKER) == 1
        assert "BLOCKED: idea-creator evidence missing (section absent: #ranked-ideas)" in report


def test_gate_blocks_artifact_outside_project_root():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        run_state.set_status(
            root,
            "idea-run",
            "research-lit",
            "done",
            artifact="../outside.md",
        )

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "BLOCKED"
        assert any("artifact escapes project root" in reason for reason in result.reasons)


def test_gate_never_calls_accept(monkeypatch):
    # Doctrine: the gate records its verdict under gates.<name> and must not
    # confer phase-level acceptance — that belongs to each stage's own gate.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)

        def forbidden_accept(*args, **kwargs):
            raise AssertionError("gate must not call run_state.accept")

        monkeypatch.setattr(gate.run_state, "accept", forbidden_accept)
        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "PASS"


def test_idea_discovery_mirrors_require_the_evidence_gate():
    paths = (
        REPO_ROOT / "skills" / "idea-discovery" / "SKILL.md",
        REPO_ROOT / "skills" / "skills-codex" / "idea-discovery" / "SKILL.md",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "Per-stage evidence gate" in text
        assert "idea_discovery_gate.py" in text
        assert "BLOCKED: <stage> evidence missing" in text
        assert "research-refine-pipeline" in text
