# Session Recovery & State Persistence Guide

[中文版](SESSION_RECOVERY_GUIDE_CN.md) | English

> How to maintain project state across sessions and context compaction in ARIS workflows — the core design is **Pipeline Status in your project CLAUDE.md**, with optional Claude Code hooks for automation.

## Why Session Recovery Matters

ARIS workflows can run for hours (idea discovery, auto-review loops, overnight training). Two things regularly break state continuity:

1. **Context compaction** — when the context window fills up, Claude Code auto-compresses prior messages. After compaction, the LLM only has a compressed summary and may forget which stage you're in, what experiments are running, or what to do next.
2. **Proactive new sessions** — LLM capability degrades noticeably when context usage exceeds ~50%. Experienced users proactively start fresh sessions to restore full model capability, rather than waiting for auto-compaction. This means the LLM must reconstruct project state from disk.

ARIS already persists some state to files (`review-stage/REVIEW_STATE.json`, `review-stage/AUTO_REVIEW.md`), but **there is no systematic mechanism to ensure the LLM reads those files on recovery**. After compaction, it often doesn't.

## The Core Solution: Pipeline Status

The single most important thing you can do is maintain a **`## Pipeline Status`** section in your project's `CLAUDE.md`. This is a lightweight, structured snapshot of "where the project is right now" — readable in 30 seconds, enough for any LLM to resume work.

### What Pipeline Status Contains

Add this to your project `CLAUDE.md`:

```yaml
## Pipeline Status
stage: idea-discovery | implementation | training | paper
idea: "one-line description of the current idea"
contract: idea-stage/docs/research_contract.md
current_branch: feature/idea-name
baseline: "representative dataset acc=95.2 (paper reports 95.5)"
training_status: running on server-X, GPU 0-3, tmux=train01, wandb=run_id,
  check: ssh server-X "tmux capture-pane -t train01 -p | tail -5"
active_tasks:
  - "training exp01 on server-X (tmux=exp01, GPU 0-3)"
  - "downloading dataset-Y on server-Z (tmux=download01)"
language: en         # en | zh — controls skill output language
last_updated: ""     # YYYY-MM-DD HH:mm — auto-updated by skills on every output write
next: what to do next
```

> 💡 Start from the template: `cp templates/CLAUDE_MD_TEMPLATE.md CLAUDE.md`

| Field | Purpose | Example |
|-------|---------|---------|
| `stage` | Which workflow phase you're in | `training` |
| `idea` | What you're working on | `"factorized attention gap in discrete diffusion LMs"` |
| `contract` | Pointer to detailed context | `idea-stage/docs/research_contract.md` |
| `current_branch` | Git branch for this idea | `feature/factorized-gap` |
| `baseline` | Baseline numbers for comparison | `"WikiText-103 PPL=18.2 (paper 18.5)"` |
| `training_status` | Overall training state | `running on b2, GPU 0-3, tmux=exp01` |
| `active_tasks` | All running tasks (training, downloads, evals) with location and check commands — prevents new sessions from losing track of background work | `training exp01 on b2 (GPU 0-3)` |
| `next` | Concrete next action | `"wait for training, then run eval on test set"` |
| `language` | Skill output language | `en` or `zh` — controls skill output language |
| `last_updated` | When skills last wrote output | `2025-06-15 14:30` — auto-updated by skills |

### When to Update Pipeline Status

The LLM should update Pipeline Status **immediately** when any of these happen:

- Stage transition (e.g., idea-discovery → implementation)
- Idea selected or changed
- Baseline confirmed
- Training started or finished
- Major decision made
- **User says "save", "record", "new session", "wrap up"** — this is the signal to persist all state before the user starts a fresh session

### Why You Need a Research Contract

After Workflow 1 (`/idea-discovery`), `idea-stage/IDEA_REPORT.md` contains 8-12 candidate ideas. Once you pick one and move to implementation, keeping all candidates in context wastes the LLM's working memory and degrades its output quality.

**`idea-stage/docs/research_contract.md`** solves this by extracting *only the active idea* into a focused working document — claims, experiment design, baselines, and results. New sessions read this instead of the full IDEA_REPORT.md. See [`templates/RESEARCH_CONTRACT_TEMPLATE.md`](../templates/RESEARCH_CONTRACT_TEMPLATE.md) for the template.

- **Created**: when an idea is selected (Workflow 1 → Workflow 1.5)
- **Updated**: as baselines are reproduced, experiments complete, decisions are made
- **Read**: on every session recovery — this is the primary context document

### How Recovery Works

**New session or post-compaction**, the LLM reads in this order:

1. `CLAUDE.md` → `## Pipeline Status` (30-second orientation)
2. `idea-stage/docs/research_contract.md` (focused context for the active idea — not the full IDEA_REPORT)
3. Project notes or log files, if you maintain any (restore debugging context, decision rationale)
4. If `active_tasks`/`training_status` is non-empty → check remote sessions, rebuild monitoring

This works on **any platform** (Claude Code, Cursor, Trae, Codex CLI, OpenClaw) — it's just a Markdown convention.

### Recommended CLAUDE.md Rules

Add these rules to your project `CLAUDE.md` so the LLM knows when and how to maintain state:

```markdown
## State Persistence Rules

Pipeline Status update triggers:
- Stage transitions, idea selection, baseline confirmed, training start/stop
- User says "save" / "record" / "new session" / "wrap up"
- Before any long pause or handoff

On new session or post-compaction recovery:
1. Read ## Pipeline Status
2. Read idea-stage/docs/research_contract.md (the active idea's focused context)
3. Read project notes if any (e.g., experiment logs, decision rationale)
4. If active_tasks is non-empty → check remote status, rebuild monitoring
5. Resume work without asking the user
```

## Optional: Claude Code Hooks for Automation

The Pipeline Status convention works without any tooling — the LLM just needs to follow the rules in CLAUDE.md. But in practice, LLMs sometimes forget, especially after compaction. Claude Code [hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) can automate the recovery.

> **These hooks are Claude Code-specific.** If you use Cursor, Trae, or other platforms, skip this section — the Pipeline Status convention above is all you need.
>
> **They are copy-paste snippets, not shipped automation** — `install_aris.sh` does not create or register them; you set them up manually with the steps below. `session-restore.sh` alone covers ~80% of the value if you only want one.

### Overview

| Hook | Event | Purpose |
|------|-------|---------|
| `session-restore.sh` | `PreToolUse` (first call) | New session → auto-read Pipeline Status + state files |
| `context-refresh.sh` | `PreToolUse` (throttled) | Periodically inject Pipeline Status into context |
| `pre-compact-remind.sh` | `PreCompact` | Remind LLM to save state before compaction |
| `progress-remind.sh` | `PostToolUse` (Write/Edit) | Remind LLM to update EXPERIMENT_TRACKER.md after code changes |

### Setup

#### 1. Create hooks directory

```bash
mkdir -p ~/.claude/hooks
```

#### 2. Create hook scripts

##### `session-restore.sh` — Auto-recover on new session

The most important hook. On the first tool call of a new session, it reads your project's Pipeline Status and reminds the LLM which workflow to resume.

```bash
cat > ~/.claude/hooks/session-restore.sh << 'HOOKEOF'
#!/bin/bash
# PreToolUse hook: auto-recover project state on new session start.
# Fires once per session (first tool call only).
# Customize RESEARCH_ROOT to your project parent directory.

RESEARCH_ROOT="${ARIS_RESEARCH_ROOT:-$HOME/research}"
CWD=$(pwd)

[[ "$CWD" != "$RESEARCH_ROOT"/* ]] && exit 0

# Once per session (PID-based flag)
FLAG="/tmp/aris-session-restore-$$"
[ -f "$FLAG" ] && exit 0
touch "$FLAG"

# Find project root (nearest directory with CLAUDE.md)
PROJECT_DIR=""
SEARCH_DIR="$CWD"
while [[ "$SEARCH_DIR" == "$RESEARCH_ROOT"/* ]]; do
  if [ -f "$SEARCH_DIR/CLAUDE.md" ]; then
    PROJECT_DIR="$SEARCH_DIR"
    break
  fi
  SEARCH_DIR=$(dirname "$SEARCH_DIR")
done
[ -z "$PROJECT_DIR" ] && exit 0

OUTPUT=""

# 1. Read Pipeline Status
STATUS=$(sed -n '/^## Pipeline Status/,/^## /{ /^## Pipeline Status/d; /^## /d; p; }' "$PROJECT_DIR/CLAUDE.md" 2>/dev/null | head -15)
if [ -n "$STATUS" ]; then
  OUTPUT="[session-restore] Research project detected. Current state:\n$STATUS"
fi

# 2. Check for research_contract.md (new path first, legacy fallback)
if [ -f "$PROJECT_DIR/idea-stage/docs/research_contract.md" ]; then
  OUTPUT="$OUTPUT\n\n[session-restore] idea-stage/docs/research_contract.md exists — read it to restore full idea context."
elif [ -f "$PROJECT_DIR/docs/research_contract.md" ]; then
  OUTPUT="$OUTPUT\n\n[session-restore] docs/research_contract.md exists (legacy path) — read it to restore full idea context."
fi

# 3. Check for active training
if grep -q "training_status:.*running" "$PROJECT_DIR/CLAUDE.md" 2>/dev/null; then
  OUTPUT="$OUTPUT\n\n[session-restore] Active training detected — check remote status and rebuild monitoring."
fi

# 4. Check for REVIEW_STATE.json (auto-review-loop recovery, new path first, legacy fallback)
REVIEW_STATE=""
if [ -f "$PROJECT_DIR/review-stage/REVIEW_STATE.json" ]; then
  REVIEW_STATE="$PROJECT_DIR/review-stage/REVIEW_STATE.json"
elif [ -f "$PROJECT_DIR/REVIEW_STATE.json" ]; then
  REVIEW_STATE="$PROJECT_DIR/REVIEW_STATE.json"
fi
if [ -n "$REVIEW_STATE" ]; then
  RS_STATUS=$(python3 -c "import json; d=json.load(open('$REVIEW_STATE')); print(d.get('status',''))" 2>/dev/null)
  if [ "$RS_STATUS" = "in_progress" ]; then
    OUTPUT="$OUTPUT\n\n[session-restore] $(basename $(dirname $REVIEW_STATE))/REVIEW_STATE.json found (in_progress) — auto-review-loop can resume."
  fi
fi

# 5. Suggest stage-appropriate actions
STAGE=$(grep -oP '(?<=stage:\s).*' "$PROJECT_DIR/CLAUDE.md" 2>/dev/null | head -1 | tr -d ' ')
case "$STAGE" in
  idea-discovery)
    OUTPUT="$OUTPUT\n\n[session-restore] Stage: idea-discovery. Resume with /idea-discovery or /research-lit." ;;
  implementation)
    OUTPUT="$OUTPUT\n\n[session-restore] Stage: implementation. Resume with /experiment-bridge." ;;
  training)
    OUTPUT="$OUTPUT\n\n[session-restore] Stage: training. Check experiments, then /auto-review-loop if results are ready." ;;
  paper)
    OUTPUT="$OUTPUT\n\n[session-restore] Stage: paper. Resume with /paper-writing or /paper-write." ;;
esac

[ -n "$OUTPUT" ] && echo -e "$OUTPUT"
HOOKEOF
chmod +x ~/.claude/hooks/session-restore.sh
```

##### `context-refresh.sh` — Periodic state injection

Keeps the LLM aware of current project state during long sessions.

```bash
cat > ~/.claude/hooks/context-refresh.sh << 'HOOKEOF'
#!/bin/bash
# PreToolUse hook: periodically inject Pipeline Status into context.
# Throttled to once every 30 tool calls.

INPUT=$(cat)
RESEARCH_ROOT="${ARIS_RESEARCH_ROOT:-$HOME/research}"
CWD=$(pwd)

[[ "$CWD" != "$RESEARCH_ROOT"/* ]] && exit 0

COUNTER_FILE="/tmp/aris-context-refresh-counter"
COUNT=0
[ -f "$COUNTER_FILE" ] && COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

[ "$COUNT" -ne 1 ] && [ $((COUNT % 30)) -ne 0 ] && exit 0

PROJECT_CLAUDE=""
SEARCH_DIR="$CWD"
while [[ "$SEARCH_DIR" == "$RESEARCH_ROOT"/* ]]; do
  if [ -f "$SEARCH_DIR/CLAUDE.md" ]; then
    PROJECT_CLAUDE="$SEARCH_DIR/CLAUDE.md"
    break
  fi
  SEARCH_DIR=$(dirname "$SEARCH_DIR")
done
[ -z "$PROJECT_CLAUDE" ] && exit 0

STATUS=$(sed -n '/^## Pipeline Status/,/^## [^P]/p' "$PROJECT_CLAUDE" | head -20 | sed '$d')
if [ -n "$STATUS" ]; then
  echo "[context-refresh] Current project state:"
  echo "$STATUS"
fi
HOOKEOF
chmod +x ~/.claude/hooks/context-refresh.sh
```

##### `pre-compact-remind.sh` — Save state before compaction

```bash
cat > ~/.claude/hooks/pre-compact-remind.sh << 'HOOKEOF'
#!/bin/bash
# PreCompact hook: remind LLM to save state before context compaction.

RESEARCH_ROOT="${ARIS_RESEARCH_ROOT:-$HOME/research}"
CWD=$(pwd)

[[ "$CWD" != "$RESEARCH_ROOT"/* ]] && exit 0

echo "[pre-compact] Context compaction is about to happen."
echo "[pre-compact] Before continuing, ensure these are up to date:"
echo "  1. CLAUDE.md Pipeline Status (stage, idea, active_tasks, next)"
echo "  2. idea-stage/docs/research_contract.md (current idea context and results)"
echo "  3. EXPERIMENT_TRACKER.md (any unreported results)"
echo "  4. review-stage/REVIEW_STATE.json (if running auto-review-loop)"
echo "[pre-compact] After compaction, read CLAUDE.md and idea-stage/docs/research_contract.md to recover."
HOOKEOF
chmod +x ~/.claude/hooks/pre-compact-remind.sh
```

##### `progress-remind.sh` — Nudge after code changes

```bash
cat > ~/.claude/hooks/progress-remind.sh << 'HOOKEOF'
#!/bin/bash
# PostToolUse hook: after code edits, periodically remind to update state files.

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

case "$TOOL_NAME" in
  Write|Edit) ;;
  *) exit 0 ;;
esac

RESEARCH_ROOT="${ARIS_RESEARCH_ROOT:-$HOME/research}"
CWD=$(pwd)
[[ "$CWD" != "$RESEARCH_ROOT"/* ]] && exit 0

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
case "$FILE_PATH" in
  */CLAUDE.md|*/IDEA_REPORT.md|*/AUTO_REVIEW.md|*/REVIEW_STATE.json|*/EXPERIMENT_TRACKER.md|*/research_contract.md)
    exit 0 ;;
esac

COUNTER_FILE="/tmp/aris-progress-remind-counter"
COUNT=0
[ -f "$COUNTER_FILE" ] && COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

[ $((COUNT % 10)) -ne 0 ] && exit 0

echo "[progress-remind] ${COUNT} code edits so far. If you have milestone results, update EXPERIMENT_TRACKER.md and Pipeline Status."
HOOKEOF
chmod +x ~/.claude/hooks/progress-remind.sh
```

#### 3. Register hooks in settings.json

Add to `~/.claude/settings.json` (merge with existing hooks):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/session-restore.sh",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "~/.claude/hooks/context-refresh.sh",
            "timeout": 3
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/pre-compact-remind.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/progress-remind.sh",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

#### 4. Set your research root (optional)

```bash
export ARIS_RESEARCH_ROOT="$HOME/my-projects"  # default: ~/research
```

## How It All Fits Together

```
┌─────────────────────────────────────────────────────────┐
│                    Pipeline Status                        │
│              (in project CLAUDE.md)                       │
│                                                          │
│  The single source of truth for "where am I?"            │
│  Updated by LLM on every state change.                   │
│  Read by LLM (or hooks) on every recovery.               │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   New Session    Compaction    User says
                                "new session"
        │              │              │
        ▼              ▼              ▼
   Read status    Read status    Save status
   from disk      from disk      then exit
        │              │
        ▼              ▼
   Resume work    Resume work

Optional automation (Claude Code only):
  session-restore.sh → auto-reads status on new session
  context-refresh.sh → periodically re-injects status
  pre-compact-remind.sh → reminds to save before compaction
  progress-remind.sh → nudges to persist results
```

## Adapting for Other Platforms

The Pipeline Status convention works everywhere. Only the automation layer differs:

| Platform | How to automate recovery |
|----------|------------------------|
| **Claude Code** | Hooks (this guide) |
| **Cursor** | `.cursor/rules/session-recovery.mdc` — rule that triggers on `CLAUDE.md` and instructs agent to read Pipeline Status first |
| **Trae** | `.trae/rules/` — add session recovery instructions |
| **Codex CLI** | Prepend state-reading instructions to system prompt or `codex.md` |
| **OpenClaw** | Include recovery steps in initial agent prompt |

The key insight: **Pipeline Status is the protocol. Hooks are one implementation. The protocol works without the hooks — the hooks just make it reliable.**

## FAQ

**Q: Do I need the hooks?**
A: No. Pipeline Status in CLAUDE.md is the core — it works on any platform. Hooks make it automatic on Claude Code but are optional.

**Q: Do I need all 4 hooks?**
A: `session-restore.sh` alone covers 80% of the value. Start there.

**Q: Will hooks slow down my workflow?**
A: No. Each runs in <100ms. Throttling keeps them infrequent.

**Q: I don't use `## Pipeline Status` — will this work?**
A: Hooks look for `## Pipeline Status`. Use a different name? Edit the `sed` pattern. No section found? Hooks silently do nothing.
