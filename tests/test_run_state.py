"""Tests for tools/run_state.py — resumable run-state with the done/accepted split."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_state as rs  # noqa: E402

PHASES = ["W1", "W1.5", "W2", "W3"]


def _tmp():
    return tempfile.TemporaryDirectory()


def test_start_creates_pending_phases():
    with _tmp() as d:
        st = rs.start_run(d, "run-a", PHASES)
        assert [p["phase"] for p in st["phases"]] == PHASES
        assert all(p["status"] == "pending" for p in st["phases"])
        # resume of a fresh run points at the first phase
        assert rs.resume_point(d, "run-a")["phase"] == "W1"


def test_start_is_idempotent():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        rs.set_status(d, "run-a", "W1", "done")
        again = rs.start_run(d, "run-a", PHASES)  # must NOT clobber progress
        assert rs._find_phase(again, "W1")["status"] == "done"


def test_set_status_cannot_write_accepted():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        for ok in ("running", "done", "failed"):
            rs.set_status(d, "run-a", "W1", ok)
        for reserved in ("accepted", "provisional"):
            try:
                rs.set_status(d, "run-a", "W1", reserved)
                raised = False
            except ValueError:
                raised = True
            assert raised, f"set_status must refuse to write {reserved!r}"


def test_accept_requires_verdict_and_reviewer():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        for vid, rev in (("", "codex"), ("codex:1", ""), ("", "")):
            try:
                rs.accept(d, "run-a", "W1", vid, rev)
                raised = False
            except ValueError:
                raised = True
            assert raised, f"accept must require both verdict_id and reviewer (got {vid!r},{rev!r})"
        rs.set_status(d, "run-a", "W1", "done")  # accept now requires the phase be done
        st = rs.accept(d, "run-a", "W1", "codex:019e", "codex-gpt-5.5")
        ph = rs._find_phase(st, "W1")
        assert ph["status"] == "accepted" and ph["verdict_id"] == "codex:019e" and ph["reviewer"] == "codex-gpt-5.5"


def test_accept_requires_phase_done():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        # Cannot accept a phase that never ran (still pending).
        try:
            rs.accept(d, "run-a", "W1", "v:1", "codex")
            raised = False
        except ValueError:
            raised = True
        assert raised, "accept must refuse a non-done phase without force"
        # --force overrides (e.g. a purely deterministic phase with no executor step).
        rs.accept(d, "run-a", "W1", "v:1", "deterministic:x", force=True)
        assert rs._find_phase(rs._load(d, "run-a"), "W1")["status"] == "accepted"
        # The normal path: done → accept.
        rs.set_status(d, "run-a", "W2", "done")
        rs.accept(d, "run-a", "W2", "v:2", "codex")
        assert rs._find_phase(rs._load(d, "run-a"), "W2")["status"] == "accepted"


def test_accept_uses_recorded_executor_family_when_available():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES, executor="codex-gpt-5.5")
        rs.set_status(d, "run-a", "W1", "done")
        try:
            rs.accept(d, "run-a", "W1", "agent:self", "gpt-5.5")
            raised = False
        except ValueError:
            raised = True
        assert raised, "known same-family review must use mark_provisional"

        accepted = rs.accept(d, "run-a", "W1", "claude:1", "claude-opus-4-8")
        phase = rs._find_phase(accepted, "W1")
        assert phase["status"] == "accepted"
        assert phase["review_independence"] == "cross-family"
        assert phase["reviewer_family"] == "anthropic"


def test_legacy_state_defaults_to_claude_and_rejects_unknown_reviewer():
    import json
    with _tmp() as d:
        # Pre-provenance JSON had no executor/family/acceptance fields. Its
        # historical mainline executor was Claude, so a Codex verdict remains
        # compatible and becomes explicit rather than unclassified.
        run_path = Path(d) / ".aris" / "runs" / "run-a.json"
        run_path.parent.mkdir(parents=True)
        legacy = {
            "run_id": "run-a",
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
            "phases": [
                {"phase": phase, "status": "done" if phase == "W1" else "pending",
                 "artifact": None, "verdict_id": None, "reviewer": None,
                 "updated": "2026-01-01T00:00:00Z"}
                for phase in PHASES
            ],
        }
        run_path.write_text(json.dumps(legacy), encoding="utf-8")
        state = rs.accept(d, "run-a", "W1", "codex:1", "codex-gpt-5.5")
        phase = rs._find_phase(state, "W1")
        assert phase["executor_model"] == "claude"
        assert phase["executor_family"] == "anthropic"

        rs.set_status(d, "run-a", "W1.5", "done")
        try:
            rs.accept(d, "run-a", "W1.5", "mystery:1", "mystery-reviewer")
            raised = False
        except ValueError:
            raised = True
        assert raised, "unclassified reviewers must never receive accepted status"


def test_skipped_is_terminal_for_resume():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        rs.set_status(d, "run-a", "W1", "done"); rs.accept(d, "run-a", "W1", "v", "codex")
        rs.set_status(d, "run-a", "W1.5", "skipped")   # phase doesn't apply to this run
        rs.set_status(d, "run-a", "W2", "done"); rs.accept(d, "run-a", "W2", "v", "codex")
        rs.set_status(d, "run-a", "W3", "skipped")
        # Only accepted/skipped are terminal → all terminal → resume COMPLETE.
        assert rs.resume_point(d, "run-a") is None


def test_resume_skips_only_accepted_not_done():
    """The load-bearing invariant: a `done`-but-unaccepted phase is STILL a resume target."""
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        rs.set_status(d, "run-a", "W1", "done")
        rs.accept(d, "run-a", "W1", "codex:1", "codex")     # W1 accepted
        rs.set_status(d, "run-a", "W1.5", "done")           # W1.5 done but NOT accepted (crashed before audit)
        # resume must return W1.5 (first non-accepted), NOT W2 — done != accepted.
        assert rs.resume_point(d, "run-a")["phase"] == "W1.5"
        # accept W1.5, then resume advances to W2 (still pending).
        rs.accept(d, "run-a", "W1.5", "codex:2", "codex")
        assert rs.resume_point(d, "run-a")["phase"] == "W2"


def test_mark_provisional_records_same_family_review():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES, executor="codex-gpt-5.5")
        rs.set_status(d, "run-a", "W1", "done", artifact="idea-stage/IDEA_REPORT.md")
        state = rs.mark_provisional(
            d,
            "run-a",
            "W1",
            verdict_id="agent:019f",
            reviewer="gpt-5.5",
        )
        phase = rs._find_phase(state, "W1")
        assert phase["status"] == "provisional"
        assert phase["acceptance_status"] == "provisional"
        assert phase["review_independence"] == "same-family"
        assert phase["executor_model"] == "codex-gpt-5.5"
        assert phase["executor_family"] == "openai"
        assert phase["reviewer"] == "gpt-5.5"
        assert phase["reviewer_family"] == "openai"


def test_mark_provisional_requires_done_and_same_family():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES, executor="codex-gpt-5.5")
        for reviewer in ("gpt-5.5", "gemini-3.1-pro", "mystery-model"):
            try:
                rs.mark_provisional(d, "run-a", "W1", "agent:1", reviewer)
                raised = False
            except ValueError:
                raised = True
            assert raised, "a pending phase cannot be marked provisional"

        rs.set_status(d, "run-a", "W1", "done")
        for reviewer in ("gemini-3.1-pro", "mystery-model", "deterministic:pytest"):
            try:
                rs.mark_provisional(d, "run-a", "W1", "agent:1", reviewer)
                raised = False
            except ValueError:
                raised = True
            assert raised, f"reviewer {reviewer!r} is not a same-family Codex review"


def test_provisional_advances_only_under_explicit_policy():
    # Codex-native mirror: start_run opts IN, provisional closes the phase for resume
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES, executor="codex", provisional_advances=True)
        rs.set_status(d, "run-a", "W1", "done")
        rs.mark_provisional(d, "run-a", "W1", "agent:1", "gpt-5.6-sol")
        assert rs.resume_point(d, "run-a")["phase"] == "W1.5"
        for phase in PHASES[1:]:
            rs.set_status(d, "run-a", phase, "skipped")
        assert rs.resume_point(d, "run-a") is None


def test_provisional_does_not_advance_mainline_default():
    # mainline default policy: a same-family provisional verdict is NOT terminal —
    # the phase remains the resume target until a cross-family acceptance lands
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES, executor="codex")
        rs.set_status(d, "run-a", "W1", "done")
        rs.mark_provisional(d, "run-a", "W1", "agent:1", "gpt-5.6-sol")
        assert rs.resume_point(d, "run-a")["phase"] == "W1"


def test_provisional_upgrades_to_accepted_by_cross_family():
    # the monotonic path: a later Claude/Gemini overlay acquits a provisional phase
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES, executor="codex")
        rs.set_status(d, "run-a", "W1", "done")
        rs.mark_provisional(d, "run-a", "W1", "agent:1", "gpt-5.6-sol")
        st = rs.accept(d, "run-a", "W1", "claude:v1", "claude-opus-4-8")
        ph = next(p for p in st["phases"] if p["phase"] == "W1")
        assert ph["status"] == "accepted"
        assert ph["review_independence"] == "cross-family"
        assert rs.resume_point(d, "run-a")["phase"] == "W1.5"


def test_resume_none_when_all_accepted():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        for ph in PHASES:
            rs.set_status(d, "run-a", ph, "done")
            rs.accept(d, "run-a", ph, f"v:{ph}", "deterministic:test")
        assert rs.resume_point(d, "run-a") is None


def test_invalid_run_id_rejected():
    with _tmp() as d:
        for bad in ("../escape", "a/b", "a b", "a;rm"):
            try:
                rs.start_run(d, bad, PHASES)
                raised = False
            except ValueError:
                raised = True
            assert raised, f"invalid run_id {bad!r} must be rejected"


def test_unknown_phase_raises():
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        try:
            rs.set_status(d, "run-a", "W9", "done")
            raised = False
        except KeyError:
            raised = True
        assert raised


def test_state_is_valid_json_on_disk():
    import json
    with _tmp() as d:
        rs.start_run(d, "run-a", PHASES)
        rs.set_status(d, "run-a", "W1", "done", artifact="x/y.md")
        p = Path(d) / ".aris" / "runs" / "run-a.json"
        state = json.loads(p.read_text())  # must parse
        assert rs._find_phase(state, "W1")["artifact"] == "x/y.md"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
