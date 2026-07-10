---
name: paper-poster-html
description: "DEFAULT poster pipeline — build an academic conference poster (ICML/NeurIPS/ICLR/CVPR/...) as a single HTML/CSS file with measurement-driven hard gates, real paper figures, a two-hue design-token system, and print-ready PDF via headless Chromium. Use when the user says \"做海报\", \"poster\", \"conference poster\", \"paper poster\", or asks to design/redo a research poster."
argument-hint: "[paper-dir-or-pdf] [— venue: ICLR, canvas: 185x90cm landscape, venue-colors: true]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, mcp__gemini-review__review, mcp__gemini-review__review_start, mcp__gemini-review__review_reply_start, mcp__gemini-review__review_status
---

> Override for Codex users who want **Gemini**, not a second Codex/Codex-MCP reviewer, to act as the reviewer. Install this package **after** `skills/skills-codex/*`.

# Paper Poster (HTML): measurement-gated poster generation

> **Gemini overlay assurance:** `review_independence: cross-family` and `acceptance_status: accepted`.

One HTML file styled for an exact print canvas (`@page { size: W H }`), rendered to PDF
via Playwright print emulation. **Iterate by measuring, not eyeballing** — the screen
preview lies; only print emulation at the correct viewport tells the truth. Core gate
machinery is adapted from [posterly](https://github.com/Chenruishuo/posterly) (MIT, ©
2026 Ruishuo Chen — see `NOTICE.md` and `LICENSES/posterly-MIT.txt` in the mainline
skill directory); ARIS adds style discipline gates, figure-provenance gates, the
cross-model review loop, and the anti-patch-loop fix vocabulary.

This overlay is identical to `skills/skills-codex/paper-poster-html/` except that the
two cross-model review calls go to **Gemini** through the local `gemini-review` MCP
bridge instead of a spawned GPT reviewer agent. Follow the base mirror for everything
not restated here (phases, gates, fix vocabulary, figure provenance, output contract).

## Reviewer constants (overlay)

- **REVIEWER_MODEL = `gemini-review`** — Gemini invoked through the local
  `gemini-review` MCP bridge.
- **Fresh review job per call** — start each review with
  `mcp__gemini-review__review_start`; never reuse a prior review job across review
  boundaries. Save the returned `jobId`, poll `mcp__gemini-review__review_status` with
  a bounded `waitSeconds` until `done=true`, and treat the completed payload's
  `response` as the reviewer output.
- The Gemini bridge cannot read your local files — paste the relevant content into the
  prompt, and pass rendered posters via `imagePaths`.
- If the `gemini-review` bridge is unavailable, stop and tell the user what to
  configure. Do not silently degrade the cross-model reviews into self-review.

## Phase 1 step 2 — Cross-model content audit (Gemini)

```text
mcp__gemini-review__review_start:
  prompt: |
    Audit a conference-poster content plan against its source paper.

    ## Poster content plan
    [PASTE poster_html/POSTER_CONTENT_PLAN.md]

    ## Paper source (relevant sections)
    [PASTE the paper sections backing the plan's claims — abstract, headline
    results tables, method equations, theorem statements]

    For EVERY claim, number, equation, and attribution in the plan, output one row:
    | claim on poster | paper location | paper says (verbatim) | match? |
    with match ∈ {OK, NUMERIC-MISMATCH, OVERCLAIM, MISSING-PRECONDITION,
    NOT-IN-PAPER, SCOPE-NARROWED}. End with a count per category.
```

Poll `review_status` until `done=true`; save the response to
`poster_html/CLAIM_EVIDENCE.md`. Fix every non-OK row or record it as a
user-acknowledged tradeoff.

## Phase 6 — Final review (Gemini, multimodal)

All hard gates PASS + polish warnings zero-or-waived + executor visual score ≥ 9
first. Then:

```text
mcp__gemini-review__review_start:
  imagePaths: ["poster_html/poster_preview.png"]
  prompt: |
    Final print-readiness audit of a conference poster (image attached).

    ## Final poster text content
    [PASTE the text content extracted from poster_html/poster.html]

    ## Gate report summary
    [PASTE the overall/hard_failures/warnings fields of poster_html/GATE_REPORT.json]

    ## Claim→evidence audit
    [PASTE poster_html/CLAIM_EVIDENCE.md]

    Check: (1) fidelity & overclaims RE-CHECKED on the final text (polish introduces
    new claims), (2) residue (\ref{, TODO, raw < in math, missing images, remote
    URLs), (3) visual rhetoric (headline numbers prominent, banner readable from
    2 m, two-hue discipline, real paper figures central and inside their cards),
    (4) gate-log coherence.
    Verdict: PRINT-READY or NEEDS-FIX with a numbered, severity-ordered issue list.
```

Poll `mcp__gemini-review__review_status` with a bounded `waitSeconds` until `done=true`;
treat the completed payload's `response` as the reviewer verdict.

The reviewer recommends; it does not edit. Any fix → back through Phase 4/5 gates —
never straight to re-review.

## Review tracing

Save both review jobs' raw responses per `../../shared-references/review-tracing.md` to
`.aris/traces/paper-poster-html/<date>_run<NN>/`.
