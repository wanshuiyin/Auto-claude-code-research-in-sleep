---
name: paper-poster
description: "DEPRECATED — superseded by /paper-poster-html. Kept only as a redirect for muscle memory; do not use for new posters."
argument-hint: "[paper-dir-or-pdf]"
allowed-tools: Read
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - `/x "args"` = load `skills/x/SKILL.md` from this pack and follow it; `$ARGUMENTS` = the user's instruction text.
> - Any reviewer call (`mcp__codex__codex(-reply)`, `codex exec`, `mcp__llm-chat__chat`, `mcp__manual_review__*`, `mcp__oracle__*`, `mcp__gemini_review__*`) maps to a **Cursor Task subagent** per [reviewer-routing.md](../shared-references/reviewer-routing.md) — cross-family built-in model; `threadId` = the subagent id (`Task(resume: ...)`).
> - `allowed-tools` frontmatter is advisory on Cursor.

# Paper Poster (DEPRECATED → /paper-poster-html)

This skill is retired. The LaTeX/tcbposter pipeline it described produced posters with
unbounded color palettes, no real paper figures, and no print-canvas verification, and
has been replaced by the measurement-gated HTML/CSS pipeline.

**Immediately proceed with `/paper-poster-html`**, passing through all of the user's
arguments unchanged. Do not attempt the legacy LaTeX flow.

The full legacy implementation remains available in git history
(`git log -- skills/paper-poster/SKILL.md`) if a venue ever mandates LaTeX poster
source — none is known to.
