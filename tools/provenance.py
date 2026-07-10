#!/usr/bin/env python3
"""Provenance-as-authorization for ARIS auto-authored artifacts.

The primitive ARIS needs the MOMENT it auto-writes a skill / memory node: a
record of WHO authored an artifact and WHO acquitted it, so that (a) auto-curation
(meta-optimize, a future skill-curator) only ever touches MACHINE-authored
artifacts — never the hand-written canonical skills or the user's own notes — and
(b) it is provably true that no single model both wrote and approved an artifact.

This is the provenance-as-authorization-boundary pattern (adapted from
NousResearch/hermes-agent's skill_provenance ContextVar, MIT). ARIS's increment:
Hermes records only `created_by`, and its cross-model curator is OPTIONAL config
(defaults to the SAME chat model). ARIS records the RICHER tuple
{author_model, reviewer_model, verdict_id, content_hash}. Strict `stamp()` keeps
cross-family acceptance NON-NEGOTIABLE. Codex-only workflows may instead write
an explicit same-family `stamp_provisional()` receipt; it is traceable but never
authorizes future automatic curation. See shared-references/skill-governance.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Model-name → family. Vendor words match as substrings ("gpt5" → openai); the
# short, ambiguous o-series needles (_SHORT) match only as EXACT tokens, so they
# can't substring-bleed into an unrelated name. ARIS routes oracle-pro to a
# GPT-Pro tier, so `oracle` is the OPENAI family (NOT a separate one) — getting
# this wrong would let oracle "cross-check" a GPT executor.
_FAMILY = [
    ("anthropic", ("claude", "opus", "sonnet", "haiku")),
    ("openai", ("gpt", "codex", "oracle", "chatgpt", "o1", "o3", "o4")),
    ("google", ("gemini", "palm", "bard")),
    ("deepseek", ("deepseek",)),
    ("minimax", ("minimax", "abab")),
    ("moonshot", ("kimi", "moonshot")),
    ("qwen", ("qwen", "tongyi")),
    ("xai", ("grok",)),
    ("meta", ("llama",)),
    ("mistral", ("mistral", "mixtral")),
]
_SHORT = {"o1", "o3", "o4"}  # ambiguous → exact-token match only


def model_family(name: str) -> str:
    """Map a model/reviewer name to a coarse family ('unknown' if unrecognized).

    A 'deterministic:<verifier>' reviewer maps to 'deterministic' — a verifier is
    a process, not a model family, and is always a valid cross-check.

    Fails closed on COLLISION: a name that matches TWO families' needles (e.g. a
    mislabeled 'claude-gpt-4') returns 'unknown' rather than letting first-match-wins
    silently pick one — so a colliding name can never slip through assert_cross_family
    as a (wrong) cross-family pair; it raises instead.
    """
    n = (name or "").strip().lower()
    if n.startswith("deterministic:") or n == "deterministic":
        return "deterministic"
    tokens = set(re.split(r"[^a-z0-9.]+", n))
    matched = set()
    for fam, needles in _FAMILY:
        if any((k in tokens) if k in _SHORT else (k in n) for k in needles):
            matched.add(fam)
    return next(iter(matched)) if len(matched) == 1 else "unknown"


def assert_cross_family(author_model: str, reviewer_model: str) -> None:
    """Raise unless the reviewer is a different model family than the author (or a
    deterministic verifier). This is the structural cross-model invariant — a
    same-family acquittal is forbidden, and an unrecognized family fails closed."""
    fr = model_family(reviewer_model)
    if fr == "deterministic":
        return
    fa = model_family(author_model)
    if fa == "unknown" or fr == "unknown":
        raise ValueError(
            f"unrecognized model family for author={author_model!r} ({fa}) / "
            f"reviewer={reviewer_model!r} ({fr}) — cannot assert the cross-model "
            f"invariant; use a recognized reviewer or a 'deterministic:<verifier>'.")
    if fa == fr:
        raise ValueError(
            f"author ({author_model}={fa}) and reviewer ({reviewer_model}={fr}) are "
            f"the SAME model family — self-acquittal is forbidden. The reviewer must "
            f"be a different family (e.g. executor=Claude → reviewer=codex/gemini) "
            f"or a deterministic verifier.")


def content_hash(path: str) -> str:
    """SHA-256 of the file at `path` (tamper-evident anchor for the provenance)."""
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def _sidecar(target: str) -> Path:
    p = Path(target)
    return (p / ".provenance.json") if p.is_dir() else p.with_name(p.name + ".provenance.json")


def _stamp_record(target: str, author_model: str, reviewer_model: str,
                  verdict_id: str, review_independence: str,
                  acceptance_status: str, created_by: str,
                  ts: Optional[str]) -> dict:
    if not verdict_id:
        raise ValueError("provenance requires a non-empty verdict_id (the reviewer's "
                         "thread/trace id, or the verifier report path/sha).")
    p = Path(target)
    hash_target = (p / "SKILL.md") if p.is_dir() and (p / "SKILL.md").is_file() else p
    record = {
        "created_by": created_by,
        "author_model": author_model,
        "author_family": model_family(author_model),
        "reviewer_model": reviewer_model,
        "reviewer_family": model_family(reviewer_model),
        "review_independence": review_independence,
        "acceptance_status": acceptance_status,
        "verdict_id": verdict_id,
        "content_hash": content_hash(str(hash_target)) if hash_target.is_file() else None,
        "stamped_at": ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _sidecar(target).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def stamp(target: str, author_model: str, reviewer_model: str, verdict_id: str,
          created_by: str = "aris-auto", ts: Optional[str] = None) -> dict:
    """Record accepted provenance for an auto-authored artifact.

    REFUSES (raises) if author and reviewer are the same model family, or if the
    verdict id is empty. Deterministic reviewers remain valid acceptance gates.
    """
    assert_cross_family(author_model, reviewer_model)
    independence = (
        "deterministic"
        if model_family(reviewer_model) == "deterministic"
        else "cross-family"
    )
    return _stamp_record(
        target, author_model, reviewer_model, verdict_id,
        independence, "accepted", created_by, ts,
    )


def stamp_provisional(target: str, author_model: str, reviewer_model: str,
                      verdict_id: str, created_by: str = "aris-auto",
                      ts: Optional[str] = None) -> dict:
    """Record an explicit same-family review without granting acceptance.

    Both model names must resolve to the same non-deterministic family. A
    different-family reviewer must use :func:`stamp`; unknown model families
    fail closed so a provisional receipt cannot conceal ambiguous provenance.
    """
    author_family = model_family(author_model)
    reviewer_family = model_family(reviewer_model)
    if author_family == "unknown" or reviewer_family == "unknown":
        raise ValueError(
            f"unrecognized model family for provisional author={author_model!r} "
            f"({author_family}) / reviewer={reviewer_model!r} ({reviewer_family})")
    if reviewer_family == "deterministic" or author_family != reviewer_family:
        raise ValueError(
            "stamp_provisional is only for same-family model review; use stamp "
            "for a cross-family or deterministic acceptance gate.")
    # MONOTONIC: a provisional receipt must never silently replace an accepted
    # one — acceptance can only be superseded by a new accepted stamp.
    existing = read(target)
    if existing and _record_is_accepted(existing):
        raise ValueError(
            "refusing to overwrite an ACCEPTED provenance record with a "
            "provisional one (acceptance is monotonic; re-run the cross-family "
            "gate via stamp() if the artifact changed).")
    return _stamp_record(
        target, author_model, reviewer_model, verdict_id,
        "same-family", "provisional", created_by, ts,
    )


def read(target: str) -> Optional[dict]:
    sc = _sidecar(target)
    return json.loads(sc.read_text(encoding="utf-8")) if sc.exists() else None


def is_auto_authored(target: str) -> bool:
    """True iff the artifact has a provenance record marking it machine-authored.
    Auto-curation (meta-optimize etc.) may ONLY touch artifacts where this is True —
    canonical hand-written skills and user notes have no such record and are off-limits."""
    rec = read(target)
    return bool(rec and rec.get("created_by") == "aris-auto")


def _record_is_accepted(rec: dict) -> bool:
    """A record counts as ACCEPTED only when its own stored fields survive
    re-verification — a sidecar is plain JSON on disk, so nothing in it is
    trusted at face value:

    - families are RECOMPUTED from the stored model names (a hand-edited
      ``reviewer_family`` cannot fake independence);
    - the recomputed pair must be cross-family or reviewer-deterministic;
    - ``acceptance_status`` must be explicitly "accepted", or absent
      (legacy record — those predate the field but were only creatable via the
      strict cross-family stamp(), and the recomputation above re-checks that);
    - ``review_independence``, when present, must agree ("cross-family");
    - ``verdict_id`` must be non-empty.
    """
    if not isinstance(rec, dict):
        return False
    if rec.get("acceptance_status", None) not in ("accepted", None):
        return False
    if rec.get("review_independence") not in (None, "cross-family"):
        return False
    if not str(rec.get("verdict_id") or "").strip():
        return False
    author_family = model_family(str(rec.get("author_model") or ""))
    reviewer_family = model_family(str(rec.get("reviewer_model") or ""))
    if reviewer_family == "deterministic":
        return True
    return ("unknown" not in (author_family, reviewer_family)
            and author_family != reviewer_family)


def is_auto_curatable(target: str) -> bool:
    """Whether an auto-authored artifact carries accepted authorization that
    still HOLDS. Beyond :func:`_record_is_accepted` (fields re-verified, never
    trusted), the stored ``content_hash`` must match the CURRENT artifact — a
    stamp for a file that has since been edited authorizes nothing. Explicit
    provisional records are never sufficient authorization for automatic
    rewrites."""
    rec = read(target)
    if not (rec and rec.get("created_by") == "aris-auto" and _record_is_accepted(rec)):
        return False
    p = Path(target)
    hash_target = (p / "SKILL.md") if p.is_dir() and (p / "SKILL.md").is_file() else p
    if not hash_target.is_file():
        return False
    stored = rec.get("content_hash")
    return bool(stored) and stored == content_hash(str(hash_target))


__all__ = [
    "model_family", "assert_cross_family", "content_hash", "stamp",
    "stamp_provisional", "read", "is_auto_authored", "is_auto_curatable",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="ARIS provenance-as-authorization.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stamp"); s.add_argument("target"); s.add_argument("--author", required=True)
    s.add_argument("--reviewer", required=True); s.add_argument("--verdict-id", required=True)
    s = sub.add_parser("stamp-provisional"); s.add_argument("target"); s.add_argument("--author", required=True)
    s.add_argument("--reviewer", required=True); s.add_argument("--verdict-id", required=True)
    s = sub.add_parser("read"); s.add_argument("target")
    s = sub.add_parser("is-auto"); s.add_argument("target")
    s = sub.add_parser("check"); s.add_argument("--author", required=True); s.add_argument("--reviewer", required=True)
    a = ap.parse_args()
    try:
        if a.cmd == "stamp":
            print(json.dumps(stamp(a.target, a.author, a.reviewer, a.verdict_id), ensure_ascii=False, indent=2))
        elif a.cmd == "stamp-provisional":
            print(json.dumps(stamp_provisional(a.target, a.author, a.reviewer, a.verdict_id), ensure_ascii=False, indent=2))
        elif a.cmd == "read":
            rec = read(a.target)
            print(json.dumps(rec, ensure_ascii=False, indent=2) if rec else "no provenance record")
            return 0 if rec else 1
        elif a.cmd == "is-auto":
            ok = is_auto_authored(a.target)
            print("aris-auto" if ok else "not aris-auto (canonical/user — off-limits to auto-curation)")
            return 0 if ok else 1
        elif a.cmd == "check":
            assert_cross_family(a.author, a.reviewer)
            print(f"OK: {model_family(a.author)} ≠ {model_family(a.reviewer)} (cross-family)")
    except ValueError as e:
        print(f"REJECTED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
