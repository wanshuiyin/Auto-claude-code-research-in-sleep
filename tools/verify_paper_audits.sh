#!/usr/bin/env bash
# verify_paper_audits.sh — External verifier for ARIS mandatory paper audits.
#
# Single source of truth for "are this paper's mandatory audits complete and
# current?" Called by paper-writing Phase 6 and by the audit-enforcement Stop
# hook. Both rely on this script's exit code, not on the LLM's claims.
#
# Usage:
#   bash tools/verify_paper_audits.sh <paper-dir> [--assurance draft|submission] [--json-out <path>]
#
# Defaults:
#   --assurance: read from <paper-dir>/.aris/assurance.txt if present, else "draft"
#   --json-out:  <paper-dir>/.aris/audit-verifier-report.json
#
# Exit codes:
#   0  All required audits present, schema-valid, fresh (no STALE), no
#      blocking verdicts (FAIL/BLOCKED/ERROR) at submission level
#   1  Any blocking issue (missing artifact / schema invalid / STALE / FAIL /
#      BLOCKED / ERROR at submission level)
#   2  Bad arguments
#
# Exit 0 at draft level means "audits, where present, are well-formed."
# Exit 0 at submission level additionally means "no skipped mandatory audits,
# no stale audits, no FAIL/BLOCKED/ERROR verdicts."
#
# Allowed verdicts (per assurance-contract.md):
#   PASS WARN FAIL NOT_APPLICABLE BLOCKED ERROR
#
# Required artifact fields (per assurance-contract.md):
#   audit_skill verdict reason_code summary audited_input_hashes
#   trace_path (thread_id OR agent_id) reviewer_model reviewer_reasoning generated_at
# New artifacts also emit review_independence + acceptance_status. Older
# artifacts remain readable and are conservatively classified provisional.

set -uo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────
MANDATORY_AUDITS=(
    "PROOF_AUDIT.json|proof-checker"
    "PAPER_CLAIM_AUDIT.json|paper-claim-audit"
    "CITATION_AUDIT.json|citation-audit"
    "KILL_ARGUMENT.json|kill-argument"
)
ALLOWED_VERDICTS=("PASS" "WARN" "FAIL" "NOT_APPLICABLE" "BLOCKED" "ERROR")
SUBMISSION_BLOCKING=("FAIL" "BLOCKED" "ERROR")
REQUIRED_FIELDS=(
    "audit_skill" "verdict" "reason_code" "summary"
    "audited_input_hashes" "trace_path"
    "reviewer_model" "reviewer_reasoning" "generated_at"
)

# ─── Args ─────────────────────────────────────────────────────────────────────
PAPER_DIR=""
ASSURANCE=""
JSON_OUT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --assurance) ASSURANCE="${2:?--assurance requires draft|submission}"; shift 2 ;;
        --json-out)  JSON_OUT="${2:?--json-out requires path}"; shift 2 ;;
        -h|--help)   sed -n '2,30p' "$0" | sed 's/^# \?//'; exit 0 ;;
        --*)         echo "unknown option: $1" >&2; exit 2 ;;
        *)
            if [[ -z "$PAPER_DIR" ]]; then PAPER_DIR="$1"
            else echo "unexpected positional: $1" >&2; exit 2; fi
            shift ;;
    esac
done

[[ -n "$PAPER_DIR" ]] || { echo "usage: $0 <paper-dir> [--assurance ...] [--json-out ...]" >&2; exit 2; }
[[ -d "$PAPER_DIR" ]] || { echo "paper-dir not found: $PAPER_DIR" >&2; exit 2; }
PAPER_DIR="$(cd "$PAPER_DIR" && pwd)"

# Resolve assurance level
if [[ -z "$ASSURANCE" ]]; then
    if [[ -f "$PAPER_DIR/.aris/assurance.txt" ]]; then
        ASSURANCE="$(tr -d '[:space:]' < "$PAPER_DIR/.aris/assurance.txt")"
    else
        ASSURANCE="draft"
    fi
fi
case "$ASSURANCE" in
    draft|submission) ;;
    *) echo "invalid --assurance: $ASSURANCE (expected draft or submission)" >&2; exit 2 ;;
esac

[[ -n "$JSON_OUT" ]] || JSON_OUT="$PAPER_DIR/.aris/audit-verifier-report.json"
mkdir -p "$(dirname "$JSON_OUT")"

# ─── Helpers ──────────────────────────────────────────────────────────────────
SHA256() {
    if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
    else echo "no_sha256_tool"; fi
}

PY=python3
command -v "$PY" >/dev/null 2>&1 || { echo "python3 required for JSON parsing" >&2; exit 2; }

# Output accumulator
declare -a REPORT_LINES=()
ANY_BLOCKING=0
ANY_PROBLEM=0
ANY_PROVISIONAL=0

add_report() {
    # add_report <audit> <status> <verdict> <stale> <review_independence> <issues_json_array>
    # Do not interpolate artifact-derived values into JSON in Bash. Audit fields
    # are model-controlled, so serialize every row through Python.
    REPORT_LINES+=("$("$PY" - "$1" "$2" "$3" "$4" "$5" "$6" <<'PYEOF'
import json, sys
try:
    issues = json.loads(sys.argv[6])
except (TypeError, json.JSONDecodeError):
    issues = [sys.argv[6]]
print(json.dumps({
    "audit": sys.argv[1],
    "status": sys.argv[2],
    "verdict": sys.argv[3],
    "stale": sys.argv[4].lower() == "true",
    "review_independence": sys.argv[5],
    "issues": issues,
}, ensure_ascii=False, separators=(",", ":")))
PYEOF
)" )
}

is_in() {
    # is_in <needle> <haystack-element-1> <haystack-element-2> ...
    local needle="$1"; shift
    for e in "$@"; do [[ "$e" == "$needle" ]] && return 0; done
    return 1
}

# ─── Per-audit verification ───────────────────────────────────────────────────
verify_one() {
    local artifact_name="$1" expected_skill="$2"
    local artifact_path="$PAPER_DIR/$artifact_name"
    local issues=()
    local verdict=""
    local stale="false"

    if [[ ! -f "$artifact_path" ]]; then
        if [[ "$ASSURANCE" == "submission" ]]; then
            issues+=("\"missing_artifact: $artifact_name\"")
            ANY_BLOCKING=1
            ANY_PROBLEM=1
            local issues_json="[$(IFS=,; echo "${issues[*]}")]"
            add_report "$expected_skill" "MISSING" "" "false" "unavailable" "$issues_json"
        else
            # draft mode: missing is fine, but record
            ANY_PROVISIONAL=1
            add_report "$expected_skill" "MISSING_DRAFT_OK" "" "false" "unavailable" "[]"
        fi
        return
    fi

    # Parse JSON, extract fields, compute stale
    # Single python call returns: VERDICT|FIELD_ISSUES|STALE_FILES|TRACE_OK|INDEPENDENCE
    local parsed
    parsed=$("$PY" - "$artifact_path" "$expected_skill" "$PAPER_DIR" <<'PYEOF'
import json, hashlib, os, sys
artifact_path, expected_skill, paper_dir = sys.argv[1], sys.argv[2], sys.argv[3]

REQUIRED = ["audit_skill","verdict","reason_code","summary",
            "audited_input_hashes","trace_path",
            "reviewer_model","reviewer_reasoning","generated_at"]
ALLOWED_VERDICTS = ["PASS","WARN","FAIL","NOT_APPLICABLE","BLOCKED","ERROR"]
FAMILIES = [
    ("anthropic", ("claude", "opus", "sonnet", "haiku")),
    ("openai", ("gpt", "codex", "oracle", "chatgpt", "o1", "o3", "o4")),
    ("google", ("gemini", "palm", "bard")),
    ("deepseek", ("deepseek",)), ("minimax", ("minimax", "abab")),
    ("moonshot", ("kimi", "moonshot")), ("qwen", ("qwen", "tongyi")),
    ("xai", ("grok",)), ("meta", ("llama",)), ("mistral", ("mistral", "mixtral")),
]
SHORT = {"o1", "o3", "o4"}

def model_family(name):
    import re
    name = (name or "").strip().lower()
    if name == "deterministic" or name.startswith("deterministic:"):
        return "deterministic"
    tokens = set(re.split(r"[^a-z0-9.]+", name))
    found = {
        family for family, needles in FAMILIES
        if any((needle in tokens) if needle in SHORT else (needle in name)
               for needle in needles)
    }
    return next(iter(found)) if len(found) == 1 else "unknown"

issues = []
verdict = ""
stale_files = []
trace_ok = True
independence = "legacy-unspecified"

def _san(x):
    # the |-protocol to bash is a trust boundary: artifact-controlled text must
    # not be able to smuggle field separators or newlines into it
    import re as _re
    return _re.sub(r"[|,\r\n]", "_", str(x))

def _emit(verdict, issues, stale, trace_ok, independence):
    print("|".join([_san(verdict), ";".join(_san(i) for i in issues),
                    ";".join(_san(x) for x in stale), _san(trace_ok), _san(independence)]))

try:
    with open(artifact_path) as f:
        data = json.load(f)
except Exception:
    _emit("BLOCKED", ["schema_invalid:cannot_parse_json"], [], False, "unknown")
    sys.exit(0)
if not isinstance(data, dict):
    _emit("BLOCKED", ["schema_invalid:not_a_json_object"], [], False, "unknown")
    sys.exit(0)

try:

    # Required fields
    for k in REQUIRED:
        if k not in data:
            issues.append(f"missing_field:{k}")
    if not data.get("thread_id") and not data.get("agent_id"):
        issues.append("missing_field:thread_id_or_agent_id")

    # Verdict valid
    verdict = data.get("verdict","")
    if verdict not in ALLOWED_VERDICTS:
        issues.append(f"invalid_verdict:{verdict}")

    # audit_skill matches expected
    if data.get("audit_skill") and data.get("audit_skill") != expected_skill:
        issues.append(f"wrong_audit_skill:{data.get('audit_skill')}_vs_{expected_skill}")

    # Review-independence metadata. Legacy artifacts (with none of the new fields)
    # remain schema-readable but cannot prove independent acceptance, so the aggregate
    # treats them provisional. Any partially-new artifact is invalid: it must retain
    # executor/reviewer provenance and prove its claimed independence.
    new_fields = ("review_independence", "acceptance_status", "executor_model",
                  "executor_family", "reviewer_family")
    if any(k in data for k in new_fields):
        for k in new_fields:
            if not data.get(k):
                issues.append(f"missing_field:{k}")
        independence = data.get("review_independence", "")
        if independence not in ("same-family", "cross-family", "deterministic"):
            issues.append(f"invalid_review_independence:{independence}")
        executor_family = model_family(data.get("executor_model", ""))
        reviewer_family = model_family(data.get("reviewer_model", ""))
        # A deterministic verifier is a process, not a model family, so it may
        # formally accept artifacts produced by tooling whose model family is not
        # known. Same-/cross-family model reviews still fail closed on unknowns.
        if reviewer_family == "unknown" or (
            independence != "deterministic" and executor_family == "unknown"
        ):
            issues.append(
                f"unrecognized_model_family:executor={executor_family},reviewer={reviewer_family}")
        if data.get("executor_family") != executor_family:
            issues.append(f"executor_family_mismatch:{data.get('executor_family')}_vs_{executor_family}")
        if data.get("reviewer_family") != reviewer_family:
            issues.append(f"reviewer_family_mismatch:{data.get('reviewer_family')}_vs_{reviewer_family}")
        if independence == "same-family":
            expected_acceptance = "provisional"
            if executor_family == "deterministic" or reviewer_family == "deterministic" or executor_family != reviewer_family:
                issues.append("same_family_independence_mismatch")
        elif independence == "cross-family":
            expected_acceptance = "accepted"
            if reviewer_family == "deterministic" or executor_family == reviewer_family:
                issues.append("cross_family_independence_mismatch")
        else:
            expected_acceptance = "accepted"
            if reviewer_family != "deterministic":
                issues.append("deterministic_independence_mismatch")
            else:
                # These four audits are SEMANTIC (proof/claims/citations/attack) —
                # a self-reported deterministic label cannot acquit them; only a
                # real cross-family model review can. Whitelist is empty until a
                # genuinely deterministic audit type exists AND binds its report.
                issues.append(
                    f"deterministic_reviewer_not_allowed_for_semantic_audit:{expected_skill}")
        if data.get("acceptance_status") != expected_acceptance:
            issues.append(
                f"acceptance_status_mismatch:{data.get('acceptance_status')}_vs_{expected_acceptance}")

    # Hashes are dict and recompute
    hashes = data.get("audited_input_hashes", {})
    if not isinstance(hashes, dict):
        issues.append("audited_input_hashes_not_dict")
    else:
        for rel_path, recorded in hashes.items():
            # Strip 'sha256:' prefix
            if isinstance(recorded, str) and recorded.startswith("sha256:"):
                recorded_hex = recorded.split(":",1)[1]
            else:
                recorded_hex = recorded
            full_path = os.path.join(paper_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
            if not os.path.isfile(full_path):
                stale_files.append(f"{rel_path}:file_gone")
                continue
            try:
                with open(full_path,"rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
                if h != recorded_hex:
                    stale_files.append(rel_path)
            except Exception as e:
                stale_files.append(f"{rel_path}:read_error_{e}")

    # Trace path exists and is non-empty
    trace_path = data.get("trace_path","")
    if trace_path:
        full_trace = os.path.join(paper_dir, trace_path) if not os.path.isabs(trace_path) else trace_path
        if os.path.isdir(full_trace):
            try:
                if not any(True for _ in os.scandir(full_trace)):
                    trace_ok = False
                    issues.append(f"trace_path_empty:{trace_path}")
            except Exception as e:
                trace_ok = False
                issues.append(f"trace_path_unreadable:{trace_path}")
        elif os.path.isfile(full_trace):
            try:
                if os.path.getsize(full_trace) == 0:
                    trace_ok = False
                    issues.append(f"trace_path_empty_file:{trace_path}")
            except Exception as e:
                trace_ok = False
                issues.append(f"trace_path_unreadable:{trace_path}")
        else:
            trace_ok = False
            issues.append(f"trace_path_missing:{trace_path}")

except Exception as e:  # any analysis crash is a BLOCKING schema failure, never fail-open
    _emit("BLOCKED", [f"internal_error:{type(e).__name__}"], [], False, "unknown")
    sys.exit(0)

# Output protocol: VERDICT|ISSUE;ISSUE|STALE;STALE|TRACE_OK|INDEPENDENCE (all sanitized)
_emit(verdict, issues, stale_files, trace_ok, independence)
PYEOF
)
    local prc=$?
    if [[ $prc -ne 0 || -z "$parsed" ]]; then
        # the analyzer itself failed — NEVER fail open
        if [[ "$ASSURANCE" == "submission" ]]; then ANY_BLOCKING=1; fi
        ANY_PROBLEM=1
        add_report "$expected_skill" "SCHEMA_INVALID" "BLOCKED" "false" "unknown" "[\"analyzer_failed_rc_${prc}\"]"
        return
    fi
    local v_issues v_stale v_trace v_independence
    verdict="$(echo "$parsed" | awk -F'|' '{print $1}')"
    v_issues="$(echo "$parsed" | awk -F'|' '{print $2}')"
    v_stale="$(echo "$parsed"  | awk -F'|' '{print $3}')"
    v_trace="$(echo "$parsed"  | awk -F'|' '{print $4}')"
    v_independence="$(echo "$parsed"  | awk -F'|' '{print $5}')"

    if [[ "$v_independence" == "same-family" || "$v_independence" == "legacy-unspecified" ]]; then
        ANY_PROVISIONAL=1
    fi

    # Build issues array
    if [[ -n "$v_issues" ]]; then
        IFS=';' read -ra fissues <<< "$v_issues"
        for fi in "${fissues[@]}"; do issues+=("\"$fi\""); done
    fi

    # Stale handling
    if [[ -n "$v_stale" ]]; then
        IFS=';' read -ra fstale <<< "$v_stale"
        for fs in "${fstale[@]}"; do issues+=("\"stale:$fs\""); done
        stale="true"
        if [[ "$ASSURANCE" == "submission" ]]; then
            ANY_BLOCKING=1
        fi
        ANY_PROBLEM=1
    fi

    # Submission-blocking verdict?
    if [[ "$ASSURANCE" == "submission" ]] && is_in "$verdict" "${SUBMISSION_BLOCKING[@]}"; then
        ANY_BLOCKING=1
        ANY_PROBLEM=1
    fi

    # Schema or missing fields → blocking at submission
    if [[ ${#issues[@]} -gt 0 ]]; then
        if [[ "$ASSURANCE" == "submission" ]]; then ANY_BLOCKING=1; fi
        ANY_PROBLEM=1
    fi

    # Verdict must be one of the known values — anything else blocks at submission
    case "$verdict" in
        PASS|WARN|FAIL|NOT_APPLICABLE|BLOCKED|ERROR) : ;;
        *)
            issues+=("\"unknown_verdict_token\"")
            if [[ "$ASSURANCE" == "submission" ]]; then ANY_BLOCKING=1; fi
            ANY_PROBLEM=1
            ;;
    esac
    # An empty/schema-invalid verdict blocks at submission (no silent pass-through)
    if [[ -z "$verdict" && "$ASSURANCE" == "submission" ]]; then
        ANY_BLOCKING=1; ANY_PROBLEM=1
    fi

    # Status label
    local status="OK"
    if [[ -z "$verdict" ]]; then status="SCHEMA_INVALID"
    elif [[ "$stale" == "true" ]]; then status="STALE"
    elif is_in "$verdict" "${SUBMISSION_BLOCKING[@]}"; then status="BLOCKING_VERDICT"
    elif [[ ${#issues[@]} -gt 0 ]]; then status="HAS_ISSUES"
    fi

    local issues_json
    if [[ ${#issues[@]} -eq 0 ]]; then issues_json="[]"
    else issues_json="[$(IFS=,; echo "${issues[*]}")]"
    fi

    add_report "$expected_skill" "$status" "$verdict" "$stale" "$v_independence" "$issues_json"
}

# ─── Run all checks ───────────────────────────────────────────────────────────
for entry in "${MANDATORY_AUDITS[@]}"; do
    artifact="${entry%%|*}"
    skill="${entry##*|}"
    verify_one "$artifact" "$skill"
done

# ─── Write report ─────────────────────────────────────────────────────────────
OVERALL_ASSURANCE="accepted"
if [[ "$ANY_BLOCKING" -eq 1 ]]; then
    OVERALL_ASSURANCE="blocked"
elif [[ "$ANY_PROVISIONAL" -eq 1 ]]; then
    OVERALL_ASSURANCE="provisional"
fi

"$PY" - "$JSON_OUT" "$PAPER_DIR" "$ASSURANCE" "$ANY_PROBLEM" "$ANY_BLOCKING" "$OVERALL_ASSURANCE" "${REPORT_LINES[@]}" <<'PYEOF'
import json, sys
from datetime import datetime, timezone

json_out, paper_dir, assurance, any_problem, any_blocking, overall, *rows = sys.argv[1:]
report = {
    "verifier_version": "2",
    "paper_dir": paper_dir,
    "assurance": assurance,
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "any_problem": any_problem == "1",
    "submission_blocking": any_blocking == "1",
    "overall_assurance": overall,
    "audits": [json.loads(row) for row in rows],
}
with open(json_out, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
    f.write("\n")
PYEOF

# ─── Human-readable summary to stderr ─────────────────────────────────────────
echo "" >&2
echo "Audit verifier report ($ASSURANCE)" >&2
echo "  paper:      $PAPER_DIR" >&2
echo "  json:       $JSON_OUT" >&2
echo "" >&2
for line in "${REPORT_LINES[@]}"; do
    skill="$(echo "$line" | sed -n 's/.*"audit":"\([^"]*\)".*/\1/p')"
    status="$(echo "$line" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p')"
    verdict="$(echo "$line" | sed -n 's/.*"verdict":"\([^"]*\)".*/\1/p')"
    stale="$(echo "$line" | sed -n 's/.*"stale":\([^,]*\).*/\1/p')"
    independence="$(echo "$line" | sed -n 's/.*"review_independence":"\([^"]*\)".*/\1/p')"
    if [[ "$status" == "OK" ]]; then mark="✓"
    elif [[ "$status" == "MISSING_DRAFT_OK" ]]; then mark="·"
    else mark="✗"
    fi
    printf "  %s  %-22s  status=%-18s verdict=%-15s independence=%-18s stale=%s\n" \
        "$mark" "$skill" "$status" "${verdict:-(none)}" "$independence" "$stale" >&2
done
echo "  overall assurance: $OVERALL_ASSURANCE" >&2
echo "" >&2

# ─── Exit ─────────────────────────────────────────────────────────────────────
if [[ "$ASSURANCE" == "submission" && "$ANY_BLOCKING" -eq 1 ]]; then
    echo "FAIL: submission-level enforcement triggered." >&2
    echo "      Fix the issues above (or downgrade to --assurance draft) before finalizing." >&2
    exit 1
fi
if [[ "$ASSURANCE" == "draft" && "$ANY_PROBLEM" -eq 1 ]]; then
    # Draft level: surface but do not block
    echo "WARN: draft-mode artifacts present but have issues (see above). Not blocking." >&2
    exit 0
fi
exit 0
