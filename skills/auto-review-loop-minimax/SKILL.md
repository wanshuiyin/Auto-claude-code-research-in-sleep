---
name: auto-review-loop-minimax
description: "(Superseded in the Cursor pack) Auto review loop with the MiniMax API as reviewer. In this zero-API pack, use auto-review-loop instead — its reviewer already runs on a cross-family Cursor built-in model."
argument-hint: "[topic-or-scope]"
---
> **ARIS-Cursor port — superseded stub.**
>
> Upstream, this variant wired the review loop to the MiniMax HTTP API
> (`MINIMAX_API_KEY`). In this Cursor pack the standard
> [`auto-review-loop`](../auto-review-loop/SKILL.md) already runs its reviewer
> as a **Cursor Task subagent on a cross-family built-in model** — zero API
> keys, same loop protocol.
>
> **→ Load `skills/auto-review-loop/SKILL.md` and run it instead.**
>
> Only if the user explicitly wants the MiniMax API as reviewer (they have a
> key and say so), use the upstream original at
> `$ARIS_REPO/skills/auto-review-loop-minimax/SKILL.md`.
