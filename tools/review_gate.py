#!/usr/bin/env python3
"""Deterministic state transitions for /auto-review-loop reviewer backends.

The skill remains the orchestrator.  This helper owns only the stop/continue/
escalate decision so that the safety-critical transition table is executable
and testable instead of existing solely as prose in SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from dataclasses import asdict, dataclass


TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

KNOWN_FAMILIES = {
    "openai", "anthropic", "google", "deepseek", "moonshot", "qwen",
    "zhipu", "minimax", "xiaomi", "bytedance", "xai", "meta", "mistral",
}
POSITIVE_VERDICTS = {"ready", "almost"}
VALID_BACKENDS = {"codex", "manual", "copilot", "copilot-native", "oracle-pro", "agy", "llm-chat"}
VALID_VERDICTS = POSITIVE_VERDICTS | {"not ready"}


@dataclass(frozen=True)
class Transition:
    decision: str
    next_backend: str | None
    requires_external_acquittal: bool
    identity_assurance: str
    reason: str


@dataclass(frozen=True)
class NativeEvidence:
    evidence_id: str
    executor_model: str
    reviewer_model: str
    score: float
    verdict: str


class NativeEvidenceError(RuntimeError):
    """Native evidence is missing, malformed, or cannot be validated."""


def _normalized(value: str) -> str:
    return value.strip().lower()


def derive_model_family(model: str) -> str:
    name = _normalized(model)
    families: set[str] = set()
    if re.search(r"(^|[^a-z0-9])(gpt|chatgpt|codex|oracle|o1|o3|o4)([^a-z0-9]|$)", name):
        families.add("openai")
    if re.search(r"(^|[^a-z0-9])(claude|sonnet|opus|haiku|anthropic)([^a-z0-9]|$)", name):
        families.add("anthropic")
    if re.search(r"(^|[^a-z0-9])(gemini|google)([^a-z0-9]|$)", name):
        families.add("google")
    # [0-9.]* so versioned names (qwen3-max, qwen2.5-72b) still match.
    if re.search(r"(^|[^a-z0-9])(deepseek)[0-9.]*([^a-z0-9]|$)", name):
        families.add("deepseek")
    if re.search(r"(^|[^a-z0-9])(kimi|moonshot)[0-9.]*([^a-z0-9]|$)", name):
        families.add("moonshot")
    if re.search(r"(^|[^a-z0-9])(qwen|tongyi)[0-9.]*([^a-z0-9]|$)", name):
        families.add("qwen")
    if re.search(r"(^|[^a-z0-9])(glm|zhipu)[0-9.]*([^a-z0-9]|$)", name):
        families.add("zhipu")
    if re.search(r"(^|[^a-z0-9])(minimax|abab)[0-9.]*([^a-z0-9]|$)", name):
        families.add("minimax")
    if re.search(r"(^|[^a-z0-9])(mimo|xiaomi)[0-9.]*([^a-z0-9]|$)", name):
        families.add("xiaomi")
    if re.search(r"(^|[^a-z0-9])(doubao|bytedance|volcengine)[0-9.]*([^a-z0-9]|$)", name):
        families.add("bytedance")
    if re.search(r"(^|[^a-z0-9])(grok)[0-9.]*([^a-z0-9]|$)", name):
        families.add("xai")
    if re.search(r"(^|[^a-z0-9])(llama)[0-9.]*([^a-z0-9]|$)", name):
        families.add("meta")
    if re.search(r"(^|[^a-z0-9])(mistral|mixtral)[0-9.]*([^a-z0-9]|$)", name):
        families.add("mistral")
    return next(iter(families)) if len(families) == 1 else "unknown"


def _parse_native_assessment(response: str) -> tuple[float, str]:
    score_matches = re.findall(
        r"(?im)^\s*(?:[-*]\s*)?score:\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*10\s*$",
        response,
    )
    verdict_matches = re.findall(
        r"(?im)^\s*(?:[-*]\s*)?verdict:\s*(ready|almost|not\s+ready)\s*$",
        response,
    )
    if len(score_matches) != 1 or len(verdict_matches) != 1:
        raise NativeEvidenceError(
            "native reviewer response must contain exactly one anchored Score and Verdict field"
        )
    return float(score_matches[0]), re.sub(r"\s+", " ", verdict_matches[0].lower())


def load_native_evidence(path: str | Path) -> NativeEvidence:
    try:
        from copilot_native_evidence import (
            EvidenceError as HostEvidenceError,
            validate_evidence_artifact,
        )
    except ImportError as exc:
        raise NativeEvidenceError(
            "copilot_native_evidence.py is unavailable beside review_gate.py"
        ) from exc
    try:
        artifact = validate_evidence_artifact(Path(path))
    except HostEvidenceError as exc:
        raise NativeEvidenceError(str(exc)) from exc
    response_path = artifact.get("response_path")
    if not isinstance(response_path, str) or not response_path:
        raise NativeEvidenceError("native evidence is missing response_path")
    response = Path(response_path).read_text(encoding="utf-8")
    score, verdict = _parse_native_assessment(response)
    return NativeEvidence(
        evidence_id=str(artifact["evidence_id"]),
        executor_model=str(artifact["executor_model"]),
        reviewer_model=str(artifact["reviewer_model"]),
        score=score,
        verdict=verdict,
    )


def evaluate_transition(
    *,
    round_backend: str,
    score: float,
    verdict: str,
    requires_external_acquittal: bool = False,
    executor_model: str = "",
    reviewer_model: str = "",
    codex_available: bool = False,
    manual_available: bool = False,
    manual_identity_reported: bool = False,
    native_evidence: NativeEvidence | None = None,
) -> Transition:
    """Return the authoritative transition for one completed review round.

    ``executor_model`` is caller-declared in the compatibility Copilot drive
    integration.  It is useful for fail-closed route selection, but the
    resulting family relation is not independent identity attestation.
    ``copilot-native`` never uses those caller model fields: its identities and
    structured verdict are loaded from a revalidated host event artifact.
    Family strings are never accepted as inputs; this helper derives them from
    the model identities itself.
    """

    backend = _normalized(round_backend)
    normalized_verdict = _normalized(verdict)
    executor = derive_model_family(executor_model)
    reviewer = derive_model_family(reviewer_model)

    if backend not in VALID_BACKENDS:
        return Transition(
            "review_unavailable",
            None,
            requires_external_acquittal,
            "unverified",
            f"unknown reviewer backend: {round_backend}",
        )
    if normalized_verdict not in VALID_VERDICTS:
        return Transition(
            "review_unavailable",
            None,
            requires_external_acquittal,
            "unverified",
            f"unknown verdict: {verdict}",
        )
    if not math.isfinite(score) or not 1 <= score <= 10:
        return Transition(
            "review_unavailable",
            None,
            requires_external_acquittal,
            "unverified",
            f"score must be finite and within 1..10: {score}",
        )
    if backend != "copilot-native" and native_evidence is not None:
        return Transition(
            "review_unavailable",
            None,
            requires_external_acquittal,
            "failed",
            "native Copilot evidence was supplied for a non-native backend",
        )

    positive = score >= 6 and normalized_verdict in POSITIVE_VERDICTS

    if backend == "copilot-native":
        if requires_external_acquittal:
            return Transition(
                "review_unavailable",
                None,
                True,
                "unverified",
                "invalid state: native Copilot review cannot inherit a compatibility-finalizer obligation",
            )
        if native_evidence is None:
            return Transition(
                "review_unavailable",
                None,
                False,
                "unverified",
                "native Copilot round is missing host-event evidence",
            )
        native_executor = derive_model_family(native_evidence.executor_model)
        native_reviewer = derive_model_family(native_evidence.reviewer_model)
        if native_executor not in KNOWN_FAMILIES or native_reviewer not in KNOWN_FAMILIES:
            return Transition(
                "review_unavailable",
                None,
                False,
                "failed",
                "native Copilot evidence contains an unknown model family",
            )
        if native_executor == native_reviewer:
            return Transition(
                "review_unavailable",
                None,
                False,
                "failed",
                "native Copilot reviewer is same-family as the host-reported executor",
            )
        if not math.isclose(score, native_evidence.score, rel_tol=0.0, abs_tol=1e-9):
            return Transition(
                "review_unavailable",
                None,
                False,
                "failed",
                "declared score does not match the host-bound native reviewer response",
            )
        if normalized_verdict != _normalized(native_evidence.verdict):
            return Transition(
                "review_unavailable",
                None,
                False,
                "failed",
                "declared verdict does not match the host-bound native reviewer response",
            )
        if not positive:
            return Transition(
                "continue",
                "copilot-native",
                False,
                "host_event_verified",
                f"native cross-family reviewer {native_evidence.evidence_id} did not meet the positive threshold",
            )
        return Transition(
            "stop",
            None,
            False,
            "host_event_verified",
            f"native cross-family reviewer {native_evidence.evidence_id} returned a host-bound positive verdict",
        )

    if backend == "copilot":
        if requires_external_acquittal:
            return Transition(
                "review_unavailable",
                None,
                True,
                "unverified",
                "invalid state: copilot cannot resume after finalizer escalation",
            )
        if not positive:
            return Transition(
                "continue",
                "copilot",
                False,
                "unverified",
                "copilot drive verdict is not positive",
            )
        if executor not in KNOWN_FAMILIES:
            return Transition(
                "review_unavailable",
                None,
                False,
                "unverified",
                "cannot select an opposite-family finalizer from an unknown executor family",
            )

        if executor == "openai":
            if not manual_available:
                return Transition(
                    "review_unavailable",
                    None,
                    False,
                    "caller_declared",
                    "OpenAI-family executor requires a non-OpenAI manual finalizer",
                )
            next_backend = "manual"
        elif codex_available:
            next_backend = "codex"
        elif manual_available:
            next_backend = "manual"
        else:
            return Transition(
                "review_unavailable",
                None,
                False,
                "caller_declared",
                "no policy-approved finalizer is available",
            )

        return Transition(
            "escalate",
            next_backend,
            True,
            "caller_declared",
            "copilot is drive-only; a positive verdict requires an external finalizer",
        )

    if not positive:
        return Transition(
            "continue",
            backend,
            requires_external_acquittal,
            "unverified",
            "positive threshold not met",
        )

    if backend == "llm-chat":
        if requires_external_acquittal:
            return Transition(
                "review_unavailable",
                None,
                True,
                "unverified",
                "Copilot finalizer state permits only codex or manual",
            )
        if executor not in KNOWN_FAMILIES or reviewer not in KNOWN_FAMILIES:
            return Transition(
                "review_unavailable",
                None,
                False,
                "unverified",
                "HTTP reviewer family relation cannot be derived",
            )
        if executor == reviewer:
            return Transition(
                "review_unavailable",
                None,
                False,
                "failed",
                "HTTP reviewer is same-family as the declared executor model",
            )
        return Transition(
            "stop",
            None,
            False,
            "caller_declared",
            "HTTP reviewer returned a positive cross-family verdict; executor identity remains caller-declared",
        )

    if backend in {"codex", "oracle-pro", "agy"} and not requires_external_acquittal:
        return Transition(
            "stop",
            None,
            False,
            "not_required",
            "non-Copilot backend preserves the pre-Copilot positive-stop contract",
        )

    if backend in {"oracle-pro", "agy"} and requires_external_acquittal:
        return Transition(
            "review_unavailable",
            None,
            True,
            "unverified",
            "Copilot finalizer state permits only codex or manual",
        )

    if backend == "manual" and not manual_identity_reported:
        return Transition(
            "review_unavailable",
            None,
            requires_external_acquittal,
            "unverified",
            "manual final verdict is missing its required reported model identity",
        )

    if backend == "manual":
        if executor not in KNOWN_FAMILIES or reviewer not in KNOWN_FAMILIES:
            return Transition(
                "review_unavailable",
                None,
                requires_external_acquittal,
                "unverified",
                "manual verdict family relation cannot be derived",
            )
        if executor == reviewer:
            return Transition(
                "review_unavailable",
                None,
                requires_external_acquittal,
                "failed",
                "manual reviewer is same-family as the declared executor model",
            )

    if requires_external_acquittal:
        if executor not in KNOWN_FAMILIES or reviewer not in KNOWN_FAMILIES:
            return Transition(
                "review_unavailable",
                None,
                True,
                "unverified",
                "finalizer family relation cannot be derived",
            )
        if executor == reviewer:
            return Transition(
                "review_unavailable",
                None,
                True,
                "failed",
                "finalizer is same-family as the declared executor model",
            )
        return Transition(
            "stop",
            None,
            False,
            "caller_declared",
            "policy-approved finalizer returned a positive verdict; executor identity remains caller-declared",
        )

    return Transition(
        "stop",
        None,
        False,
        "caller_declared",
        "explicit manual backend returned a positive verdict with its required model identity",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-backend", required=True, choices=sorted(VALID_BACKENDS))
    parser.add_argument("--score", required=True, type=float)
    parser.add_argument("--verdict", required=True, choices=sorted(VALID_VERDICTS))
    parser.add_argument("--requires-external-acquittal", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--executor-model", default="")
    parser.add_argument("--reviewer-model", default="")
    parser.add_argument("--codex-available", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--manual-available", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--manual-identity-reported", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--native-evidence", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    native_evidence = None
    if args.native_evidence and args.round_backend != "copilot-native":
        transition = Transition(
            "review_unavailable",
            None,
            args.requires_external_acquittal,
            "failed",
            "native Copilot evidence is valid only for --round-backend copilot-native",
        )
        print(json.dumps(asdict(transition), sort_keys=True))
        return
    if args.native_evidence:
        try:
            native_evidence = load_native_evidence(args.native_evidence)
        except (NativeEvidenceError, OSError, UnicodeError, KeyError) as exc:
            transition = Transition(
                "review_unavailable",
                None,
                args.requires_external_acquittal,
                "failed",
                f"invalid native Copilot evidence: {exc}",
            )
            print(json.dumps(asdict(transition), sort_keys=True))
            return
    transition = evaluate_transition(
        round_backend=args.round_backend,
        score=args.score,
        verdict=args.verdict,
        requires_external_acquittal=args.requires_external_acquittal,
        executor_model=args.executor_model,
        reviewer_model=args.reviewer_model,
        codex_available=args.codex_available,
        manual_available=args.manual_available,
        manual_identity_reported=args.manual_identity_reported,
        native_evidence=native_evidence,
    )
    print(json.dumps(asdict(transition), sort_keys=True))


if __name__ == "__main__":
    main()
