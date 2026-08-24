#!/usr/bin/env bash
# save_trace.sh — Save a reviewer call trace to .aris/traces/
# Part of the ARIS Review Tracing Protocol (shared-references/review-tracing.md)
#
# Policy C (forensic helper). SKILL callers MUST resolve the helper path
# through the canonical chain documented in
# `skills/shared-references/integration-contract.md` §2; the SKILL bash
# block then runs `bash "$TRACE_HELPER" --skill ... --purpose ... --model ...`.
# Do NOT hard-code `bash tools/save_trace.sh` from a SKILL; the path is
# only stable from inside the ARIS repo (manual smoke testing) and breaks
# silently in downstream user projects that have only `.aris/tools/`,
# `$ARIS_REPO/tools/` (env var or manifest), or `$ARIS_REPO/tools/` resolved
# via the global pointer file `~/.aris/repo` (#366).
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
PROMPT_FILE="" RESPONSE_FILE="" TRACE_MODE="${ARIS_TRACE_MODE:-full}" EFFORT="" FALLBACK_REASON="" STATUS="ok"
BACKEND="" TOOL="" EXECUTOR="" EXECUTOR_MODEL="" EXECUTOR_FAMILY="" REVIEWER_PROFILE="" REVIEWER_FAMILY="" INDEPENDENCE_VERIFIED=""
REQUESTED_REVIEWER_MODEL="" REPORTED_REVIEWER_MODEL="" MEMORY_HASH=""
EXECUTOR_MODEL_SOURCE="unavailable" REVIEWER_MODEL_SOURCE="unavailable" FAMILY_RELATION="unknown"
NATIVE_EVIDENCE="" NATIVE_EVIDENCE_ID="" NATIVE_EVIDENCE_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill)       SKILL="$2";         shift 2 ;;
    --purpose)     PURPOSE="$2";       shift 2 ;;
    --model)       MODEL="$2";         shift 2 ;;
    --effort)      EFFORT="$2";        shift 2 ;;
    --fallback-reason) FALLBACK_REASON="$2"; shift 2 ;;
    --status)      STATUS="$2";        shift 2 ;;
    --thread-id)   THREAD_ID="$2";     shift 2 ;;
    --prompt)      PROMPT="$2";        shift 2 ;;
    --response)    RESPONSE="$2";      shift 2 ;;
    --prompt-file) PROMPT_FILE="$2";   shift 2 ;;
    --response-file) RESPONSE_FILE="$2"; shift 2 ;;
    --trace-mode)  TRACE_MODE="$2";    shift 2 ;;
    --backend)            BACKEND="$2";            shift 2 ;;
    --tool)               TOOL="$2";               shift 2 ;;
    --executor)           EXECUTOR="$2";           shift 2 ;;
    --executor-model)     EXECUTOR_MODEL="$2";     shift 2 ;;
    --executor-family)    EXECUTOR_FAMILY="$2";    shift 2 ;;
    --reviewer-profile)   REVIEWER_PROFILE="$2";   shift 2 ;;
    --reviewer-family)    REVIEWER_FAMILY="$2";    shift 2 ;;
    --requested-reviewer-model) REQUESTED_REVIEWER_MODEL="$2"; shift 2 ;;
    --reported-reviewer-model)  REPORTED_REVIEWER_MODEL="$2";  shift 2 ;;
    --independence-verified) INDEPENDENCE_VERIFIED="$2"; shift 2 ;;
    --memory-hash)        MEMORY_HASH="$2";        shift 2 ;;
    --native-evidence)    NATIVE_EVIDENCE="$2";    shift 2 ;;
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

# Derive provenance from model identities, never from caller-supplied family or
# independence labels.  The legacy family/independence flags remain accepted so
# older callers do not break, but they are only consistency hints.
derive_model_family() {
  ST_MODEL_NAME="$1" python3 -c '
import os, re

name = (os.environ.get("ST_MODEL_NAME") or "").strip().lower()
families = set()
if re.search(r"(^|[^a-z0-9])(gpt|chatgpt|codex|oracle|o1|o3|o4)([^a-z0-9]|$)", name):
    families.add("openai")
if re.search(r"(^|[^a-z0-9])(claude|sonnet|opus|haiku|anthropic)([^a-z0-9]|$)", name):
    families.add("anthropic")
if re.search(r"(^|[^a-z0-9])(gemini|google)([^a-z0-9]|$)", name):
    families.add("google")
print(next(iter(families)) if len(families) == 1 else "unknown")
'
}

lowercase() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

CALLER_EXECUTOR_FAMILY="$EXECUTOR_FAMILY"
CALLER_REVIEWER_FAMILY="$REVIEWER_FAMILY"
CALLER_INDEPENDENCE_VERIFIED="$INDEPENDENCE_VERIFIED"

if [[ "$(lowercase "$BACKEND")" == "copilot-native" ]]; then
  [[ -n "$TOOL" ]] || TOOL="task(agent_type=rubber-duck)"
  [[ -n "$EXECUTOR" ]] || EXECUTOR="copilot"
  if [[ -z "$NATIVE_EVIDENCE" ]]; then
    if [[ "$(lowercase "$STATUS")" != "error" ]]; then
      echo "Error: successful --backend copilot-native traces require --native-evidence" >&2
      exit 1
    fi
    # A dispatch can fail before any reviewer lifecycle/evidence exists. Keep
    # that attempt traceable, but never promote caller model claims to host
    # evidence or verified independence.
    if [[ -n "$EXECUTOR_MODEL" ]]; then
      EXECUTOR_MODEL_SOURCE="caller-declared"
    fi
  else
    NATIVE_HELPER="$(dirname "$0")/copilot_native_evidence.py"
    if [[ ! -f "$NATIVE_HELPER" ]]; then
      echo "Error: copilot_native_evidence.py is unavailable beside save_trace.sh" >&2
      exit 1
    fi
    NATIVE_JSON=$(python3 "$NATIVE_HELPER" validate --evidence "$NATIVE_EVIDENCE") || {
      echo "Error: native Copilot evidence validation failed" >&2
      exit 1
    }
    NATIVE_EXECUTOR_MODEL=$(ST_NATIVE_JSON="$NATIVE_JSON" python3 -c 'import json, os; print(json.loads(os.environ["ST_NATIVE_JSON"])["executor_model"], end="")')
    NATIVE_REVIEWER_MODEL=$(ST_NATIVE_JSON="$NATIVE_JSON" python3 -c 'import json, os; print(json.loads(os.environ["ST_NATIVE_JSON"])["reviewer_model"], end="")')
    NATIVE_EVIDENCE_ID=$(ST_NATIVE_JSON="$NATIVE_JSON" python3 -c 'import json, os; print(json.loads(os.environ["ST_NATIVE_JSON"])["evidence_id"], end="")')
    NATIVE_RESPONSE_PATH=$(ST_NATIVE_JSON="$NATIVE_JSON" python3 -c 'import json, os; print(json.loads(os.environ["ST_NATIVE_JSON"])["response_path"], end="")')
    if [[ -n "$EXECUTOR_MODEL" && "$EXECUTOR_MODEL" != "$NATIVE_EXECUTOR_MODEL" ]]; then
      echo "Error: --executor-model disagrees with native host-event evidence" >&2
      exit 1
    fi
    if [[ -n "$REPORTED_REVIEWER_MODEL" && "$REPORTED_REVIEWER_MODEL" != "$NATIVE_REVIEWER_MODEL" ]]; then
      echo "Error: --reported-reviewer-model disagrees with native host-event evidence" >&2
      exit 1
    fi
    if [[ -n "$MODEL" && "$MODEL" != "$NATIVE_REVIEWER_MODEL" ]]; then
      echo "Error: --model disagrees with native host-event evidence" >&2
      exit 1
    fi
    EXECUTOR_MODEL="$NATIVE_EXECUTOR_MODEL"
    REPORTED_REVIEWER_MODEL="$NATIVE_REVIEWER_MODEL"
    MODEL="$NATIVE_REVIEWER_MODEL"
    RESPONSE_FILE="$NATIVE_RESPONSE_PATH"
    EXECUTOR_MODEL_SOURCE="host-session-event"
    REVIEWER_MODEL_SOURCE="host-session-event"
    NATIVE_EVIDENCE_PATH=$(ST_PATH="$NATIVE_EVIDENCE" python3 -c 'import os; print(os.path.abspath(os.environ["ST_PATH"]))')
  fi
elif [[ -n "$NATIVE_EVIDENCE" ]]; then
  echo "Error: --native-evidence is valid only with --backend copilot-native" >&2
  exit 1
elif [[ -n "$EXECUTOR_MODEL" ]]; then
  # Copilot CLI exposes no stable parent-session attestation to this child
  # helper.  The value is useful for routing, but remains caller-declared.
  EXECUTOR_MODEL_SOURCE="caller-declared"
fi

EFFECTIVE_REVIEWER_MODEL="$REPORTED_REVIEWER_MODEL"
case "$(lowercase "$EFFECTIVE_REVIEWER_MODEL")" in
  ""|unknown|unavailable|none|null)
    EFFECTIVE_REVIEWER_MODEL="${REQUESTED_REVIEWER_MODEL:-$MODEL}"
    [[ -n "$EFFECTIVE_REVIEWER_MODEL" ]] && REVIEWER_MODEL_SOURCE="requested"
    ;;
  *)
    if [[ "$(lowercase "$BACKEND")" != "copilot-native" ]]; then
      REVIEWER_MODEL_SOURCE="backend-reported"
    fi
    ;;
esac

EXECUTOR_FAMILY="$(derive_model_family "$EXECUTOR_MODEL")"
REVIEWER_FAMILY="$(derive_model_family "$EFFECTIVE_REVIEWER_MODEL")"

if [[ -n "$CALLER_EXECUTOR_FAMILY" && "$(lowercase "$CALLER_EXECUTOR_FAMILY")" != "$EXECUTOR_FAMILY" ]]; then
  echo "warning: ignoring executor family '$CALLER_EXECUTOR_FAMILY'; model '$EXECUTOR_MODEL' derives as '$EXECUTOR_FAMILY'" >&2
fi
if [[ -n "$CALLER_REVIEWER_FAMILY" && "$(lowercase "$CALLER_REVIEWER_FAMILY")" != "$REVIEWER_FAMILY" ]]; then
  echo "warning: ignoring reviewer family '$CALLER_REVIEWER_FAMILY'; model '$EFFECTIVE_REVIEWER_MODEL' derives as '$REVIEWER_FAMILY'" >&2
fi

if [[ "$EXECUTOR_FAMILY" == "unknown" || "$REVIEWER_FAMILY" == "unknown" ]]; then
  FAMILY_RELATION="unknown"
  INDEPENDENCE_VERIFIED="unverified"
elif [[ "$EXECUTOR_FAMILY" != "$REVIEWER_FAMILY" ]]; then
  FAMILY_RELATION="different"
  if [[ "$(lowercase "$BACKEND")" == "copilot-native" \
        && "$EXECUTOR_MODEL_SOURCE" == "host-session-event" \
        && "$REVIEWER_MODEL_SOURCE" == "host-session-event" ]]; then
    INDEPENDENCE_VERIFIED="true"
  else
    # A different pair of model strings is a routing fact, not independent
    # proof of the parent executor's actual model.
    INDEPENDENCE_VERIFIED="unverified"
  fi
else
  FAMILY_RELATION="same"
  INDEPENDENCE_VERIFIED="false"
fi
if [[ -n "$CALLER_INDEPENDENCE_VERIFIED" && "$(lowercase "$CALLER_INDEPENDENCE_VERIFIED")" != "$INDEPENDENCE_VERIFIED" ]]; then
  echo "warning: ignoring independence value '$CALLER_INDEPENDENCE_VERIFIED'; model-derived value is '$INDEPENDENCE_VERIFIED'" >&2
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
  ST_SKILL="$SKILL" ST_RUN_ID="$RUN_ID" ST_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  ST_PROJ="$(pwd)" ST_OUT="${RUN_DIR}/run.meta.json" \
  ST_EXECUTOR="${EXECUTOR:-claude-code}" ST_EXECUTOR_MODEL="$EXECUTOR_MODEL" ST_EXECUTOR_FAMILY="$EXECUTOR_FAMILY" \
  ST_EXECUTOR_MODEL_SOURCE="$EXECUTOR_MODEL_SOURCE" ST_REVIEWER_MODEL_SOURCE="$REVIEWER_MODEL_SOURCE" \
  ST_REVIEWER_FAMILY="$REVIEWER_FAMILY" ST_REVIEWER_BACKEND="$BACKEND" \
  ST_FAMILY_RELATION="$FAMILY_RELATION" ST_INDEPENDENCE_VERIFIED="$INDEPENDENCE_VERIFIED" \
  ST_NATIVE_EVIDENCE_ID="$NATIVE_EVIDENCE_ID" ST_NATIVE_EVIDENCE_PATH="$NATIVE_EVIDENCE_PATH" python3 -c '
import json, os
e = os.environ
raw_iv = (e.get("ST_INDEPENDENCE_VERIFIED") or "unverified").lower()
iv = True if raw_iv == "true" else False if raw_iv == "false" else "unverified"
json.dump({"skill": e["ST_SKILL"], "run_id": e["ST_RUN_ID"],
           "started_at": e["ST_STARTED"],
           "executor": e.get("ST_EXECUTOR") or "claude-code",
           "executor_model": e.get("ST_EXECUTOR_MODEL") or None,
           "executor_model_source": e.get("ST_EXECUTOR_MODEL_SOURCE") or "unavailable",
           "executor_family": e.get("ST_EXECUTOR_FAMILY") or None,
           "reviewer_model_source": e.get("ST_REVIEWER_MODEL_SOURCE") or "unavailable",
           "reviewer_family": e.get("ST_REVIEWER_FAMILY") or None,
           "reviewer_backend": e.get("ST_REVIEWER_BACKEND") or None,
           "native_evidence_id": e.get("ST_NATIVE_EVIDENCE_ID") or None,
           "native_evidence_path": e.get("ST_NATIVE_EVIDENCE_PATH") or None,
           "family_relation": e.get("ST_FAMILY_RELATION") or "unknown",
           "independence_verified": iv,
           "project_dir": e["ST_PROJ"]},
          open(e["ST_OUT"], "w"), indent=2)
'
fi

# --- Determine call number ---
CALL_NUM=$(find "$RUN_DIR" -maxdepth 1 -name '*.request.json' 2>/dev/null | wc -l | tr -d ' ')
CALL_NUM=$((CALL_NUM + 1))
CALL_PREFIX=$(printf '%03d' $CALL_NUM)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# --- Write request ---
if [[ "$TRACE_MODE" == "full" ]]; then
  # Write full prompt
  # values pass via env — never interpolated into python source (quote/injection safety)
  ST_CALL_NUM="$CALL_NUM" ST_PURPOSE="$PURPOSE" ST_TIMESTAMP="$TIMESTAMP" \
  ST_MODEL="$MODEL" ST_EFFORT="$EFFORT" ST_FALLBACK="$FALLBACK_REASON" ST_STATUS="$STATUS" \
  ST_TOOL="$TOOL" ST_BACKEND="$BACKEND" \
  ST_EXECUTOR="${EXECUTOR:-claude-code}" ST_EXECUTOR_MODEL="$EXECUTOR_MODEL" ST_EXECUTOR_FAMILY="$EXECUTOR_FAMILY" \
  ST_EXECUTOR_MODEL_SOURCE="$EXECUTOR_MODEL_SOURCE" ST_REVIEWER_MODEL_SOURCE="$REVIEWER_MODEL_SOURCE" \
  ST_REVIEWER_FAMILY="$REVIEWER_FAMILY" ST_REVIEWER_PROFILE="$REVIEWER_PROFILE" \
  ST_REQUESTED_REVIEWER_MODEL="$REQUESTED_REVIEWER_MODEL" ST_REPORTED_REVIEWER_MODEL="$REPORTED_REVIEWER_MODEL" \
  ST_FAMILY_RELATION="$FAMILY_RELATION" ST_INDEPENDENCE_VERIFIED="$INDEPENDENCE_VERIFIED" \
  ST_MEMORY_HASH="$MEMORY_HASH" ST_NATIVE_EVIDENCE_ID="$NATIVE_EVIDENCE_ID" \
  ST_NATIVE_EVIDENCE_PATH="$NATIVE_EVIDENCE_PATH" \
  ST_OUT="${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}.request.json" python3 -c '
import json, os, sys
e = os.environ
effort_unpinned = (e.get("ST_BACKEND") == "copilot" and
                   (e.get("ST_EFFORT") or "").lower() != "xhigh")
raw_iv = (e.get("ST_INDEPENDENCE_VERIFIED") or "unverified").lower()
iv = True if raw_iv == "true" else False if raw_iv == "false" else "unverified"
data = {
    "call_number": int(e["ST_CALL_NUM"]),
    "purpose": e["ST_PURPOSE"],
    "timestamp": e["ST_TIMESTAMP"],
    "tool": e.get("ST_TOOL") or "mcp__codex__codex",
    "backend": e.get("ST_BACKEND") or "codex",
    "model": e["ST_MODEL"],
    "effort": e["ST_EFFORT"],
    "effort_unpinned": effort_unpinned,
    "fallback_reason": e["ST_FALLBACK"],
    "status": e["ST_STATUS"],
    "executor": e.get("ST_EXECUTOR") or "claude-code",
    "executor_model": e.get("ST_EXECUTOR_MODEL") or None,
    "executor_model_source": e.get("ST_EXECUTOR_MODEL_SOURCE") or "unavailable",
    "executor_family": e.get("ST_EXECUTOR_FAMILY") or None,
    "reviewer_model_source": e.get("ST_REVIEWER_MODEL_SOURCE") or "unavailable",
    "reviewer_family": e.get("ST_REVIEWER_FAMILY") or None,
    "reviewer_profile": e.get("ST_REVIEWER_PROFILE") or None,
    "requested_reviewer_model": e.get("ST_REQUESTED_REVIEWER_MODEL") or None,
    "reported_reviewer_model": e.get("ST_REPORTED_REVIEWER_MODEL") or None,
    "native_evidence_id": e.get("ST_NATIVE_EVIDENCE_ID") or None,
    "native_evidence_path": e.get("ST_NATIVE_EVIDENCE_PATH") or None,
    "family_relation": e.get("ST_FAMILY_RELATION") or "unknown",
    "independence_verified": iv,
    "memory_hash": e.get("ST_MEMORY_HASH") or None,
    "prompt": sys.stdin.read(),
}
json.dump(data, open(e["ST_OUT"], "w"), indent=2, ensure_ascii=False)
' <<< "$PROMPT"

  # Write full response
  printf '%s' "$RESPONSE" > "${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}.response.md"
else
  # Meta-only mode: no prompt/response content
  ST_CALL_NUM="$CALL_NUM" ST_PURPOSE="$PURPOSE" ST_TIMESTAMP="$TIMESTAMP" \
  ST_MODEL="$MODEL" ST_EFFORT="$EFFORT" ST_FALLBACK="$FALLBACK_REASON" ST_STATUS="$STATUS" \
  ST_PLEN="${#PROMPT}" ST_RLEN="${#RESPONSE}" \
  ST_TOOL="$TOOL" ST_BACKEND="$BACKEND" \
  ST_EXECUTOR="${EXECUTOR:-claude-code}" ST_EXECUTOR_MODEL="$EXECUTOR_MODEL" ST_EXECUTOR_FAMILY="$EXECUTOR_FAMILY" \
  ST_EXECUTOR_MODEL_SOURCE="$EXECUTOR_MODEL_SOURCE" ST_REVIEWER_MODEL_SOURCE="$REVIEWER_MODEL_SOURCE" \
  ST_REVIEWER_FAMILY="$REVIEWER_FAMILY" ST_REVIEWER_PROFILE="$REVIEWER_PROFILE" \
  ST_REQUESTED_REVIEWER_MODEL="$REQUESTED_REVIEWER_MODEL" ST_REPORTED_REVIEWER_MODEL="$REPORTED_REVIEWER_MODEL" \
  ST_FAMILY_RELATION="$FAMILY_RELATION" ST_INDEPENDENCE_VERIFIED="$INDEPENDENCE_VERIFIED" \
  ST_MEMORY_HASH="$MEMORY_HASH" ST_NATIVE_EVIDENCE_ID="$NATIVE_EVIDENCE_ID" \
  ST_NATIVE_EVIDENCE_PATH="$NATIVE_EVIDENCE_PATH" \
  ST_OUT="${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}.request.json" python3 -c '
import json, os
e = os.environ
effort_unpinned = (e.get("ST_BACKEND") == "copilot" and
                   (e.get("ST_EFFORT") or "").lower() != "xhigh")
raw_iv = (e.get("ST_INDEPENDENCE_VERIFIED") or "unverified").lower()
iv = True if raw_iv == "true" else False if raw_iv == "false" else "unverified"
data = {
    "call_number": int(e["ST_CALL_NUM"]),
    "purpose": e["ST_PURPOSE"],
    "timestamp": e["ST_TIMESTAMP"],
    "tool": e.get("ST_TOOL") or "mcp__codex__codex",
    "backend": e.get("ST_BACKEND") or "codex",
    "model": e["ST_MODEL"],
    "effort": e["ST_EFFORT"],
    "effort_unpinned": effort_unpinned,
    "fallback_reason": e["ST_FALLBACK"],
    "status": e["ST_STATUS"],
    "prompt_length": int(e["ST_PLEN"]),
    "response_length": int(e["ST_RLEN"]),
    "executor": e.get("ST_EXECUTOR") or "claude-code",
    "executor_model": e.get("ST_EXECUTOR_MODEL") or None,
    "executor_model_source": e.get("ST_EXECUTOR_MODEL_SOURCE") or "unavailable",
    "executor_family": e.get("ST_EXECUTOR_FAMILY") or None,
    "reviewer_model_source": e.get("ST_REVIEWER_MODEL_SOURCE") or "unavailable",
    "reviewer_family": e.get("ST_REVIEWER_FAMILY") or None,
    "reviewer_profile": e.get("ST_REVIEWER_PROFILE") or None,
    "requested_reviewer_model": e.get("ST_REQUESTED_REVIEWER_MODEL") or None,
    "reported_reviewer_model": e.get("ST_REPORTED_REVIEWER_MODEL") or None,
    "native_evidence_id": e.get("ST_NATIVE_EVIDENCE_ID") or None,
    "native_evidence_path": e.get("ST_NATIVE_EVIDENCE_PATH") or None,
    "family_relation": e.get("ST_FAMILY_RELATION") or "unknown",
    "independence_verified": iv,
    "memory_hash": e.get("ST_MEMORY_HASH") or None,
}
json.dump(data, open(e["ST_OUT"], "w"), indent=2)
'
fi

# --- Write response metadata ---
ST_CALL_NUM="$CALL_NUM" ST_PURPOSE="$PURPOSE" ST_TIMESTAMP="$TIMESTAMP" \
ST_THREAD="$THREAD_ID" ST_MODEL="$MODEL" ST_EFFORT="$EFFORT" \
ST_FALLBACK="$FALLBACK_REASON" ST_STATUS="$STATUS" \
ST_BACKEND="$BACKEND" ST_EXECUTOR="${EXECUTOR:-claude-code}" ST_EXECUTOR_MODEL="$EXECUTOR_MODEL" ST_EXECUTOR_FAMILY="$EXECUTOR_FAMILY" \
ST_EXECUTOR_MODEL_SOURCE="$EXECUTOR_MODEL_SOURCE" ST_REVIEWER_MODEL_SOURCE="$REVIEWER_MODEL_SOURCE" \
ST_REVIEWER_FAMILY="$REVIEWER_FAMILY" ST_REVIEWER_PROFILE="$REVIEWER_PROFILE" \
ST_REQUESTED_REVIEWER_MODEL="$REQUESTED_REVIEWER_MODEL" ST_REPORTED_REVIEWER_MODEL="$REPORTED_REVIEWER_MODEL" \
ST_FAMILY_RELATION="$FAMILY_RELATION" ST_INDEPENDENCE_VERIFIED="$INDEPENDENCE_VERIFIED" \
ST_MEMORY_HASH="$MEMORY_HASH" ST_NATIVE_EVIDENCE_ID="$NATIVE_EVIDENCE_ID" \
ST_NATIVE_EVIDENCE_PATH="$NATIVE_EVIDENCE_PATH" \
ST_OUT="${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}.meta.json" python3 -c '
import json, os
e = os.environ
effort_unpinned = (e.get("ST_BACKEND") == "copilot" and
                   (e.get("ST_EFFORT") or "").lower() != "xhigh")
raw_iv = (e.get("ST_INDEPENDENCE_VERIFIED") or "unverified").lower()
iv = True if raw_iv == "true" else False if raw_iv == "false" else "unverified"
data = {
    "call_number": int(e["ST_CALL_NUM"]),
    "purpose": e["ST_PURPOSE"],
    "timestamp": e["ST_TIMESTAMP"],
    "thread_id": e["ST_THREAD"] or None,
    "model": e["ST_MODEL"],
    "model_family": e.get("ST_REVIEWER_FAMILY") or None,
    "effort": e["ST_EFFORT"],
    "effort_unpinned": effort_unpinned,
    "fallback_reason": e["ST_FALLBACK"],
    "status": e["ST_STATUS"],
    "executor": e.get("ST_EXECUTOR") or "claude-code",
    "executor_model": e.get("ST_EXECUTOR_MODEL") or None,
    "executor_model_source": e.get("ST_EXECUTOR_MODEL_SOURCE") or "unavailable",
    "executor_family": e.get("ST_EXECUTOR_FAMILY") or None,
    "reviewer_model_source": e.get("ST_REVIEWER_MODEL_SOURCE") or "unavailable",
    "requested_reviewer_model": e.get("ST_REQUESTED_REVIEWER_MODEL") or None,
    "reported_reviewer_model": e.get("ST_REPORTED_REVIEWER_MODEL") or None,
    "native_evidence_id": e.get("ST_NATIVE_EVIDENCE_ID") or None,
    "native_evidence_path": e.get("ST_NATIVE_EVIDENCE_PATH") or None,
    "family_relation": e.get("ST_FAMILY_RELATION") or "unknown",
    "independence_verified": iv,
    "reviewer_profile": e.get("ST_REVIEWER_PROFILE") or None,
    "memory_hash": e.get("ST_MEMORY_HASH") or None,
}
json.dump(data, open(e["ST_OUT"], "w"), indent=2)
'

# --- Append to events.jsonl (if it exists) ---
EVENTS_FILE=".aris/meta/events.jsonl"
if [[ -d ".aris/meta" ]]; then
  ST_SKILL="$SKILL" ST_PURPOSE="$PURPOSE" ST_THREAD="$THREAD_ID" \
  ST_TRACE="${RUN_DIR}/" ST_STATUS="$STATUS" ST_EVENTS="$EVENTS_FILE" \
  ST_BACKEND="$BACKEND" ST_TOOL="$TOOL" \
  ST_EFFORT="$EFFORT" \
  ST_EXECUTOR="${EXECUTOR:-claude-code}" ST_EXECUTOR_MODEL="$EXECUTOR_MODEL" ST_EXECUTOR_FAMILY="$EXECUTOR_FAMILY" \
  ST_EXECUTOR_MODEL_SOURCE="$EXECUTOR_MODEL_SOURCE" ST_REVIEWER_MODEL_SOURCE="$REVIEWER_MODEL_SOURCE" \
  ST_REVIEWER_FAMILY="$REVIEWER_FAMILY" ST_FAMILY_RELATION="$FAMILY_RELATION" \
  ST_MEMORY_HASH="$MEMORY_HASH" ST_NATIVE_EVIDENCE_ID="$NATIVE_EVIDENCE_ID" \
  ST_NATIVE_EVIDENCE_PATH="$NATIVE_EVIDENCE_PATH" \
  ST_INDEPENDENCE_VERIFIED="$INDEPENDENCE_VERIFIED" python3 -c '
import json, os
e = os.environ
effort_unpinned = (e.get("ST_BACKEND") == "copilot" and
                   (e.get("ST_EFFORT") or "").lower() != "xhigh")
raw_iv = (e.get("ST_INDEPENDENCE_VERIFIED") or "unverified").lower()
iv = True if raw_iv == "true" else False if raw_iv == "false" else "unverified"
evt = {
    "event": "review_trace",
    "skill": e["ST_SKILL"],
    "purpose": e["ST_PURPOSE"],
    "thread_id": e["ST_THREAD"] or None,
    "trace_path": e["ST_TRACE"],
    "backend": e.get("ST_BACKEND") or None,
    "tool": e.get("ST_TOOL") or None,
    "executor": e.get("ST_EXECUTOR") or "claude-code",
    "executor_model": e.get("ST_EXECUTOR_MODEL") or None,
    "executor_model_source": e.get("ST_EXECUTOR_MODEL_SOURCE") or "unavailable",
    "executor_family": e.get("ST_EXECUTOR_FAMILY") or None,
    "reviewer_model_source": e.get("ST_REVIEWER_MODEL_SOURCE") or "unavailable",
    "reviewer_family": e.get("ST_REVIEWER_FAMILY") or None,
    "native_evidence_id": e.get("ST_NATIVE_EVIDENCE_ID") or None,
    "native_evidence_path": e.get("ST_NATIVE_EVIDENCE_PATH") or None,
    "family_relation": e.get("ST_FAMILY_RELATION") or "unknown",
    "effort_unpinned": effort_unpinned,
    "independence_verified": iv,
    "memory_hash": e.get("ST_MEMORY_HASH") or None,
    "status": e["ST_STATUS"],
}
with open(e["ST_EVENTS"], "a") as f:
    f.write(json.dumps(evt) + "\n")
' 2>/dev/null || true
fi

echo "Trace saved: ${RUN_DIR}/${CALL_PREFIX}-${PURPOSE}" >&2
