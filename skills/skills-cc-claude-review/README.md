# skills-cc-claude-review

Override layer for **Claude Code** users who want **Claude CLI** as the external
reviewer instead of Codex MCP (GPT).

## Architecture

- **Executor**: Claude Code (your current session)
- **Reviewer**: A fresh Claude CLI instance, invoked through the `claude-review` MCP bridge
- **Transport**: `mcp-servers/claude-review/server.py`

Flow:
```
Claude Code (executor) -> claude-review MCP -> fresh Claude CLI -> Claude API
```

## What this package contains

Override skills (23 total):
- `ablation-planner`
- `auto-paper-improvement-loop`
- `auto-review-loop`
- `experiment-bridge`
- `grant-proposal`
- `idea-creator`
- `idea-discovery`
- `idea-discovery-robot`
- `novelty-check`
- `paper-figure`
- `paper-illustration`
- `paper-plan`
- `paper-poster`
- `paper-slides`
- `paper-write`
- `paper-writing`
- `rebuttal`
- `research-pipeline`
- `research-refine`
- `research-refine-pipeline`
- `research-review`
- `result-to-claim`
- `training-check`

## Install

```bash
# 1. Switch to Claude reviewer backend
./tools/switch_reviewer.sh claude

# 2. Or manually: register MCP + copy skills
claude mcp add claude-review -s user -- python3 $(pwd)/mcp-servers/claude-review/server.py
cp -a skills/skills-cc-claude-review/* skills/
```

## Switch back to Codex

```bash
./tools/switch_reviewer.sh codex
```

## Regenerate

```bash
python3 tools/generate_cc_claude_review_overrides.py
```
