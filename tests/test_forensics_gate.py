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
    # `evaluate` = fold + gate in one locked transaction (the launcher's
    # canonical call; a bare `gate` on an unfolded report BLOCKs by design)
    rep = _report(os.path.join(d, "report.json"), verdict, findings)
    rc = fg.main(["evaluate", "--report", rep, "--paper-dir", d,
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
        # proper resolution → closes; then the post-fix RE-SWEEP is folded in
        # (the gate only speaks for a report the ledger has folded — sha-bound)
        fg.main(["resolve", "--paper-dir", d, "--obligation-id", oid,
                 "--fix-type", "corrected-from-results", "--evidence", ev,
                 "--verified-by", "codex-thread-019f..."])
        clean = _report(os.path.join(d, "report.json"), "CLEAN_GIVEN_EVIDENCE", [])
        fg.main(["update", "--report", clean, "--paper-dir", d])
        rc, g = _gate(d, "CLEAN_GIVEN_EVIDENCE")
        assert rc == 0 and g["policy_decision"] == "NO_NEW_BLOCKER"
        assert g["ledger_bound"] is True


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
        clean = _report(os.path.join(d, "report.json"), "CLEAN_GIVEN_EVIDENCE", [])
        fg.main(["update", "--report", clean, "--paper-dir", d])
        rc, g = _gate(d, "CLEAN_GIVEN_EVIDENCE")
        assert rc == 0    # waived obligations no longer block — but the record is permanent




# ---- round-2 review hardening ----

def test_severity_ratchets_and_clean_still_blocks():
    with tempfile.TemporaryDirectory() as d:
        r1 = _report(os.path.join(d, "r1.json"), "SOFT_FLAGS", [_finding(sev="minor")])
        fg.main(["update", "--report", r1, "--paper-dir", d])
        r2 = _report(os.path.join(d, "r2.json"), "HARD_FLAGS", [_finding(sev="critical")])
        fg.main(["update", "--report", r2, "--paper-dir", d])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        assert len(led["obligations"]) == 1 and led["obligations"][0]["severity"] == "critical"
        # even a later CLEAN report cannot outrank the open critical obligation
        rc, g = _gate(d, "CLEAN_GIVEN_EVIDENCE")
        assert rc == 1 and g["policy_decision"] == "BLOCK"


def test_recurrence_after_resolution_reopens():
    with tempfile.TemporaryDirectory() as d:
        r1 = _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [_finding()])
        fg.main(["update", "--report", r1, "--paper-dir", d])
        oid = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))["obligations"][0]["obligation_id"]
        ev = os.path.join(d, "results.json"); open(ev, "w").write("{}")
        fg.main(["resolve", "--paper-dir", d, "--obligation-id", oid,
                 "--fix-type", "corrected-from-results", "--evidence", ev, "--verified-by", "x"])
        # the same finding comes back — the fix didn't hold
        r2 = _report(os.path.join(d, "r2.json"), "HARD_FLAGS", [_finding()])
        fg.main(["update", "--report", r2, "--paper-dir", d])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        o = led["obligations"][0]
        assert o["status"] == "OPEN" and o["previous_resolutions"]   # archived, not erased
        rc, _g = _gate(d, "HARD_FLAGS")
        assert rc == 1


def test_unrelated_edit_does_not_duplicate_obligations():
    # identity excludes artifact_hash: the same finding re-reported after an
    # unrelated edit to the same file (new file hash) is ONE obligation
    with tempfile.TemporaryDirectory() as d:
        f1 = _finding(); f1["evidence"][0]["artifact_hash"] = "hash-before-edit"
        f2 = _finding(); f2["evidence"][0]["artifact_hash"] = "hash-after-edit"
        fg.main(["update", "--report", _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [f1]),
                 "--paper-dir", d])
        fg.main(["update", "--report", _report(os.path.join(d, "r2.json"), "HARD_FLAGS", [f2]),
                 "--paper-dir", d])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        assert len(led["obligations"]) == 1


def test_null_findings_and_weird_status_fail_closed():
    with tempfile.TemporaryDirectory() as d:
        # findings: null is tolerated as empty (strict-parsed), non-list is fatal
        json.dump({"overall_verdict": "CLEAN_GIVEN_EVIDENCE", "findings": None},
                  open(os.path.join(d, "rn.json"), "w"))
        assert fg.main(["update", "--report", os.path.join(d, "rn.json"), "--paper-dir", d]) == 0
        json.dump({"overall_verdict": "CLEAN_GIVEN_EVIDENCE", "findings": {"x": 1}},
                  open(os.path.join(d, "rb.json"), "w"))
        try:
            fg.main(["update", "--report", os.path.join(d, "rb.json"), "--paper-dir", d])
            assert False
        except SystemExit:
            pass
        # a mangled ledger status is not "closed" — gate BLOCKs
        led_path = os.path.join(d, ".aris", "forensics", "obligations.json")
        led = json.load(open(led_path))
        led["obligations"].append({"obligation_id": "x" * 24, "status": "TOTALLY_DONE"})
        json.dump(led, open(led_path, "w"))
        rc, g = _gate(d, "CLEAN_GIVEN_EVIDENCE")
        assert rc == 1 and g["malformed_ledger_entries"] == 1


def test_gate_refuses_unfolded_report():
    # the gate only speaks for the report the ledger last folded (sha binding)
    with tempfile.TemporaryDirectory() as d:
        r1 = _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [_finding()])
        fg.main(["update", "--report", r1, "--paper-dir", d])
        clean = _report(os.path.join(d, "clean.json"), "CLEAN_GIVEN_EVIDENCE", [])
        rc = fg.main(["gate", "--report", clean, "--paper-dir", d,   # never folded
                      "--anti-ar-commit", "d8f510c"])
        g = json.load(open(os.path.join(d, ".aris", "forensics", "gate.json")))
        assert rc == 1 and g["ledger_bound"] is False


def test_gate_refuses_missing_ledger():
    # deleting (or never creating) obligations.json must not let a CLEAN
    # report exit 0 — an unfolded gate is unbound, hence BLOCK
    with tempfile.TemporaryDirectory() as d:
        clean = _report(os.path.join(d, "clean.json"), "CLEAN_GIVEN_EVIDENCE", [])
        rc = fg.main(["gate", "--report", clean, "--paper-dir", d,
                      "--anti-ar-commit", "d8f510c"])
        g = json.load(open(os.path.join(d, ".aris", "forensics", "gate.json")))
        assert rc == 1 and g["policy_decision"] == "BLOCK" and g["ledger_bound"] is False


def test_schema_drift_fails_closed():
    # a critical finding whose weight/severity this tool cannot classify must
    # STOP the gate, never silently drop its obligation
    with tempfile.TemporaryDirectory() as d:
        f = _finding(); f["_verdict_weight"] = "1"          # string, not int
        rep = _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [f])
        try:
            fg.main(["update", "--report", rep, "--paper-dir", d]); assert False
        except SystemExit:
            pass
        f2 = _finding(); f2["severity"] = f2["_severity_final"] = "catastrophic"
        rep2 = _report(os.path.join(d, "r2.json"), "HARD_FLAGS", [f2])
        try:
            fg.main(["update", "--report", rep2, "--paper-dir", d]); assert False
        except SystemExit:
            pass
        rep3 = _report(os.path.join(d, "r3.json"), "CLEAN_GIVEN_EVIDENCE", ["not-an-object"])
        try:
            fg.main(["update", "--report", rep3, "--paper-dir", d]); assert False
        except SystemExit:
            pass


def test_closed_status_without_receipt_blocks():
    # hand-editing "status": "RESOLVED"/"WAIVED" without the receipt must not
    # open the gate — closure is only valid WITH its evidence
    with tempfile.TemporaryDirectory() as d:
        rep = _report(os.path.join(d, "report.json"), "CLEAN_GIVEN_EVIDENCE", [])
        fg.main(["update", "--report", rep, "--paper-dir", d])
        led_path = os.path.join(d, ".aris", "forensics", "obligations.json")
        led = json.load(open(led_path))
        led["obligations"].append({"obligation_id": "a" * 24, "status": "RESOLVED",
                                   "severity": "critical"})   # no resolution receipt
        led["obligations"].append({"obligation_id": "b" * 24, "status": "WAIVED"})
        json.dump(led, open(led_path, "w"))
        rc = fg.main(["gate", "--report", rep, "--paper-dir", d,
                      "--anti-ar-commit", "d8f510c"])
        g = json.load(open(os.path.join(d, ".aris", "forensics", "gate.json")))
        assert rc == 1 and g["malformed_ledger_entries"] == 2


def test_disappearance_history_survives_reappearance():
    # appeared → vanished → reappeared: the vanished episode is archived,
    # never erased (append-only audit trail)
    with tempfile.TemporaryDirectory() as d:
        fg.main(["update", "--report",
                 _report(os.path.join(d, "r1.json"), "HARD_FLAGS", [_finding()]),
                 "--paper-dir", d])
        fg.main(["update", "--report",
                 _report(os.path.join(d, "r2.json"), "CLEAN_GIVEN_EVIDENCE", []),
                 "--paper-dir", d])
        fg.main(["update", "--report",
                 _report(os.path.join(d, "r3.json"), "HARD_FLAGS", [_finding()]),
                 "--paper-dir", d])
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        o = led["obligations"][0]
        assert o["status"] == "OPEN"
        assert "unresolved_disappearance" not in o          # current: present again
        assert len(o["disappearance_history"]) == 1          # episode archived
        assert o["disappearance_history"][0]["reappeared_in_report"]


def test_paper_freshness_binding():
    # gate.json binds to the paper text; editing a .tex afterwards → STALE
    with tempfile.TemporaryDirectory() as d:
        tex = os.path.join(d, "main.tex"); open(tex, "w").write("\\emph{16.7\\%}")
        assert fg.main(["fresh", "--paper-dir", d]) == 1     # no gate yet
        rep = _report(os.path.join(d, "report.json"), "CLEAN_GIVEN_EVIDENCE", [])
        fg.main(["evaluate", "--report", rep, "--paper-dir", d,
                 "--anti-ar-commit", "d8f510c"])
        assert fg.main(["fresh", "--paper-dir", d]) == 0
        open(tex, "a").write("\n% reworded after the sweep")
        assert fg.main(["fresh", "--paper-dir", d]) == 1     # STALE


def test_concurrent_updates_lose_nothing():
    import concurrent.futures, subprocess
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools",
                        "forensics_gate.py")
    with tempfile.TemporaryDirectory() as d:
        reports = []
        for i in range(8):
            f = _finding(span=f"unique finding number {i} with its own span text")
            reports.append(_report(os.path.join(d, f"r{i}.json"), "HARD_FLAGS", [f]))
        def run(rep):
            return subprocess.run([sys.executable, tool, "update", "--report", rep,
                                   "--paper-dir", d], capture_output=True, text=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(run, reports))
        assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        assert len(led["obligations"]) == 8      # append-only survived concurrency


def test_evaluate_is_atomic_update_plus_gate():
    with tempfile.TemporaryDirectory() as d:
        rep = _report(os.path.join(d, "report.json"), "HARD_FLAGS", [_finding()])
        rc = fg.main(["evaluate", "--report", rep, "--paper-dir", d,
                      "--anti-ar-commit", "d8f510c"])
        assert rc == 1
        g = json.load(open(os.path.join(d, ".aris", "forensics", "gate.json")))
        assert g["policy_decision"] == "BLOCK" and g["ledger_bound"] is True


def test_concurrent_evaluates_do_not_corrupt():
    # evaluate holds ONE lock across update+gate, and gate.json uses unique
    # temp files — concurrent evaluates must neither crash nor lose obligations
    import concurrent.futures, subprocess
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools",
                        "forensics_gate.py")
    with tempfile.TemporaryDirectory() as d:
        reports = []
        for i in range(4):
            f = _finding(span=f"concurrent evaluate finding {i} distinct span")
            reports.append(_report(os.path.join(d, f"r{i}.json"), "HARD_FLAGS", [f]))
        def run(rep):
            return subprocess.run([sys.executable, tool, "evaluate", "--report", rep,
                                   "--paper-dir", d, "--anti-ar-commit", "d8f510c"],
                                  capture_output=True, text=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(run, reports))
        assert all(r.returncode == 1 for r in results), [r.stderr for r in results]
        assert all("Traceback" not in r.stderr for r in results), [r.stderr for r in results]
        led = json.load(open(os.path.join(d, ".aris", "forensics", "obligations.json")))
        assert len(led["obligations"]) == 4
        g = json.load(open(os.path.join(d, ".aris", "forensics", "gate.json")))
        assert g["policy_decision"] == "BLOCK"   # whichever won, it's a coherent artifact


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok {fn.__name__}")
    print(f"{len(fns)} passed")
