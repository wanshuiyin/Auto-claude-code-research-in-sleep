#!/usr/bin/env python3
"""Deterministic evidence pre-check for ARIS claim audits.

Before spending a cross-model (codex) call to judge whether a claim is supported,
mechanically verify the claim's CITED EVIDENCE actually exists: does the source
file exist, and does the cited number/string actually appear in it? This catches
HALLUCINATED evidence ("claim X is supported by results/eval.json: 73.2") for
free — no model call — and downgrades unverifiable claims before the jury sees
them.

This is the reconcile pattern (a model's self-report cross-checked against
mechanical ground-truth, adapted from NousResearch/hermes-agent's curator
reconcile-classifier) made into a two-stage gate:

    stage 1 (this file)  deterministic. Catches HALLUCINATION — the cited path
                         is missing, or the cited value is not in the source.
                         Cheap, no model, fail-closed (favors false-negative).
    stage 2 (the jury)   cross-model (codex/gemini). Catches WRONG-BUT-REAL — the
                         number IS in the file, but it doesn't support the claim.

A `verified` here means ONLY "the cited evidence exists" — NOT "the claim is
correct." Existence is execution-completeness (safe same-model / deterministic);
support is a quality verdict that stays with the cross-model jury
(acceptance-gate.md: drive, not acquit). The numeric matcher is deliberately
conservative — it must NEVER emit a false `verified`. It uses an ALLOW-LIST of
safe boundaries, so a number that is part of a compound construct
(date/time/version/fraction/locale grouping, or flanked by any non-ASCII
delimiter such as a Unicode minus/dash) fails closed and goes to the jury. See
shared-references/evidence-precheck.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List

# The numeric core: optional sign; an integer (with optional comma-grouping like
# 1,000), or a plain int, or a leading-decimal (.5) / trailing-decimal (1.);
# optional scientific exponent.
_NUM_CORE = r"[+-]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"

# Boundary policy: ALLOW-LIST, fail-closed. A number token is matchable only when
# flanked by KNOWN-SAFE boundaries — string start/end, whitespace (`\s`, which
# includes Unicode spaces like NBSP / thin space), or a small ASCII punctuation
# set. ANY OTHER adjacency — a digit, a Unicode minus/dash (− – —), ':' '/' '-',
# fullwidth punctuation, a locale grouping separator — is not a safe boundary, so
# the token fails closed to the jury. A false negative is cheap (the jury reads
# the file); a false `verified` is the bug this gate must never have. (Quote chars
# are written \x22 / \x27 to avoid Python string-termination issues.)
_BEFORE_OK = r"\s=(\[{\x22"          # allowed immediately before (or string start); \x22 = "
_AFTER_OK = r"\s)\]}\x22;,."         # allowed immediately after (or string end)
# NB: apostrophe (') is deliberately NOT a safe boundary — it is a Swiss/locale
# thousands separator (1'000), so a number adjacent to it fails closed.
_NUM_TOKEN_RE = re.compile(
    r"(?<![^" + _BEFORE_OK + r"])"   # at start, or preceded by a safe char
    r"(" + _NUM_CORE + r")(%?)"
    r"(?=[" + _AFTER_OK + r"]|$)"     # at end, or followed by a safe char
    r"(?![.,]\d)"                     # a trailing . or , must be sentence, not a decimal/sep
)
# Whitespace-grouping ("1 000", "1  234", "1\n234" — any run of any whitespace) is
# checked POST-MATCH in _value_in_text, because a fixed-width lookbehind cannot
# cover one-or-more whitespace.
_WS_GROUP_TAIL = re.compile(r"\d\s+$")              # <digit><ws+> immediately before a token
_WS_GROUP_LEAD = re.compile(r"\s+\d{3}(?!\d)")       # <ws+><exactly 3 digits> immediately after
# A grouping TAIL token is a 3-digit group, optionally carrying the final decimal
# ("234" in "1 234", or "234.5" in "1 234.5") — but NOT "2345" (4 digits).
_GROUP_TAIL_TOK = re.compile(r"\d{3}(?:\.\d+)?")
_PURE_NUMBER_RE = re.compile(_NUM_CORE)


def _dec(s: str) -> Decimal:
    """Decimal of a numeric string, ignoring thousands separators. Raises InvalidOperation."""
    return Decimal(s.replace(",", "").strip())


def _pure_number(s: str):
    """If `s` is exactly a number (optional thousands grouping, optional trailing %),
    return (Decimal, has_percent); else None. Exact Decimal, no float tolerance."""
    v = s.strip()
    has_pct = v.endswith("%")
    core = v[:-1].strip() if has_pct else v
    if not _PURE_NUMBER_RE.fullmatch(core):
        return None
    try:
        return _dec(core), has_pct
    except InvalidOperation:
        return None


def _value_in_text(value: str, text: str) -> bool:
    """True if `value` is present in `text` — conservatively (never a false positive).

    PURE NUMBER (incl. scientific notation, thousands grouping, .5/1. forms,
    optional trailing %): EXACT decimal equality against safely-bounded number
    tokens, with percent-flag consistency. Fails closed on compound constructs
    (dates/times/versions/fractions/locale grouping) and any non-ASCII delimiter.
    NON-NUMERIC / mixed (e.g. "4-point gain", "SOTA on COCO"): normalized-whitespace
    substring of the literal value. An empty value never matches.
    """
    if not value.strip():
        return False
    pn = _pure_number(value)
    if pn is not None:
        dval, want_pct = pn
        for m in _NUM_TOKEN_RE.finditer(text):
            tok = m.group(1)
            # Fail closed on whitespace-grouped numbers: an exactly-3-digit token
            # preceded by <digit><ws+> is a grouping tail; any token followed by
            # <ws+><exactly 3 digits> is a grouping head/middle.
            if _GROUP_TAIL_TOK.fullmatch(tok) and _WS_GROUP_TAIL.search(text[:m.start()]):
                continue
            if _WS_GROUP_LEAD.match(text[m.end():]):
                continue
            try:
                tnum = _dec(tok)
            except InvalidOperation:
                continue
            if tnum == dval and bool(m.group(2)) == want_pct:
                return True
        return False
    norm = re.sub(r"\s+", " ", text)
    return value.strip() in norm


def _resolve_sources(source: str, root: str) -> List[Path]:
    base = Path(root)
    p = base / source
    if p.is_file():
        return [p]
    matches = sorted(base.glob(source))  # treat as a glob relative to root
    return [m for m in matches if m.is_file()]


def check_claim(value: str, source: str, root: str = ".") -> dict:
    """Verify a cited (value, source) pair deterministically.

    status ∈ {"verified", "path_missing", "value_not_found"}.
    `verified` means only that the cited evidence EXISTS — not that the claim holds.
    """
    files = _resolve_sources(source, root)
    if not files:
        return {"status": "path_missing", "value": value, "source": source,
                "detail": f"no file matches {source!r} under {root!r}"}
    read_any = False
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # skip an unreadable file, keep checking the rest
        read_any = True
        if _value_in_text(value, text):
            return {"status": "verified", "value": value, "source": str(f),
                    "detail": f"{value!r} found in {f}"}
    if not read_any:
        return {"status": "path_missing", "value": value, "source": source,
                "detail": f"file(s) matching {source!r} exist but are unreadable"}
    return {"status": "value_not_found", "value": value, "source": source,
            "detail": f"{value!r} not found in {source!r} "
                      f"({len(files)} file(s) checked) — send to the cross-model jury"}


def check_batch(claims: List[dict], root: str = ".") -> dict:
    """claims: [{"id"?, "value", "source", ...}]. Returns per-claim results + a summary.

    A claim with no usable (value, source) is reported `unparseable` — not checkable
    here; the jury handles it. `value is None` (not falsy) so a legit numeric 0 is
    still checked; empty strings are unparseable.
    """
    results = []
    for c in claims:
        value, source = c.get("value"), c.get("source")
        if value is None or source is None or str(value).strip() == "" or str(source).strip() == "":
            results.append({**c, "status": "unparseable",
                            "detail": "claim has no usable (value, source) to pre-check"})
        else:
            results.append({**c, **check_claim(str(value), str(source), root)})
    counts: dict = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"results": results, "summary": counts}


__all__ = ["check_claim", "check_batch"]


def main() -> int:
    ap = argparse.ArgumentParser(description="ARIS deterministic evidence pre-check.")
    ap.add_argument("root", help="project root the sources are relative to")
    ap.add_argument("--value", help="the cited value (number/string)")
    ap.add_argument("--source", help="the cited source file or glob (relative to root)")
    ap.add_argument("--batch", help="JSON file with a list of {value, source, ...} claims")
    a = ap.parse_args()
    if a.batch:
        claims = json.loads(Path(a.batch).read_text(encoding="utf-8"))
        out = check_batch(claims, a.root)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        bad = {"path_missing", "value_not_found"}
        return 1 if any(r["status"] in bad for r in out["results"]) else 0
    if not a.value or not a.source:
        ap.error("provide --value and --source, or --batch")
    res = check_claim(a.value, a.source, a.root)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
