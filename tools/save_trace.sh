#!/usr/bin/env bash
# save_trace.sh — Save a reviewer MCP call trace to .aris/traces/
# Part of the ARIS Review Tracing Protocol (shared-references/review-tracing.md)
#
# Policy C (forensic helper). SKILL callers MUST resolve the helper path
# through the canonical chain documented in
# `skills/shared-references/integration-contract.md` §2; the SKILL bash
# block then runs `bash "$TRACE_HELPER" --skill ... --purpose ... --model ...`.
# Do NOT hard-code `bash tools/save_trace.sh` from a SKILL; the path is
# only stable from inside the ARIS repo (manual smoke testing) and breaks
# silently in downstream user projects that have only `.aris/tools/` or
# `$ARIS_REPO/tools/`.
#
# Usage (from inside the ARIS repo, smoke test):
#   bash tools/save_trace.sh \
#     --skill "auto-review-loop" \
#     --purpose "round-1-review" \
#     --model "gpt-5.6-sol" \
#     --effort "ultra" \
#     --thread-id "019d8fe0-..." \
#     --prompt-file /tmp/prompt.txt \
#     --response-file /tmp/response.txt
#
# Or with inline content (for shorter prompts/responses):
#   bash tools/save_trace.sh \
#     --skill "experiment-audit" \
#     --purpose "code-audit" \
#     --model "gpt-5.6-sol" \
#     --effort "ultra" \
#     --thread-id "019d8fe0-..." \
#     --prompt "Review this code..." \
#     --response "Score: 7/10..."

set -euo pipefail

# --- Parse arguments ---
SKILL="" PURPOSE="" MODEL="" THREAD_ID="" PROMPT="" RESPONSE=""
PROMPT_FILE="" RESPONSE_FILE="" TRACE_MODE="${ARIS_TRACE_MODE:-full}" EFFORT="" FALLBACK_REASON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill)       SKILL="$2";         shift 2 ;;
    --purpose)     PURPOSE="$2";       shift 2 ;;
    --model)       MODEL="$2";         shift 2 ;;
    --effort)      EFFORT="$2";        shift 2 ;;
    --fallback-reason) FALLBACK_REASON="$2"; shift 2 ;;
    --thread-id)   THREAD_ID="$2";     shift 2 ;;
    --prompt)      PROMPT="$2";        shift 2 ;;
    --response)    RESPONSE="$2";      shift 2 ;;
    --prompt-file) PROMPT_FILE="$2";   shift 2 ;;
    --response-file) RESPONSE_FILE="$2"; shift 2 ;;
    --trace-mode)  TRACE_MODE="$2";    shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# --- Validate ---
if [[ -z "$SKILL" || -z "$PURPOSE" ]]; then
  echo "Error: --skill and --purpose are required" >&2
  exit 1
fi

if [[ "$TRACE_MODE" == "off" ]]; then
  exit 0
fi

# --- Read from files if provided ---
if [[ -n "$PROMPT_FILE" && -f "$PROMPT_FILE" ]]; then
  PROMPT=$(cat "$PROMPT_FILE")
fi
if [[ -n "$RESPONSE_FILE" && -f "$RESPONSE_FILE" ]]; then
  RESPONSE=$(cat "$RESPONSE_FILE")
fi

# --- Determine run directory ---
TODAY=$(date +%Y-%m-%d)
TRACES_DIR=".aris/traces/${SKILL}"
mkdir -p "$TRACES_DIR"

# Find next run number for today
RUN_NUM=1
while [[ -d "${TRACES_DIR}/${TODAY}_run$(printf '%02d' $RUN_NUM)" ]]; do
  # Check if this run dir was created in the last 2 hours (same session)
  RUN_DIR="${TRACES_DIR}/${TODAY}_run$(printf '%02d' $RUN_NUM)"
  if [[ -f "${RUN_DIR}/run.meta.json" ]]; then
    # Reuse existing run if it exists (same skill session)
    break
  fi
  RUN_NUM=$((RUN_NUM + 1))
done

RUN_ID="${TODAY}_run$(printf '%02d' $RUN_NUM)"
RUN_DIR="${TRACES_DIR}/${RUN_ID}"
mkdir -p "$RUN_DIR"

# --- Create run.meta.json if it doesn't exist ---
if [[ ! -f "${RUN_DIR}/run.meta.json" ]]; then
  cat > "${RUN_DIR}/run.meta.json" << METAEOF
{
  "skill": "${SKILL}",
  "run_id": "${RUN_ID}",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project_dir": "$(pwd)"
}
METAEOF
fi

# --- Determine call number ---
CALL_NUM=$(ls "${RUN_DIR}/"*.request.json 2>/dev/null | wc -l | tr -d ' ')
CALL_NUM=$((CALL_NUM + 1))
CALL_PREFIX=$(printf '%03d' $CALL_NUM)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# --- Write request ---
if [[ "$TRACE_MODE" == "full" ]]; then
  # Write full prompt
  python3 -c "
import json, sys
data = {
    'call_number': ${CALL_NUM},
    'purpose': '${PURPOSE}',
    'timestamp': '${TIMESTAMP}',
    'tool': 'mcp__codex__codex',
    'model': '${MODEL}',
    'effort': '${EFFORT}',
    'fallback_reason': '${FALLBACK_REASON}',
    'prompt': sys.stdin.read()
}
json.dump(data, open('${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}.request.json', 'w'), indent=2, ensure_ascii=False)
" <<< "$PROMPT"

  # Write full response
  printf '%s' "$RESPONSE" > "${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}.response.md"
else
  # Meta-only mode: no prompt/response content
  python3 -c "
import json
data = {
    'call_number': ${CALL_NUM},
    'purpose': '${PURPOSE}',
    'timestamp': '${TIMESTAMP}',
    'tool': 'mcp__codex__codex',
    'model': '${MODEL}',
    'prompt_length': ${#PROMPT},
    'response_length': ${#RESPONSE}
}
json.dump(data, open('${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}.request.json', 'w'), indent=2)
"
fi

# --- Write response metadata ---
python3 -c "
import json
data = {
    'call_number': ${CALL_NUM},
    'purpose': '${PURPOSE}',
    'timestamp': '${TIMESTAMP}',
    'thread_id': '${THREAD_ID}',
    'model': '${MODEL}',
    'status': 'ok'
}
json.dump(data, open('${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}.meta.json', 'w'), indent=2)
"

# --- Append to events.jsonl (if it exists) ---
EVENTS_FILE=".aris/meta/events.jsonl"
if [[ -d ".aris/meta" ]]; then
  python3 -c "
import json
evt = {
    'event': 'review_trace',
    'skill': '${SKILL}',
    'purpose': '${PURPOSE}',
    'thread_id': '${THREAD_ID}',
    'trace_path': '${RUN_DIR}/',
    'status': 'ok'
}
with open('${EVENTS_FILE}', 'a') as f:
    f.write(json.dumps(evt) + '\n')
" 2>/dev/null || true
fi

echo "Trace saved: ${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}" >&2
