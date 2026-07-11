#!/usr/bin/env bash
# ARIS Meta-Optimize: Readiness Check
# Called by SessionEnd hook. If enough data has accumulated,
# outputs a reminder to stdout (injected into Claude's context).
#
# Trigger: ≥5 skill invocations since last /meta-optimize run

set -euo pipefail

ARIS_META_DIR="${CLAUDE_PROJECT_DIR:-.}/.aris/meta"
EVENTS_FILE="$ARIS_META_DIR/events.jsonl"
LAST_RUN_FILE="$ARIS_META_DIR/.last_optimize"

# No log = nothing to check
[ -f "$EVENTS_FILE" ] || exit 0

# Count skill invocations. Match the full event-field key so a stray
# "skill_invoke" substring inside args/prompt values can't false-match.
# Note: `grep -c` prints "0" then exits 1 on no match, so `... || echo 0`
# would produce a two-line string "0\n0" that breaks the later integer
# comparison. Use `|| true` to absorb the non-zero exit and keep the
# captured "0" alone.
TOTAL_SKILLS=$(grep -cE '"event": *"skill_invoke"' "$EVENTS_FILE" 2>/dev/null || true)
TOTAL_SKILLS=${TOTAL_SKILLS:-0}

# Check when meta-optimize was last run
if [ -f "$LAST_RUN_FILE" ]; then
    LAST_TS=$(cat "$LAST_RUN_FILE")
    # Count skill invocations AFTER last run.
    # WARNING: do NOT use `$0 > ts` here — every JSONL row starts with `{`
    # (ASCII 0x7B), which sorts greater than every digit in an ISO 8601
    # timestamp, so the comparison would degenerate to "always true" and
    # SINCE_LAST would equal TOTAL_SKILLS. Extract the embedded "ts" value
    # and compare that instead. log_event.sh emits Python json.dumps default
    # format (`"ts": "..."` with a space after the colon), so the regex
    # tolerates 0+ spaces between key and value to stay compatible if that
    # ever changes.
    SINCE_LAST=$(awk -v ts="$LAST_TS" '
        /"event": *"skill_invoke"/ {
            if (match($0, /"ts": *"[^"]+"/)) {
                event_ts = substr($0, RSTART, RLENGTH)
                sub(/^"ts": *"/, "", event_ts)
                sub(/"$/, "", event_ts)
                if (event_ts > ts) count++
            }
        }
        END { print count + 0 }
    ' "$EVENTS_FILE")
else
    SINCE_LAST=$TOTAL_SKILLS
fi

# Threshold: 5 skill invocations since last optimize
if [ "$SINCE_LAST" -ge 5 ]; then
    echo "📊 ARIS has logged $SINCE_LAST skill runs since last optimization. Run /meta-optimize to check for improvement opportunities."
fi

# Model-delta trigger (harness diet): a model bump makes existing scaffolding a
# deletion candidate, independent of usage volume. /meta-optimize records the
# session model at each run in .last_optimize_model; compare against the LATEST
# session_start event's model. Absent files (older installs, no session_start
# yet) silently skip.
LAST_MODEL_FILE="$ARIS_META_DIR/.last_optimize_model"
if [ -f "$LAST_MODEL_FILE" ]; then
    CURRENT_MODEL=$(awk '
        /"event": *"session_start"/ {
            if (match($0, /"model": *"[^"]+"/)) {
                m = substr($0, RSTART, RLENGTH)
                sub(/^"model": *"/, "", m)
                sub(/"$/, "", m)
                latest = m
            }
        }
        END { if (latest != "") print latest }
    ' "$EVENTS_FILE")
    LAST_MODEL=$(cat "$LAST_MODEL_FILE")
    if [ -n "$CURRENT_MODEL" ] && [ -n "$LAST_MODEL" ] && [ "$CURRENT_MODEL" != "$LAST_MODEL" ]; then
        echo "🔁 Model changed since last optimization ($LAST_MODEL → $CURRENT_MODEL). Run /meta-optimize — a model bump makes existing scaffolding a deletion candidate (harness diet)."
    fi
fi
