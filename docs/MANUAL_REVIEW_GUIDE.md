# Manual Review Guide

> **Zero API cost cross-model review.** Copy the prompt to a **different** model family, paste the response back. If the executor is Claude Code, do NOT use Claude products as the reviewer.

## Overview

The Manual Review MCP server is a human-in-the-loop alternative to the default Codex MCP reviewer. Instead of requiring a GPT Plus/Pro subscription for automated cross-model review, it lets you manually mediate the review using a **different** model family. If the executor is Claude Code, do NOT use Claude products as the reviewer. Recommended: ChatGPT, DeepSeek, Kimi, Gemini or Qwen. The reviewer's model must be one ARIS can classify — a name outside the recognized families cannot be shown to differ from the executor's, so it cannot acquit. See the `Reviewer-Model:` section below for the list.

The trade-off: you lose full automation (you need to copy/paste), but gain complete flexibility in model choice and zero API cost.

## When to Use

- You have a Claude Code subscription but no GPT Plus/Codex subscription
- You want to use free-tier models for review
- You prefer to choose which model reviews each piece of work
- You're experimenting and don't want to burn API credits on reviews

## Installation

```bash
# One-time setup: register the MCP server with Claude Code
claude mcp add manual-review -s user -- python3 /path/to/Auto-claude-code-research-in-sleep/mcp-servers/manual-review/server.py
```

No additional dependencies required — the server uses only Python standard library.

## Usage

Add `— reviewer: manual` to any wired skill (see Supported Skills below):

```
/auto-review-loop "your topic" — reviewer: manual
/research-review "paper/" — reviewer: manual
/experiment-audit "results/" — reviewer: manual
/proof-checker "paper/" — reviewer: manual
/rebuttal "paper/" — reviewer: manual
/idea-creator "direction" — reviewer: manual
```

## Workflow

### Browser Mode (default)

1. The pipeline reaches a review step
2. A browser page opens automatically at `http://127.0.0.1:<port>`
3. **Left panel**: the full review prompt (click "Copy Prompt")
4. **Right panel**: paste the model's response here — **its first line must be
   `Reviewer-Model: <exact-model-id>`** (see below)
5. Click "Submit" — the pipeline continues. If the header is missing or the model
   is the same family as the executor, the page tells you why and you can fix the
   line in place.

### File Mode (headless Linux / SSH)

Set `MANUAL_REVIEW_MODE=file` in your environment.

1. The pipeline reaches a review step
2. Check `.aris/pending_review/pending_review.json` for the `prompt_file` and `response_file` paths.
3. Open the file at `prompt_file` to read the prompt.
4. Copy to your model, get the response.
5. Write the response to the file at `response_file`, with
   `Reviewer-Model: <exact-model-id>` as its first line (see below).
6. The server detects the file (after confirming it's stable) and continues.

**Important**: The server waits for the response file to be non-empty AND stable (unchanged across two reads). Do not hardcode `.aris/pending_review/response.md` — always use the path from `pending_review.json`. Don't create an empty file first — write the full content in one operation, or use a temporary name and rename.

## Multi-Round Reviews

For skills that use multiple review rounds (e.g., `/auto-review-loop`), the browser page shows previous exchanges in a collapsible "History" section. This helps you maintain context when continuing the conversation in your chosen model.

**Tip**: Keep the same model conversation open across rounds for best continuity.

## The `Reviewer-Model:` header

Verdict-bearing reviews require the response to begin with one line naming the
model that actually wrote it:

```
Reviewer-Model: deepseek-v3

Score: 7/10
...
```

ARIS derives the reviewer's model family from that line and refuses a review by
the executor's own family — that is the whole point of routing the review outside
the executor. Recognized families are OpenAI (`gpt*`, `o1/o3/o4`, `codex`),
Anthropic (`claude*`), Google (`gemini*`), DeepSeek, Moonshot (`kimi*`), and
Qwen (`qwen*`, `tongyi`). A model outside that list cannot be classified, so it
cannot acquit — name it exactly as the provider does.

This is a declared identity, not an attestation: ARIS checks the line you write,
it does not independently discover which web UI you used.

## Tips for Best Results

1. **Use a reasoning-capable model** — the config badge shows `reasoning_effort = xhigh`, meaning the prompt is designed for deep reasoning. Models like GPT-4o, DeepSeek-V3, Kimi, or Gemini work well. Do NOT use any Claude-family model if the executor is Claude Code.
2. **Keep the `Reviewer-Model:` line first** — before any blank line, heading, or
   preamble your model may have added.
3. **Paste the FULL response** — don't truncate or summarize. The pipeline parses specific fields (scores, verdicts, action items) from the response.
4. **Don't modify the prompt** — paste it exactly as shown. The prompt is identical to what Codex would receive.
5. **For multi-round reviews** — maintain the conversation in your model (don't start a new chat for round 2).

## Recovery

- **Accidentally closed the tab?** Check `.aris/pending_review/pending_review.json` for the full URL (it includes a one-time token — copy it in full, don't type the bare `http://127.0.0.1:17900`). The server is still running — just reopen the URL.
- **Server timed out?** Default timeout is 24 hours. If exceeded, the pipeline reports an error. Re-run the skill.
- **Wrong response pasted?** There's no undo after submit. Re-run the skill if needed.

## Supported Skills

The following skills have manual-review wired (Claude Code only):

| Skill | Review Purpose |
|-------|---------------|
| `/research-review` | Paper critique |
| `/auto-review-loop` | Iterative improvement |
| `/experiment-audit` | Eval code integrity |
| `/proof-checker` | Math verification |
| `/rebuttal` | Rebuttal stress test |
| `/idea-creator` | Idea evaluation |

> `/research-lit` currently has no manual-review call block; use `— reviewer: oracle-pro` where supported, or run a separate review skill manually.

## Future Work

- **Image generation**: Manual alternative to `codex-image2` for paper illustrations (upload/paste images back)
- **Image review loop**: Iterative illustration improvement through the same UI
