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
import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

try:
    import fcntl  # POSIX
except ImportError:  # pragma: no cover
    fcntl = None

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
    """Stable identity of a finding ACROSS re-runs. Deliberately excludes:
    finding_id (F001... is positional), claim_id (positional in the ledger),
    and artifact_hash (upstream hashes the WHOLE source file, so any unrelated
    edit to the same .tex would re-identify every finding in it — duplicating
    obligations on honest revisions). Identity = which auditor, which pattern,
    the verbatim evidence spans (whitespace-normalized), and their file paths;
    artifact hashes remain recorded on each observation as provenance."""
    ev = sorted(
        (_norm_ws(e.get("span")),
         os.path.normpath((e.get("location") or {}).get("file") or ""))
        for e in (f.get("evidence") or []) if isinstance(e, dict)
    )
    basis = json.dumps({"skill": f.get("skill"), "pattern_id": f.get("pattern_id"),
                        "evidence": ev}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def _forensics_dir(paper_dir):
    d = os.path.join(paper_dir, ".aris", "forensics")
    os.makedirs(d, exist_ok=True)
    return d


SEV_RANK = {"minor": 1, "major": 2, "critical": 3}


@contextlib.contextmanager
def _ledger_lock(paper_dir):
    """One lock around every load→mutate→save transaction — concurrent
    update/resolve/waive must never lose records (append-only is a promise)."""
    lock_path = os.path.join(_forensics_dir(paper_dir), ".ledger.lock")
    fh = open(lock_path, "w")
    try:
        if fcntl is not None:
            fcntl.flock(fh, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _load_ledger(path):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("obligations"), list):
            raise SystemExit(f"FATAL: {path} is not an obligations ledger")
        return data
    return {"ledger_version": "1", "obligations": []}


def _save_ledger(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _load_report_strict(path):
    """A report that cannot be parsed into the expected shape must fail CLOSED —
    never fall through to a permissive gate."""
    try:
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
    except Exception as e:
        raise SystemExit(f"FATAL: cannot parse report {path}: {type(e).__name__}")
    if not isinstance(report, dict):
        raise SystemExit(f"FATAL: report {path} is not a JSON object")
    findings = report.get("findings")
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        raise SystemExit(f"FATAL: report {path} has a non-list findings field")
    if not isinstance(report.get("overall_verdict", ""), str):
        raise SystemExit(f"FATAL: report {path} has a non-string overall_verdict")
    report["findings"] = [f for f in findings if isinstance(f, dict)]
    return report


def cmd_update(args):
    """Fold a fresh report into the ledger. APPEND-ONLY: new findings open new
    obligations; existing ones are untouched except for two escalations that can
    only move TOWARD caution — severity ratchets up to the historical max, and a
    RESOLVED obligation whose finding RECURS re-opens (the fix evidently didn't
    hold; the old resolution is archived, never erased). OPEN obligations whose
    fingerprint is absent from this report gain an UNRESOLVED_DISAPPEARANCE note
    (they stay OPEN — disappearance is not resolution). WAIVED stays closed
    (a human already dispositioned it)."""
    report = _load_report_strict(args.report)
    report_sha = _sha256_file(args.report)
    path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    ledger = _load_ledger(path)
    by_id = {o["obligation_id"]: o for o in ledger["obligations"]}

    current = {}
    for f in report["findings"]:
        if _is_obligation_bearing(f):
            current[fingerprint(f)] = f

    opened = reopened = 0
    for fid, f in current.items():
        if fid in by_id:
            o = by_id[fid]
            o["last_seen_report"] = report_sha
            o.pop("unresolved_disappearance", None)
            # severity ratchet: minor->critical escalates, never de-escalates
            new_sev, old_sev = _severity(f), o.get("severity", "minor")
            if SEV_RANK.get(new_sev, 0) > SEV_RANK.get(old_sev, 0):
                o["severity"] = new_sev
                o.setdefault("_escalations", []).append(
                    {"from": old_sev, "to": new_sev, "at": _now(), "report": report_sha})
            # recurrence after resolution: the fix did not hold — re-open
            if o["status"] == "RESOLVED":
                o.setdefault("previous_resolutions", []).append(o.pop("resolution"))
                o["status"] = "OPEN"
                o["recurred_after_resolution"] = {"at": _now(), "report": report_sha}
                reopened += 1
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
    ledger["last_report_sha256"] = report_sha   # binds gate to the folded report

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
    print(f"obligations: +{opened} opened, {reopened} re-opened (recurrence), "
          f"{vanished} unresolved-disappearance, "
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
    report = _load_report_strict(args.report)
    verdict = report.get("overall_verdict", "")
    report_sha = _sha256_file(args.report)
    path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    ledger = _load_ledger(path) if os.path.isfile(path) else {"obligations": []}
    open_obl = [o for o in ledger["obligations"] if o.get("status") == "OPEN"]
    open_critical = [o for o in open_obl if o.get("severity") == "critical"]
    # an unknown/mangled status is not "closed" — fail toward caution
    weird = [o for o in ledger["obligations"]
             if o.get("status") not in ("OPEN", "RESOLVED", "WAIVED")]
    # the gate only speaks for a report the ledger has actually folded in
    unbound = (ledger.get("last_report_sha256") is not None
               and ledger["last_report_sha256"] != report_sha)

    if verdict in ("HARD_FLAGS", "REVIEW_UNAVAILABLE") or open_critical or weird or unbound:
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
        "report_sha256": report_sha,
        "ledger_bound": not unbound,
        "malformed_ledger_statuses": len(weird),
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

    e = sub.add_parser("evaluate", help="atomic update + gate in one transaction (preferred)")
    e.add_argument("--report", required=True)
    e.add_argument("--paper-dir", required=True)
    e.add_argument("--anti-ar-commit", required=True)
    e.add_argument("--executor-model", default="claude")

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
    if a.cmd == "gate":
        return cmd_gate(a)          # read-only
    if a.cmd == "evaluate":
        with _ledger_lock(a.paper_dir):
            rc = cmd_update(a)
            if rc != 0:
                return rc
        return cmd_gate(a)
    with _ledger_lock(a.paper_dir):
        return {"update": cmd_update, "resolve": cmd_resolve,
                "waive": cmd_waive}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
