#!/usr/bin/env python3
"""Deterministically gate Idea Discovery reports on recorded stage evidence."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import run_state
except ImportError:  # package import: ``from tools import idea_discovery_gate``
    from tools import run_state


GATE_NAME = "idea-discovery-evidence"
REQUIRED_PHASES = (
    "research-lit",
    "idea-creator",
    "novelty-check",
    "research-review",
    "research-refine-pipeline",
)
START_MARKER = "<!-- ARIS_IDEA_DISCOVERY_EVIDENCE_GATE:START -->"
END_MARKER = "<!-- ARIS_IDEA_DISCOVERY_EVIDENCE_GATE:END -->"


@dataclass(frozen=True)
class GateResult:
    verdict: str
    reasons: tuple[str, ...]


def _artifact_target(root: Path, artifact: str) -> tuple[Path, str | None]:
    path_text, separator, anchor = artifact.partition("#")
    if not path_text:
        raise ValueError("artifact path is empty")
    candidate = (root / path_text).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"artifact escapes project root: {artifact}") from exc
    return candidate, anchor if separator else None


def _heading_slugs(path: Path) -> set[str]:
    headings = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        text = match.group(1).strip().lower()
        slug = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
        headings.add(re.sub(r"[\s-]+", "-", slug).strip("-"))
    return headings


def evaluate(root: str | Path, state: dict) -> GateResult:
    """Check that every required stage has completed, durable evidence."""
    project_root = Path(root).resolve()
    phases = {phase["phase"]: phase for phase in state.get("phases", [])}
    reasons: list[str] = []

    for name in REQUIRED_PHASES:
        phase = phases.get(name)
        if phase is None:
            reasons.append(f"{name} evidence missing (phase not recorded)")
            continue
        if phase.get("status") not in {"done", "accepted", "provisional"}:
            reasons.append(
                f"{name} evidence missing (status={phase.get('status', 'unknown')})"
            )
            continue
        artifact = phase.get("artifact")
        if not artifact:
            reasons.append(f"{name} evidence missing (artifact not recorded)")
            continue
        try:
            artifact_path, anchor = _artifact_target(project_root, artifact)
        except ValueError as exc:
            reasons.append(f"{name} evidence missing ({exc})")
            continue
        if not artifact_path.is_file():
            reasons.append(f"{name} evidence missing (artifact absent: {artifact})")
            continue
        if anchor and anchor not in _heading_slugs(artifact_path):
            reasons.append(f"{name} evidence missing (section absent: #{anchor})")

    return GateResult("PASS" if not reasons else "BLOCKED", tuple(reasons))


def _gate_section(result: GateResult) -> str:
    lines = [START_MARKER, "## Evidence Gate", f"**Status:** {result.verdict}", ""]
    if result.verdict == "PASS":
        lines.append("All required stage records, artifacts, and report sections are present.")
    else:
        lines.append("The workflow is not complete. Required stage evidence is missing:")
        lines.extend(f"- BLOCKED: {reason}" for reason in result.reasons)
    lines.extend([END_MARKER, ""])
    return "\n".join(lines)


def write_report_gate(root: str | Path, report: str | Path, result: GateResult) -> Path:
    project_root = Path(root).resolve()
    report_path = (project_root / report).resolve()
    try:
        report_path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"report escapes project root: {report}") from exc

    report_path.parent.mkdir(parents=True, exist_ok=True)
    original = report_path.read_text(encoding="utf-8") if report_path.exists() else "# Idea Discovery Report\n"
    section = _gate_section(result)
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}\n?",
        flags=re.DOTALL,
    )
    if pattern.search(original):
        updated = pattern.sub(section, original)
    else:
        updated = original.rstrip() + "\n\n" + section
    report_path.write_text(updated, encoding="utf-8")
    return report_path


def run(root: str | Path, run_id: str, report: str | Path) -> GateResult:
    try:
        state = run_state.load_run(str(root), run_id)
    except FileNotFoundError:
        result = GateResult("BLOCKED", ("run state missing",))
        write_report_gate(root, report, result)
        return result

    result = evaluate(root, state)
    # The gate's verdict lives ONLY in gates.<GATE_NAME>. It must not mark the
    # semantic phases `accepted`: per resumable-runs.md, file-exists evidence
    # can accept a purely mechanical phase, while these five stages carry
    # quality semantics whose acceptance belongs to their own cross-model or
    # stage-level deterministic gates — and resume relies on done-but-not-
    # accepted to know a stage still needs its audit.
    run_state.record_gate_result(str(root), run_id, GATE_NAME, result.verdict, list(result.reasons))
    write_report_gate(root, report, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("run_id")
    parser.add_argument("--report", default="idea-stage/IDEA_REPORT.md")
    args = parser.parse_args()

    try:
        result = run(args.root, args.run_id, args.report)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    for reason in result.reasons:
        print(f"BLOCKED: {reason}")
    if result.verdict == "PASS":
        print("PASS: idea-discovery evidence gate")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
