#!/usr/bin/env python3
"""run_gates - canonical gate orchestrator for HTML academic posters.

Runs the five poster gates in their fixed canonical order and writes a
single ``GATE_REPORT.json`` that the SKILL workflow (and any reviewer)
reads to decide pass/fail and find the full fix surface in one shot::

    preflight -> style -> asset -> measure -> polish

WHY an orchestrator instead of calling each gate by hand:

  - The order is load-bearing. ``preflight`` is a cheap static lint that
    catches the bugs (LaTeX residue, missing images, broken roles) that
    would otherwise burn an expensive render cycle in ``measure`` /
    ``polish``; ``style`` and ``asset`` source-gate the design before we
    pay for rendering at all. Putting that order in one script keeps it
    from drifting across callers.
  - Default ACCUMULATE: a poster author wants the WHOLE fix surface at
    once, not a stop-at-first-error trickle. ``--fail-fast`` is opt-in
    for CI that only cares whether the build is green.
  - The vendored ``poster_check.py`` keeps its own subcommand CLI
    (preflight / measure / polish) and the new sibling gates
    (style_check.py / asset_check.py) keep theirs, so the vendor diff
    stays clean. This file is pure orchestration: it shells out to each,
    parses what it can, and aggregates into the §7 schema.

Integration contract (DESIGN_FINAL.md §7, IMPLEMENTATION_CONVENTIONS.md
§C): child processes run with ``sys.executable``, ``cwd`` = the poster
HTML's directory (so relative ``assets/...`` paths resolve), and the
gate script paths are resolved relative to THIS file's location -- never
the cwd -- so the orchestrator is position-independent.

Exit code: 0 = overall PASS (zero hard failures), 1 = at least one hard
failure, 2 = usage / environment error.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Make ``_posterly`` importable when this file is run directly, exactly
# like the vendored poster_check.py / render_preview.py do.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from _posterly import canvas as _canvas  # noqa: E402
from _posterly.textutil import ascii_safe  # noqa: E402

SCHEMA_VERSION = 1
SKILL_NAME = "paper-poster-html"

# Canonical gate order. The orchestration depends on this list order, so
# it is the single source of truth for "what runs and in what sequence".
CANONICAL_ORDER = ["preflight", "style", "asset", "measure", "polish"]

# Severity of each gate as a whole. ``preflight``, ``style``, ``asset``,
# and ``measure`` are HARD gates: a FAIL blocks ``overall``. ``polish``
# is SOFT by default (its findings are WARN) and only becomes hard under
# ``--strict-polish`` (which maps to ``poster_check.py polish --strict``).
GATE_SEVERITY = {
    "preflight": "hard",
    "style": "hard",
    "asset": "hard",
    "measure": "hard",
    "polish": "soft",
}

# How many trailing lines of child stdout/stderr to keep in the report
# summary for the vendored gates (which have no machine-readable output).
# Enough to capture the "[gate] PASS/FAIL" verdict line and the couple of
# FAIL: lines above it without bloating the JSON.
TAIL_LINES = 8


def _eprint(*args: Any, **kw: Any) -> None:
    print(*args, file=sys.stderr, **kw)


def _tail(text: str, n: int = TAIL_LINES) -> str:
    """Return the last ``n`` non-empty lines of ``text``, ascii-safe.

    Used to summarise a vendored gate's human output when it offers no
    ``--json``. Non-empty filtering drops the trailing newline noise so
    the verdict line lands at the end of the tail.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return ascii_safe("\n".join(lines[-n:]))


def _now_iso() -> str:
    """UTC timestamp, second precision, ``Z`` suffix -- stable for diffs."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# --------------------------------------------------------------------------
# Canvas resolution (GATE_REPORT.json `canvas` block).
# --------------------------------------------------------------------------
def _orientation(width: float, height: float) -> str:
    """Landscape when wider than tall, else portrait (square -> portrait)."""
    return "landscape" if width > height else "portrait"


def resolve_canvas(html_path: Path) -> dict[str, Any]:
    """Build the ``canvas`` block for the report.

    Source priority (DESIGN_FINAL §7):
      1. ``POSTER_STATE.json`` sitting next to the poster HTML, if it
         carries canvas dimensions -- the workflow records the resolved
         venue canvas there, so it is authoritative once present.
      2. The ``@page { size }`` rule parsed from the HTML via
         ``_posterly.canvas`` -- source tagged ``"page-rule"``.
      3. ``None`` everywhere with source ``"unknown"`` -- we never invent
         a default; a downstream consumer must notice the canvas is not
         resolved rather than trust a fabricated size.
    """
    state_path = html_path.parent / "POSTER_STATE.json"
    if state_path.exists():
        block = _canvas_from_state(state_path)
        if block is not None:
            return block

    # Fall back to the @page rule. canvas.py returns inches; the report
    # schema is in centimetres.
    parsed = _canvas.read_canvas_from_html(html_path)
    if parsed is not None:
        w_cm = round(parsed[0] * 2.54, 2)
        h_cm = round(parsed[1] * 2.54, 2)
        return {
            "source": "page-rule",
            "width_cm": w_cm,
            "height_cm": h_cm,
            "orientation": _orientation(w_cm, h_cm),
            "source_url": None,
        }

    # Neither source resolved -- be explicit, do not fabricate a size.
    return {
        "source": "unknown",
        "width_cm": None,
        "height_cm": None,
        "orientation": None,
        "source_url": None,
    }


def _canvas_from_state(state_path: Path) -> dict[str, Any] | None:
    """Pull a canvas block out of POSTER_STATE.json, defensively.

    The workflow owns POSTER_STATE.json's full shape; we only need the
    canvas. Accept either a nested ``{"canvas": {...}}`` object or the
    canvas fields at top level, and tolerate missing/garbage by returning
    ``None`` so the caller can fall through to the @page rule. A partial
    state (e.g. dimensions but no orientation) is completed where we can.
    """
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    canvas = data.get("canvas") if isinstance(data.get("canvas"), dict) else data
    width = canvas.get("width_cm")
    height = canvas.get("height_cm")
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        # No usable dimensions -> let the @page rule speak instead.
        return None

    orientation = canvas.get("orientation")
    if orientation not in ("landscape", "portrait"):
        orientation = _orientation(float(width), float(height))

    return {
        "source": canvas.get("source") or "poster-state",
        "width_cm": round(float(width), 2),
        "height_cm": round(float(height), 2),
        "orientation": orientation,
        "source_url": canvas.get("source_url"),
    }


# --------------------------------------------------------------------------
# Child-process gate invocation.
# --------------------------------------------------------------------------
def _run_child(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a gate as a subprocess, return ``(returncode, stdout, stderr)``.

    A child that cannot even start (e.g. its script file is missing, or
    the interpreter rejects it) is surfaced as return code 2 with the
    OSError text on stderr -- the same "environment error" code the
    children themselves use -- so the gate is marked SKIPPED rather than
    crashing the orchestrator.
    """
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:  # script missing, not executable, etc.
        return 2, "", f"failed to launch {ascii_safe(argv)}: {ascii_safe(exc)}"
    return proc.returncode, proc.stdout, proc.stderr


def _parse_json_gate(stdout: str) -> dict[str, Any] | None:
    """Parse a JSON-emitting gate's stdout (style / asset).

    Those gates write their structured verdict to a ``--json`` file, but
    we also accept JSON on stdout as a fallback. We scan from the LAST
    ``{`` so any leading human log lines don't poison the parse. Returns
    ``None`` when no JSON object is found.
    """
    start = stdout.rfind("{")
    if start == -1:
        return None
    candidate = stdout[start:]
    try:
        obj = json.loads(candidate)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _status_from_returncode(returncode: int, severity: str) -> str:
    """Map a child exit code to a gate status string.

    0 -> PASS, 1 -> FAIL (hard) / WARN (soft polish), 2 -> SKIPPED
    (environment error: missing playwright, missing script, etc.). The
    soft/hard distinction only matters at exit 1: a soft gate that exits
    1 *without* ``--strict`` would not have happened (it returns 0 on
    warnings), so an exit-1 polish under ``--strict-polish`` is a real
    FAIL; we still resolve via severity for safety.
    """
    if returncode == 0:
        return "PASS"
    if returncode == 1:
        return "FAIL" if severity == "hard" else "WARN"
    return "SKIPPED"


def _build_argv(
    gate: str,
    scripts_dir: Path,
    html_path: Path,
    opts: argparse.Namespace,
    report_json_dir: Path,
) -> list[str]:
    """Construct the exact argv for one gate.

    Script paths are resolved against ``scripts_dir`` (THIS file's
    directory) so the orchestrator is position-independent. The HTML is
    passed as an ABSOLUTE path because each child runs with cwd set to
    the HTML's directory and we don't want to assume the child re-derives
    it. Per-gate ``--json`` sidecar files (style / asset) are written
    next to the report so the full machine-readable trail lives together.
    """
    py = sys.executable
    html = str(html_path)

    if gate == "preflight":
        return [py, str(scripts_dir / "poster_check.py"), "preflight", html]

    if gate == "style":
        argv = [py, str(scripts_dir / "style_check.py"), html]
        if opts.tokens:
            argv += ["--tokens", str(Path(opts.tokens).resolve())]
        if opts.no_render:
            argv += ["--no-render"]
        argv += ["--json", str(report_json_dir / "style_check.json")]
        return argv

    if gate == "asset":
        argv = [py, str(scripts_dir / "asset_check.py"), html]
        # asset_check requires --manifest; pass through whatever we got
        # (its absence is the child's job to report as a hard FAIL).
        if opts.manifest:
            argv += ["--manifest", str(Path(opts.manifest).resolve())]
        if opts.waive_total_area:
            argv += ["--waive-total-area"]
        if opts.no_render:
            argv += ["--no-render"]
        argv += ["--json", str(report_json_dir / "asset_check.json")]
        return argv

    if gate == "measure":
        return [py, str(scripts_dir / "poster_check.py"), "measure", html]

    if gate == "polish":
        argv = [py, str(scripts_dir / "poster_check.py"), "polish", html]
        if opts.strict_polish:
            argv += ["--strict"]
        return argv

    raise ValueError(f"unknown gate: {gate}")  # pragma: no cover


def _summarize_gate(
    gate: str,
    returncode: int,
    stdout: str,
    stderr: str,
    report_json_dir: Path,
) -> tuple[str | dict[str, Any], list[str]]:
    """Build ``(summary, artifacts)`` for one finished gate.

    style / asset speak JSON, so we prefer their structured verdict
    (sidecar file first, then stdout). The vendored gates (preflight /
    measure / polish) have no machine format, so we keep a tail of their
    combined stdout+stderr -- that captures the ``[gate] PASS/FAIL``
    verdict line and any ``FAIL:`` lines, which is all a human needs to
    locate the failure without re-running.
    """
    artifacts: list[str] = []

    if gate in ("style", "asset"):
        sidecar = report_json_dir / f"{gate}_check.json"
        obj: dict[str, Any] | None = None
        if sidecar.exists():
            try:
                obj = json.loads(sidecar.read_text(encoding="utf-8"))
                artifacts.append(str(sidecar))
            except (OSError, ValueError):
                obj = None
        if obj is None:
            obj = _parse_json_gate(stdout)
        if obj is not None:
            return obj, artifacts
        # No JSON at all -> the gate likely failed to start; fall back to
        # the stderr/stdout tail so the report still says something useful.
        return _tail(stdout + "\n" + stderr), artifacts

    # Vendored gate: heuristic stdout/stderr tail + exit code.
    combined = (stdout + "\n" + stderr).strip()
    return {
        "exit_code": returncode,
        "tail": _tail(combined),
    }, artifacts


def run_gate(
    gate: str,
    scripts_dir: Path,
    html_path: Path,
    opts: argparse.Namespace,
    report_json_dir: Path,
) -> dict[str, Any]:
    """Run one gate and return its report entry (DESIGN_FINAL §7 shape)."""
    severity = GATE_SEVERITY[gate]
    argv = _build_argv(gate, scripts_dir, html_path, opts, report_json_dir)
    returncode, stdout, stderr = _run_child(argv, cwd=html_path.parent)
    status = _status_from_returncode(returncode, severity)
    summary, artifacts = _summarize_gate(
        gate, returncode, stdout, stderr, report_json_dir
    )
    return {
        "name": gate,
        "severity": severity,
        "status": status,
        "command": argv,
        "summary": summary,
        "artifacts": artifacts,
    }


# --------------------------------------------------------------------------
# Orchestration.
# --------------------------------------------------------------------------
def run_all(html_path: Path, opts: argparse.Namespace) -> dict[str, Any]:
    """Run the canonical gate sequence and assemble the GATE_REPORT dict."""
    scripts_dir = Path(__file__).resolve().parent
    report_path = (
        Path(opts.report).resolve()
        if opts.report
        else html_path.parent / "GATE_REPORT.json"
    )
    # Sidecar JSON (style/asset --json) lands next to the report.
    report_json_dir = report_path.parent

    gates: list[dict[str, Any]] = []
    hard_failures = 0
    warnings = 0

    for gate in CANONICAL_ORDER:
        entry = run_gate(gate, scripts_dir, html_path, opts, report_json_dir)
        gates.append(entry)
        is_hard = entry["severity"] == "hard"
        if entry["status"] == "FAIL" and is_hard:
            hard_failures += 1
            if opts.fail_fast:
                # Stop scheduling further gates; mark the rest SKIPPED so
                # the report still enumerates the full canonical sequence.
                gates.extend(_skipped_remainder(gate))
                break
        elif entry["status"] == "WARN":
            warnings += 1
        # A soft polish FAIL only happens under --strict-polish, where it
        # counts as a hard failure for `overall`.
        if entry["status"] == "FAIL" and not is_hard:
            hard_failures += 1
            if opts.fail_fast:
                gates.extend(_skipped_remainder(gate))
                break

    overall = "PASS" if hard_failures == 0 else "FAIL"

    return {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "timestamp": _now_iso(),
        "poster_html": str(html_path),
        "canvas": resolve_canvas(html_path),
        "overall": overall,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "gates": gates,
    }


def _skipped_remainder(stopped_at: str) -> list[dict[str, Any]]:
    """Build SKIPPED entries for every gate after ``stopped_at``.

    Under ``--fail-fast`` we abort the run on the first hard failure but
    still want the report to list the full canonical sequence, with the
    not-run gates explicitly marked SKIPPED (reason: fail-fast) rather
    than silently absent.
    """
    idx = CANONICAL_ORDER.index(stopped_at)
    out: list[dict[str, Any]] = []
    for gate in CANONICAL_ORDER[idx + 1:]:
        out.append({
            "name": gate,
            "severity": GATE_SEVERITY[gate],
            "status": "SKIPPED",
            "command": [],
            "summary": {"skipped": "fail-fast: a prior hard gate failed"},
            "artifacts": [],
        })
    return out


def _print_human_summary(report: dict[str, Any]) -> None:
    """Print a compact human-readable digest to stdout alongside the JSON
    file write, so a terminal run isn't silent."""
    print(f"[run_gates] {ascii_safe(report['poster_html'])}")
    canvas = report["canvas"]
    if canvas["width_cm"] is not None:
        print(
            f"  canvas: {canvas['width_cm']} x {canvas['height_cm']} cm "
            f"{canvas['orientation']} (source: {canvas['source']})"
        )
    else:
        print(f"  canvas: UNRESOLVED (source: {canvas['source']})")
    for g in report["gates"]:
        print(f"  {g['name']:9s} [{g['severity']:4s}] -> {g['status']}")
    print(
        f"  overall: {report['overall']}   "
        f"hard_failures: {report['hard_failures']}   "
        f"warnings: {report['warnings']}"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_gates",
        description=(
            "Run the canonical poster gate sequence "
            "(preflight -> style -> asset -> measure -> polish) and write "
            "GATE_REPORT.json. Default accumulates all results; "
            "--fail-fast stops at the first hard failure."
        ),
    )
    p.add_argument("html", help="path to poster.html")
    p.add_argument(
        "--report", default=None,
        help="output GATE_REPORT.json path "
             "(default: GATE_REPORT.json next to the HTML)",
    )
    p.add_argument(
        "--fail-fast", action="store_true",
        help="stop at the first HARD failure instead of accumulating "
             "the full fix surface",
    )
    p.add_argument(
        "--strict-polish", action="store_true",
        help="treat polish warnings as failures "
             "(maps to poster_check.py polish --strict)",
    )
    p.add_argument(
        "--tokens", default=None,
        help="design tokens JSON, passed through to style_check.py",
    )
    p.add_argument(
        "--manifest", default=None,
        help="FIGURE_MANIFEST.json, passed through to asset_check.py "
             "(its absence makes the asset gate hard-fail)",
    )
    p.add_argument(
        "--waive-total-area", action="store_true",
        help="theory-paper waiver, passed through to asset_check.py",
    )
    p.add_argument(
        "--no-render", action="store_true",
        help="skip render-dependent checks; passed through to "
             "style_check.py / asset_check.py (their render rules degrade "
             "to SKIPPED / natural-size estimates)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        _eprint(f"ERROR: HTML not found: {ascii_safe(html_path)}")
        return 2

    report = run_all(html_path, args)

    report_path = (
        Path(args.report).resolve()
        if args.report
        else html_path.parent / "GATE_REPORT.json"
    )
    try:
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        _eprint(f"ERROR: cannot write report {ascii_safe(report_path)}: "
                f"{ascii_safe(exc)}")
        return 2

    _print_human_summary(report)
    print(f"[run_gates] report -> {ascii_safe(report_path)}")

    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
