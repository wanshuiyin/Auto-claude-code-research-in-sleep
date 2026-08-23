---
name: paper-illustration
description: "Generate publication-quality AI illustrations for academic papers. Creates architecture diagrams and method illustrations with a strict supervised iterative refinement loop. Use when user says \"生成图表\", \"画架构图\", \"AI绘图\", \"paper illustration\", \"generate diagram\", or needs visual figures for papers."
argument-hint: "[description-or-method-file] [— style-ref: <source>]"
allowed-tools: Read, Write, Edit, Grep, Glob, WebSearch
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - **This skill was rewritten**: the upstream version required the Gemini image API
>   (`GEMINI_API_KEY`, gemini-3-pro-image). This edition renders with Cursor's native
>   **GenerateImage** tool — same supervised refinement loop, no key. The upstream
>   original (for Gemini users) lives at `$ARIS_REPO/skills/paper-illustration/SKILL.md`.
> - For **deterministic vector diagrams** (precise architecture/flow charts, exact labels),
>   prefer `/figure-spec` (SVG, no AI rendering) or `/mermaid-diagram` — AI-rendered raster
>   images are for concept/illustration figures, not data-bearing charts.

# Paper Illustration: Supervised Iterative Figure Generation

Generate publication-quality illustrations using a **multi-stage workflow** with **the executor as the STRICT supervisor/reviewer**.

## Core Design Philosophy

```
User request
  → Step 1 (executor): parse request, extract EVERY component/arrow/label the
    figure must contain, write the render prompt
  → Step 2 (executor): optimize the layout description (positioning, spacing,
    grouping, flow direction) inside the prompt
  → Step 3 (executor): apply venue style constraints (CVPR/NeurIPS-clean look,
    muted palette, sans-serif labels, no clutter) to the prompt
  → Step 4 (GenerateImage): render
  → Step 5 (executor, STRICT): review the rendered image against the Step-1
    inventory — every arrow direction, every block label, aesthetics. Score 1-10.
  → Score ≥ TARGET_SCORE? accept : generate SPECIFIC feedback → revise prompt
    → re-render (max MAX_ITERATIONS)
```

## Constants

- **RENDERER** — Cursor `GenerateImage` tool
- **MAX_ITERATIONS = 5** — Maximum refinement rounds
- **TARGET_SCORE = 9** — Minimum acceptable score (1-10)
- **OUTPUT_DIR = `figures/ai_generated/`** — Output directory

## Workflow

### Step 1: Parse & Inventory (the contract)

Read the method description / file from `$ARGUMENTS`. Write an explicit
**figure contract** (working notes):

- Components: every box/module/entity that MUST appear, with its exact label
- Connections: every arrow with direction and label
- Groupings: which components cluster together
- Flow: left→right or top→bottom narrative
- Caption draft

If `— style-ref: <source>` is passed: read the reference figure/paper and note
its structural conventions (layout density, palette mood) — never copy content.

### Step 2: Compose the Render Prompt

Write a single detailed prompt for GenerateImage:

- Describe the layout spatially ("three columns; left column contains …")
- Name every label VERBATIM in quotes (image models misspell — keep labels
  short; prefer ≤3 words per label)
- Style clause: "clean academic paper figure, flat design, muted professional
  color palette (2-4 colors), white background, sans-serif labels, thin arrows,
  no photorealism, no clutter, vector-illustration look"
- Aspect ratio suited to the paper column (16:9 for full-width, 4:3 for column)

### Step 3: Render

Call `GenerateImage` with the composed prompt. Save to
`OUTPUT_DIR/<figure-name>_v<N>.png`.

### Step 4: STRICT Review (the supervisor gate)

Look at the rendered image (attach/read it) and check against the Step-1 contract:

| Check | Rule |
|---|---|
| Every component present | missing block = automatic score ≤ 5 |
| Every label correct | misspelled/garbled text = automatic score ≤ 6 |
| Every arrow direction correct | wrong direction = automatic score ≤ 5 |
| Groupings match | wrong clustering = -1 |
| Aesthetics | cluttered/ugly/wrong palette = -1 to -2 |

Score 1-10 honestly. **Text fidelity is the known weak point of AI rendering** —
if labels keep failing after 2 rounds, strip text from the image prompt and
plan to overlay labels in post (LaTeX `\node` overlays or figure-spec SVG).

### Step 5: Iterate or Accept

- Score ≥ TARGET_SCORE → accept. Write the final PNG + a `.prompt.txt` sidecar
  (the exact prompt used, for reproducibility) + caption suggestion.
- Score < TARGET_SCORE and iterations < MAX_ITERATIONS → write SPECIFIC
  feedback ("arrow from Encoder to Decoder points backwards; label 'KV$' is
  garbled — should be 'KV cache'"), revise the prompt to address each point,
  re-render.
- MAX_ITERATIONS exhausted → present the best version + its score + remaining
  defects, and recommend `/figure-spec` (deterministic SVG) for the
  precision-critical parts.

## Key Rules

- The executor is a STRICT reviewer — a figure with a wrong arrow is WORSE than
  no figure (it misleads reviewers). Never accept below TARGET_SCORE silently.
- Data-bearing charts (plots, tables) are `/paper-figure`'s job (matplotlib) —
  never AI-render numbers.
- Precise architecture diagrams with many exact labels → `/figure-spec` SVG is
  usually the better tool; offer it when text fidelity fails.
- Record every accepted figure in the paper's figure inventory (used by
  `/paper-writing` Phase 3).
