# Claude Code + Claude CLI Reviewer Guide

Use **Claude CLI** as the external reviewer instead of Codex MCP (GPT) when running
skills in Claude Code. This is useful if you have more Claude API credits than OpenAI credits.

## Architecture

```
Claude Code (executor)
  -> claude-review MCP bridge
    -> fresh Claude CLI instance (reviewer)
      -> Claude API
```

- **Executor**: Your current Claude Code session runs the skill pipeline
- **Reviewer**: A separate Claude CLI process provides external review/judgment
- **Transport**: The `claude-review` MCP server bridges the two

## Quick Start

One command to switch:

```bash
./tools/switch_reviewer.sh claude
```

This will:
1. Generate overlay skills (if not already generated)
2. Install them over the Codex-based originals (with backups)
3. Register the `claude-review` MCP server in Claude Code

## Switch Back

```bash
./tools/switch_reviewer.sh codex
```

## Check Current Backend

```bash
./tools/switch_reviewer.sh status
```

## Manual Setup

If you prefer manual control:

### 1. Register MCP Server

```bash
claude mcp add claude-review -s user -- python3 $(pwd)/mcp-servers/claude-review/server.py
```

With a specific model:

```bash
claude mcp add claude-review -s user \
  -e CLAUDE_REVIEW_MODEL=claude-opus-4-1 \
  -- python3 $(pwd)/mcp-servers/claude-review/server.py
```

### 2. Generate and Install Overlay Skills

```bash
# Generate
python3 tools/generate_cc_claude_review_overrides.py

# Install (copies overlay SKILL.md files into skills/)
cp -a skills/skills-cc-claude-review/*/SKILL.md skills/  # or use switch_reviewer.sh
```

## MCP Server Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_BIN` | `claude` | Path to Claude CLI binary |
| `CLAUDE_REVIEW_MODEL` | *(empty)* | Force a specific Claude model |
| `CLAUDE_REVIEW_SYSTEM` | *(empty)* | Custom system prompt for reviewer |
| `CLAUDE_REVIEW_TOOLS` | *(unset)* | Tools override; unset = full default tools, `""` = no tools |
| `CLAUDE_REVIEW_TIMEOUT_SEC` | `1800` | Max seconds per review call (30 min) |
| `CLAUDE_REVIEW_STATE_DIR` | `~/.codex/state/claude-review` | Job state directory |

## How It Works

The `claude-review` MCP server exposes 5 tools:

| Tool | Description |
|------|-------------|
| `review_start` | Start async review (returns `jobId`) |
| `review_reply_start` | Start async follow-up in same thread |
| `review_status` | Poll for job completion |
| `review` | Synchronous review (for short prompts) |
| `review_reply` | Synchronous follow-up |

Skills use the async pattern (`review_start` + `review_status` polling) to avoid
timeout issues with long review prompts.

## Affected Skills

23 skills are transformed (all that reference the external reviewer):

- ablation-planner, auto-paper-improvement-loop, auto-review-loop
- experiment-bridge, grant-proposal, idea-creator
- idea-discovery, idea-discovery-robot, novelty-check
- paper-figure, paper-illustration, paper-plan
- paper-poster, paper-slides, paper-write, paper-writing
- rebuttal, research-pipeline, research-refine, research-refine-pipeline
- research-review, result-to-claim, training-check

## Regenerating Overlays

After updating the base skills in `skills/`, regenerate the overlay:

```bash
python3 tools/generate_cc_claude_review_overrides.py
```

## Troubleshooting

### Reviewer times out

The default timeout is 30 minutes (1800s). If the reviewer uses tools (WebSearch, Read, etc.) extensively, it may need more time. Increase with:

```bash
claude mcp remove claude-review
claude mcp add claude-review -s user \
  -e CLAUDE_REVIEW_TIMEOUT_SEC=3600 \
  -- python3 $(pwd)/mcp-servers/claude-review/server.py
```

**Important**: After changing `server.py` or environment variables, you must **restart Claude Code** for the MCP server process to pick up the new values.

### Claude Code still calls Codex after switching

Claude Code reads skills from `~/.claude/skills/` with priority over project-level `skills/`. The `switch_reviewer.sh` script handles both locations. If skills are still stale:

1. Check `~/.claude/skills/research-review/SKILL.md` — it should reference `mcp__claude-review__review_start`
2. Restart Claude Code after running `switch_reviewer.sh`

### Thread expired on follow-up rounds

If `review_reply_start` fails with "session not found", fall back to `review_start` with the full accumulated context (include all prior round summaries in the prompt). This happens when the reviewer CLI session expires between rounds.

## Comparison

| | Codex MCP (default) | Claude CLI Reviewer |
|---|---|---|
| Reviewer model | GPT via OpenAI | Claude via Anthropic |
| Reviewer tools | None | Full (WebSearch, Read, Grep, etc.) |
| MCP tools | `mcp__codex__codex` | `mcp__claude-review__review_start` |
| API credits | OpenAI | Anthropic (Claude) |
| Timeout | N/A | 30 min (configurable) |
| Switch command | `./tools/switch_reviewer.sh codex` | `./tools/switch_reviewer.sh claude` |
