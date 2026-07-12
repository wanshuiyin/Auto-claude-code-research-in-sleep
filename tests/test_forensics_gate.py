#!/usr/bin/env python3
"""
Tests for the /integrity-forensics typed gate + append-only obligations ledger.

The invariants under test are doctrinal:
- CLEAN_GIVEN_EVIDENCE maps to NO_NEW_BLOCKER — never any accepted/PASS token;
- unknown/missing verdicts fail CLOSED to BLOCK;
- obligations are append-only: a vanished finding NEVER auto-closes (it gains
  UNRESOLVED_DISAPPEARANCE and keeps blocking/warning);
- resolution requires an existing evidence file + verifier; waiver is a human
  act distinct from resolution; zero-weight findings never gate.

Run: python3 tests/test_forensics_gate.py   (also pytest-compatible)
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import forensics_gate as fg  # noqa: E402


def _finding(sev="critical", pattern="HP-DELTA-ERROR", span="a 16.7% relative improvement",
             weight=1):
    return {"finding_id": "F001", "skill": "consistency-audit", "pattern_id": pattern,
            "title": "delta wrong", "severity": sev, "_severity_final": sev,
            "_verdict_weight": weight,
            "evidence": [{"claim_id": "C012", "span": span,
                          "artifact_hash": "abc123", "location": {"file": "main.tex"}}]}


def _report(path, verdict, findings=()):
    json.dump({"overall_verdict": verdict, "adjudicator": "deterministic-rules-v2",
               "observability_level": 1, "coverage": {}, "findings": list(findings)},
              open(path, "w"))
    return path


def _gate(d, verdict, findings=(), executor="claude-opus-4-8"):
    rep = _report(os.path.join(d, "report.json"), verdict, findings)
    rc = fg.main(["gate", "--report", rep, "--paper-dir", d,
                  "--anti-ar-commit", "d8f510c", "--executor-model", executor])
    gate = json.load(open(os.path.join(d, ".aris", "forensics", "gate.json")))
    return rc, gate


def test_policy_mapping_and_no_acquittal_tokens():
    with tempfile.TemporaryDirectory() as d:
        rc, g = _gate(d, "CLEAN_GIVEN_EVIDENCE")
        assert rc == 0 and g["policy_decision"] == "NO_NEW_BLOCKER"
        blob = json.dumps(g)
        assert "PASS" not in blob and "accepted" not in blob   # no acquittal vocabulary
        rc, g = _gate(d, "SOFT_FLAGS")
        assert rc == 0 and g["policy_decision"] == "WARN"
        rc, g = _gate(d, "HARD_FLAGS")
        assert rc == 1 and g["policy_decision"] == "BLOCK"
        rc, g = _gate(d, "REVIEW_UNAVAILABLE")
        assert rc == 1 and g["policy_decision"] == "BLOCK"     # incomplete sweep never waves through


def test_unknown_verdict_fails_closed():
    with tempfile.TemporaryDirectory() as d:
        rc, g = _gate(d, "TOTALLY_FINE_TRUST_ME")
        assert rc == 1 and g["policy_decision"] == "BLOCK"


def test_provenance_labeling_is_honest_per_executor():
    with tempfile.TemporaryDirectory() as d:
        _, g = _gate(d, "CLEAN_GIVEN_EVIDENCE", executor="claude-opus-4-8")
        assert g["proposal_provenance"] == "cross-family"
        _, g = _gate(d, "CLEAN_GIVEN_EVIDENCE", executor="codex-gpt-5.6-sol")
        assert g["proposal_provenance"] == "same-family"


def test_obligations_append_only_and_disappearance_never_closes():
    with tempfile.TemporaryDirectory() as d:
        rep1 = _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [_finding()])
        fg.main(["update", "--report", rep1, "--paper-dir", d])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        assert len(led["obligations"]) == 1 and led["obligations"][0]["status"] == "OPEN"
        # the finding vanishes from the next report (reworded span) — must stay OPEN
        rep2 = _report(os.path.join(d, "r2.json"), "CLEAN_GIVEN_EVIDENCE", [])
        fg.main(["update", "--report", rep2, "--paper-dir", d])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        o = led["obligations"][0]
        assert o["status"] == "OPEN" and "unresolved_disappearance" in o
        # and the gate still BLOCKS despite the clean upstream verdict
        rc, g = _gate(d, "CLEAN_GIVEN_EVIDENCE")
        assert rc == 1 and g["policy_decision"] == "BLOCK"
        assert g["open_critical_obligations"] == 1


def test_same_finding_across_runs_is_one_obligation():
    with tempfile.TemporaryDirectory() as d:
        rep1 = _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [_finding()])
        rep2 = _report(os.path.join(d, "r2.json"), "HARD_FLAGS", [_finding()])
        fg.main(["update", "--report", rep1, "--paper-dir", d])
        fg.main(["update", "--report", rep2, "--paper-dir", d])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        assert len(led["obligations"]) == 1     # fingerprint-stable, not F001-keyed


def test_zero_weight_findings_never_gate():
    with tempfile.TemporaryDirectory() as d:
        ais = _finding(sev="info", pattern="AIS-LLM-PHRASE-TICS", weight=0)
        rep = _report(os.path.join(d, "r1.json"), "CLEAN_GIVEN_EVIDENCE", [ais])
        fg.main(["update", "--report", rep, "--paper-dir", d])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        assert led["obligations"] == []


def test_resolution_requires_evidence_and_verifier():
    with tempfile.TemporaryDirectory() as d:
        rep = _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [_finding()])
        fg.main(["update", "--report", rep, "--paper-dir", d])
        oid = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))["obligations"][0]["obligation_id"]
        # missing evidence file → refused
        try:
            fg.main(["resolve", "--paper-dir", d, "--obligation-id", oid,
                     "--fix-type", "corrected-from-results",
                     "--evidence", os.path.join(d, "nope.json"), "--verified-by", "x"])
            assert False
        except SystemExit:
            pass
        # bogus fix type → refused
        ev = os.path.join(d, "results.json"); open(ev, "w").write("{}")
        try:
            fg.main(["resolve", "--paper-dir", d, "--obligation-id", oid,
                     "--fix-type", "reworded-the-sentence", "--evidence", ev,
                     "--verified-by", "x"])
            assert False
        except SystemExit:
            pass
        # proper resolution → closes, gate clears
        fg.main(["resolve", "--paper-dir", d, "--obligation-id", oid,
                 "--fix-type", "corrected-from-results", "--evidence", ev,
                 "--verified-by", "codex-thread-019f..."])
        rc, g = _gate(d, "CLEAN_GIVEN_EVIDENCE")
        assert rc == 0 and g["policy_decision"] == "NO_NEW_BLOCKER"


def test_waiver_is_not_resolution_and_needs_a_human():
    with tempfile.TemporaryDirectory() as d:
        rep = _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [_finding()])
        fg.main(["update", "--report", rep, "--paper-dir", d])
        oid = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))["obligations"][0]["obligation_id"]
        fg.main(["waive", "--paper-dir", d, "--obligation-id", oid,
                 "--approver", "Ruofeng Yang", "--reason", "known benchmark quirk, documented in appendix"])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        o = led["obligations"][0]
        assert o["status"] == "WAIVED" and o["finding_snapshot"]["severity"] == "critical"
        rc, g = _gate(d, "CLEAN_GIVEN_EVIDENCE")
        assert rc == 0    # waived obligations no longer block — but the record is permanent


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok {fn.__name__}")
    print(f"{len(fns)} passed")
