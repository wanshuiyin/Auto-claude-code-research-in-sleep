---
name: auto-review-loop-llm
description: "(Superseded in the Cursor pack) Auto review loop with any OpenAI-compatible API as reviewer. In this zero-API pack, use auto-review-loop instead — its reviewer already runs on a cross-family Cursor built-in model."
argument-hint: "[topic-or-scope]"
---
> **ARIS-Cursor port — superseded stub.**
>
> Upstream, this variant existed so users **without** a Codex subscription could
> run the review loop through any OpenAI-compatible HTTP API (DeepSeek / GLM /
> Kimi / MiniMax) via the `llm-chat` MCP server + an API key.
>
> In this Cursor pack that niche is gone: the standard
> [`auto-review-loop`](../auto-review-loop/SKILL.md) already runs its reviewer
> as a **Cursor Task subagent on a cross-family built-in model** — zero API
> keys, thread continuity via `Task(resume: ...)`, same loop protocol.
>
> **→ Load `skills/auto-review-loop/SKILL.md` and run it instead.**
>
> Only if the user explicitly wants an external HTTP-API reviewer (they have a
> key and say so), use the upstream original at
> `$ARIS_REPO/skills/auto-review-loop-llm/SKILL.md` with the `llm-chat` MCP
> configured per `$ARIS_REPO/docs/CURSOR_ADAPTATION.md` §2.3.
