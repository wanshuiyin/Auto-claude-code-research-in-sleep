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
#   trace_path thread_id reviewer_model reviewer_reasoning generated_at

set -uo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────
MANDATORY_AUDITS=(
    "PROOF_AUDIT.json|proof-checker"
    "PAPER_CLAIM_AUDIT.json|paper-claim-audit"
    "CITATION_AUDIT.json|citation-audit"
)
ALLOWED_VERDICTS=("PASS" "WARN" "FAIL" "NOT_APPLICABLE" "BLOCKED" "ERROR")
SUBMISSION_BLOCKING=("FAIL" "BLOCKED" "ERROR")
REQUIRED_FIELDS=(
    "audit_skill" "verdict" "reason_code" "summary"
    "audited_input_hashes" "trace_path" "thread_id"
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

add_report() {
    # add_report <audit> <status> <verdict> <stale> <issues_json_array>
    REPORT_LINES+=("    {\"audit\":\"$1\",\"status\":\"$2\",\"verdict\":\"$3\",\"stale\":$4,\"issues\":$5}")
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
            add_report "$expected_skill" "MISSING" "" "false" "$issues_json"
        else
            # draft mode: missing is fine, but record
            add_report "$expected_skill" "MISSING_DRAFT_OK" "" "false" "[]"
        fi
        return
    fi

    # Parse JSON, extract fields, compute stale
    # Single python call returns: VERDICT|FIELD_ISSUES|STALE_FILES|TRACE_OK|EXTRA
    local parsed
    parsed=$("$PY" - "$artifact_path" "$expected_skill" "$PAPER_DIR" <<'PYEOF'
import json, hashlib, os, sys
artifact_path, expected_skill, paper_dir = sys.argv[1], sys.argv[2], sys.argv[3]

REQUIRED = ["audit_skill","verdict","reason_code","summary",
            "audited_input_hashes","trace_path","thread_id",
            "reviewer_model","reviewer_reasoning","generated_at"]
ALLOWED_VERDICTS = ["PASS","WARN","FAIL","NOT_APPLICABLE","BLOCKED","ERROR"]

issues = []
verdict = ""
stale_files = []
trace_ok = True

try:
    with open(artifact_path) as f:
        data = json.load(f)
except Exception as e:
    print(f"||schema_invalid:cannot_parse_json:{e}|||")
    sys.exit(0)

# Required fields
for k in REQUIRED:
    if k not in data:
        issues.append(f"missing_field:{k}")

# Verdict valid
verdict = data.get("verdict","")
if verdict not in ALLOWED_VERDICTS:
    issues.append(f"invalid_verdict:{verdict}")

# audit_skill matches expected
if data.get("audit_skill") and data.get("audit_skill") != expected_skill:
    issues.append(f"wrong_audit_skill:{data.get('audit_skill')}_vs_{expected_skill}")

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

# Output: VERDICT|ISSUE,ISSUE|STALE,STALE|TRACE_OK
print(f"{verdict}|{','.join(issues)}|{','.join(stale_files)}|{trace_ok}")
PYEOF
)
    local v_issues v_stale v_trace
    verdict="$(echo "$parsed" | awk -F'|' '{print $1}')"
    v_issues="$(echo "$parsed" | awk -F'|' '{print $2}')"
    v_stale="$(echo "$parsed"  | awk -F'|' '{print $3}')"
    v_trace="$(echo "$parsed"  | awk -F'|' '{print $4}')"

    # Build issues array
    if [[ -n "$v_issues" ]]; then
        IFS=',' read -ra fissues <<< "$v_issues"
        for fi in "${fissues[@]}"; do issues+=("\"$fi\""); done
    fi

    # Stale handling
    if [[ -n "$v_stale" ]]; then
        IFS=',' read -ra fstale <<< "$v_stale"
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

    add_report "$expected_skill" "$status" "$verdict" "$stale" "$issues_json"
}

# ─── Run all checks ───────────────────────────────────────────────────────────
for entry in "${MANDATORY_AUDITS[@]}"; do
    artifact="${entry%%|*}"
    skill="${entry##*|}"
    verify_one "$artifact" "$skill"
done

# ─── Write report ─────────────────────────────────────────────────────────────
{
    echo "{"
    echo "  \"verifier_version\": \"1\","
    echo "  \"paper_dir\": \"$PAPER_DIR\","
    echo "  \"assurance\": \"$ASSURANCE\","
    echo "  \"generated_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    echo "  \"any_problem\": $([ "$ANY_PROBLEM" -eq 1 ] && echo true || echo false),"
    echo "  \"submission_blocking\": $([ "$ANY_BLOCKING" -eq 1 ] && echo true || echo false),"
    echo "  \"audits\": ["
    if [[ ${#REPORT_LINES[@]} -gt 0 ]]; then
        printf '%s' "${REPORT_LINES[0]}"
        for ((i=1; i<${#REPORT_LINES[@]}; i++)); do
            printf ',\n%s' "${REPORT_LINES[$i]}"
        done
        echo ""
    fi
    echo "  ]"
    echo "}"
} > "$JSON_OUT"

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
    if [[ "$status" == "OK" ]]; then mark="✓"
    elif [[ "$status" == "MISSING_DRAFT_OK" ]]; then mark="·"
    else mark="✗"
    fi
    printf "  %s  %-22s  status=%-18s verdict=%-15s stale=%s\n" \
        "$mark" "$skill" "$status" "${verdict:-(none)}" "$stale" >&2
done
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
