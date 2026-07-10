"""Public CLI tests for review-independence aggregation in paper audits."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "tools" / "verify_paper_audits.sh"
AUDITS = {
    "PROOF_AUDIT.json": "proof-checker",
    "PAPER_CLAIM_AUDIT.json": "paper-claim-audit",
    "CITATION_AUDIT.json": "citation-audit",
    "KILL_ARGUMENT.json": "kill-argument",
}


def _family(model: str) -> str:
    if model.startswith("deterministic"):
        return "deterministic"
    if "claude" in model:
        return "anthropic"
    if "gemini" in model:
        return "google"
    if "gpt" in model or "codex" in model:
        return "openai"
    return "unknown"


def _write_audits(
    paper: Path,
    independence: str | None,
    verdict: str = "PASS",
    executor: str = "codex-gpt-5.5",
    reviewer: str | None = None,
) -> None:
    trace = paper / ".aris" / "traces" / "audit"
    trace.mkdir(parents=True)
    (trace / "response.md").write_text("review\n", encoding="utf-8")
    for filename, skill in AUDITS.items():
        selected_reviewer = reviewer or {
            "same-family": "gpt-5.5",
            "cross-family": "claude-opus-4-8",
            "deterministic": "deterministic:pytest",
        }.get(independence, "gpt-5.5")
        artifact = {
            "audit_skill": skill,
            "verdict": verdict,
            "reason_code": "test",
            "summary": "fixture",
            "audited_input_hashes": {},
            "trace_path": ".aris/traces/audit",
            "agent_id": "agent_019f",
            "reviewer_model": selected_reviewer,
            "reviewer_reasoning": "xhigh",
            "generated_at": "2026-07-10T00:00:00Z",
        }
        if independence is not None:
            artifact["review_independence"] = independence
            artifact["acceptance_status"] = (
                "provisional" if independence == "same-family" else "accepted"
            )
            artifact["executor_model"] = executor
            artifact["executor_family"] = _family(executor)
            artifact["reviewer_family"] = _family(selected_reviewer)
        (paper / filename).write_text(json.dumps(artifact), encoding="utf-8")


def _verify(
    independence: str | None,
    verdict: str = "PASS",
    executor: str = "codex-gpt-5.5",
    reviewer: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    with tempfile.TemporaryDirectory() as d:
        paper = Path(d) / "paper"
        paper.mkdir()
        _write_audits(paper, independence, verdict, executor, reviewer)
        result = subprocess.run(
            ["bash", str(VERIFIER), str(paper), "--assurance", "submission"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        report = json.loads((paper / ".aris" / "audit-verifier-report.json").read_text())
        return result, report


def test_same_family_green_audits_are_provisional_and_nonblocking():
    result, report = _verify("same-family")
    assert result.returncode == 0, result.stderr
    assert report["overall_assurance"] == "provisional"
    assert report["submission_blocking"] is False
    assert all(row["review_independence"] == "same-family" for row in report["audits"])


def test_cross_family_green_audits_are_accepted():
    result, report = _verify("cross-family")
    assert result.returncode == 0, result.stderr
    assert report["overall_assurance"] == "accepted"


def test_deterministic_label_cannot_acquit_semantic_audits():
    # these four audits are SEMANTIC — a self-reported deterministic:pytest
    # label is just metadata, not a verifier that ran; it must block, not acquit
    result, report = _verify("deterministic")
    assert result.returncode == 1
    assert report["overall_assurance"] == "blocked"
    result, report = _verify("deterministic", executor="local-tooling")
    assert result.returncode == 1
    assert report["overall_assurance"] == "blocked"


def _run_on(mutate) -> tuple[subprocess.CompletedProcess[str], dict]:
    """Like _verify('cross-family') but lets the test corrupt the paper dir first."""
    with tempfile.TemporaryDirectory() as d:
        paper = Path(d) / "paper"
        paper.mkdir()
        _write_audits(paper, "cross-family")
        mutate(paper)
        result = subprocess.run(
            ["bash", str(VERIFIER), str(paper), "--assurance", "submission"],
            cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        report = json.loads((paper / ".aris" / "audit-verifier-report.json").read_text())
        return result, report


def test_non_object_json_artifact_blocks():
    # a bare [] is valid JSON but not an audit artifact — must fail CLOSED
    def corrupt(paper):
        (paper / sorted(AUDITS)[0]).write_text("[]", encoding="utf-8")
    result, report = _run_on(corrupt)
    assert result.returncode == 1
    assert report["overall_assurance"] == "blocked"


def test_pipe_injection_in_verdict_cannot_forge_pass():
    # artifact text reaches bash through a |-delimited protocol; a verdict
    # crafted with separators must not smuggle a PASS or hide issues
    def inject(paper):
        first = sorted(AUDITS)[0]
        art = json.loads((paper / first).read_text())
        art["verdict"] = "EVIL|PASS||True|cross-family"
        (paper / first).write_text(json.dumps(art), encoding="utf-8")
    result, report = _run_on(inject)
    assert result.returncode == 1
    assert report["overall_assurance"] == "blocked"
    assert all("EVIL" not in (row.get("verdict") or "") or row["verdict"] != "PASS"
               for row in report["audits"])
    assert all(row.get("verdict") != "PASS" or row["audit"] != sorted(AUDITS.values())[0]
               for row in report["audits"])


def test_legacy_unspecified_independence_is_conservatively_provisional():
    result, report = _verify(None)
    assert result.returncode == 0, result.stderr
    assert report["overall_assurance"] == "provisional"
    assert all(row["review_independence"] == "legacy-unspecified" for row in report["audits"])


def test_blocked_audit_remains_submission_blocking():
    result, report = _verify("same-family", verdict="BLOCKED")
    assert result.returncode == 1
    assert report["overall_assurance"] == "blocked"
    assert report["submission_blocking"] is True


def test_spoofed_cross_family_metadata_is_submission_blocking():
    result, report = _verify("cross-family", executor="codex-gpt-5.5", reviewer="gpt-5.5")
    assert result.returncode == 1
    assert report["overall_assurance"] == "blocked"
    assert all("cross_family_independence_mismatch" in row["issues"] for row in report["audits"])


def test_hostile_metadata_cannot_break_verifier_report_json():
    result, report = _verify('cross-family" injected')
    assert result.returncode == 1
    assert report["overall_assurance"] == "blocked"
    assert all(row["status"] == "HAS_ISSUES" for row in report["audits"])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {test.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
