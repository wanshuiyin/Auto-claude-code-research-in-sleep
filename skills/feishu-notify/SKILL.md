---
name: feishu-notify
description: "Send notifications to Feishu/Lark. Internal utility used by other skills, or manually via /feishu-notify. Use when user says \"发飞书\", \"notify feishu\", or other skills need to send status updates."
argument-hint: "[message-text]"
allowed-tools: Bash(curl *), Bash(cat *), Read, Glob
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - `/x "args"` = load `skills/x/SKILL.md` from this pack and follow it; `$ARGUMENTS` = the user's instruction text.
> - Runs locally on Cursor built-in models with standard workspace tools.
> - `allowed-tools` frontmatter is advisory on Cursor.

# Feishu/Lark Notification

Send a notification: **$ARGUMENTS**

## Overview

This skill provides Feishu/Lark integration for ARIS. It is designed as an **internal utility** — other skills call it at key events (experiment done, review scored, checkpoint waiting). It can also be invoked manually.

**Zero-impact guarantee**: If no `feishu.json` config exists (or if `FEISHU_WEBHOOK_URL` is unset), this skill does nothing and returns silently. All existing workflows are completely unaffected.

## Configuration

The skill looks for configuration in the following order:
1. Environment variable: `FEISHU_WEBHOOK_URL` (direct webhook URL)
2. Project-level config: `.cursor/feishu.json` or `.aris/feishu.json`
3. User-level config: `~/.cursor/feishu.json` (fallback: `~/.claude/feishu.json` for legacy setups)

If none of these configuration sources exist, **all Feishu functionality is disabled** — skills behave normally.

### Config Format

```json
{
  "mode": "push",
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_ID",
  "interactive": {
    "bridge_url": "http://localhost:5000",
    "timeout_seconds": 300
  }
}
```

### Modes

| Mode | `"mode"` value | What it does | Requires |
|------|----------------|--------------|----------|
| **Off** | `"off"` or config absent | Nothing. Regular workflow as-is | Nothing |
| **Push only** | `"push"` | Send webhook notifications at key events. Mobile push, no reply | Feishu bot webhook URL |
| **Interactive** | `"interactive"` | Full bidirectional. Approve/reject from Feishu, reply to checkpoints | Feishu notification bridge running |

## Workflow

### Step 1: Read Config

Check environment variable `FEISHU_WEBHOOK_URL` or load the first available config file (`.cursor/feishu.json`, `.aris/feishu.json`, `~/.cursor/feishu.json`, or `~/.claude/feishu.json`).

- **Config not found / Unset** → return silently, do nothing
- **`"mode": "off"`** → return silently, do nothing
- **`"mode": "push"`** → proceed to Step 2 (push)
- **`"mode": "interactive"`** → proceed to Step 3 (interactive)

### Step 2: Push Notification (webhook)

Send a rich card to the Feishu webhook:

```bash
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "msg_type": "interactive",
    "card": {
      "header": {
        "title": {"tag": "plain_text", "content": "TITLE"},
        "template": "COLOR"
      },
      "elements": [
        {"tag": "markdown", "content": "BODY"}
      ]
    }
  }'
```

**Card templates by event type:**

| Event | Title | Color | Body |
|-------|-------|-------|------|
| `experiment_done` | Experiment Complete | `green` | Results table, delta vs baseline |
| `review_scored` | Review Round N: X/10 | `blue` (≥6) / `orange` (<6) | Score, verdict, top 3 weaknesses |
| `checkpoint` | Checkpoint: Waiting for Input | `yellow` | Question, options, context |
| `error` | Error: [type] | `red` | Error message, what failed |
| `pipeline_done` | Pipeline Complete | `purple` | Final summary, deliverables |
| `custom` | Custom | `blue` | Free-form message from $ARGUMENTS |

**Return immediately after curl** — push mode never waits for a response.

### Step 3: Interactive Notification (bidirectional)

Interactive mode connects to a local/remote notification bridge service:

1. **Send message** to the bridge:
   ```bash
   curl -s -X POST "$BRIDGE_URL/send" \
     -H "Content-Type: application/json" \
     -d '{"type": "EVENT_TYPE", "title": "TITLE", "body": "BODY", "options": ["approve", "reject", "custom"]}'
   ```

2. **Wait for reply** (with timeout):
   ```bash
   curl -s "$BRIDGE_URL/poll?timeout=$TIMEOUT_SECONDS"
   ```
   Returns: `{"reply": "approve"}` or `{"reply": "reject"}` or `{"reply": "user typed message"}` or `{"timeout": true}`

3. **On timeout**: Fall back to `AUTO_PROCEED` behavior (proceed with default option).

4. **Return the user's reply** to the calling skill so it can act on it.

### Step 4: Verify Delivery

- **Push mode**: Check curl exit code. If non-zero, log warning but do NOT block the workflow.
- **Interactive mode**: If bridge is unreachable, fall back to push mode (if webhook configured) or skip silently.

## Helper Pattern (for other skills)

Other skills should use this pattern to send notifications:

```markdown
### Feishu Notification (if configured)

Check if Feishu notification is configured (`FEISHU_WEBHOOK_URL` or `.cursor/feishu.json` / `.aris/feishu.json` / `~/.cursor/feishu.json`):
- If **push** mode: send webhook notification with event summary
- If **interactive** mode: send notification and wait for user reply
- If **off** or config absent: skip entirely (no-op)
```

**This check is always guarded.** If the config file or webhook is absent, the skill skips the notification block entirely — zero overhead, zero side effects.

## Event Catalog

Skills send these events at these moments:

| Skill | Event | When |
|-------|-------|------|
| `/auto-review-loop` | `review_scored` | After each round's review score |
| `/auto-review-loop` | `pipeline_done` | Loop complete (positive or max rounds) |
| `/auto-paper-improvement-loop` | `review_scored` | After each round's review score |
| `/auto-paper-improvement-loop` | `pipeline_done` | All rounds complete |
| `/run-experiment` | `experiment_done` | Screen session finishes |
| `/idea-discovery` | `checkpoint` | Between phases (if interactive) |
| `/idea-discovery` | `pipeline_done` | Final report ready |
| `/monitor-experiment` | `experiment_done` | Results collected |
| `/research-pipeline` | `checkpoint` | Between workflow stages |
| `/research-pipeline` | `pipeline_done` | Full pipeline complete |

## Key Rules

- **NEVER block a workflow** because Feishu is unreachable. Always fail open.
- **NEVER require Feishu config** — all skills must work without it.
- **Config file absent = mode off.** No error, no warning, no log.
- **Push mode is fire-and-forget.** Send curl, check exit code, move on.
- **Interactive timeout = auto-proceed.** Don't hang forever waiting for a reply.
- **Respect `AUTO_PROCEED`**: In interactive mode, if the user doesn't reply within timeout, use the same auto-proceed logic as the calling skill.
- **No secrets in notifications.** Never include API keys, tokens, or passwords in Feishu messages.
