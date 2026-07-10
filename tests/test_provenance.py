"""Tests for tools/provenance.py — provenance-as-authorization.

Core safety property: stamp()/assert_cross_family() must NEVER record or pass a
same-family acquittal. The cross-model invariant is the whole point — a bug here
would let one model both author and approve an auto-written skill.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import provenance as pv  # noqa: E402


def test_model_family_mapping():
    assert pv.model_family("claude-opus-4-8") == "anthropic"
    assert pv.model_family("Sonnet") == "anthropic"
    assert pv.model_family("gpt-5.5") == "openai"
    assert pv.model_family("gpt-5.6-sol") == "openai"     # current default reviewer (2026-07)
    assert pv.model_family("codex") == "openai"
    # CRITICAL: oracle-pro routes to GPT-Pro → it is the OPENAI family, not its own.
    assert pv.model_family("oracle-pro") == "openai"
    assert pv.model_family("gemini-3.1-pro") == "google"
    assert pv.model_family("deepseek-v3") == "deepseek"
    assert pv.model_family("kimi-k2") == "moonshot"
    assert pv.model_family("deterministic:evidence_check") == "deterministic"
    assert pv.model_family("some-random-model") == "unknown"
    assert pv.model_family("") == "unknown"
    # real o-series names still classify (exact-token), but the short needle does
    # NOT substring-bleed into unrelated names.
    assert pv.model_family("o3-mini") == "openai"
    assert pv.model_family("o4-mini") == "openai"


def test_collision_fails_closed():
    """A name matching TWO families' needles must fail closed (→ unknown → raise),
    never silently resolve to one family and slip through as cross-family."""
    assert pv.model_family("claude-gpt-4") == "unknown"   # anthropic + openai
    assert pv.model_family("gemini-o3") == "unknown"      # google + openai
    # so a mislabeled colliding name can't defeat the gate — it raises:
    try:
        pv.assert_cross_family("claude-gpt-4", "gpt-5.5")
        raise AssertionError("collision name must fail closed, not pass as cross-family")
    except ValueError:
        pass


def test_assert_cross_family_accepts_different():
    pv.assert_cross_family("claude-opus-4-8", "gpt-5.5")          # anthropic ≠ openai
    pv.assert_cross_family("claude-opus-4-8", "gemini-3.1-pro")   # anthropic ≠ google
    pv.assert_cross_family("gpt-5.5", "gemini-3.1-pro")           # openai ≠ google
    pv.assert_cross_family("claude-opus-4-8", "oracle-pro")       # anthropic ≠ openai(oracle)


def test_assert_cross_family_rejects_same():
    for author, reviewer in [
        ("claude-opus-4-8", "claude-sonnet-4-6"),  # both anthropic
        ("gpt-5.5", "codex"),                       # both openai
        ("gpt-5.5", "oracle-pro"),                  # openai vs oracle(openai) — the trap
        ("codex", "oracle-pro"),                    # both openai
        ("gemini-3.1-pro", "gemini-2.5-pro"),       # both google
    ]:
        try:
            pv.assert_cross_family(author, reviewer)
            raise AssertionError(f"should have rejected same-family {author}/{reviewer}")
        except ValueError:
            pass


def test_assert_cross_family_deterministic_always_ok():
    # A deterministic verifier is a process, not a model family — valid even if the
    # author is unknown.
    pv.assert_cross_family("claude-opus-4-8", "deterministic:evidence_check")
    pv.assert_cross_family("some-unknown-model", "deterministic:pytest")


def test_assert_cross_family_fails_closed_on_unknown():
    # Unknown reviewer/author family → cannot prove cross-family → must raise.
    for author, reviewer in [
        ("claude-opus-4-8", "mystery-reviewer"),
        ("mystery-model", "gpt-5.5"),
        ("foo", "bar"),
    ]:
        try:
            pv.assert_cross_family(author, reviewer)
            raise AssertionError(f"should fail closed on unknown {author}/{reviewer}")
        except ValueError:
            pass


def test_stamp_refuses_same_family():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "SKILL.md"
        f.write_text("# auto skill\n", encoding="utf-8")
        try:
            pv.stamp(str(f), author_model="claude-opus-4-8",
                     reviewer_model="claude-sonnet-4-6", verdict_id="t_123")
            raise AssertionError("stamp should refuse same-family")
        except ValueError:
            pass
        # and no sidecar must have been written
        assert pv.read(str(f)) is None


def test_stamp_refuses_empty_verdict():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "SKILL.md"
        f.write_text("# auto skill\n", encoding="utf-8")
        try:
            pv.stamp(str(f), "claude-opus-4-8", "gpt-5.5", verdict_id="")
            raise AssertionError("stamp should refuse empty verdict_id")
        except ValueError:
            pass


def test_stamp_and_read_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "node.md"
        f.write_text("auto-authored content\n", encoding="utf-8")
        rec = pv.stamp(str(f), author_model="claude-opus-4-8",
                       reviewer_model="gpt-5.5", verdict_id="codex_thread_abc",
                       ts="2026-05-29T00:00:00Z")
        assert rec["created_by"] == "aris-auto"
        assert rec["review_independence"] == "cross-family"
        assert rec["acceptance_status"] == "accepted"
        assert rec["author_family"] == "anthropic"
        assert rec["reviewer_family"] == "openai"
        assert rec["content_hash"] == pv.content_hash(str(f))
        back = pv.read(str(f))
        assert back == rec
        # tamper-evidence: edit the file → hash no longer matches the stamped record
        f.write_text("tampered\n", encoding="utf-8")
        assert pv.content_hash(str(f)) != back["content_hash"]


def test_stamp_provisional_records_same_family_without_auto_curation_authority():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "node.md"
        f.write_text("same-family reviewed content\n", encoding="utf-8")

        rec = pv.stamp_provisional(
            str(f),
            author_model="codex-gpt-5.5",
            reviewer_model="gpt-5.5",
            verdict_id="agent_019f",
            ts="2026-07-10T00:00:00Z",
        )

        assert rec["author_family"] == "openai"
        assert rec["reviewer_family"] == "openai"
        assert rec["review_independence"] == "same-family"
        assert rec["acceptance_status"] == "provisional"
        assert pv.is_auto_authored(str(f)) is True
        assert pv.is_auto_curatable(str(f)) is False


def test_stamp_provisional_refuses_cross_family_and_unknown_models():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "node.md"
        f.write_text("content\n", encoding="utf-8")
        for author, reviewer in [
            ("codex-gpt-5.5", "gemini-3.1-pro"),
            ("unknown-executor", "gpt-5.5"),
        ]:
            try:
                pv.stamp_provisional(str(f), author, reviewer, verdict_id="agent_1")
                raise AssertionError(f"should reject provisional route {author}/{reviewer}")
            except ValueError:
                pass
        assert pv.read(str(f)) is None


def test_stamp_dir_hashes_skill_md():
    with tempfile.TemporaryDirectory() as d:
        skill = Path(d) / "myskill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("# skill body\n", encoding="utf-8")
        rec = pv.stamp(str(skill), "claude-opus-4-8", "gemini-3.1-pro",
                       verdict_id="g_1", ts="2026-05-29T00:00:00Z")
        assert rec["content_hash"] == pv.content_hash(str(skill / "SKILL.md"))
        assert (skill / ".provenance.json").is_file()  # sidecar lives inside the dir


def test_is_auto_authored():
    with tempfile.TemporaryDirectory() as d:
        auto = Path(d) / "auto.md"
        auto.write_text("x\n", encoding="utf-8")
        pv.stamp(str(auto), "claude-opus-4-8", "gpt-5.5", verdict_id="t1")
        assert pv.is_auto_authored(str(auto)) is True
        assert pv.is_auto_curatable(str(auto)) is True

        # a hand-written / canonical artifact has NO provenance → off-limits to curation
        canonical = Path(d) / "canonical.md"
        canonical.write_text("hand-written\n", encoding="utf-8")
        assert pv.is_auto_authored(str(canonical)) is False
        assert pv.is_auto_curatable(str(canonical)) is False

        # a record with created_by != aris-auto is also not auto-curatable
        human = Path(d) / "human.md"
        human.write_text("y\n", encoding="utf-8")
        pv.stamp(str(human), "claude-opus-4-8", "gpt-5.5", verdict_id="t2",
                 created_by="human")
        assert pv.is_auto_authored(str(human)) is False
        assert pv.is_auto_curatable(str(human)) is False




# ---- sidecar hardening: a sidecar is untrusted JSON on disk ----

def test_spoofed_sidecar_status_cannot_authorize_curation():
    import json as _json
    with tempfile.TemporaryDirectory() as d:
        art = Path(d) / "skill.md"
        art.write_text("x\n", encoding="utf-8")
        pv.stamp_provisional(str(art), "codex-gpt-5.6-sol", "gpt-5.6-sol", verdict_id="agent:1")
        sc = Path(str(art) + ".provenance.json")
        rec = _json.loads(sc.read_text())
        # attack 1: flip the status field to accepted
        rec["acceptance_status"] = "accepted"
        sc.write_text(_json.dumps(rec))
        assert pv.is_auto_curatable(str(art)) is False   # families re-verified
        # attack 2: delete the field to masquerade as a legacy record
        del rec["acceptance_status"]
        sc.write_text(_json.dumps(rec))
        assert pv.is_auto_curatable(str(art)) is False   # legacy re-verifies families too
        # attack 3: also spoof the family labels (recomputation must win)
        rec["reviewer_family"] = "anthropic"
        rec["review_independence"] = "cross-family"
        sc.write_text(_json.dumps(rec))
        assert pv.is_auto_curatable(str(art)) is False


def test_stale_stamp_after_edit_is_not_curatable():
    with tempfile.TemporaryDirectory() as d:
        art = Path(d) / "skill.md"
        art.write_text("x\n", encoding="utf-8")
        pv.stamp(str(art), "claude-opus-4-8", "gpt-5.6-sol", verdict_id="t1")
        assert pv.is_auto_curatable(str(art)) is True
        art.write_text("x edited after acceptance\n", encoding="utf-8")
        assert pv.is_auto_curatable(str(art)) is False   # hash no longer matches


def test_provisional_cannot_overwrite_accepted():
    with tempfile.TemporaryDirectory() as d:
        art = Path(d) / "skill.md"
        art.write_text("x\n", encoding="utf-8")
        pv.stamp(str(art), "claude-opus-4-8", "gpt-5.6-sol", verdict_id="t1")
        try:
            pv.stamp_provisional(str(art), "codex-gpt-5.6-sol", "gpt-5.6-sol", verdict_id="agent:2")
            assert False, "provisional must not silently replace accepted"
        except ValueError:
            pass
        assert pv.is_auto_curatable(str(art)) is True    # acceptance survived


def test_legitimate_deterministic_stamp_still_curatable():
    # regression guard: hardening must not reject a REAL deterministic verifier
    with tempfile.TemporaryDirectory() as d:
        art = Path(d) / "skill.md"
        art.write_text("x\n", encoding="utf-8")
        pv.stamp(str(art), "claude-opus-4-8", "deterministic:pytest", verdict_id="report:tests")
        assert pv.is_auto_curatable(str(art)) is True
        # but a deterministic LABEL on a model reviewer is rejected
        import json as _json
        sc = Path(str(art) + ".provenance.json")
        rec = _json.loads(sc.read_text())
        rec["reviewer_model"] = "gpt-5.6-sol"
        rec["review_independence"] = "deterministic"
        sc.write_text(_json.dumps(rec))
        assert pv.is_auto_curatable(str(art)) is False


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
