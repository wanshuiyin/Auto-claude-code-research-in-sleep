#!/usr/bin/env bash
# ARIS Meta-Optimize: Event Logger
# Reads Claude Code hook JSON from stdin, extracts key fields,
# appends structured event to .aris/meta/events.jsonl
#
# Called automatically by Claude Code hooks (PostToolUse, UserPromptSubmit, etc.)
# Input: JSON via stdin (Claude Code hook payload)
# Output: Appends one JSONL line to $PROJECT/.aris/meta/events.jsonl

set -euo pipefail

ARIS_META_DIR="${CLAUDE_PROJECT_DIR:-.}/.aris/meta"
mkdir -p "$ARIS_META_DIR"

# Read entire stdin into variable
PAYLOAD="$(cat)"

# Process with python3 — stdin payload passed via heredoc
python3 - "$ARIS_META_DIR/events.jsonl" << 'PYEOF' <<< "$PAYLOAD"
import json, sys, os
from datetime import datetime, timezone

log_file = sys.argv[1]

# Read payload from stdin
raw = sys.stdin.read().strip()
if not raw:
    sys.exit(0)
try:
    p = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(0)

event_name = p.get("hook_event_name", "unknown")
session_id = p.get("session_id", "")
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

record = {"ts": ts, "session": session_id, "event": event_name}

if event_name in ("PostToolUse", "PostToolUseFailure"):
    tool_name = p.get("tool_name", "")
    tool_input = p.get("tool_input", {})
    record["tool"] = tool_name

    if event_name == "PostToolUseFailure":
        record["event"] = "tool_failure"

    # Detect skill invocations
    if tool_name == "Skill":
        record["event"] = "skill_invoke"
        record["skill"] = tool_input.get("skill", "")
        record["args"] = tool_input.get("args", "")
    elif tool_name == "Bash":
        record["input_summary"] = tool_input.get("command", "")[:200]
    elif tool_name in ("Edit", "Write", "Read"):
        record["input_summary"] = tool_input.get("file_path", "")
    elif tool_name.startswith("mcp__codex__"):
        record["event"] = "codex_call"
        record["input_summary"] = tool_input.get("prompt", "")[:150]

elif event_name == "UserPromptSubmit":
    prompt = p.get("prompt", "")
    if prompt.startswith("/"):
        parts = prompt.split(None, 1)
        record["event"] = "slash_command"
        record["command"] = parts[0]
        record["args"] = parts[1] if len(parts) > 1 else ""
    else:
        record["event"] = "user_prompt"
        record["prompt_preview"] = prompt[:100]

elif event_name == "SessionStart":
    record["event"] = "session_start"
    record["source"] = p.get("source", "")
    record["model"] = p.get("model", "")

elif event_name == "SessionEnd":
    record["event"] = "session_end"

with open(log_file, "a") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")
PYEOF
