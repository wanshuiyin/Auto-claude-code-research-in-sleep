#!/usr/bin/env python3
"""iteration_log.py — overnight-loop stall detection → forced structural pivot.

Append-only per-iteration ledger for an unattended research loop. Each tick the
orchestrator records how many NEW findings the iteration produced — where a "finding"
is a concrete added entry (new evidence, a falsified hypothesis, a candidate direction),
NOT a subjective "valuable result". Consecutive zero-finding iterations accumulate a
stale_count, which drives a forced pivot:

  stale_count >= 2  → pivot = "structural"  (change a STRUCTURAL constraint, not tactical params)
  stale_count >= 4  → pivot = "human"        (flag for human attention)

This is a **Type-A signal**: it COUNTS entries and changes *direction*; it does NOT judge
quality — quality/correctness stays with the cross-model jury (shared-references/
acceptance-gate.md). It only ever says "keep going / change direction," never "good enough".

The ledger is a sidecar at `.aris/runs/<run_id>.iterations.jsonl`; it deliberately does
NOT import or touch run_state.py's done/accepted state machine (only shares the `.aris/runs/`
dir, with a distinct `.iterations.jsonl` suffix). An optional `direction` per record lets
the loop's re-generation step reject candidates too close to a tried direction. See
shared-references/external-cadence.md → "Stall detection & forced structural pivot".

Usage:
    python3 iteration_log.py note <root> <run_id> <phase> <new_findings> [--direction "..."]
    python3 iteration_log.py show <root> <run_id>
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore

PIVOT_STRUCTURAL_AT = 2   # consecutive zero-finding iterations → force a structural pivot
ESCALATE_HUMAN_AT = 4     # still stalled → flag for human attention


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_path(root: str, run_id: str) -> Path:
    # Same run_id discipline as run_state.py: no path escape.
    safe = "".join(c for c in run_id if c.isalnum() or c in "-_.")
    if not safe or safe != run_id or run_id in (".", ".."):
        raise ValueError(f"invalid run_id {run_id!r} (use [A-Za-z0-9-_.])")
    return Path(root) / ".aris" / "runs" / f"{run_id}.iterations.jsonl"


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    """Best-effort advisory lock (single-orchestrator contract; guards a stray resumer)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        yield
        return
    fh = open(path.with_suffix(".jsonl.lock"), "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            fh.close()


def _last_stale(path: Path) -> int:
    """Read the most recent stale_count from the append-only ledger (0 if none)."""
    if not path.is_file():
        return 0
    last = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                last = int(json.loads(line).get("stale_count", last))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue  # tolerate a partial/garbled line, keep the last good count
    except OSError:
        return 0
    return last


def pivot_for(stale_count: int) -> str:
    if stale_count >= ESCALATE_HUMAN_AT:
        return "human"
    if stale_count >= PIVOT_STRUCTURAL_AT:
        return "structural"
    return "none"


def note(root: str, run_id: str, phase: str, new_findings: int,
         direction: Optional[str] = None) -> dict:
    """Record one iteration; return {stale_count, pivot}. Append-only; never blocks work."""
    new_findings = int(new_findings)
    if new_findings < 0:
        raise ValueError(f"new_findings must be >= 0, got {new_findings}")
    path = _log_path(root, run_id)
    with _lock(path):
        stale_count = 0 if new_findings > 0 else _last_stale(path) + 1
        pivot = pivot_for(stale_count)
        rec = {"ts": _now(), "phase": phase, "new_findings": new_findings,
               "stale_count": stale_count, "pivot": pivot}
        if direction is not None:
            rec["direction"] = direction
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"stale_count": stale_count, "pivot": pivot}


def show(root: str, run_id: str) -> str:
    path = _log_path(root, run_id)
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="overnight-loop stall detection → forced structural pivot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("note")
    n.add_argument("root"); n.add_argument("run_id"); n.add_argument("phase")
    n.add_argument("new_findings", type=int); n.add_argument("--direction", default=None)
    s = sub.add_parser("show"); s.add_argument("root"); s.add_argument("run_id")
    a = ap.parse_args()
    if a.cmd == "note":
        print(json.dumps(note(a.root, a.run_id, a.phase, a.new_findings, a.direction)))
    elif a.cmd == "show":
        sys.stdout.write(show(a.root, a.run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
