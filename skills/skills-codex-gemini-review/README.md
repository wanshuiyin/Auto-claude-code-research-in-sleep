# skills-codex-gemini-review

This package is a **thin override layer** for users who want:

- **Codex** as the main executor
- **Gemini** as the reviewer
- the local `gemini-review` MCP bridge instead of a second Codex reviewer

It is designed to sit on top of the upstream Codex-native package at `skills/skills-codex/`.

## What this package contains

- Only the reviewer-aware skill overrides that need a different reviewer backend
- No duplicate templates or resource directories
- No replacement for the base `skills/skills-codex/` installation

Current overrides:

- `idea-creator`
- `idea-discovery`
- `idea-discovery-robot`
- `research-review`
- `novelty-check`
- `research-refine`
- `auto-review-loop`
- `grant-proposal`
- `paper-plan`
- `paper-figure`
- `paper-poster`
- `paper-slides`
- `paper-write`
- `paper-writing`
- `auto-paper-improvement-loop`

## Install

Before registering the bridge, prepare the direct Gemini API path:

- **Gemini API**: set `GEMINI_API_KEY` or `GOOGLE_API_KEY` (for example in `~/.gemini/.env`)

Optional fallback only:

- **Gemini CLI**: install `gemini` and complete login/auth if you explicitly want `GEMINI_REVIEW_BACKEND=cli`

1. Install the base Codex-native skills first:

```bash
mkdir -p ~/.codex/skills
cp -a skills/skills-codex/* ~/.codex/skills/
```

2. Install the Gemini-review overrides second:

```bash
cp -a skills/skills-codex-gemini-review/* ~/.codex/skills/
```

3. Register the local reviewer bridge:

```bash
mkdir -p ~/.codex/mcp-servers/gemini-review
cp mcp-servers/gemini-review/server.py ~/.codex/mcp-servers/gemini-review/server.py
codex mcp add gemini-review --env GEMINI_REVIEW_BACKEND=api -- python3 ~/.codex/mcp-servers/gemini-review/server.py
```

The bridge defaults to the direct Gemini API path. This is the intended reviewer backend for this overlay.

## Why this exists

The upstream `skills/skills-codex/` path already supports Codex-native execution with a second Codex reviewer via `spawn_agent`.

This package adds a different split:

- executor: Codex
- reviewer: Gemini direct API
- transport: `gemini-review` MCP

For long paper and review prompts, the reviewer path uses:

- `review_start`
- `review_reply_start`
- `review_status`

This avoids the observed Codex-hosted timeout issue when Gemini is invoked synchronously through a local bridge.

## Validation Summary

This overlay was validated in two ways:

- **Coverage check**: all `15` predefined reviewer-aware skill overrides in this package were checked to confirm they target `gemini-review`
- **Runtime check**:
  - the underlying bridge completed sync, async, threaded follow-up, and multimodal local-image review tests
  - representative Codex-side runs on a private, non-public research repository confirmed that real skill executions could reach the Gemini reviewer path for research-review, idea-generation, and paper-planning style tasks

Operational note:

- Gemini free tier was usable for this workflow in practice, but bursty stress tests could still produce temporary `429` responses
- for long prompts, prefer the async `review_start` / `review_reply_start` + `review_status` path

## References

- Upstream overlay pattern from ARIS:
  - <https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/main/skills/skills-codex-claude-review>
  - <https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/main/mcp-servers/claude-review>
- Local Gemini reviewer bridge in this repo:
  - `mcp-servers/gemini-review/README.md`
- Gemini backends referenced by this overlay:
  - Official Gemini API: <https://ai.google.dev/api>
  - Official Gemini CLI: <https://github.com/google-gemini/gemini-cli>
  - AI Studio API key entry: <https://aistudio.google.com/apikey>

This package keeps the upstream ARIS skill shape, but swaps the reviewer transport to the local `gemini-review` bridge. It now covers every predefined Codex skill in this repo that previously depended on a secondary Codex reviewer or `mcp__codex__codex` review step. We intentionally did not directly depend on a generic Gemini MCP server package because the ARIS review skills rely on the narrow `review*` tool contract, resumable review-thread behavior, and now optional local-image review for poster PNGs.
