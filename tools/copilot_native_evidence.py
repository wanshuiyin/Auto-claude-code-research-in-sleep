#!/usr/bin/env python3
"""Bind an ARIS review to Copilot CLI's native rubber-duck subagent.

Copilot persists machine-readable session events for the root model, tool call,
subagent lifecycle, resolved reviewer model, and tool result.  This helper turns
that host-owned event chain into a small evidence artifact.  It deliberately
does not accept executor/reviewer model names from the caller.

The protocol prevents a recent, unrelated Copilot session from being
mistaken for the current one:

1. ``marker`` runs as one short root tool call and emits a unique caller token.
2. After that call returns (and Copilot has persisted it), ``challenge`` binds
   the marker event and records the host-reported executor model.
3. The caller includes the returned nonce in a native ``rubber-duck`` task.
   ``verify`` then requires a successful, completed child subagent with the
   same tool-call id, extracts its host-reported model and raw result, and
   rejects same/unknown-family pairs.

The resulting evidence is revalidated by ``review_gate.py`` before a native
positive verdict is allowed to stop the loop.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any, Iterable


CHALLENGE_SCHEMA = "aris.copilot-native.challenge/v1"
EVIDENCE_SCHEMA = "aris.copilot-native.evidence/v1"
NONCE_PREFIX = "ARIS_REVIEW_NONCE="
MAX_EVENT_LOG_BYTES = 256 * 1024 * 1024
KNOWN_FAMILIES = {"openai", "anthropic", "google"}


class EvidenceError(RuntimeError):
    """A deterministic evidence failure with a stable process exit code."""

    def __init__(self, message: str, *, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


class PolicyRejected(EvidenceError):
    """The host event chain is real, but it violates reviewer policy."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code=10)


@dataclass(frozen=True)
class EventRecord:
    event: dict[str, Any]
    end_offset: int


def derive_model_family(model: str) -> str:
    """Derive a provider family from an exact model id, failing closed."""

    name = (model or "").strip().lower()
    families: set[str] = set()
    if re.search(r"(^|[^a-z0-9])(gpt|chatgpt|codex|oracle|o1|o3|o4)([^a-z0-9]|$)", name):
        families.add("openai")
    if re.search(r"(^|[^a-z0-9])(claude|sonnet|opus|haiku|anthropic)([^a-z0-9]|$)", name):
        families.add("anthropic")
    if re.search(r"(^|[^a-z0-9])(gemini|google)([^a-z0-9]|$)", name):
        families.add("google")
    return next(iter(families)) if len(families) == 1 else "unknown"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceError("event is missing an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"invalid event timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_regular_file(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise EvidenceError(f"file not found: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise EvidenceError(f"expected a non-symlink regular file: {path}")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise EvidenceError(f"refusing event file owned by another user: {path}")


def _read_event_log(path: Path) -> tuple[bytes, list[EventRecord]]:
    _safe_regular_file(path)
    size = path.stat().st_size
    if size > MAX_EVENT_LOG_BYTES:
        raise EvidenceError(f"Copilot event log exceeds {MAX_EVENT_LOG_BYTES} bytes: {path}")
    raw = path.read_bytes()
    records: list[EventRecord] = []
    offset = 0
    for line_number, line in enumerate(raw.splitlines(keepends=True), start=1):
        offset += len(line)
        payload = line.rstrip(b"\r\n")
        if not payload:
            continue
        try:
            event = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceError(f"malformed Copilot event JSON at {path}:{line_number}") from exc
        if not isinstance(event, dict):
            raise EvidenceError(f"non-object Copilot event at {path}:{line_number}")
        records.append(EventRecord(event=event, end_offset=offset))
    return raw, records


def _session_metadata(records: Iterable[EventRecord]) -> tuple[str, str]:
    starts = [record.event for record in records if record.event.get("type") == "session.start"]
    if len(starts) != 1:
        raise EvidenceError(f"expected exactly one session.start event, found {len(starts)}")
    data = starts[0].get("data") or {}
    context = data.get("context") or {}
    session_id = data.get("sessionId")
    cwd = context.get("cwd")
    if not isinstance(session_id, str) or not session_id:
        raise EvidenceError("session.start is missing sessionId")
    if not isinstance(cwd, str) or not cwd:
        raise EvidenceError("session.start is missing context.cwd")
    return session_id, str(Path(cwd).resolve())


def _event_arguments_text(event: dict[str, Any]) -> str:
    data = event.get("data") or {}
    try:
        return json.dumps(data.get("arguments") or {}, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def _tool_result_text(event: dict[str, Any]) -> str:
    data = event.get("data") or {}
    result = data.get("result") or {}
    if not isinstance(result, dict):
        return ""
    parts = [
        value
        for value in (result.get("content"), result.get("detailedContent"))
        if isinstance(value, str)
    ]
    return "\n".join(parts)


def _is_root_event(event: dict[str, Any]) -> bool:
    return not event.get("agentId")


def _atomic_write(path: Path, payload: bytes, *, replace: bool = False) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise EvidenceError(f"refusing to overwrite existing artifact: {path}")
    temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temp, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() and not replace:
            raise EvidenceError(f"refusing to overwrite existing artifact: {path}")
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _write_json(path: Path, data: dict[str, Any], *, replace: bool = False) -> None:
    _atomic_write(path, json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n", replace=replace)


def _load_json(path: Path) -> dict[str, Any]:
    _safe_regular_file(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"JSON artifact must be an object: {path}")
    return value


def _iter_session_logs(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    return sorted(root.glob("*/events.jsonl"))


def create_challenge(
    *,
    output: Path,
    binding: str,
    cwd: Path,
    session_root: Path,
    max_age_seconds: int,
    replace: bool = False,
) -> dict[str, Any]:
    """Bind this helper invocation to one current root Copilot session."""

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{15,127}", binding):
        raise EvidenceError("--binding must be a 16..128 character stable token")
    canonical_cwd = str(cwd.resolve())
    now = datetime.now(timezone.utc)
    candidates: list[tuple[Path, bytes, EventRecord, EventRecord, str, str]] = []

    for event_path in _iter_session_logs(session_root.resolve()):
        try:
            raw, records = _read_event_log(event_path)
            session_id, session_cwd = _session_metadata(records)
        except EvidenceError:
            continue
        if session_cwd != canonical_cwd:
            continue
        for record in records:
            event = record.event
            if event.get("type") != "tool.execution_start" or not _is_root_event(event):
                continue
            data = event.get("data") or {}
            if str(data.get("toolName") or "").lower() not in {"bash", "shell", "powershell"}:
                continue
            model = data.get("model")
            if not isinstance(model, str) or not model.strip():
                continue
            age = (now - _parse_timestamp(event.get("timestamp"))).total_seconds()
            if age < -5 or age > max_age_seconds:
                continue
            argument_text = _event_arguments_text(event)
            if binding not in argument_text or "marker" not in argument_text:
                continue
            tool_call_id = data.get("toolCallId")
            marker_json = json.dumps(
                {"schema": CHALLENGE_SCHEMA, "status": "marker", "binding": binding},
                sort_keys=True,
                ensure_ascii=False,
            )
            completions = [
                candidate
                for candidate in records
                if candidate.event.get("type") == "tool.execution_complete"
                and _is_root_event(candidate.event)
                and (candidate.event.get("data") or {}).get("toolCallId") == tool_call_id
                and (candidate.event.get("data") or {}).get("success") is True
                and marker_json in _tool_result_text(candidate.event)
            ]
            if len(completions) != 1 or completions[0].end_offset <= record.end_offset:
                continue
            candidates.append(
                (event_path.resolve(), raw, record, completions[0], session_id, model.strip())
            )

    if not candidates:
        raise EvidenceError(
            "binding marker is not present in a current Copilot root session event",
            code=3,
        )
    if len(candidates) != 1:
        raise EvidenceError(
            f"ambiguous Copilot session binding: found {len(candidates)} matching events",
            code=4,
        )

    event_path, raw, record, completion, session_id, executor_model = candidates[0]
    executor_family = derive_model_family(executor_model)
    if executor_family not in KNOWN_FAMILIES:
        raise EvidenceError(f"host-reported executor model has unknown family: {executor_model}", code=5)
    event = record.event
    tool_call_id = (event.get("data") or {}).get("toolCallId")
    event_id = event.get("id")
    if not isinstance(tool_call_id, str) or not tool_call_id:
        raise EvidenceError("challenge tool event is missing toolCallId")
    if not isinstance(event_id, str) or not event_id:
        raise EvidenceError("challenge tool event is missing id")

    completion_id = completion.event.get("id")
    if not isinstance(completion_id, str) or not completion_id:
        raise EvidenceError("challenge marker completion is missing id")
    prefix = raw[: completion.end_offset]
    challenge = {
        "schema": CHALLENGE_SCHEMA,
        "status": "bound",
        "binding": binding,
        "nonce": secrets.token_urlsafe(24),
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "cwd": canonical_cwd,
        "session_id": session_id,
        "session_events": str(event_path),
        "challenge_event_id": event_id,
        "challenge_completion_event_id": completion_id,
        "challenge_tool_call_id": tool_call_id,
        "challenge_event_timestamp": event.get("timestamp"),
        "executor_model": executor_model,
        "executor_family": executor_family,
        "event_prefix_bytes": len(prefix),
        "event_prefix_sha256": _sha256(prefix),
    }
    _write_json(output, challenge, replace=replace)
    return challenge


def _require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"artifact is missing non-empty string field: {key}")
    return value


def _validate_challenge_prefix(challenge: dict[str, Any]) -> tuple[Path, bytes, list[EventRecord]]:
    if challenge.get("schema") != CHALLENGE_SCHEMA or challenge.get("status") != "bound":
        raise EvidenceError("unsupported or unbound Copilot challenge")
    event_path = Path(_require_string(challenge, "session_events")).resolve()
    raw, records = _read_event_log(event_path)
    prefix_length = challenge.get("event_prefix_bytes")
    if not isinstance(prefix_length, int) or prefix_length <= 0 or prefix_length > len(raw):
        raise EvidenceError("challenge event prefix length is invalid")
    if _sha256(raw[:prefix_length]) != _require_string(challenge, "event_prefix_sha256"):
        raise EvidenceError("Copilot challenge event prefix changed after binding")
    session_id, session_cwd = _session_metadata(records)
    if session_id != _require_string(challenge, "session_id"):
        raise EvidenceError("challenge session id does not match its event log")
    if session_cwd != str(Path(_require_string(challenge, "cwd")).resolve()):
        raise EvidenceError("challenge cwd does not match its event log")

    matches = [
        record
        for record in records
        if record.end_offset <= prefix_length
        and record.event.get("id") == challenge.get("challenge_event_id")
        and record.event.get("type") == "tool.execution_start"
    ]
    if len(matches) != 1:
        raise EvidenceError("challenge root tool event is missing or duplicated")
    event = matches[0].event
    data = event.get("data") or {}
    if not _is_root_event(event):
        raise EvidenceError("challenge was not issued by the root Copilot agent")
    if data.get("toolCallId") != challenge.get("challenge_tool_call_id"):
        raise EvidenceError("challenge tool-call id mismatch")
    if data.get("model") != challenge.get("executor_model"):
        raise EvidenceError("challenge executor model mismatch")
    if _require_string(challenge, "binding") not in _event_arguments_text(event):
        raise EvidenceError("challenge binding token is absent from the host tool event")
    completion_matches = [
        record
        for record in records
        if record.end_offset <= prefix_length
        and record.event.get("id") == challenge.get("challenge_completion_event_id")
        and record.event.get("type") == "tool.execution_complete"
    ]
    if len(completion_matches) != 1:
        raise EvidenceError("challenge marker completion is missing or duplicated")
    completion = completion_matches[0]
    completion_data = completion.event.get("data") or {}
    expected_marker = json.dumps(
        {
            "schema": CHALLENGE_SCHEMA,
            "status": "marker",
            "binding": _require_string(challenge, "binding"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    if (
        not _is_root_event(completion.event)
        or completion_data.get("toolCallId") != challenge.get("challenge_tool_call_id")
        or completion_data.get("success") is not True
        or expected_marker not in _tool_result_text(completion.event)
        or completion.end_offset <= matches[0].end_offset
    ):
        raise EvidenceError("challenge marker completion does not prove a successful marker call")
    return event_path, raw, records


def validate_challenge_artifact(path: Path) -> dict[str, Any]:
    """Revalidate a bound challenge before selecting an external fallback."""

    challenge = _load_json(path.resolve())
    _validate_challenge_prefix(challenge)
    executor_model = _require_string(challenge, "executor_model")
    executor_family = derive_model_family(executor_model)
    if executor_family not in KNOWN_FAMILIES:
        raise EvidenceError(
            f"host-reported executor model has unknown family: {executor_model}"
        )
    if challenge.get("executor_family") != executor_family:
        raise EvidenceError("challenge executor family does not match its host model")
    return challenge


def _native_prompt(arguments: dict[str, Any]) -> str:
    for key in ("prompt", "query", "input"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value
    return ""


def _is_rubber_duck_invocation(event: dict[str, Any], nonce: str) -> bool:
    if event.get("type") != "tool.execution_start" or not _is_root_event(event):
        return False
    data = event.get("data") or {}
    arguments = data.get("arguments") or {}
    if not isinstance(arguments, dict):
        return False
    tool_name = str(data.get("toolName") or "").lower().replace("_", "-")
    agent_name = arguments.get("agent_type", arguments.get("agentType"))
    native_agent = tool_name == "task" and agent_name == "rubber-duck"
    native_tool = tool_name in {"rubber-duck", "rubberduck"}
    if not (native_agent or native_tool):
        return False
    marker = re.compile(rf"(?m)^{re.escape(NONCE_PREFIX + nonce)}\s*$")
    return marker.search(_native_prompt(arguments)) is not None


def _extract_response(result: Any) -> str:
    if not isinstance(result, dict):
        raise EvidenceError("native reviewer tool result is not an object")
    content = result.get("content")
    detailed = result.get("detailedContent")
    if not isinstance(content, str) or not content.strip():
        raise EvidenceError("native reviewer tool result has no text content")
    if (
        isinstance(detailed, str)
        and len(detailed) >= len(content)
        and "(Full response provided to agent)" not in detailed
    ):
        return detailed
    return content


def _evidence_identity(data: dict[str, Any]) -> str:
    fields = {
        "session_id": data.get("session_id"),
        "challenge_event_id": data.get("challenge_event_id"),
        "tool_call_id": data.get("tool_call_id"),
        "executor_model": data.get("executor_model"),
        "reviewer_model": data.get("reviewer_model"),
        "response_sha256": data.get("response_sha256"),
        "event_prefix_sha256": data.get("event_prefix_sha256"),
    }
    return f"cne_{_sha256(_canonical_json(fields))[:32]}"


def verify_native_review(
    *,
    challenge_path: Path,
    output: Path,
    response_output: Path,
    replace: bool = False,
) -> dict[str, Any]:
    """Verify and extract one native rubber-duck review from host events."""

    challenge = _load_json(challenge_path.resolve())
    event_path, raw, records = _validate_challenge_prefix(challenge)
    nonce = _require_string(challenge, "nonce")
    challenge_time = _parse_timestamp(challenge.get("challenge_event_timestamp"))

    invocations = [
        record
        for record in records
        if _parse_timestamp(record.event.get("timestamp")) >= challenge_time
        and _is_rubber_duck_invocation(record.event, nonce)
    ]
    if len(invocations) != 1:
        raise EvidenceError(
            f"expected exactly one nonce-bound native rubber-duck invocation, found {len(invocations)}",
            code=6,
        )
    invocation = invocations[0]
    challenge_prefix_length = challenge.get("event_prefix_bytes")
    if not isinstance(challenge_prefix_length, int) or invocation.end_offset <= challenge_prefix_length:
        raise EvidenceError("native rubber-duck invocation does not follow the bound challenge")
    invocation_data = invocation.event.get("data") or {}
    tool_call_id = invocation_data.get("toolCallId")
    if not isinstance(tool_call_id, str) or not tool_call_id:
        raise EvidenceError("native rubber-duck invocation is missing toolCallId")

    executor_model = invocation_data.get("model")
    if not isinstance(executor_model, str) or not executor_model:
        raise EvidenceError("native invocation is missing host-reported executor model")
    if executor_model != challenge.get("executor_model"):
        raise EvidenceError("executor model changed between challenge and native review")

    starts = [
        record
        for record in records
        if record.event.get("type") == "subagent.started"
        and (record.event.get("data") or {}).get("toolCallId") == tool_call_id
    ]
    completions = [
        record
        for record in records
        if record.event.get("type") == "subagent.completed"
        and (record.event.get("data") or {}).get("toolCallId") == tool_call_id
    ]
    failures = [
        record
        for record in records
        if record.event.get("type") == "subagent.failed"
        and (record.event.get("data") or {}).get("toolCallId") == tool_call_id
    ]
    tool_completions = [
        record
        for record in records
        if record.event.get("type") == "tool.execution_complete"
        and (record.event.get("data") or {}).get("toolCallId") == tool_call_id
    ]
    if failures:
        raise EvidenceError("native rubber-duck subagent failed", code=7)
    if (
        len(tool_completions) == 1
        and (tool_completions[0].event.get("data") or {}).get("success") is not True
    ):
        raise EvidenceError("native rubber-duck tool execution did not succeed", code=7)
    if len(starts) != 1 or len(completions) != 1 or len(tool_completions) != 1:
        raise EvidenceError(
            "native rubber-duck lifecycle is incomplete or ambiguous "
            f"(started={len(starts)}, completed={len(completions)}, tool_complete={len(tool_completions)})",
            code=7,
        )
    start_data = starts[0].event.get("data") or {}
    completion_data = completions[0].event.get("data") or {}
    tool_completion_data = tool_completions[0].event.get("data") or {}
    if start_data.get("agentName") != "rubber-duck" or completion_data.get("agentName") != "rubber-duck":
        raise EvidenceError("nonce-bound task was not completed by the rubber-duck subagent")
    if starts[0].event.get("agentId") != tool_call_id or completions[0].event.get("agentId") != tool_call_id:
        raise EvidenceError("rubber-duck lifecycle is not bound to its child agent id")
    if not (
        invocation.end_offset < starts[0].end_offset
        <= completions[0].end_offset
        < tool_completions[0].end_offset
    ):
        raise EvidenceError("native rubber-duck lifecycle events are out of order")
    completion_executor_model = tool_completion_data.get("model")
    if isinstance(completion_executor_model, str) and completion_executor_model != executor_model:
        raise EvidenceError("root executor model changed before native tool completion")

    start_model = start_data.get("model")
    reviewer_model = completion_data.get("model") or start_model
    if not isinstance(reviewer_model, str) or not reviewer_model:
        raise EvidenceError("native reviewer completion is missing its resolved model")
    if isinstance(start_model, str) and start_model and start_model != reviewer_model:
        raise EvidenceError("native reviewer model changed within one subagent lifecycle")

    response = _extract_response(tool_completion_data.get("result"))
    response_bytes = response.encode("utf-8")
    _atomic_write(response_output, response_bytes, replace=replace)

    executor_family = derive_model_family(executor_model)
    reviewer_family = derive_model_family(reviewer_model)
    if executor_family not in KNOWN_FAMILIES or reviewer_family not in KNOWN_FAMILIES:
        status = "rejected"
        reason = "unknown-model-family"
    elif executor_family == reviewer_family:
        status = "rejected"
        reason = "same-model-family"
    else:
        status = "verified"
        reason = "host-event-verified-cross-family"

    final_offset = max(invocation.end_offset, starts[0].end_offset, completions[0].end_offset, tool_completions[0].end_offset)
    prefix = raw[:final_offset]
    evidence: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "status": status,
        "reason": reason,
        "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "binding": challenge.get("binding"),
        "nonce": nonce,
        "cwd": challenge.get("cwd"),
        "session_id": challenge.get("session_id"),
        "session_events": str(event_path),
        "challenge_event_id": challenge.get("challenge_event_id"),
        "challenge_completion_event_id": challenge.get("challenge_completion_event_id"),
        "challenge_tool_call_id": challenge.get("challenge_tool_call_id"),
        "tool_call_id": tool_call_id,
        "agent_name": "rubber-duck",
        "executor_model": executor_model,
        "executor_model_source": "host-session-event",
        "executor_family": executor_family,
        "reviewer_model": reviewer_model,
        "reviewer_model_source": "host-session-event",
        "reviewer_family": reviewer_family,
        "family_relation": "different" if executor_family != reviewer_family and "unknown" not in {executor_family, reviewer_family} else "same" if executor_family == reviewer_family and executor_family != "unknown" else "unknown",
        "independence_verified": status == "verified",
        "response_path": str(response_output.resolve()),
        "response_sha256": _sha256(response_bytes),
        "event_prefix_bytes": len(prefix),
        "event_prefix_sha256": _sha256(prefix),
    }
    evidence["evidence_id"] = _evidence_identity(evidence)
    _write_json(output, evidence, replace=replace)
    if status != "verified":
        raise PolicyRejected(f"native reviewer evidence rejected: {reason}")
    return evidence


def validate_evidence_artifact(path: Path) -> dict[str, Any]:
    """Revalidate a verified evidence artifact against its event-log prefix."""

    evidence = _load_json(path.resolve())
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise EvidenceError("unsupported Copilot native evidence schema")
    if evidence.get("status") != "verified" or evidence.get("independence_verified") is not True:
        raise EvidenceError("Copilot native evidence is not verified")
    if evidence.get("agent_name") != "rubber-duck":
        raise EvidenceError("evidence agent is not rubber-duck")

    event_path = Path(_require_string(evidence, "session_events")).resolve()
    raw, records = _read_event_log(event_path)
    prefix_length = evidence.get("event_prefix_bytes")
    if not isinstance(prefix_length, int) or prefix_length <= 0 or prefix_length > len(raw):
        raise EvidenceError("evidence event prefix length is invalid")
    prefix = raw[:prefix_length]
    if _sha256(prefix) != _require_string(evidence, "event_prefix_sha256"):
        raise EvidenceError("Copilot evidence event prefix was modified")

    session_id, session_cwd = _session_metadata(records)
    if session_id != evidence.get("session_id") or session_cwd != str(Path(_require_string(evidence, "cwd")).resolve()):
        raise EvidenceError("evidence session metadata mismatch")
    tool_call_id = _require_string(evidence, "tool_call_id")
    nonce = _require_string(evidence, "nonce")
    challenge_matches = [
        record
        for record in records
        if record.end_offset <= prefix_length
        and record.event.get("id") == evidence.get("challenge_event_id")
        and record.event.get("type") == "tool.execution_start"
    ]
    challenge_completions = [
        record
        for record in records
        if record.end_offset <= prefix_length
        and record.event.get("id") == evidence.get("challenge_completion_event_id")
        and record.event.get("type") == "tool.execution_complete"
    ]
    if len(challenge_matches) != 1 or len(challenge_completions) != 1:
        raise EvidenceError("evidence challenge marker lifecycle is missing or duplicated")
    challenge_data = challenge_matches[0].event.get("data") or {}
    challenge_completion_data = challenge_completions[0].event.get("data") or {}
    expected_marker = json.dumps(
        {
            "schema": CHALLENGE_SCHEMA,
            "status": "marker",
            "binding": _require_string(evidence, "binding"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    if (
        not _is_root_event(challenge_matches[0].event)
        or not _is_root_event(challenge_completions[0].event)
        or challenge_data.get("toolCallId") != evidence.get("challenge_tool_call_id")
        or challenge_completion_data.get("toolCallId") != evidence.get("challenge_tool_call_id")
        or challenge_completion_data.get("success") is not True
        or expected_marker not in _tool_result_text(challenge_completions[0].event)
        or challenge_data.get("model") != evidence.get("executor_model")
        or challenge_completions[0].end_offset <= challenge_matches[0].end_offset
    ):
        raise EvidenceError("evidence challenge marker lifecycle is invalid")

    prefix_records = [record for record in records if record.end_offset <= prefix_length]
    invocations = [record for record in prefix_records if _is_rubber_duck_invocation(record.event, nonce)]
    invocations = [record for record in invocations if (record.event.get("data") or {}).get("toolCallId") == tool_call_id]
    starts = [record for record in prefix_records if record.event.get("type") == "subagent.started" and (record.event.get("data") or {}).get("toolCallId") == tool_call_id]
    completions = [record for record in prefix_records if record.event.get("type") == "subagent.completed" and (record.event.get("data") or {}).get("toolCallId") == tool_call_id]
    failures = [record for record in prefix_records if record.event.get("type") == "subagent.failed" and (record.event.get("data") or {}).get("toolCallId") == tool_call_id]
    tool_completions = [record for record in prefix_records if record.event.get("type") == "tool.execution_complete" and (record.event.get("data") or {}).get("toolCallId") == tool_call_id]
    if not (len(invocations) == len(starts) == len(completions) == len(tool_completions) == 1):
        raise EvidenceError("evidence lifecycle events are missing or duplicated")
    if failures:
        raise EvidenceError("evidence contains a failed native reviewer lifecycle")
    start_data = starts[0].event.get("data") or {}
    completion_data = completions[0].event.get("data") or {}
    tool_data = tool_completions[0].event.get("data") or {}
    if start_data.get("agentName") != "rubber-duck" or completion_data.get("agentName") != "rubber-duck":
        raise EvidenceError("evidence lifecycle agent mismatch")
    if starts[0].event.get("agentId") != tool_call_id or completions[0].event.get("agentId") != tool_call_id:
        raise EvidenceError("evidence child agent id mismatch")
    if not (
        challenge_completions[0].end_offset < invocations[0].end_offset
        < starts[0].end_offset
        <= completions[0].end_offset
        < tool_completions[0].end_offset
    ):
        raise EvidenceError("evidence lifecycle events are out of order")
    if not tool_data.get("success"):
        raise EvidenceError("evidence tool completion is not successful")
    executor_model = (invocations[0].event.get("data") or {}).get("model")
    reviewer_model = completion_data.get("model") or start_data.get("model")
    if executor_model != evidence.get("executor_model") or reviewer_model != evidence.get("reviewer_model"):
        raise EvidenceError("evidence model ids differ from host lifecycle events")
    if start_data.get("model") not in {None, "", reviewer_model}:
        raise EvidenceError("evidence reviewer model changed within its lifecycle")
    if tool_data.get("model") not in {None, "", executor_model}:
        raise EvidenceError("evidence executor model changed before tool completion")
    executor_family = derive_model_family(str(executor_model or ""))
    reviewer_family = derive_model_family(str(reviewer_model or ""))
    if executor_family not in KNOWN_FAMILIES or reviewer_family not in KNOWN_FAMILIES or executor_family == reviewer_family:
        raise EvidenceError("evidence no longer establishes a known cross-family pair")
    if evidence.get("executor_family") != executor_family or evidence.get("reviewer_family") != reviewer_family:
        raise EvidenceError("evidence family fields do not match its model ids")
    if evidence.get("family_relation") != "different":
        raise EvidenceError("evidence family relation is not different")
    if evidence.get("executor_model_source") != "host-session-event" or evidence.get("reviewer_model_source") != "host-session-event":
        raise EvidenceError("evidence model sources are not host session events")

    response = _extract_response(tool_data.get("result"))
    response_path = Path(_require_string(evidence, "response_path")).resolve()
    _safe_regular_file(response_path)
    response_bytes = response_path.read_bytes()
    if response_bytes != response.encode("utf-8") or _sha256(response_bytes) != evidence.get("response_sha256"):
        raise EvidenceError("native reviewer response artifact does not match the host tool result")
    if _evidence_identity(evidence) != evidence.get("evidence_id"):
        raise EvidenceError("native evidence id does not match its bound fields")
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    marker = subparsers.add_parser("marker", help="emit a binding marker in its own root tool call")
    marker.add_argument("--binding", required=True)

    challenge = subparsers.add_parser("challenge", help="bind the current Copilot root session")
    challenge.add_argument("--output", type=Path, required=True)
    challenge.add_argument("--binding", required=True)
    challenge.add_argument("--cwd", type=Path, default=Path.cwd())
    challenge.add_argument("--session-root", type=Path, default=Path.home() / ".copilot" / "session-state")
    challenge.add_argument("--max-age-seconds", type=int, default=60)
    challenge.add_argument("--replace", action="store_true")

    verify = subparsers.add_parser("verify", help="verify one completed rubber-duck subagent call")
    verify.add_argument("--challenge", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.add_argument("--response-output", type=Path, required=True)
    verify.add_argument("--replace", action="store_true")

    validate_challenge = subparsers.add_parser(
        "validate-challenge",
        help="revalidate a challenge before an opposite-family fallback",
    )
    validate_challenge.add_argument("--challenge", type=Path, required=True)

    validate = subparsers.add_parser("validate", help="revalidate an existing evidence artifact")
    validate.add_argument("--evidence", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "marker":
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{15,127}", args.binding):
                raise EvidenceError("--binding must be a 16..128 character stable token")
            result = {"schema": CHALLENGE_SCHEMA, "status": "marker", "binding": args.binding}
        elif args.command == "challenge":
            if args.max_age_seconds < 1 or args.max_age_seconds > 600:
                raise EvidenceError("--max-age-seconds must be within 1..600")
            result = create_challenge(
                output=args.output,
                binding=args.binding,
                cwd=args.cwd,
                session_root=args.session_root,
                max_age_seconds=args.max_age_seconds,
                replace=args.replace,
            )
        elif args.command == "verify":
            result = verify_native_review(
                challenge_path=args.challenge,
                output=args.output,
                response_output=args.response_output,
                replace=args.replace,
            )
        elif args.command == "validate-challenge":
            result = validate_challenge_artifact(args.challenge)
        else:
            result = validate_evidence_artifact(args.evidence)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except EvidenceError as exc:
        print(json.dumps({"status": "error", "error": str(exc), "exit_code": exc.code}), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
