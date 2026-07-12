#!/usr/bin/env python3
"""
forensics_gate.py — typed policy gate + append-only obligations ledger for the
/integrity-forensics launcher (Anti-Autoresearch integration).

Doctrine (cross-model design review, 2026-07-12):

- Anti-Autoresearch's verdict is preserved VERBATIM and never re-labeled. In
  particular `CLEAN_GIVEN_EVIDENCE` maps to `NO_NEW_BLOCKER` — "no flag found in
  the evidence at hand" — NEVER to PASS/accepted. A forensics sweep can raise
  flags; it cannot acquit anything (flags are computable, acquittals are not).
- Findings become APPEND-ONLY obligations. A re-run may add obligations; a
  finding that disappears from a later report NEVER auto-closes its obligation
  (an LLM asked to "make the flag go away" learns to reword the span faster
  than to fix the number). A vanished, unresolved obligation is marked
  `UNRESOLVED_DISAPPEARANCE` — deterministically recorded, not an accusation.
- Closure is an explicit, evidence-bearing act: `resolve` (typed fix + evidence
  file hashed at closure time + who verified) or `waive` (human sign-off; a
  waiver is never a resolution and never rewrites the original finding).

Gate policy (fixed):
  upstream HARD_FLAGS          → BLOCK
  upstream REVIEW_UNAVAILABLE  → BLOCK   (an incomplete sweep cannot wave a paper through)
  any OPEN critical obligation → BLOCK
  upstream SOFT_FLAGS          → WARN    (human disposition)
  any OPEN obligation          → WARN
  otherwise                    → NO_NEW_BLOCKER

Pure stdlib. Artifacts:
  <paper>/.aris/forensics/gate.json          (one per run; overwritten)
  <paper>/.aris/forensics/obligations.json   (append-only ledger; never pruned)
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

GATE_VERSION = "1"
AUDITOR_FAMILY = "openai"   # Anti-AR's reviewer pins are GPT-family by upstream contract

BLOCK = "BLOCK"
WARN = "WARN"
NO_NEW_BLOCKER = "NO_NEW_BLOCKER"

FIX_TYPES = ("corrected-from-results", "claim-narrowed", "claim-withdrawn",
             "citation-replaced")

_FAMILY_NEEDLES = [
    ("anthropic", ("claude", "opus", "sonnet", "haiku")),
    ("openai", ("gpt", "codex", "oracle", "chatgpt", "o1", "o3", "o4")),
    ("google", ("gemini", "palm", "bard")),
]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm_ws(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _executor_family(name):
    n = (name or "").strip().lower()
    hits = {fam for fam, needles in _FAMILY_NEEDLES if any(x in n for x in needles)}
    return next(iter(hits)) if len(hits) == 1 else "unknown"


def _severity(f):
    return f.get("_severity_final") or f.get("severity") or "info"


def _is_obligation_bearing(f):
    """Weight-1, above-info findings become obligations. Zero-weight tracks
    (AIS/advisory) inform; they never gate."""
    if f.get("_verdict_weight", 1) != 1:
        return False
    return _severity(f) in ("critical", "major", "minor")


def fingerprint(f):
    """Stable identity of a finding ACROSS re-runs. Deliberately excludes
    finding_id (F001... is positional) and claim_id (positional in the ledger).
    Uses what survives an honest re-run: which auditor, which pattern, the
    verbatim evidence spans (whitespace-normalized), their artifact hashes and
    file locations."""
    ev = sorted(
        (_norm_ws(e.get("span")), e.get("artifact_hash") or "",
         ((e.get("location") or {}).get("file") or ""))
        for e in (f.get("evidence") or []) if isinstance(e, dict)
    )
    basis = json.dumps({"skill": f.get("skill"), "pattern_id": f.get("pattern_id"),
                        "evidence": ev}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def _forensics_dir(paper_dir):
    d = os.path.join(paper_dir, ".aris", "forensics")
    os.makedirs(d, exist_ok=True)
    return d


def _load_ledger(path):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("obligations"), list):
            raise SystemExit(f"FATAL: {path} is not an obligations ledger")
        return data
    return {"ledger_version": "1", "obligations": []}


def _save_ledger(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def cmd_update(args):
    """Fold a fresh report into the ledger. APPEND-ONLY: new findings open new
    obligations; existing ones are untouched; OPEN obligations whose fingerprint
    is absent from this report gain an UNRESOLVED_DISAPPEARANCE note (they stay
    OPEN — disappearance is not resolution)."""
    with open(args.report, encoding="utf-8") as fh:
        report = json.load(fh)
    report_sha = _sha256_file(args.report)
    path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    ledger = _load_ledger(path)
    by_id = {o["obligation_id"]: o for o in ledger["obligations"]}

    current = {}
    for f in report.get("findings", []):
        if isinstance(f, dict) and _is_obligation_bearing(f):
            current[fingerprint(f)] = f

    opened = 0
    for fid, f in current.items():
        if fid in by_id:
            by_id[fid]["last_seen_report"] = report_sha
            by_id[fid].pop("unresolved_disappearance", None)
            continue
        ledger["obligations"].append({
            "obligation_id": fid,
            "status": "OPEN",
            "severity": _severity(f),
            "skill": f.get("skill"),
            "pattern_id": f.get("pattern_id"),
            "title": f.get("title", ""),
            "finding_snapshot": f,          # immutable record of the accusation
            "first_seen_report": report_sha,
            "last_seen_report": report_sha,
            "opened_at": _now(),
        })
        opened += 1

    vanished = 0
    for o in ledger["obligations"]:
        if o["status"] == "OPEN" and o["obligation_id"] not in current \
                and o.get("last_seen_report") != report_sha:
            o["unresolved_disappearance"] = {
                "noted_at": _now(), "absent_from_report": report_sha,
                "note": "finding no longer detected but obligation was never "
                        "resolved with evidence — disappearance is not resolution",
            }
            vanished += 1

    _save_ledger(path, ledger)
    print(f"obligations: +{opened} opened, {vanished} unresolved-disappearance, "
          f"{sum(1 for o in ledger['obligations'] if o['status'] == 'OPEN')} open total -> {path}")
    return 0


def cmd_resolve(args):
    if args.fix_type not in FIX_TYPES:
        raise SystemExit(f"FATAL: fix_type must be one of {FIX_TYPES}")
    if not os.path.isfile(args.evidence):
        raise SystemExit(f"FATAL: evidence file does not exist: {args.evidence} "
                         "(a resolution without evidence is a reworded flag)")
    if not (args.verified_by or "").strip():
        raise SystemExit("FATAL: --verified-by is required (family checker, fresh "
                         "cross-family review thread id, or a human)")
    path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    ledger = _load_ledger(path)
    for o in ledger["obligations"]:
        if o["obligation_id"] == args.obligation_id:
            if o["status"] != "OPEN":
                raise SystemExit(f"FATAL: obligation is {o['status']}, not OPEN")
            o["status"] = "RESOLVED"
            o["resolution"] = {
                "fix_type": args.fix_type,
                "evidence_path": args.evidence,
                "evidence_sha256": _sha256_file(args.evidence),
                "verified_by": args.verified_by,
                "resolved_at": _now(),
            }
            _save_ledger(path, ledger)
            print(f"resolved {args.obligation_id} ({args.fix_type})")
            return 0
    raise SystemExit(f"FATAL: no obligation {args.obligation_id}")


def cmd_waive(args):
    if not (args.approver or "").strip() or not (args.reason or "").strip():
        raise SystemExit("FATAL: waive requires --approver (a HUMAN) and --reason")
    path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    ledger = _load_ledger(path)
    for o in ledger["obligations"]:
        if o["obligation_id"] == args.obligation_id:
            if o["status"] != "OPEN":
                raise SystemExit(f"FATAL: obligation is {o['status']}, not OPEN")
            o["status"] = "WAIVED"     # a waiver is NOT a resolution
            o["waiver"] = {"approver": args.approver, "reason": args.reason,
                           "waived_at": _now()}
            _save_ledger(path, ledger)
            print(f"waived {args.obligation_id} (approver: {args.approver})")
            return 0
    raise SystemExit(f"FATAL: no obligation {args.obligation_id}")


def cmd_gate(args):
    with open(args.report, encoding="utf-8") as fh:
        report = json.load(fh)
    verdict = report.get("overall_verdict", "")
    path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    ledger = _load_ledger(path) if os.path.isfile(path) else {"obligations": []}
    open_obl = [o for o in ledger["obligations"] if o.get("status") == "OPEN"]
    open_critical = [o for o in open_obl if o.get("severity") == "critical"]

    if verdict in ("HARD_FLAGS", "REVIEW_UNAVAILABLE") or open_critical:
        decision = BLOCK
    elif verdict == "SOFT_FLAGS" or open_obl:
        decision = WARN
    elif verdict == "CLEAN_GIVEN_EVIDENCE":
        decision = NO_NEW_BLOCKER
    else:
        decision = BLOCK   # unknown verdict token: fail closed

    exec_family = _executor_family(args.executor_model)
    claims = os.path.join(args.paper_dir, "claims.json")
    gate = {
        "gate_version": GATE_VERSION,
        "generated_at": _now(),
        # the upstream verdict, VERBATIM — this gate never re-labels it
        "upstream_verdict": verdict,
        "upstream_adjudicator": report.get("adjudicator", ""),
        "policy_decision": decision,
        "anti_ar_commit": args.anti_ar_commit,
        "report_sha256": _sha256_file(args.report),
        "ledger_sha256": _sha256_file(claims) if os.path.isfile(claims) else None,
        "observability_level": report.get("observability_level"),
        "coverage": report.get("coverage", {}),
        "open_obligations": len(open_obl),
        "open_critical_obligations": len(open_critical),
        # honest provenance: the sweep's auditors are GPT-family. For a Claude
        # executor that is cross-family PROPOSAL provenance; for a Codex executor
        # it is same-family. Either way this gate only raises flags — it records
        # provenance, it does not (cannot) grant acceptance.
        "executor_model": args.executor_model,
        "proposal_provenance": ("cross-family" if exec_family not in (AUDITOR_FAMILY, "unknown")
                                else ("same-family" if exec_family == AUDITOR_FAMILY
                                      else "unknown")),
    }
    out = os.path.join(_forensics_dir(args.paper_dir), "gate.json")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(gate, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, out)
    print(f"forensics gate: {decision} (upstream: {verdict or '(missing)'}; "
          f"open obligations: {len(open_obl)}, critical: {len(open_critical)}) -> {out}")
    return 0 if decision != BLOCK else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Typed gate + obligations for /integrity-forensics.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gate", help="compute the policy decision from an Anti-AR report")
    g.add_argument("--report", required=True)
    g.add_argument("--paper-dir", required=True)
    g.add_argument("--anti-ar-commit", required=True,
                   help="the SHA-pin the launcher ran (provenance)")
    g.add_argument("--executor-model", default="claude",
                   help="the pipeline's executor, for honest provenance labeling")

    u = sub.add_parser("update", help="fold a report's findings into the append-only ledger")
    u.add_argument("--report", required=True)
    u.add_argument("--paper-dir", required=True)

    r = sub.add_parser("resolve", help="close ONE obligation with typed, hashed evidence")
    r.add_argument("--paper-dir", required=True)
    r.add_argument("--obligation-id", required=True)
    r.add_argument("--fix-type", required=True)
    r.add_argument("--evidence", required=True)
    r.add_argument("--verified-by", required=True)

    w = sub.add_parser("waive", help="human-approved waiver (never a resolution)")
    w.add_argument("--paper-dir", required=True)
    w.add_argument("--obligation-id", required=True)
    w.add_argument("--approver", required=True)
    w.add_argument("--reason", required=True)

    a = ap.parse_args(argv)
    return {"gate": cmd_gate, "update": cmd_update,
            "resolve": cmd_resolve, "waive": cmd_waive}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
