---
name: paper-writing
description: "Workflow 3: Full paper writing pipeline. Orchestrates paper-plan → paper-figure → figure-spec/paper-illustration/mermaid-diagram → paper-write → paper-compile → auto-paper-improvement-loop to go from a narrative report to a polished PDF. At `— effort: max | beast` (or explicit `— assurance: submission`), Phase 6 gates the Final Report on `tools/verify_paper_audits.sh`; the PDF is labelled `submission-ready` only when the external verifier is green. Use when user says \"写论文全流程\", \"write paper pipeline\", \"从报告到PDF\", \"paper writing\", or wants the complete paper generation workflow."
argument-hint: "[narrative-report-path-or-topic] [— style-ref: <source>]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Workflow 3: Paper Writing Pipeline

Orchestrate a complete paper writing workflow for: **$ARGUMENTS**

## Overview

This skill chains five sub-skills into a single automated pipeline:

```
/paper-plan → /paper-figure → /paper-write → /paper-compile → /auto-paper-improvement-loop
  (outline)     (plots)        (LaTeX)        (build PDF)       (review & polish ×2)
```

Each phase builds on the previous one's output. The final deliverable is a polished, reviewed `paper/` directory with LaTeX source and compiled PDF.

In this hybrid pack, the pipeline itself is unchanged, but `paper-plan` and `paper-write` use Orchestra-adapted shared references for stronger story framing and prose guidance.

## Constants

- **VENUE = `ICLR`** — Target venue. Options: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`, `IEEE_JOURNAL` (IEEE Transactions / Letters), `IEEE_CONF` (IEEE conferences). Affects style file, page limit, citation format.
- **MAX_IMPROVEMENT_ROUNDS = 2** — Number of review→fix→recompile rounds in the improvement loop.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for plan review, figure review, writing review, and improvement loop.
- **AUTO_PROCEED = true** — Auto-continue between phases. Set `false` to pause and wait for user approval after each phase.
- **HUMAN_CHECKPOINT = false** — When `true`, the improvement loop (Phase 5) pauses after each round's review to let you see the score and provide custom modification instructions. When `false` (default), the loop runs fully autonomously. Passed through to `/auto-paper-improvement-loop`.
- **ILLUSTRATION = `figurespec`** — Architecture/illustration generator for Phase 2b: `figurespec` (default, deterministic JSON→SVG via `/figure-spec`, best for architecture/workflow/topology), `gemini` (AI-generated via `/paper-illustration`, best for qualitative method illustrations; needs `GEMINI_API_KEY`), `codex-image2` (AI-generated via `/paper-illustration-image2` through the local Codex native image bridge — no external API key, uses your ChatGPT Plus/Pro quota; experimental), `mermaid` (Mermaid syntax via `/mermaid-diagram`, free, best for flowcharts), or `false` (skip Phase 2b, manual only).

> Override inline: `/paper-writing "NARRATIVE_REPORT.md" — venue: NeurIPS, illustration: gemini, human checkpoint: true`
> IEEE example: `/paper-writing "NARRATIVE_REPORT.md" — venue: IEEE_JOURNAL`

## Inputs

This pipeline accepts one of:

1. **`NARRATIVE_REPORT.md`** (best) — structured research narrative with claims, experiments, results, figures
2. **Research direction + experiment results** — the skill will help draft the narrative first
3. **Existing `PAPER_PLAN.md`** — skip Phase 1, start from Phase 2

The more detailed the input (especially figure descriptions and quantitative results), the better the output.

## Optional: Style reference (`— style-ref: <source>`, opt-in)

Lets the user steer **structural** style (section ordering, theorem density, sentence cadence, figure density, bibliography style) of the generated paper toward a reference paper they admire. **Default OFF — when the user does not pass `— style-ref`, do nothing differently from before.**

When `— style-ref: <source>` is in `$ARGUMENTS`, run the helper FIRST, before Phase 1 (paper-plan):

```bash
if [ ! -f tools/extract_paper_style.py ]; then
  echo "error: tools/extract_paper_style.py not found — re-run 'bash tools/install_aris.sh' to refresh the '.aris/tools' symlink (added in #174), or copy the helper manually from the ARIS repo" >&2
  exit 1
fi
CACHE=$(python3 tools/extract_paper_style.py --source "<source>")
case $? in
  0) ;;                                       # share $CACHE/style_profile.md with downstream WRITER phases only
  2) echo "warning: style-ref skipped (missing optional dep)" >&2 ;;
  3) echo "error: --style-ref source failed; aborting pipeline" >&2 ; exit 1 ;;
  *) echo "error: helper failed unexpectedly; aborting pipeline" >&2 ; exit 1 ;;
esac
```

Then forward `— style-ref: <source>` only to the **writer-side** sub-skills:
- `/paper-plan` (Phase 1) — outline structure
- `/paper-write` (Phase 3) — section-by-section prose
- `/paper-illustration` (Phase 2b) — figure structural matching, optional

Sources accepted: local TeX dir / file, local PDF, arXiv id, http(s) URL. Overleaf URLs/IDs are rejected — clone via `/overleaf-sync setup <id>` first and pass the local clone path.

**Strict rules** (full contract in `tools/extract_paper_style.py` docstring):

- Use `style_profile.md` as **structural** guidance only. Match section-count tendency, theorem density, caption-length distribution, sentence cadence, math display ratio, citation style.
- **Never copy prose, claims, examples, or terminology** from anything reachable through the cache.
- **Never pass `— style-ref` (or the cache contents) to reviewer / auditor sub-skills** — Phase 4.5 (`/proof-checker`), Phase 4.7 / 5.5 (`/paper-claim-audit`), Phase 5 (`/auto-paper-improvement-loop` reviewer), Phase 5.8 (`/citation-audit`) MUST run on the artifact alone. Cross-model review independence (`../shared-references/reviewer-independence.md`).

## Pipeline

### Phase 0: Assurance Setup

Resolve the active `assurance` level and persist it so Phase 6's external
verifier reads the same value. **Run once at pipeline start, before Phase 1.**

**Resolution order** (first match wins):

1. Explicit `— assurance: draft | submission` in `$ARGUMENTS`
2. Derived from `— effort:`
   - `lite` / `balanced` → `draft` (default, **zero change from current behavior**)
   - `max` / `beast` → `submission`
3. Default: `draft`

**Action:**

```bash
mkdir -p paper/.aris
echo "<resolved-level>" > paper/.aris/assurance.txt   # draft or submission
```

**What each level does downstream:**

- **`draft`** — Existing behavior. Audits run only when their content detector
  matches (Phase 4.5 / 4.7 / 5.5 / 5.8). Missing artifacts are non-blocking.
  Silent-skip allowed.
- **`submission`** — The three mandatory audits (proof-checker,
  paper-claim-audit, citation-audit) are treated as load-bearing gates. Each
  sub-audit must emit its JSON artifact (PASS / WARN / FAIL / NOT_APPLICABLE /
  BLOCKED / ERROR) — never silent-skip. Phase 6 runs
  `tools/verify_paper_audits.sh`; a non-zero exit blocks the Final Report.

**Escape hatch:** a user wanting the old "beast = depth-only, no audit gate"
can pass `— effort: beast, assurance: draft` explicitly. Legal but
discouraged for actual submissions. See
`shared-references/assurance-contract.md` for the full contract.

**Announce the resolved level in-line before Phase 1:**

```
📋 Assurance: <level> (derived from effort: <effort>)
   <either "current behavior, no audit gate" OR "mandatory audits gated by tools/verify_paper_audits.sh">
```

### Phase 1: Paper Plan

Invoke `/paper-plan` to create the structural outline:

```
/paper-plan "$ARGUMENTS"
```

If `— style-ref: <source>` was passed in `$ARGUMENTS` and the helper succeeded above, append `— style-ref: <source>` to the invocation: `/paper-plan "<topic> — style-ref: <source>"`. (Writer-side phase — forwarding is allowed; reviewer/auditor phases below must not see the style ref.)

**What this does:**
- Parse NARRATIVE_REPORT.md for claims, evidence, and figure descriptions
- Build a **Claims-Evidence Matrix** — every claim maps to evidence, every experiment supports a claim
- Design section structure (5-8 sections depending on paper type)
- Plan figure/table placement with data sources
- Scaffold citation structure
- GPT-5.4 reviews the plan for completeness

**Output:** `PAPER_PLAN.md` with section plan, figure plan, citation scaffolding.

**Checkpoint:** Present the plan summary to the user.

```
📐 Paper plan complete:
- Title: [proposed title]
- Sections: [N] ([list])
- Figures: [N] auto-generated + [M] manual
- Target: [VENUE], [PAGE_LIMIT] pages

Shall I proceed with figure generation?
```

- **User approves** (or AUTO_PROCEED=true) → proceed to Phase 2.
- **User requests changes** → adjust plan and re-present.

### Phase 2: Figure Generation

If `— style-ref: <source>` was passed in `$ARGUMENTS` and the helper succeeded above, append `— style-ref: <source>` to every writer-side sub-skill invocation in this pipeline (Phases 1, 2b, 3, 5). Do **not** append it to reviewer/auditor invocations (Phases 4.5, 4.7, 5.5, 5.8).

Invoke `/paper-figure` to generate data-driven plots and tables:

```
/paper-figure "PAPER_PLAN.md"
```

**What this does:**
- Read figure plan from PAPER_PLAN.md
- Generate matplotlib/seaborn plots from JSON/CSV data
- Generate LaTeX comparison tables
- Create `figures/latex_includes.tex` for easy insertion
- GPT-5.4 reviews figure quality and captions

**Output:** `figures/` directory with PDFs, generation scripts, and LaTeX snippets.

> **Scope:** `paper-figure` covers data plots and comparison tables. Architecture diagrams, pipeline figures, and method illustrations are handled in Phase 2b below.

#### Phase 2b: Architecture & Illustration Generation

**Skip this step entirely if `illustration: false`.**

If the paper plan includes architecture diagrams, pipeline figures, audit cascades, or method illustrations, invoke the appropriate generator based on the `illustration` parameter:

**When `illustration: figurespec`** (default) — invoke `/figure-spec`:
```
/figure-spec "[architecture/workflow description from PAPER_PLAN.md]"
```
- Deterministic JSON → SVG vector rendering (editable, reproducible)
- Best for: system architecture, workflow pipelines, audit cascades, layered topology
- Output: `figures/*.svg` + `figures/*.pdf` (via rsvg-convert) + `figures/specs/*.json`
- No external API, runs fully local

If `— style-ref: <source>` was passed and the helper succeeded above, append `— style-ref: <source>` to the invocation below as well.

**When `illustration: gemini`** — invoke `/paper-illustration`:
```
/paper-illustration "[method description from PAPER_PLAN.md or NARRATIVE_REPORT.md]"
```
- Claude plans → Gemini optimizes → Nano Banana Pro renders → Claude reviews (score ≥ 9)
- Best for: qualitative method illustrations, natural-style diagrams, result grids
- Output: `figures/ai_generated/*.png`
- Requires `GEMINI_API_KEY` environment variable

**When `illustration: mermaid`** — invoke `/mermaid-diagram`:
```
/mermaid-diagram "[method description from PAPER_PLAN.md]"
```
- Generates Mermaid syntax diagrams (flowchart, sequence, class, state, etc.)
- Best for: lightweight flowcharts, state machines, simple sequence diagrams
- Output: `figures/*.mmd` + `figures/*.png`
- Free, no API key needed

**When `illustration: codex-image2`** — invoke `/paper-illustration-image2`:
```
/paper-illustration-image2 "[method description from PAPER_PLAN.md or NARRATIVE_REPORT.md]"
```
- Claude plans → Codex native image generation renders → Claude reviews (same multi-stage workflow as `gemini`, different renderer)
- Best for: users who want a GPT-image-style renderer without needing `GEMINI_API_KEY`; uses your existing Codex / ChatGPT Plus/Pro quota
- Output: `figures/ai_generated/figure_final.png` + `latex_include.tex` + `review_log.json` (emitted via `tools/paper_illustration_image2.py finalize`)
- **Prerequisites** (beyond ARIS's standard Claude Code + Codex coexistence): the local Codex app-server must be signed in (`codex debug app-server send-message-v2 "ping"` succeeds), and the dedicated MCP bridge must be registered — see `mcp-servers/codex-image2/README.md` for the one-time `claude mcp add` command. Run `python3 tools/paper_illustration_image2.py preflight --workspace .` to confirm before relying on this path.
- **Experimental**: this renderer shells through the Codex debug app-server, which Codex documents as an unstable surface. Prefer `figurespec` or `gemini` for production submission flows until `codex-image2` stabilizes.

**When `illustration: false`** — skip entirely. All non-data figures must be created manually (draw.io, Figma, TikZ) and placed in `figures/` before Phase 3.

**Choosing the right mode:**
- Formal architecture / workflow / topology figures → `figurespec` (default)
- Method concept illustrations with natural style, have `GEMINI_API_KEY` → `gemini`
- Method concept illustrations, prefer ChatGPT Plus/Pro quota over Gemini key → `codex-image2`
- Quick flowchart / state machine → `mermaid`
- Full manual control → `false`

These are complementary, not mutually exclusive: you can run multiple generators for different figures in the same paper by re-invoking with different `illustration` overrides.

**Checkpoint:** List generated vs manual figures.

```
📊 Figures complete:
- Data plots (auto, Phase 2): [list]
- Architecture/illustrations (auto, Phase 2b, mode=<illustration>): [list]
- Manual (need your input): [list]
- LaTeX snippets: figures/latex_includes.tex

[If manual figures needed]: Please add them to figures/ before I proceed.
[If all auto]: Shall I proceed with LaTeX writing?
```

### Phase 3: LaTeX Writing

Invoke `/paper-write` to generate section-by-section LaTeX:

```
/paper-write "PAPER_PLAN.md"
```

If `— style-ref: <source>` was passed in `$ARGUMENTS` and the helper succeeded above, append `— style-ref: <source>` to the invocation: `/paper-write "PAPER_PLAN.md — style-ref: <source>"`.

**What this does:**
- Write each section following the plan, with proper LaTeX formatting
- Insert figure/table references from `figures/latex_includes.tex`
- Build `references.bib` from citation scaffolding
- Clean stale files from previous section structures
- Automated bib cleaning (remove uncited entries)
- De-AI polish (remove "delve", "pivotal", "landscape"...)
- GPT-5.4 reviews each section for quality

**Output:** `paper/` directory with `main.tex`, `sections/*.tex`, `references.bib`, `math_commands.tex`.

**Checkpoint:** Report section completion.

```
✍️ LaTeX writing complete:
- Sections: [N] written ([list])
- Citations: [N] unique keys in references.bib
- Stale files cleaned: [list, if any]

Shall I proceed with compilation?
```

### Phase 4: Compilation

Invoke `/paper-compile` to build the PDF:

```
/paper-compile "paper/"
```

**What this does:**
- `latexmk -pdf` with automatic multi-pass compilation
- Auto-fix common errors (missing packages, undefined refs, BibTeX syntax)
- Up to 3 compilation attempts
- Post-compilation checks: undefined refs, page count, font embedding
- Precise page verification via `pdftotext`
- Stale file detection

**Output:** `paper/main.pdf`

**Checkpoint:** Report compilation results.

```
🔨 Compilation complete:
- Status: SUCCESS
- Pages: [X] (main body) + [Y] (references) + [Z] (appendix)
- Within page limit: YES/NO
- Undefined references: 0
- Undefined citations: 0

Shall I proceed with the improvement loop?
```

### Phase 4.5: Proof Verification (theory papers only)

**Skip this phase if the paper contains no theorems, lemmas, or proofs.**

```
if paper contains \begin{theorem} or \begin{lemma} or \begin{proof}:
    Run /proof-checker "paper/"
    This invokes GPT-5.4 xhigh to:
    - Verify all proof steps (hypothesis discharge, interchange justification, etc.)
    - Check for logic gaps, quantifier errors, missing domination conditions
    - Attempt counterexamples on key lemmas
    - Generate PROOF_AUDIT.md with issue list + severity

    If FATAL or CRITICAL issues found:
        Fix before proceeding to improvement loop
    If only MAJOR/MINOR:
        Proceed, improvement loop may address remaining issues
else:
    skip — no proofs, no action
```

### Phase 4.7: Paper Claim Audit

**Skip if no result files exist (e.g., survey/position papers with no experiments).**

```
if results/*.json or results/*.csv or outputs/*.json exist:
    Run /paper-claim-audit "paper/"
    Fresh zero-context reviewer compares every number in the paper
    against raw result files. Catches rounding inflation, best-seed
    cherry-pick, config mismatch, delta errors.

    If FAIL:
        Fix mismatched numbers before improvement loop
    If WARN:
        Proceed, but flag for manual verification
else:
    skip — no experimental results to verify
```

### Phase 5: Auto Improvement Loop

Invoke `/auto-paper-improvement-loop` to polish the paper:

```
/auto-paper-improvement-loop "paper/"
```

If `— style-ref: <source>` was passed in `$ARGUMENTS` and the helper succeeded above, append `— style-ref: <source>` to the invocation: `/auto-paper-improvement-loop "paper/ — style-ref: <source>"`. The improvement loop's reviewer sub-agent will still NOT see the style ref (the loop's own SKILL forbids it); only the fix-implementation phase consumes it.

**What this does (2 rounds):**

**Round 1:** GPT-5.4 xhigh reviews the full paper → identifies CRITICAL/MAJOR/MINOR issues → Claude Code implements fixes → recompile → save `main_round1.pdf`

**Round 2:** GPT-5.4 xhigh re-reviews with conversation context → identifies remaining issues → Claude Code implements fixes → recompile → save `main_round2.pdf`

**Typical improvements:**
- Fix assumption-model mismatches
- Soften overclaims to match evidence
- Add missing interpretations and notation
- Strengthen limitations section
- Add theory-aligned experiments if needed

**Output:** Three PDFs for comparison + `PAPER_IMPROVEMENT_LOG.md`.

**Format check** (included in improvement loop Step 8): After final recompilation, auto-detect and fix overfull hboxes (content exceeding margins), verify page count vs venue limit, and ensure compact formatting. Location-aware thresholds: any main-body overfull blocks completion regardless of size; appendix overfulls block only if >10pt; bibliography overfulls block only if >20pt.

### Phase 5.5: Final Paper Claim Audit (MANDATORY submission gate)

After `/auto-paper-improvement-loop` finishes, **rerun** `/paper-claim-audit` before the final report whenever the paper contains numeric claims and machine-readable raw result files exist.

Use the same detectors as Phase 4.7:
- numeric-claim regex over `paper/main.tex` and `paper/sections/*.tex`
- raw-evidence file search in `results/`, `outputs/`, `experiments/`, and `figures/` for `.json`, `.jsonl`, `.csv`, `.tsv`, `.yaml`, or `.yml`

This phase is **mandatory** if both detectors are positive. It blocks the final report.
If numeric claims exist but no raw result files are found, stop and warn the user before declaring the paper complete.
If no numeric claims exist, skip.

```bash
NUMERIC_CLAIMS=$(rg -n -e '[0-9]+(\.[0-9]+)?\s*(%|\\%|±|\\pm|x|×)' \
  -e '(accuracy|BLEU|F1|AUC|mAP|top-1|top-5|error|loss|perplexity|speedup|improvement)' \
  paper/main.tex paper/sections 2>/dev/null || true)

RAW_RESULT_FILES=$(find results outputs experiments figures -type f \
  \( -name '*.json' -o -name '*.jsonl' -o -name '*.csv' -o -name '*.tsv' -o -name '*.yaml' -o -name '*.yml' \) 2>/dev/null | head -200)

if [ -n "$NUMERIC_CLAIMS" ] && [ -n "$RAW_RESULT_FILES" ]; then
    Run /paper-claim-audit "paper/"
    If FAIL:
        Fix mismatched numbers before the final report
elif [ -n "$NUMERIC_CLAIMS" ]; then
    Stop and warn: the paper contains numeric claims but no raw evidence files were found
fi
```

**Empirical motivation:** in a real submission run, the final paper claimed a narrower experiment grid than the raw JSON actually contained, and a tolerance value was rounded down past the actual relative error. Both were caught only after manual `paper-claim-audit` invocation in the final round; the improvement loop did not detect them.

### Phase 5.6: Kill-Argument Adversarial Review (theory / scope-heavy papers)

After Phase 5.5 (claim audit) passes, run `/kill-argument` whenever the paper is theory-heavy or makes explicit scope/generality claims in the title or abstract. This is a final adversarial check that complements the claim/citation/proof audits: those verify *local correctness* (numbers match, cites resolve, theorems prove); kill-argument tests *headline-level* survival — whether the paper as a whole answers the worst rejection paragraph a senior area chair would write.

```bash
THEORY_ENV_COUNT=$(rg -c '\\begin\{(theorem|lemma|proposition|corollary)\}' paper/main.tex paper/sections 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
SCOPE_HINT=$(rg -i 'general(ization)?|broad|universal|across|any [A-Za-z]+ model|holds for' paper/sections/0*abstract* 2>/dev/null | head -1)

if [ "$THEORY_ENV_COUNT" -ge 5 ] || [ -n "$SCOPE_HINT" ]; then
    /kill-argument "paper/"
    KILL_VERDICT=$(jq -r '.verdict' paper/KILL_ARGUMENT.json)
    KILL_REASON=$(jq -r '.reason_code' paper/KILL_ARGUMENT.json)
fi
```

**Gating** (depends on the resolved `assurance` level from Phase 0):

| Assurance level | THEORY/SCOPE detected | Behavior |
|---|---|---|
| `submission` | yes | **MANDATORY**. `FAIL` blocks the final report; `WARN` requires explicit user acknowledgment; `BLOCKED`/`ERROR` blocks the final report (cannot ship without an adversarial pass). |
| `submission` | no | Skip — `KILL_ARGUMENT.json` is written with `verdict: NOT_APPLICABLE, reason_code: not_theory_or_scope_paper` so the submission verifier sees a record. |
| `internal` / `draft` | yes | **Advisory**. Run if the user passed `— kill-argument: true`; otherwise skip. `WARN`/`FAIL` is logged but does not block. |
| `internal` / `draft` | no | Skip. |

`/kill-argument` itself never edits the paper; it writes `KILL_ARGUMENT.{md,json}`. If `still_unresolved critical` points are surfaced, queue them for the next `/auto-paper-improvement-loop` round (Step 5.5 of that skill auto-merges the findings into its fix list).

**Why this is the right place:** Phase 5 (loop) optimizes for score, Phase 5.5 (claim audit) verifies numbers, Phase 5.8 (citation audit) verifies cites — none of these catches the case where every local component is correct but the paper still oversells what it actually proves. Kill-argument is the dedicated headline-scope check.

### Phase 5.8: Citation Audit (submission gate)

After the final paper-claim-audit passes, run `/citation-audit` to verify every `\cite{...}` along three axes: existence, metadata correctness, and context appropriateness. This is the fourth and final layer of the evidence-and-claim assurance stack (`experiment-audit` → `result-to-claim` → `paper-claim-audit` → `citation-audit`).

```
if paper/references.bib (or paper.bib) exists and contains entries cited from sec/*.tex:
    Run /citation-audit "paper/"
    Fresh cross-family reviewer (gpt-5.4 via Codex MCP) with web/DBLP/arXiv lookup
    verifies each entry:
      (i)   EXISTENCE — paper resolves at claimed arXiv ID / DOI / venue
      (ii)  METADATA — author names, year, venue, title match canonical sources
      (iii) CONTEXT — cited paper actually establishes the claim it supports

    Output:
      - CITATION_AUDIT.md (human-readable per-entry verdict report)
      - CITATION_AUDIT.json (machine-readable verdict ledger)
      - Per-entry verdicts: KEEP / FIX / REPLACE / REMOVE

    If any REPLACE or REMOVE verdicts:
        Surface to user for human approval — never auto-modify content claims
    If only FIX verdicts (metadata corrections):
        Apply with user confirmation, then recompile
    If all KEEP:
        Pass — bibliography clean for submission
else:
    skip — no bib file or no citations
```

**Why this is the most diagnostic of the four audit layers:** wildly fake citations are easy to spot. The dangerous failure mode is a real paper used to support a claim it does not actually establish (wrong-context citations) — these slip past metadata-only checks and damage submission credibility. Run cost is wall-clock heavy (web lookup per entry); run once per submission, not per save.

**Empirical motivation:** in a real submission run, several real papers were cited in contexts they did not actually support, and at least one bib entry shipped with `author = "Anonymous"` because the metadata had not been resolved. None were caught by the improvement loop or numeric claim audit; only fresh web-lookup review surfaced them.

### Phase 6: Final Report

**Phase 6.0 — Submission Gate**

Before writing the Final Report, resolve the active assurance level. This
uses the **same derivation rule as Phase 0** so a run where Phase 0 was
skipped or its write failed cannot silently downgrade a `beast` / `max` /
`— assurance: submission` invocation back to draft.

**Resolution at the gate** (re-derive; do not trust `.aris/assurance.txt`
alone):

1. Parse `$ARGUMENTS` for an explicit `— assurance: draft | submission` or
   an `— effort: lite | balanced | max | beast` directive.
2. Derive the expected level:
   - explicit `assurance:` wins
   - else `lite` / `balanced` → `draft`, `max` / `beast` → `submission`
   - else `draft`
3. Read `paper/.aris/assurance.txt`. If the file is missing, write it now
   with the derived level.
4. If the file's value **disagrees** with the derived level (e.g. file
   says `draft` but `$ARGUMENTS` says `beast`), **overwrite** the file
   with the derived level and surface a one-line warning in-chat:
   `⚠️ .aris/assurance.txt was draft but $ARGUMENTS says submission; overriding.`
5. Use the re-derived level as authoritative for the rest of Phase 6.

```bash
# Final authoritative value, written and read from the same source
ASSURANCE=<derived-from-$ARGUMENTS>        # draft | submission
mkdir -p paper/.aris
echo "$ASSURANCE" > paper/.aris/assurance.txt
```

If `ASSURANCE=draft`, skip directly to the Final Report template below —
**current behavior, no change** for the default `balanced` user.

If `ASSURANCE=submission`, run the pre-flight checklist below, then the
verifier. The verifier's exit code is the source of truth — do NOT
self-declare "audits complete" based on conversation memory.

#### Submission pre-flight checklist

Print this checklist verbatim at the start of Phase 6.0 and confirm each row
before proceeding. This resists the common failure mode of the model
skipping audits while claiming to have run them.

```
📋 Submission audits required before Final Report:
   [ ] 1. /proof-checker        → paper/PROOF_AUDIT.json
   [ ] 2. /paper-claim-audit    → paper/PAPER_CLAIM_AUDIT.json
   [ ] 3. /citation-audit       → paper/CITATION_AUDIT.json
   [ ] 4. bash <ARIS_REPO>/tools/verify_paper_audits.sh paper/ --assurance submission
   [ ] 5. Block Final Report iff verifier exit code != 0
```

> `<ARIS_REPO>` placeholder — replace with the absolute path to your ARIS
> clone (e.g. `~/Desktop/Auto-claude-code-research-in-sleep` or the path
> returned by `dirname $(readlink ~/.claude/skills/paper-writing/SKILL.md)/../..`).
> The path is stable across runs; store it in a shell variable if you
> prefer (`export ARIS_REPO=~/…` and use `"$ARIS_REPO"` in the command).

#### Invoking the three audits

Each sub-audit runs in a **fresh Codex thread** (never `codex-reply`,
never pass prior audit output as context — this preserves reviewer
independence per `shared-references/reviewer-independence.md`).

Each sub-audit **always** emits its JSON artifact, even when the content
detector is negative. A detector-negative run emits verdict
`NOT_APPLICABLE`; a silent skip is forbidden. See the "Submission artifact
emission" section of each audit's SKILL.md.

Order:

1. `/proof-checker "paper/"` → writes `paper/PROOF_AUDIT.json` (emits
   `NOT_APPLICABLE` if the paper contains no theorems / lemmas / proofs)
2. `/paper-claim-audit "paper/"` → writes `paper/PAPER_CLAIM_AUDIT.json`
   (emits `NOT_APPLICABLE` if the paper has no numeric claims; emits
   `BLOCKED` if numeric claims exist but raw result files are missing)
3. `/citation-audit "paper/"` → writes `paper/CITATION_AUDIT.json`
   (emits `NOT_APPLICABLE` if no `.bib` file or no `\cite{...}` usage)

#### Running the verifier

```bash
bash <ARIS_REPO>/tools/verify_paper_audits.sh paper/ --assurance submission
```

- **Exit 0** — All mandatory audits present, JSON schema-valid, hashes fresh,
  no blocking verdicts. Proceed to the Final Report below.
- **Exit 1** — Surface `paper/.aris/audit-verifier-report.json` to the user
  verbatim, **refuse to generate the Final Report**, and list the specific
  remediation for each failing row:
  - `MISSING` → rerun that audit
  - `STALE` → paper files edited after the audit ran; rerun the affected audit
  - `BLOCKING_VERDICT` (FAIL / BLOCKED / ERROR) → fix the underlying issue,
    then rerun the audit
  - `SCHEMA_INVALID` → audit artifact malformed; rerun the audit

The verifier is cheap to rerun (< 1 s). After fixing any issue, rerun it
before claiming green.

#### Optional hardening (not default)

Teams that want hook-level enforcement — i.e., the harness physically
prevents a Stop event while the verifier is red — can register a Stop hook
in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {"command": "bash <ARIS_REPO>/tools/verify_paper_audits.sh paper/ --assurance submission"}
    ]
  }
}
```

This is documented here, not required. Phase 6.0's verifier-as-truth
pattern is the default repo behavior.

---

**Phase 6.1 — Final Report** (runs only after the submission gate is green,
or directly if `assurance=draft`)

```markdown
# Paper Writing Pipeline Report

**Input**: [NARRATIVE_REPORT.md or topic]
**Venue**: [ICLR/NeurIPS/ICML/CVPR/ACL/AAAI/ACM/IEEE_JOURNAL/IEEE_CONF]
**Assurance**: [draft | submission]
**Submission-ready**: [yes | no]   <!-- yes iff assurance=submission AND verifier exit 0 -->
**Date**: [today]

## Pipeline Summary

| Phase | Status | Output |
|-------|--------|--------|
| 0. Assurance Setup | ✅ | paper/.aris/assurance.txt = [draft\|submission] |
| 1. Paper Plan | ✅ | PAPER_PLAN.md |
| 2. Figures | ✅ | figures/ ([N] auto + [M] manual) |
| 3. LaTeX Writing | ✅ | paper/sections/*.tex ([N] sections, [M] citations) |
| 4. Compilation | ✅ | paper/main.pdf ([X] pages) |
| 5. Improvement | ✅ | [score0]/10 → [score2]/10 |
| 4.5 Proof Audit | [PASS\|WARN\|FAIL\|NOT_APPLICABLE\|BLOCKED\|ERROR] | PROOF_AUDIT.{md,json} |
| 5.5 Paper Claim Audit | [PASS\|WARN\|FAIL\|NOT_APPLICABLE\|BLOCKED\|ERROR] | PAPER_CLAIM_AUDIT.{md,json} |
| 5.8 Citation Audit | [PASS\|WARN\|FAIL\|NOT_APPLICABLE\|BLOCKED\|ERROR] | CITATION_AUDIT.{md,json} |
| 6.0 Assurance Verifier | [OK\|STALE\|BLOCKING_VERDICT\|HAS_ISSUES\|SCHEMA_INVALID\|MISSING] per audit; exit [0\|1] overall (N/A if draft) | .aris/audit-verifier-report.json |

## Improvement Scores
| Round | Score | Key Changes |
|-------|-------|-------------|
| Round 0 | X/10 | Baseline |
| Round 1 | Y/10 | [summary] |
| Round 2 | Z/10 | [summary] |

## Deliverables
- paper/main.pdf — Final polished paper
- paper/main_round0_original.pdf — Before improvement
- paper/main_round1.pdf — After round 1
- paper/main_round2.pdf — After round 2
- paper/PAPER_IMPROVEMENT_LOG.md — Full review log
- paper/PROOF_AUDIT.{md,json} — Proof-obligation verification (always emitted at `assurance=submission`; `NOT_APPLICABLE` when no theorems)
- paper/PAPER_CLAIM_AUDIT.{md,json} — Numerical claim verification (always emitted at `assurance=submission`; `NOT_APPLICABLE` when no numeric claims; omitted in `draft` mode if Phase 5.5 detector was negative)
- paper/CITATION_AUDIT.{md,json} — Bibliography verification (always emitted at `assurance=submission`; `NOT_APPLICABLE` when no `.bib` or no `\cite{...}`; omitted in `draft` mode if Phase 5.8 detector was negative)
- paper/.aris/audit-verifier-report.json — External verifier report (submission only)

## Remaining Issues (if any)
- [items from final review that weren't addressed]

## Next Steps
- [ ] Visual inspection of PDF
- [ ] Add any missing manual figures
- [ ] Submit to [venue] via OpenReview / CMT / HotCRP
```

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../shared-references/output-language.md)** — note: paper-writing always outputs English LaTeX for venue submission

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.
- **Don't skip phases.** Each phase builds on the previous one — skipping leads to errors.
- **Checkpoint between phases** when AUTO_PROCEED=false. Present results and wait for approval.
- **Manual figures first.** If the paper needs architecture diagrams or qualitative results, the user must provide them before Phase 3.
- **Compilation must succeed** before entering the improvement loop. Fix all errors first.
- **Preserve all PDFs.** The user needs round0/round1/round2 for comparison.
- **Document everything.** The pipeline report should be self-contained.
- **Respect page limits.** If the paper exceeds the venue limit, suggest specific cuts before the improvement loop.

## Composing with Other Workflows

```
/idea-discovery "direction"         ← Workflow 1: find ideas
implement                           ← write code
/run-experiment                     ← deploy experiments
/auto-review-loop "paper topic"     ← Workflow 2: iterate research
/paper-writing "NARRATIVE_REPORT.md"  ← Workflow 3: you are here
                                         submit! 🎉

Or use /research-pipeline for the Workflow 1+2 end-to-end flow,
then /paper-writing for the final writing step.
```

## Typical Timeline

| Phase | Duration | Can sleep? |
|-------|----------|------------|
| 1. Paper Plan | 5-10 min | No |
| 2. Figures | 5-15 min | No |
| 3. LaTeX Writing | 15-30 min | Yes ✅ |
| 4. Compilation | 2-5 min | No |
| 5. Improvement | 15-30 min | Yes ✅ |

**Total: ~45-90 min** for a full paper from narrative report to polished PDF.
