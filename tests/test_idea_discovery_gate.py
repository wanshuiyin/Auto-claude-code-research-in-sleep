"""Tests for the deterministic evidence gate used by /idea-discovery."""

import sys
import tempfile
from pathlib import Path

import pytest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
REPO_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import idea_discovery_gate as gate  # noqa: E402
import run_state  # noqa: E402


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _complete_run(
    root: Path,
    run_id: str = "idea-run",
    *,
    review_status: str | None = "accepted",
) -> None:
    is_provisional = review_status == "provisional"
    run_state.start_run(
        root,
        run_id,
        list(gate.REQUIRED_PHASES),
        executor="codex-gpt-5.6-sol" if is_provisional else "claude-sonnet-4.5",
        provisional_advances=is_provisional,
    )
    _write(
        root,
        "idea-stage/IDEA_REPORT.md",
        """# Idea Discovery Report

## Literature Landscape
Recent work leaves a measurable gap.

## Ranked Ideas
1. Test the strongest candidate.

## Novelty Verification
The closest prior work differs in its training objective.

## External Critical Review
The reviewer recommends proceeding after one ablation.
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
    for phase in gate.REVIEW_REQUIRED_PHASES:
        if review_status == "accepted":
            run_state.accept(
                root,
                run_id,
                phase,
                verdict_id=f"trace:{phase}:accepted",
                reviewer="gpt-5.6-sol",
            )
        elif review_status == "provisional":
            run_state.mark_provisional(
                root,
                run_id,
                phase,
                verdict_id=f"trace:{phase}:provisional",
                reviewer="gpt-5.6-sol",
            )


def test_gate_accepts_complete_evidence_and_records_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        before = run_state.load_run(root, "idea-run")["phases"]

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "PASS"
        state = run_state.load_run(root, "idea-run")
        assert state["gates"][gate.GATE_NAME]["verdict"] == "PASS"
        # The gate validates existing receipts but must not grant or otherwise
        # rewrite per-phase acceptance itself.
        assert state["phases"] == before
        report = (root / "idea-stage/IDEA_REPORT.md").read_text(encoding="utf-8")
        assert "## Evidence Gate" in report
        assert "**Status:** PASS" in report


def test_gate_accepts_codex_same_family_provisional_receipts_when_policy_allows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root, review_status="provisional")

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "PASS"
        phases = {
            phase["phase"]: phase
            for phase in run_state.load_run(root, "idea-run")["phases"]
        }
        assert phases["novelty-check"]["status"] == "provisional"
        assert phases["research-review"]["status"] == "provisional"


def test_gate_blocks_done_reviews_with_empty_report_headings():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root, review_status=None)
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

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "BLOCKED"
        assert "novelty-check review evidence missing (status=done)" in result.reasons
        assert "research-review review evidence missing (status=done)" in result.reasons


@pytest.mark.parametrize("field", ["verdict_id", "reviewer"])
def test_gate_blocks_review_receipt_with_missing_credentials(field: str):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        state = run_state.load_run(root, "idea-run")
        phase = next(
            phase for phase in state["phases"] if phase["phase"] == "research-review"
        )
        phase[field] = "   "

        result = gate.evaluate(root, state)

        assert result.verdict == "BLOCKED"
        assert any(field in reason for reason in result.reasons)


@pytest.mark.parametrize(
    ("field", "value", "reason_fragment"),
    [
        ("acceptance_status", "provisional", "acceptance_status inconsistent"),
        ("review_independence", "same-family", "review_independence inconsistent"),
        ("reviewer_family", "anthropic", "reviewer_family inconsistent"),
        ("executor_family", "openai", "executor_family inconsistent"),
    ],
)
def test_gate_blocks_inconsistent_accepted_provenance(
    field: str, value: str, reason_fragment: str
):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        state = run_state.load_run(root, "idea-run")
        phase = next(
            phase for phase in state["phases"] if phase["phase"] == "research-review"
        )
        phase[field] = value

        result = gate.evaluate(root, state)

        assert result.verdict == "BLOCKED"
        assert any(reason_fragment in reason for reason in result.reasons)


def test_gate_blocks_forged_same_family_acceptance():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        state = run_state.load_run(root, "idea-run")
        phase = next(
            phase for phase in state["phases"] if phase["phase"] == "research-review"
        )
        # Make the executor/reviewer family fields internally coherent while
        # retaining the false `accepted`/`cross-family` claim.
        phase["executor_model"] = "codex-gpt-5.6-sol"
        phase["executor_family"] = "openai"

        result = gate.evaluate(root, state)

        assert result.verdict == "BLOCKED"
        assert any(
            "accepted review is same-family" in reason for reason in result.reasons
        )


def test_gate_blocks_deterministic_receipt_for_model_review_phase():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        state = run_state.load_run(root, "idea-run")
        phase = next(
            phase for phase in state["phases"] if phase["phase"] == "research-review"
        )
        phase["reviewer"] = "deterministic:file-exists"
        phase["reviewer_family"] = "deterministic"
        phase["review_independence"] = "deterministic"

        result = gate.evaluate(root, state)

        assert result.verdict == "BLOCKED"
        assert any(
            "cannot establish a model review" in reason for reason in result.reasons
        )


def test_gate_blocks_provisional_receipt_when_run_policy_disallows_advancing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root, review_status="provisional")
        state = run_state.load_run(root, "idea-run")
        state["policy"]["provisional_advances"] = False

        result = gate.evaluate(root, state)

        assert result.verdict == "BLOCKED"
        assert any(
            "provisional review cannot advance this run" in reason
            for reason in result.reasons
        )


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
        report_path.write_text(
            "# Idea Discovery Report\n## Literature Landscape\nEvidence.\n",
            encoding="utf-8",
        )

        first = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")
        second = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert first.verdict == second.verdict == "BLOCKED"
        report = report_path.read_text(encoding="utf-8")
        assert report.count(gate.START_MARKER) == 1
        assert "BLOCKED: idea-creator evidence missing (section absent: #ranked-ideas)" in report


def test_gate_blocks_present_but_empty_anchored_report_section():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        report_path = root / "idea-stage/IDEA_REPORT.md"
        report_path.write_text(
            report_path.read_text(encoding="utf-8").replace(
                "## Novelty Verification\n"
                "The closest prior work differs in its training objective.\n",
                "## Novelty Verification\n",
            ),
            encoding="utf-8",
        )

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "BLOCKED"
        assert (
            "novelty-check evidence missing (section empty: #novelty-verification)"
            in result.reasons
        )


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


@pytest.mark.parametrize("artifact", ["idea-stage/IDEA_REPORT.md#", "idea-stage/IDEA_REPORT.md#   "])
def test_gate_blocks_artifact_with_empty_anchor(artifact: str):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)
        run_state.set_status(root, "idea-run", "research-lit", "done", artifact=artifact)

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "BLOCKED"
        assert any("artifact anchor is empty" in reason for reason in result.reasons)


def test_gate_never_grants_review_status(monkeypatch):
    # Doctrine: the gate records its verdict under gates.<name> and must not
    # confer phase-level acceptance — that belongs to each stage's own gate.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root)

        def forbidden_accept(*args, **kwargs):
            raise AssertionError("gate must not grant phase-level review status")

        monkeypatch.setattr(gate.run_state, "accept", forbidden_accept)
        monkeypatch.setattr(gate.run_state, "mark_provisional", forbidden_accept)
        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "PASS"


def test_negative_review_stays_done_and_blocked_without_granting_receipt(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _complete_run(root, review_status=None)

        def forbidden_accept(*args, **kwargs):
            raise AssertionError("a blocked gate must not grant a review receipt")

        monkeypatch.setattr(gate.run_state, "accept", forbidden_accept)
        monkeypatch.setattr(gate.run_state, "mark_provisional", forbidden_accept)

        result = gate.run(root, "idea-run", "idea-stage/IDEA_REPORT.md")

        assert result.verdict == "BLOCKED"
        state = run_state.load_run(root, "idea-run")
        phases = {phase["phase"]: phase for phase in state["phases"]}
        for name in gate.REVIEW_REQUIRED_PHASES:
            assert phases[name]["status"] == "done"
            assert phases[name]["verdict_id"] is None
            assert phases[name]["reviewer"] is None
        assert state["gates"][gate.GATE_NAME]["verdict"] == "BLOCKED"


def test_idea_discovery_mirrors_require_the_evidence_gate():
    mainline = (
        REPO_ROOT / "skills" / "idea-discovery" / "SKILL.md"
    ).read_text(encoding="utf-8")
    codex = (
        REPO_ROOT / "skills" / "skills-codex" / "idea-discovery" / "SKILL.md"
    ).read_text(encoding="utf-8")
    for text in (mainline, codex):
        assert "Per-stage evidence gate" in text
        assert "idea_discovery_gate.py" in text
        assert "BLOCKED: <stage> evidence missing" in text
        assert "research-refine-pipeline" in text
        assert "reviewer-bearing phases" in text
        assert "novelty-check" in text and "research-review" in text
        assert "Never invent either value" in text
        assert "A negative verdict does not grant a review receipt" in text

    assert " accept . <run_id> novelty-check" in mainline
    assert " accept . <run_id> research-review" in mainline
    assert "--executor <actual-Codex-model>" in codex
    assert "mark-provisional . <run_id> novelty-check" in codex
    assert "mark-provisional . <run_id> research-review" in codex
