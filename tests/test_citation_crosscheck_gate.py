"""CI guard for the /citation-crosscheck deterministic verifier gate (cx_verify.py).

cx_verify.py is a load-bearing gate: it decides which citations reach MATCH/MINOR without a
main-agent fetch. Its correctness is covered by an in-script ``--selftest`` battery, and the
skill ships two byte-identical host copies (Claude Code mainline + Codex mirror). This test
runs both — pre-merge, in the normal ``pytest tests/`` suite — so a regression in the gate or a
drift between the two copies fails CI instead of being discovered on a live run.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_GATE = REPO_ROOT / "skills" / "citation-crosscheck" / "scripts" / "cx_verify.py"
CODEX_GATE = REPO_ROOT / "skills" / "skills-codex" / "citation-crosscheck" / "scripts" / "cx_verify.py"


def test_gate_scripts_exist() -> None:
    assert MAIN_GATE.is_file(), f"missing {MAIN_GATE}"
    assert CODEX_GATE.is_file(), f"missing {CODEX_GATE}"


def test_mirror_copies_are_byte_identical() -> None:
    # A fix applied to one host copy must be applied to the other, verbatim; otherwise the
    # two hosts silently run different gates.
    assert MAIN_GATE.read_bytes() == CODEX_GATE.read_bytes(), (
        "cx_verify.py mainline and Codex-mirror copies differ — re-sync them byte-for-byte "
        "(cp skills/citation-crosscheck/scripts/cx_verify.py "
        "skills/skills-codex/citation-crosscheck/scripts/cx_verify.py)"
    )


def _run_selftest(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(path), "--selftest"],
        capture_output=True,
        text=True,
    )


def test_selftest_passes_mainline() -> None:
    result = _run_selftest(MAIN_GATE)
    assert result.returncode == 0, (
        f"cx_verify.py --selftest failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    # Require an "N/N passed" summary (all cases), not just the substring "passed" — a
    # partial-failure run prints e.g. "94/107 passed" and must not read as success.
    assert re.search(r"\b(\d+)/\1 passed\b", result.stdout), result.stdout


def test_selftest_passes_codex_mirror() -> None:
    result = _run_selftest(CODEX_GATE)
    assert result.returncode == 0, (
        f"Codex-mirror cx_verify.py --selftest failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    # Require an "N/N passed" summary (all cases), not just the substring "passed" — a
    # partial-failure run prints e.g. "94/107 passed" and must not read as success.
    assert re.search(r"\b(\d+)/\1 passed\b", result.stdout), result.stdout
