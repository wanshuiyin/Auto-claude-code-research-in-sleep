from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "copilot_native_evidence.py"
SPEC = importlib.util.spec_from_file_location("copilot_native_evidence", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
evidence = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evidence
SPEC.loader.exec_module(evidence)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _event(event_type: str, event_id: str, data: dict, *, agent_id: str | None = None) -> dict:
    value = {
        "type": event_type,
        "id": event_id,
        "timestamp": _timestamp(),
        "parentId": None,
        "data": data,
    }
    if agent_id is not None:
        value["agentId"] = agent_id
    return value


def _write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item) + "\n" for item in events), encoding="utf-8")


def _append_events(path: Path, events: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for item in events:
            handle.write(json.dumps(item) + "\n")


def _session_start(session_id: str, cwd: Path) -> dict:
    return _event(
        "session.start",
        "session-start",
        {
            "sessionId": session_id,
            "version": 1,
            "producer": "copilot",
            "copilotVersion": "1.0.70",
            "startTime": _timestamp(),
            "context": {"cwd": str(cwd.resolve())},
        },
    )


def _challenge_event(binding: str, executor_model: str, *, agent_id: str | None = None) -> dict:
    return _event(
        "tool.execution_start",
        "challenge-event",
        {
            "toolCallId": "challenge-call",
            "toolName": "bash",
            "arguments": {
                "command": (
                    f"BINDING='{binding}'; python3 copilot_native_evidence.py "
                    "marker --binding \"$BINDING\""
                )
            },
            "model": executor_model,
            "turnId": "0",
        },
        agent_id=agent_id,
    )


def _marker_complete(binding: str, executor_model: str, *, agent_id: str | None = None) -> dict:
    marker = json.dumps(
        {"binding": binding, "schema": evidence.CHALLENGE_SCHEMA, "status": "marker"},
        sort_keys=True,
    )
    return _event(
        "tool.execution_complete",
        "challenge-complete",
        {
            "toolCallId": "challenge-call",
            "success": True,
            "model": executor_model,
            "result": {"content": marker + "\n<shellId: 0 completed with exit code 0>"},
        },
        agent_id=agent_id,
    )


def _native_events(nonce: str, executor_model: str, reviewer_model: str, response: str) -> list[dict]:
    tool_call_id = "native-review-call"
    return [
        _event(
            "tool.execution_start",
            "native-invocation",
            {
                "toolCallId": tool_call_id,
                "toolName": "task",
                "arguments": {
                    "agent_type": "rubber-duck",
                    "name": "aris-native-review",
                    "prompt": f"Review files directly.\n{evidence.NONCE_PREFIX}{nonce}\n",
                },
                "model": executor_model,
                "turnId": "0",
            },
        ),
        _event(
            "subagent.started",
            "native-started",
            {
                "toolCallId": tool_call_id,
                "agentName": "rubber-duck",
                "agentDisplayName": "Rubber Duck Agent",
                "agentDescription": "Independent critic",
                "model": reviewer_model,
            },
            agent_id=tool_call_id,
        ),
        _event(
            "subagent.completed",
            "native-completed",
            {
                "toolCallId": tool_call_id,
                "agentName": "rubber-duck",
                "agentDisplayName": "Rubber Duck Agent",
                "model": reviewer_model,
            },
            agent_id=tool_call_id,
        ),
        _event(
            "tool.execution_complete",
            "native-tool-complete",
            {
                "toolCallId": tool_call_id,
                "success": True,
                "model": executor_model,
                "result": {"content": response},
                "turnId": "0",
            },
        ),
    ]


def _bound_challenge(
    tmp_path: Path,
    *,
    executor_model: str = "claude-sonnet-4.6",
) -> tuple[Path, Path, dict]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_root = tmp_path / "session-state"
    session_id = "session-123"
    event_path = session_root / session_id / "events.jsonl"
    binding = "run_20260715_native_0123456789"
    _write_events(
        event_path,
        [
            _session_start(session_id, workspace),
            _challenge_event(binding, executor_model),
            _marker_complete(binding, executor_model),
        ],
    )
    challenge_path = workspace / "review-stage" / "challenge.json"
    challenge = evidence.create_challenge(
        output=challenge_path,
        binding=binding,
        cwd=workspace,
        session_root=session_root,
        max_age_seconds=60,
    )
    return event_path, challenge_path, challenge


def test_challenge_binds_root_host_model_without_caller_model_input(tmp_path: Path) -> None:
    event_path, challenge_path, challenge = _bound_challenge(tmp_path)

    assert challenge_path.exists()
    assert challenge["session_events"] == str(event_path.resolve())
    assert challenge["executor_model"] == "claude-sonnet-4.6"
    assert challenge["executor_family"] == "anthropic"
    assert challenge["challenge_tool_call_id"] == "challenge-call"
    assert challenge["challenge_completion_event_id"] == "challenge-complete"
    assert "nonce" in challenge
    assert evidence.validate_challenge_artifact(challenge_path)["executor_model"] == (
        "claude-sonnet-4.6"
    )


def test_fallback_challenge_validation_rejects_model_tampering(tmp_path: Path) -> None:
    _, challenge_path, challenge = _bound_challenge(tmp_path)
    challenge["executor_model"] = "gpt-5-mini"
    challenge_path.write_text(json.dumps(challenge), encoding="utf-8")

    with pytest.raises(evidence.EvidenceError, match="executor model mismatch"):
        evidence.validate_challenge_artifact(challenge_path)


def test_challenge_rejects_nested_agent_invocation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_root = tmp_path / "sessions"
    binding = "run_20260715_nested_0123456789"
    event_path = session_root / "session" / "events.jsonl"
    _write_events(
        event_path,
        [
            _session_start("session", workspace),
            _challenge_event(binding, "claude-sonnet-4.6", agent_id="parent-task"),
            _marker_complete(binding, "claude-sonnet-4.6", agent_id="parent-task"),
        ],
    )

    with pytest.raises(evidence.EvidenceError, match="marker is not present") as exc:
        evidence.create_challenge(
            output=workspace / "challenge.json",
            binding=binding,
            cwd=workspace,
            session_root=session_root,
            max_age_seconds=60,
        )

    assert exc.value.code == 3


def test_challenge_rejects_marker_without_successful_completion(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_root = tmp_path / "sessions"
    binding = "run_20260715_incomplete_0123456789"
    event_path = session_root / "session" / "events.jsonl"
    _write_events(
        event_path,
        [_session_start("session", workspace), _challenge_event(binding, "gpt-5.4")],
    )

    with pytest.raises(evidence.EvidenceError, match="marker is not present") as exc:
        evidence.create_challenge(
            output=workspace / "challenge.json",
            binding=binding,
            cwd=workspace,
            session_root=session_root,
            max_age_seconds=60,
        )

    assert exc.value.code == 3


def test_verify_extracts_host_bound_cross_family_response(tmp_path: Path) -> None:
    event_path, challenge_path, challenge = _bound_challenge(tmp_path)
    response = "- Score: 8/10\n- Verdict: ready\n- Weaknesses: none"
    _append_events(
        event_path,
        _native_events(challenge["nonce"], "claude-sonnet-4.6", "gpt-5.5", response),
    )
    output = challenge_path.with_name("evidence.json")
    response_output = challenge_path.with_name("response.md")

    artifact = evidence.verify_native_review(
        challenge_path=challenge_path,
        output=output,
        response_output=response_output,
    )
    validated = evidence.validate_evidence_artifact(output)

    assert artifact["status"] == "verified"
    assert artifact["family_relation"] == "different"
    assert artifact["independence_verified"] is True
    assert artifact["executor_model_source"] == "host-session-event"
    assert artifact["reviewer_model_source"] == "host-session-event"
    assert response_output.read_text() == response
    assert validated["evidence_id"] == artifact["evidence_id"]


def test_verify_rejects_same_family_but_keeps_audit_artifacts(tmp_path: Path) -> None:
    event_path, challenge_path, challenge = _bound_challenge(
        tmp_path, executor_model="gpt-5.4"
    )
    response = "Score: 9/10\nVerdict: ready"
    _append_events(
        event_path,
        _native_events(challenge["nonce"], "gpt-5.4", "gpt-5.5", response),
    )
    output = challenge_path.with_name("evidence.json")
    response_output = challenge_path.with_name("response.md")

    with pytest.raises(evidence.PolicyRejected, match="same-model-family"):
        evidence.verify_native_review(
            challenge_path=challenge_path,
            output=output,
            response_output=response_output,
        )

    rejected = json.loads(output.read_text())
    assert rejected["status"] == "rejected"
    assert rejected["independence_verified"] is False
    assert response_output.read_text() == response
    with pytest.raises(evidence.EvidenceError, match="not verified"):
        evidence.validate_evidence_artifact(output)


@pytest.mark.parametrize("false_positive", ["slash-prompt", "top-level-agent"])
def test_verify_rejects_non_subagent_rubber_duck_lookalikes(
    tmp_path: Path, false_positive: str
) -> None:
    event_path, challenge_path, challenge = _bound_challenge(tmp_path)
    if false_positive == "slash-prompt":
        lookalike = _event(
            "user.message",
            "plain-slash-prompt",
            {"content": f"/rubber-duck\n{evidence.NONCE_PREFIX}{challenge['nonce']}"},
        )
    else:
        lookalike = _event(
            "tool.execution_start",
            "top-level-agent",
            {
                "toolCallId": "shell-call",
                "toolName": "bash",
                "arguments": {
                    "command": (
                        "copilot --agent rubber-duck -p '"
                        + evidence.NONCE_PREFIX
                        + challenge["nonce"]
                        + "'"
                    )
                },
                "model": "claude-sonnet-4.6",
            },
        )
    _append_events(event_path, [lookalike])

    with pytest.raises(evidence.EvidenceError, match="found 0"):
        evidence.verify_native_review(
            challenge_path=challenge_path,
            output=challenge_path.with_name("evidence.json"),
            response_output=challenge_path.with_name("response.md"),
        )


def test_verify_fails_closed_when_native_agent_is_not_exposed(tmp_path: Path) -> None:
    event_path, challenge_path, challenge = _bound_challenge(
        tmp_path, executor_model="gpt-5-mini"
    )
    tool_call_id = "unavailable-native-review"
    _append_events(
        event_path,
        [
            _event(
                "tool.execution_start",
                "unavailable-native-invocation",
                {
                    "toolCallId": tool_call_id,
                    "toolName": "task",
                    "arguments": {
                        "agent_type": "rubber-duck",
                        "prompt": f"{evidence.NONCE_PREFIX}{challenge['nonce']}",
                    },
                    "model": "gpt-5-mini",
                    "turnId": "0",
                },
            ),
            _event(
                "tool.execution_complete",
                "unavailable-native-complete",
                {
                    "toolCallId": tool_call_id,
                    "success": False,
                    "model": "gpt-5-mini",
                    "result": {
                        "content": (
                            "Unknown agent_type: rubber-duck. Valid types are: "
                            "explore, task, code-review"
                        )
                    },
                    "turnId": "0",
                },
            ),
        ],
    )
    output = challenge_path.with_name("evidence.json")
    response_output = challenge_path.with_name("response.md")

    with pytest.raises(evidence.EvidenceError, match="did not succeed") as exc:
        evidence.verify_native_review(
            challenge_path=challenge_path,
            output=output,
            response_output=response_output,
        )

    assert exc.value.code == 7
    assert not output.exists()
    assert not response_output.exists()


def test_evidence_validation_detects_event_prefix_tampering(tmp_path: Path) -> None:
    event_path, challenge_path, challenge = _bound_challenge(tmp_path)
    response = "Score: 8/10\nVerdict: almost"
    _append_events(
        event_path,
        _native_events(challenge["nonce"], "claude-sonnet-4.6", "gpt-5.5", response),
    )
    output = challenge_path.with_name("evidence.json")
    response_output = challenge_path.with_name("response.md")
    evidence.verify_native_review(
        challenge_path=challenge_path,
        output=output,
        response_output=response_output,
    )

    event_path.write_bytes(event_path.read_bytes().replace(b'"producer": "copilot"', b'"producer": "tampered"', 1))

    with pytest.raises(evidence.EvidenceError, match="prefix was modified"):
        evidence.validate_evidence_artifact(output)


def test_appending_later_session_events_does_not_invalidate_bound_prefix(tmp_path: Path) -> None:
    event_path, challenge_path, challenge = _bound_challenge(tmp_path)
    response = "Score: 8/10\nVerdict: ready"
    _append_events(
        event_path,
        _native_events(challenge["nonce"], "claude-sonnet-4.6", "gpt-5.5", response),
    )
    output = challenge_path.with_name("evidence.json")
    response_output = challenge_path.with_name("response.md")
    evidence.verify_native_review(
        challenge_path=challenge_path,
        output=output,
        response_output=response_output,
    )
    _append_events(event_path, [_event("assistant.turn_end", "later", {"turnId": "0"})])

    assert evidence.validate_evidence_artifact(output)["status"] == "verified"


def test_save_trace_uses_only_validated_native_model_provenance(tmp_path: Path) -> None:
    event_path, challenge_path, challenge = _bound_challenge(tmp_path)
    response = "Score: 8/10\nVerdict: ready"
    _append_events(
        event_path,
        _native_events(challenge["nonce"], "claude-sonnet-4.6", "gpt-5.5", response),
    )
    output = challenge_path.with_name("evidence.json")
    response_output = challenge_path.with_name("response.md")
    artifact = evidence.verify_native_review(
        challenge_path=challenge_path,
        output=output,
        response_output=response_output,
    )

    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "tools" / "save_trace.sh"),
            "--skill",
            "auto-review-loop",
            "--purpose",
            "round-1-review",
            "--backend",
            "copilot-native",
            "--native-evidence",
            str(output),
            "--prompt",
            "review paths directly",
        ],
        cwd=challenge_path.parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    run_dir = next((challenge_path.parents[1] / ".aris" / "traces" / "auto-review-loop").iterdir())
    request_path = next(run_dir.glob("*.request.json"))
    request = json.loads(request_path.read_text())
    # The call meta, not run.meta.json — "*.meta.json" matches both, and which one
    # comes first is directory-iteration order, which is not ours to rely on.
    meta_path = request_path.with_name(request_path.name[: -len(".request.json")] + ".meta.json")
    meta = json.loads(meta_path.read_text())
    assert request["backend"] == "copilot-native"
    assert request["tool"] == "task(agent_type=rubber-duck)"
    assert request["executor_model"] == "claude-sonnet-4.6"
    assert request["model"] == "gpt-5.5"
    assert request["executor_model_source"] == "host-session-event"
    assert request["reviewer_model_source"] == "host-session-event"
    assert request["independence_verified"] is True
    assert request["native_evidence_id"] == artifact["evidence_id"]
    assert next(run_dir.glob("*.response.md")).read_text() == response
    assert meta["native_evidence_id"] == artifact["evidence_id"]


def test_save_trace_rejects_native_backend_without_evidence(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "tools" / "save_trace.sh"),
            "--skill",
            "auto-review-loop",
            "--purpose",
            "round-1-review",
            "--backend",
            "copilot-native",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "require --native-evidence" in result.stderr


def test_save_trace_records_failed_native_dispatch_without_claiming_evidence(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "tools" / "save_trace.sh"),
            "--skill",
            "auto-review-loop",
            "--purpose",
            "round-1-native-dispatch",
            "--backend",
            "copilot-native",
            "--status",
            "error",
            "--fallback-reason",
            "rubber-duck is not exposed by this Copilot session",
            "--response",
            "Unknown agent_type: rubber-duck",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    run_dir = next((tmp_path / ".aris" / "traces" / "auto-review-loop").iterdir())
    request = json.loads(next(run_dir.glob("*.request.json")).read_text())
    assert request["backend"] == "copilot-native"
    assert request["status"] == "error"
    assert request["native_evidence_id"] is None
    assert request["native_evidence_path"] is None
    assert request["executor_model_source"] == "unavailable"
    assert request["reviewer_model_source"] == "unavailable"
    assert request["independence_verified"] == "unverified"
