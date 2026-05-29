---
name: paper-illustration-image2
description: "Generate publication-quality academic illustrations through a local Codex app-server bridge that uses Codex native image generation. This is a separate experimental alternative to `paper-illustration`, intended for Claude Code users who want a GPT-image-style renderer without modifying the original skill."
argument-hint: [description-or-method-file]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, mcp__codex-image2__generate, mcp__codex-image2__generate_start, mcp__codex-image2__generate_status, spawn_agent, send_input
---

# Paper Illustration Image2

Generate publication-quality paper figures using **Claude as the planner/reviewer**
and a **local Codex app-server MCP bridge** as the raster renderer.

## Core Design Philosophy

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                    MULTI-STAGE ITERATIVE WORKFLOW                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   User Request                                                           │
│       │                                                                  │
│       ▼                                                                  │
│   ┌─────────────┐                                                        │
│   │   Claude    │ ◄─── Step 1: Parse request, create initial prompt     │
│   │  (Planner)  │      - Extract components, labels, and data flow       │
│   │             │      - Write a paper-ready figure brief                │
│   └──────┬──────┘                                                        │
│          │                                                               │
│          ▼                                                               │
│   ┌─────────────┐                                                        │
│   │Claude/Codex │ ◄─── Step 2: Optimize layout description               │
│   │   Layout    │      - Refine component positioning                    │
│   │   Review    │      - Optimize spacing and grouping                   │
│   └──────┬──────┘                                                        │
│          │                                                               │
│          ▼                                                               │
│   ┌─────────────┐                                                        │
│   │Claude/Codex │ ◄─── Step 3: CVPR/NeurIPS style verification           │
│   │   Style     │      - Check palette, arrows, and label standards      │
│   │   Check     │      - Tighten the prompt before rendering             │
│   └──────┬──────┘                                                        │
│          │                                                               │
│          ▼                                                               │
│   ┌─────────────┐                                                        │
│   │ codex-image2│ ◄─── Step 4: Native image generation via bridge        │
│   │ MCP bridge  │      - Call generate_start / generate_status           │
│   │ + app-server│      - Accept only native imageGeneration output       │
│   └──────┬──────┘                                                        │
│          │                                                               │
│          ▼                                                               │
│   ┌─────────────┐                                                        │
│   │   Claude    │ ◄─── Step 5: STRICT visual review + SCORE (1-10)      │
│   │  (Reviewer) │      - Verify logic, labels, arrows, and aesthetics    │
│   │   STRICT!   │      - Reject unclear or non-paper-ready figures       │
│   └──────┬──────┘                                                        │
│          │                                                               │
│          ▼                                                               │
│   Score ≥ 9? ──YES──► Accept & Output                                    │
│          │                                                               │
│          NO                                                              │
│          │                                                               │
│          ▼                                                               │
│   Generate SPECIFIC improvement feedback ──► Loop back to Step 2        │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Constants

- **RENDERER = `codex-image2`** — Native image generation bridge exposed through local Codex app-server
- **OPTIONAL_TEXT_CRITIC = `spawn_agent`** — Optional text-only second opinion for layout/style checks
- **MAX_ITERATIONS = 5** — Maximum refinement rounds
- **TARGET_SCORE = 9** — Minimum acceptable score (1-10)
- **OUTPUT_DIR = `figures/ai_generated/`** — Output directory
- **TEXT_LANGUAGE = `English`** — Default figure text language unless the user requests otherwise
- **NATIVE_IMAGE_REQUIREMENT = `strict`** — Accept only native `imageGeneration` output; reject shell/Python fallbacks
- **IMAGE2_HELPER** — canonical name `paper_illustration_image2.py`, resolved
  per [`shared-references/integration-contract.md`](../shared-references/integration-contract.md) §2
  (Policy A — skill-local gate). Phase 3.2 (Arch C) moved the canonical
  implementation into `skills/paper-illustration-image2/scripts/`;
  `tools/paper_illustration_image2.py` remains as an `os.execv` shim so
  legacy resolver layers keep working without a re-install. Resolve via the
  Codex-side chain:

  ```bash
  IMAGE2_HELPER=""
  cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
  if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
      ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
  fi
  [ -f ".agents/skills/paper-illustration-image2/scripts/paper_illustration_image2.py" ] && IMAGE2_HELPER=".agents/skills/paper-illustration-image2/scripts/paper_illustration_image2.py"
  [ -z "$IMAGE2_HELPER" ] && [ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/skills/paper-illustration-image2/scripts/paper_illustration_image2.py" ] && IMAGE2_HELPER="$ARIS_REPO/skills/paper-illustration-image2/scripts/paper_illustration_image2.py"
  [ -z "$IMAGE2_HELPER" ] && [ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/paper_illustration_image2.py" ] && IMAGE2_HELPER="$ARIS_REPO/tools/paper_illustration_image2.py"
  [ -z "$IMAGE2_HELPER" ] && [ -f tools/paper_illustration_image2.py ] && IMAGE2_HELPER="tools/paper_illustration_image2.py"
  [ -z "$IMAGE2_HELPER" ] && [ -f ~/.codex/skills/paper-illustration-image2/scripts/paper_illustration_image2.py ] && IMAGE2_HELPER="$HOME/.codex/skills/paper-illustration-image2/scripts/paper_illustration_image2.py"
  [ -z "$IMAGE2_HELPER" ] && {
    echo "ERROR: paper_illustration_image2.py not resolved at .agents/skills/, \$ARIS_REPO/skills/, \$ARIS_REPO/tools/, tools/, or ~/.codex/skills/." >&2
    echo "       /paper-illustration-image2 cannot proceed. Fix: rerun install_aris_codex.sh, export ARIS_REPO, or copy the canonical skill into ~/.codex/skills/." >&2
    exit 1
  }
  ```

  All invocations below use `python3 "$IMAGE2_HELPER" <subcommand>`.

## CVPR/ICLR/NeurIPS Top-Tier Conference Style Guide

**What "CVPR Style" Actually Means:**

### Visual Standards
- **Clean white background** — No decorative patterns or gradients unless extremely subtle
- **Sans-serif fonts** — Arial, Helvetica, or similarly clean paper-friendly typography
- **Subtle color palette** — Use 3-5 coordinated colors, not rainbow colors
- **Print-friendly** — Must remain understandable in grayscale
- **Professional borders** — Thin to medium, clean, and consistent

### Layout Standards
- **Horizontal flow** — Left-to-right is the default for pipelines
- **Clear grouping** — Use spacing or subtle grouping boxes for related modules
- **Consistent sizing** — Similar components should have similar sizes
- **Balanced whitespace** — Avoid both cramped and overly sparse layouts

### Arrow Standards (MOST CRITICAL)
- **Thick strokes** — Arrows must remain visible after paper scaling
- **Clear arrowheads** — Large, unmistakable arrowheads
- **Dark colors** — Prefer black or dark gray arrows
- **Labeled** — Important arrows should show what flows through them
- **No crossings** — Reorganize the figure to avoid crossings where possible
- **CORRECT DIRECTION** — Arrows must point to the right target

### Visual Appeal (Academic Professional Style)

**目标：既不保守也不花哨，找到平衡点**

#### ✅ Should have
- **Subtle gradients** — Gentle same-family gradients are acceptable
- **Rounded corners** — Modern but restrained rounded blocks
- **Clear hierarchy** — Main modules larger, secondary modules smaller
- **Consistent color coding** — Stable mapping between module types and colors
- **Professional typography** — Clean labels with readable size hierarchy

#### ❌ Avoid
- ❌ Rainbow gradients
- ❌ Heavy drop shadows
- ❌ 3D perspective effects
- ❌ Glowing effects
- ❌ Decorative clip-art icons
- ❌ Slide-deck styling that feels flashy rather than paper-ready

#### ✓ Ideal effect
- Looks intentional, professional, and immediately readable
- Has moderate visual appeal without becoming decorative
- Feels appropriate for a top-tier conference paper figure
- Survives PDF scaling and grayscale printing

### What to AVOID (CRITICAL)
- ❌ Thin, hairline arrows
- ❌ Unlabeled or ambiguous connections
- ❌ Tiny unreadable text
- ❌ Flat, boring box soup with no hierarchy
- ❌ Over-decorated figures with shadows/glows/icons
- ❌ Wrong arrow directions

## Scope

| Figure Type | Quality | Examples |
|-------------|---------|----------|
| **Architecture diagrams** | Excellent | Model architecture, pipeline, encoder-decoder |
| **Method illustrations** | Excellent | Conceptual diagrams, algorithm flowcharts |
| **Conceptual figures** | Good | Comparison diagrams, taxonomy trees |

**Not for:** Statistical plots (use `/paper-figure`), deterministic vector topology figures (prefer `/figure-spec`), photo-realistic scenes

## Workflow: MUST EXECUTE ALL STEPS

### Step 0: Pre-flight Check

Render this checklist explicitly before starting:

```text
📋 paper-illustration-image2 integration checklist:
   [ ] 1. python3 "$IMAGE2_HELPER" preflight --workspace <cwd> --json-out figures/ai_generated/preflight.json
   [ ] 2. Confirm preflight JSON says ok=true before rendering
   [ ] 3. Render via mcp__codex-image2__generate_start + generate_status
   [ ] 4. Finalize via python3 "$IMAGE2_HELPER" finalize --workspace <cwd> --best-image <best_png>
   [ ] 5. Verify artifacts via python3 "$IMAGE2_HELPER" verify --workspace <cwd> --json-out figures/ai_generated/verify.json
```

1. Create `figures/ai_generated/` if it does not exist.
2. Confirm the request is suitable for a raster illustration:
   - architecture diagram
   - conceptual method figure
   - workflow illustration
3. Prefer **English figure text** unless the user asked otherwise.
4. Run:

```bash
python3 "$IMAGE2_HELPER" preflight \
  --workspace <cwd> \
  --json-out figures/ai_generated/preflight.json
```

5. If preflight is not `ok=true`, stop and say so clearly.

## Step 1: Claude Plans the Figure

Turn the user request into a **fully specified image prompt**. Include:

- figure type
- exact modules / stages
- flow direction
- labels to show
- data-flow arrows
- style constraints
- what to avoid

When the input is a method note or a paper section, summarize it first into a
clean figure brief before writing the final image prompt.

## Step 2: Layout Optimization

This step is required. Before rendering, refine the prompt into a concrete
layout plan:

- exact module order
- spacing and grouping
- relative module prominence
- arrow routing and likely collision points

If `spawn_agent` is available, you may ask it for a short second-opinion
layout critique here, but Claude should still complete this step even without
Codex.

Use Codex layout critique for:

- missing components
- confusing layout
- weak flow hierarchy
- likely arrow-direction ambiguity or clutter

## Step 3: Style Verification

This step is also required. Check the prompt against the intended paper style
before rendering:

- palette is restrained and academic
- arrows are thick, dark, and readable
- labels are concise and in English unless requested otherwise
- the figure will read clearly in grayscale / print
- no glow, rainbow gradient, or slide-deck decoration slips in

If `spawn_agent` is available, you may ask it for a short text-only
style audit, but do not block on it.

## Step 4: Generate Through the Bridge

Call `mcp__codex-image2__generate_start` with:

- `prompt`: the final image prompt
- `cwd`: current project root or paper workspace
- `outputPath`: `figures/ai_generated/figure_v1.png`
- `system`: a short instruction like `Academic paper figure. Prefer crisp English labels.`
- `timeoutSeconds`: a bounded render timeout such as `180`

Then call `mcp__codex-image2__generate_status` with bounded waits until:

- `done=true` and `status=completed`, or
- `done=true` and `status=failed`

If generation fails, report the bridge error directly instead of hiding it.

## Step 5: Review the Output

Review the generated image with a strict checklist:

- are all major components present?
- is the logical flow obvious?
- are labels readable?
- do arrows point the right way?
- does the figure look paper-ready rather than like a slide?

Score it from 1-10.

## Step 6: Refine if Needed

If score < 9, write a targeted refinement prompt:

- say exactly what was wrong
- say what to preserve
- regenerate to `figure_v2.png`, `figure_v3.png`, etc.

Keep refinement feedback concrete:

- `Increase spacing between genome scan and scoring modules`
- `Make the off-target branch thinner and secondary`
- `Use cleaner English labels: "Candidate sgRNA library", not "sgRNA library 23 bp"`

## Step 7: Finalize And Verify

When accepted:

- run the canonical helper to promote the best image to `figure_final.png`
- let the helper write `latex_include.tex`
- let the helper write `review_log.json`
- run helper verification before claiming success

```bash
python3 "$IMAGE2_HELPER" finalize \
  --workspace <cwd> \
  --best-image figures/ai_generated/figure_vN.png \
  --score 9 \
  --review-summary "Accepted after strict review; labels and arrows are paper-ready."

python3 "$IMAGE2_HELPER" verify \
  --workspace <cwd> \
  --json-out figures/ai_generated/verify.json
```

Suggested LaTeX:

```latex
\begin{figure*}[t]
    \centering
    \includegraphics[width=0.95\textwidth]{figures/ai_generated/figure_final.png}
    \caption{[Replace with a paper-ready caption].}
    \label{fig:[replace-me]}
\end{figure*}
```

## Key Rules

1. Never skip Step 2 or Step 3; layout and style checks are required.
2. Never skip the final visual review.
3. Never accept a figure that is logically wrong just because it looks attractive.
4. Use the `codex-image2` bridge only for **native image generation**.
5. If the bridge says native image generation is unavailable, surface that honestly.
6. Reject any shell/Python/manual bitmap fallback masquerading as image generation.
7. Keep figure text in English unless the user requested another language.
8. Prefer 1-3 strong refinement rounds over many shallow ones.
9. Use specific, actionable refinement feedback instead of vague comments.
10. Review arrow direction, label clarity, and visual hierarchy every round.
11. Accept only figures that look paper-ready, not slide-ready.
12. Always use `tools/paper_illustration_image2.py finalize` to emit the final artifacts.
13. Always use `tools/paper_illustration_image2.py verify` before claiming success.

## Repair Path

If rendering succeeded but final artifacts were skipped, repair the integration explicitly:

```bash
python3 "$IMAGE2_HELPER" finalize \
  --workspace <cwd> \
  --best-image figures/ai_generated/figure_vN.png

python3 "$IMAGE2_HELPER" verify \
  --workspace <cwd> \
  --json-out figures/ai_generated/verify.json
```

## Output Structure

```text
figures/ai_generated/
├── preflight.json         # Helper preflight receipt
├── figure_v1.png          # Iteration 1
├── figure_v2.png          # Iteration 2
├── figure_v3.png          # Iteration 3
├── figure_final.png       # Accepted version (copy of best, score ≥ 9)
├── latex_include.tex      # LaTeX snippet
├── review_log.json        # Review notes and refinement history
└── verify.json            # Helper verification diagnostic
```

## Model Summary

| Stage | Agent / Tool | Purpose |
|-------|--------------|---------|
| Step 0 | `python3 "$IMAGE2_HELPER" preflight` | Observable activation predicate and preflight receipt |
| Step 1 | Claude | Parse request and create the initial figure prompt |
| Step 2 | Claude (+ optional Codex critique) | Refine layout, grouping, spacing, and arrow routing |
| Step 3 | Claude (+ optional Codex critique) | Verify academic visual style before rendering |
| Step 4 | `mcp__codex-image2__generate_start` + `generate_status` | Native raster image generation through Codex app-server |
| Step 5 | Claude | Strict visual review and scoring |
| Step 7 | `python3 "$IMAGE2_HELPER" finalize` + `verify` | Emit canonical artifacts and external verification receipt |
