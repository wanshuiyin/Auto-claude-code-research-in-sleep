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


# The compile-input closure PLUS the compiled deliverable PLUS tabular data
# sources (pgfplots/tables read .csv/.dat at compile time). Numbers moved
# into a .sty macro, a regenerated figure, an edited data file, or a rebuilt
# PDF after the sweep must all read as STALE — the sweep audited none of
# them. .json is deliberately NOT fingerprinted: the sweep's own report.json
# (and re-run siblings) live in the paper dir and would self-trip the
# staleness guard; JSON results feeding the paper are covered by resolution
# evidence re-hashing instead.
_FINGERPRINT_EXTS = (".tex", ".bib", ".sty", ".cls", ".bst", ".inc", ".def",
                     ".tikz", ".pgf", ".pdf", ".png", ".jpg", ".jpeg", ".eps",
                     ".svg", ".csv", ".tsv", ".dat")


def _paper_fingerprint(paper_dir):
    """sha256 over the paper's compile inputs + deliverables (sorted relpaths,
    dot-dirs like .aris/.git excluded, symlinked dirs followed) — binds a gate
    artifact to the content it audited, so a paper edited (or recompiled)
    AFTER a clean sweep reads as STALE (via the `fresh` subcommand) instead of
    inheriting the old gate."""
    entries = []
    for root, dirs, files in os.walk(paper_dir, followlinks=True):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for fn in files:
            if fn.lower().endswith(_FINGERPRINT_EXTS):
                fp = os.path.join(root, fn)
                entries.append((os.path.relpath(fp, paper_dir), _sha256_file(fp)))
    h = hashlib.sha256()
    for rel, sha in sorted(entries):
        h.update("{}\0{}\n".format(rel, sha).encode("utf-8"))
    return h.hexdigest()


def _assert_report_not_stale(report_path, paper_dir):
    """A report older than any audited paper file was generated BEFORE those
    edits — folding or gating it would bind new text to a sweep that never saw
    it. Refuse (fail closed); re-run the sweep instead. NOTE this is an mtime
    net for the honest resumed-run case, not proof of provenance — true
    content binding needs upstream to stamp a paper fingerprint into
    report.json (filed upstream)."""
    rep_mtime = os.path.getmtime(report_path)
    for root, dirs, files in os.walk(paper_dir, followlinks=True):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for fn in files:
            fp = os.path.join(root, fn)
            if not fn.lower().endswith(_FINGERPRINT_EXTS):
                continue
            if os.path.samefile(fp, report_path):
                continue   # the report itself may be fingerprinted (.json)
            if os.path.getmtime(fp) > rep_mtime:
                raise SystemExit(f"FATAL: {fp} was modified AFTER the report — "
                                 "stale report; re-run the sweep")


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
        for i, o in enumerate(data["obligations"]):
            if not isinstance(o, dict) or not isinstance(o.get("obligation_id"), str):
                raise SystemExit(f"FATAL: {path} obligations[{i}] is malformed")
        return data
    return {"ledger_version": "1", "obligations": []}


def _save_ledger(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    # EVERY ledger mutation invalidates the standing gate: a gate computed
    # against the previous ledger state must never survive it (`evaluate`
    # rewrites gate.json right after; a crash in between leaves NO gate —
    # which fails closed — rather than a stale pass).
    with contextlib.suppress(FileNotFoundError):
        os.remove(os.path.join(os.path.dirname(path), "gate.json"))


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
    # Structural provenance floor: every real Anti-AR report names its
    # adjudicator and carries a coverage map. A bare {verdict, findings} stub
    # is not a report this gate will speak for. (This raises the bar for a
    # skipped-sweep shortcut; it is NOT cryptographic provenance — see the
    # launcher's Trust boundary note.)
    if not (isinstance(report.get("adjudicator"), str) and report["adjudicator"].strip()):
        raise SystemExit(f"FATAL: report {path} names no adjudicator — not an "
                         "Anti-AR report; run the pinned sweep")
    if not isinstance(report.get("coverage"), dict):
        raise SystemExit(f"FATAL: report {path} carries no coverage map — not an "
                         "Anti-AR report; run the pinned sweep")
    for i, f in enumerate(findings):
        # Schema drift fails CLOSED: a finding this tool cannot classify must
        # stop the gate, not silently lose its obligation (e.g. a critical
        # finding whose _verdict_weight arrives as the STRING "1" would
        # otherwise read as non-weight-1 and never gate).
        if not isinstance(f, dict):
            raise SystemExit(f"FATAL: report {path} findings[{i}] is not an object")
        w = f.get("_verdict_weight", 1)
        if isinstance(w, bool) or not isinstance(w, int) or w not in (0, 1):
            raise SystemExit(f"FATAL: report {path} findings[{i}] has _verdict_weight "
                             f"{w!r} (must be 0 or 1) — schema drift; see Pin-bump checklist")
        for key in ("severity", "_severity_final"):
            v = f.get(key)
            if v is not None and v not in ("critical", "major", "minor", "info"):
                raise SystemExit(f"FATAL: report {path} findings[{i}] has unknown "
                                 f"{key} {v!r} — schema drift; see Pin-bump checklist")
        if f.get("severity") is None and f.get("_severity_final") is None:
            raise SystemExit(f"FATAL: report {path} findings[{i}] carries no severity "
                             "at all — schema drift; see Pin-bump checklist")
    report["findings"] = findings
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
    _assert_report_not_stale(args.report, args.paper_dir)
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
            # a closed disappearance episode is archived, never erased — the
            # appeared→vanished→reappeared trail is itself audit evidence
            gone = o.pop("unresolved_disappearance", None)
            if gone is not None:
                o.setdefault("disappearance_history", []).append(
                    {**gone, "reappeared_at": _now(), "reappeared_in_report": report_sha})
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
            d = o.get("unresolved_disappearance")
            if d is None:
                o["unresolved_disappearance"] = {
                    "noted_at": _now(), "absent_from_report": report_sha,
                    "note": "finding no longer detected but obligation was never "
                            "resolved with evidence — disappearance is not resolution",
                }
                vanished += 1
            else:   # still absent: extend the episode, never overwrite its start
                d["last_absent_report"] = report_sha
                d["last_noted_at"] = _now()

    _save_ledger(path, ledger)
    # Archive the folded report verbatim: `fresh` re-reads the VERDICT from
    # this sha-verified copy and recomputes the decision, instead of trusting
    # a stored (editable) policy token.
    with open(args.report, "rb") as src:
        blob = src.read()
    fd, tmp = tempfile.mkstemp(dir=_forensics_dir(args.paper_dir), suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(blob)
    os.replace(tmp, os.path.join(_forensics_dir(args.paper_dir), "last_report.json"))
    print(f"obligations: +{opened} opened, {reopened} re-opened (recurrence), "
          f"{vanished} unresolved-disappearance, "
          f"{sum(1 for o in ledger['obligations'] if o['status'] == 'OPEN')} open total -> {path}")
    return 0


VERIFIED_BY_RE = re.compile(r"(human|checker|cross-family-review):\S.*")


def cmd_resolve(args):
    if args.fix_type not in FIX_TYPES:
        raise SystemExit(f"FATAL: fix_type must be one of {FIX_TYPES}")
    if not os.path.isfile(args.evidence):
        raise SystemExit(f"FATAL: evidence file does not exist: {args.evidence} "
                         "(a resolution without evidence is a reworded flag)")
    if not VERIFIED_BY_RE.fullmatch((args.verified_by or "").strip()):
        raise SystemExit("FATAL: --verified-by must be typed provenance — "
                         "'human:<name>', 'checker:<tool>', or "
                         "'cross-family-review:<thread-id>' (a freehand token is "
                         "not a receipt)")
    path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    ledger = _load_ledger(path)
    for o in ledger["obligations"]:
        if o["obligation_id"] == args.obligation_id:
            if o["status"] != "OPEN":
                raise SystemExit(f"FATAL: obligation is {o['status']}, not OPEN")
            o["status"] = "RESOLVED"
            o["resolution"] = {
                "fix_type": args.fix_type,
                # abspath: the receipt is re-verified against this file on
                # every later gate — evidence must be durable and unchanged
                "evidence_path": os.path.abspath(args.evidence),
                "evidence_sha256": _sha256_file(args.evidence),
                "verified_by": args.verified_by.strip(),
                "resolved_at": _now(),
            }
            _save_ledger(path, ledger)
            print(f"resolved {args.obligation_id} ({args.fix_type})")
            return 0
    raise SystemExit(f"FATAL: no obligation {args.obligation_id}")


def cmd_waive(args):
    if not re.fullmatch(r"human:\S.*", (args.approver or "").strip()) \
            or not (args.reason or "").strip():
        raise SystemExit("FATAL: waive requires --approver 'human:<name>' and "
                         "--reason. The tool cannot authenticate humanity — the "
                         "typed prefix makes a non-human waiver an explicit false "
                         "record with a permanent paper trail, not a lazy default.")
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


def _closure_invalid(o):
    """A ledger entry counts as validly closed ONLY with its receipt: RESOLVED
    needs a typed resolution (legal fix_type, hashed evidence, verifier);
    WAIVED needs a human waiver record. A closed status WITHOUT the receipt —
    or any unknown status — is not 'closed', it is malformed: fail toward
    caution (a hand-edited `"status": "RESOLVED"` must not open the gate)."""
    st = o.get("status")
    if st == "OPEN":
        return False
    if st == "RESOLVED":
        r = o.get("resolution")
        if not (isinstance(r, dict) and r.get("fix_type") in FIX_TYPES
                and isinstance(r.get("evidence_sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", r["evidence_sha256"])
                and VERIFIED_BY_RE.fullmatch((r.get("verified_by") or "").strip())):
            return True
        # the receipt is re-verified, not remembered: the evidence file must
        # still exist and still hash to what was recorded at closure time
        p = r.get("evidence_path")
        return not (isinstance(p, str) and os.path.isfile(p)
                    and _sha256_file(p) == r["evidence_sha256"])
    if st == "WAIVED":
        w = o.get("waiver")
        return not (isinstance(w, dict)
                    and re.fullmatch(r"human:\S.*", (w.get("approver") or "").strip())
                    and (w.get("reason") or "").strip())
    return True


def _decide(verdict, ledger, report_sha):
    """The ONE deterministic decision function — cmd_gate computes with it and
    cmd_fresh RE-computes with it (a stored policy token is display, never
    authority: editing gate.json's decision field must change nothing)."""
    open_obl = [o for o in ledger["obligations"] if o.get("status") == "OPEN"]
    open_critical = [o for o in open_obl if o.get("severity") == "critical"]
    weird = [o for o in ledger["obligations"] if _closure_invalid(o)]
    # The gate only speaks for a report the ledger has actually folded in.
    # A MISSING ledger (or one that never folded anything) is unbound too —
    # deleting obligations.json must not turn a CLEAN report into exit 0.
    unbound = ledger.get("last_report_sha256") != report_sha

    if verdict in ("HARD_FLAGS", "REVIEW_UNAVAILABLE") or open_critical or weird or unbound:
        decision = BLOCK
    elif verdict == "SOFT_FLAGS" or open_obl:
        decision = WARN
    elif verdict == "CLEAN_GIVEN_EVIDENCE":
        decision = NO_NEW_BLOCKER
    else:
        decision = BLOCK   # unknown verdict token: fail closed
    return decision, open_obl, open_critical, weird, unbound


def cmd_gate(args):
    report = _load_report_strict(args.report)
    verdict = report.get("overall_verdict", "")
    report_sha = _sha256_file(args.report)
    _assert_report_not_stale(args.report, args.paper_dir)
    path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    ledger = _load_ledger(path)
    decision, open_obl, open_critical, weird, unbound = _decide(verdict, ledger, report_sha)

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
        "malformed_ledger_entries": len(weird),
        # binds this gate to the paper text it audited (checked by `fresh`)
        "paper_fingerprint": _paper_fingerprint(args.paper_dir),
        # binds this gate to the exact obligations ledger it judged — an
        # out-of-band edit (e.g. hand-deleting one obligation) reads as
        # LEDGER_DRIFT in `fresh` even when the recomputed decision agrees
        "obligations_sha256": _sha256_file(path) if os.path.isfile(path) else None,
        # upstream's span-anchored claims ledger (informational provenance —
        # honestly labeled: this is NOT the obligations ledger)
        "claims_ledger_sha256": _sha256_file(claims) if os.path.isfile(claims) else None,
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
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(out), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(gate, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, out)
    print(f"forensics gate: {decision} (upstream: {verdict or '(missing)'}; "
          f"open obligations: {len(open_obl)}, critical: {len(open_critical)}) -> {out}")
    return 0 if decision != BLOCK else 1


def cmd_fresh(args):
    """The downstream preflight, in one exit code. Exit 0 ⟺ a gate exists AND
    it speaks for the CURRENT paper content AND for the CURRENT obligations
    ledger AND its decision is pass-capable (WARN / NO_NEW_BLOCKER). Missing
    gate, post-gate edits, an unbound ledger, BLOCK, or any unknown policy
    token → exit 1: a resumed or post-edit run must re-sweep + `evaluate`,
    never inherit an old (or hand-crafted) pass."""
    out = os.path.join(_forensics_dir(args.paper_dir), "gate.json")
    if not os.path.isfile(out):
        print("forensics fresh: NO_GATE — gate.json missing; run `evaluate` first")
        return 1
    with open(out, encoding="utf-8") as fh:
        gate = json.load(fh)
    if gate.get("gate_version") != GATE_VERSION:
        print(f"forensics fresh: VERSION_MISMATCH — gate is v{gate.get('gate_version')!r}, "
              f"tool is v{GATE_VERSION}; re-run `evaluate`")
        return 1
    if args.anti_ar_commit and gate.get("anti_ar_commit") != args.anti_ar_commit:
        print(f"forensics fresh: PIN_MISMATCH — gate was produced at pin "
              f"{gate.get('anti_ar_commit')!r}, launcher pins {args.anti_ar_commit!r}; "
              "findings from an older adjudicator must be re-audited (pin-bump rule)")
        return 1
    if gate.get("paper_fingerprint") != _paper_fingerprint(args.paper_dir):
        print("forensics fresh: STALE — paper sources/deliverables changed after "
              "the gate; re-run the sweep + `evaluate`")
        return 1
    ledger_path = os.path.join(_forensics_dir(args.paper_dir), "obligations.json")
    current_ledger_sha = _sha256_file(ledger_path) if os.path.isfile(ledger_path) else None
    if gate.get("obligations_sha256") is None \
            or gate.get("obligations_sha256") != current_ledger_sha:
        print("forensics fresh: LEDGER_DRIFT — obligations.json changed after the "
              "gate (even an edit that keeps the same decision); re-run `evaluate`")
        return 1
    ledger = _load_ledger(ledger_path)
    if gate.get("report_sha256") is None \
            or gate.get("report_sha256") != ledger.get("last_report_sha256"):
        print("forensics fresh: UNBOUND — gate does not match the current "
              "obligations ledger; re-run `evaluate`")
        return 1
    # Re-derive the decision from the sha-verified ARCHIVED report + the live
    # ledger — never from the gate's stored token (a one-field edit of
    # gate.json from BLOCK to WARN must change nothing).
    archived = os.path.join(_forensics_dir(args.paper_dir), "last_report.json")
    if not os.path.isfile(archived) \
            or _sha256_file(archived) != ledger.get("last_report_sha256"):
        print("forensics fresh: NO_ARCHIVE — the folded report is missing or does "
              "not hash to the ledger's binding; re-run `evaluate`")
        return 1
    verdict = _load_report_strict(archived).get("overall_verdict", "")
    decision, _open_obl, _crit, _weird, _unbound = _decide(
        verdict, ledger, gate["report_sha256"])
    if decision != gate.get("policy_decision"):
        print(f"forensics fresh: MISMATCH — gate.json says "
              f"{gate.get('policy_decision')!r} but the recomputed decision is "
              f"{decision!r}; the gate artifact does not reproduce — re-run `evaluate`")
        return 1
    if decision not in (WARN, NO_NEW_BLOCKER):
        print(f"forensics fresh: {decision} — not pass-capable; the gate is closed")
        return 1
    print(f"forensics fresh: OK ({decision}; recomputed from the archived report "
          "and current ledger)")
    return 0


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

    f = sub.add_parser("fresh", help="verify gate.json still matches the current paper text")
    f.add_argument("--paper-dir", required=True)
    f.add_argument("--anti-ar-commit", default=None,
                   help="when given, the gate must have been produced at this pin")

    a = ap.parse_args(argv)
    if a.cmd == "gate":
        # gate does not mutate the ledger, but it must read it and write
        # gate.json under the same lock — otherwise a concurrent `evaluate`
        # could land a BLOCK gate that this older read then overwrites
        with _ledger_lock(a.paper_dir):
            return cmd_gate(a)
    if a.cmd == "fresh":
        # same lock as the mutators: a concurrent resolve/waive/update must
        # not interleave between fresh's reads (gate, ledger, archive)
        with _ledger_lock(a.paper_dir):
            return cmd_fresh(a)
    if a.cmd == "evaluate":
        # one lock across update AND gate — the emitted gate.json provably
        # describes the ledger state this same transaction produced
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
