---
name: auto-paper-improvement-loop
description: "Autonomously improve a generated paper via GPT-5.4 xhigh review → implement fixes → recompile, for 2 rounds. Use when user says \"改论文\", \"improve paper\", \"论文润色循环\", \"auto improve\", or wants to iteratively polish a generated paper."
argument-hint: [paper-directory]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Auto Paper Improvement Loop: Review → Fix → Recompile

Autonomously improve the paper at: **$ARGUMENTS**

## Context

This skill is designed to run **after** Workflow 3 (`/paper-plan` → `/paper-figure` → `/paper-write` → `/paper-compile`). It takes a compiled paper and iteratively improves it through external LLM review.

Unlike `/auto-review-loop` (which iterates on **research** — running experiments, collecting data, rewriting narrative), this skill iterates on **paper writing quality** — fixing theoretical inconsistencies, softening overclaims, adding missing content, and improving presentation.

## Constants

- **MAX_ROUNDS = 2** — Two rounds of review→fix→recompile. Empirically, Round 1 catches structural issues (4→6/10), Round 2 catches remaining presentation issues (6→7/10). Diminishing returns beyond 2 rounds for writing-only improvements.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for paper review.
- **REVIEWER_BIAS_GUARD = true** — When `true`, every review round uses a fresh `mcp__codex__codex` thread with no prior review context. Never use `mcp__codex__codex-reply` for review rounds. Set to `false` only for deliberate debugging of the legacy behavior. **Empirical evidence:** running the same paper with `codex-reply` + "since last round we did X" prompts inflated scores from real 3/10 → fake 8/10 across multiple rounds; switching to fresh threads recovered the true 3/10 assessment.
- **REVIEW_LOG = `PAPER_IMPROVEMENT_LOG.md`** — Cumulative log of all rounds, stored in paper directory.
- **HUMAN_CHECKPOINT = false** — When `true`, pause after each round's review and present score + weaknesses to the user. The user can approve fixes, provide custom modification instructions, skip specific fixes, or stop early. When `false` (default), runs fully autonomously.

> 💡 Override: `/auto-paper-improvement-loop "paper/" — human checkpoint: true`

## Inputs

1. **Compiled paper** — `paper/main.pdf` + LaTeX source files
2. **All section `.tex` files** — concatenated for review prompt

## State Persistence (Compact Recovery)

If the context window fills up mid-loop, Claude Code auto-compacts. To recover, this skill writes `PAPER_IMPROVEMENT_STATE.json` after each round:

```json
{
  "current_round": 1,
  "threadId": "019ce736-...",
  "last_score": 6,
  "status": "in_progress",
  "timestamp": "2026-03-13T21:00:00"
}
```

**On startup**: if `PAPER_IMPROVEMENT_STATE.json` exists with `"status": "in_progress"` AND `timestamp` is within 24 hours, read it + `PAPER_IMPROVEMENT_LOG.md` to recover context, then resume from the next round. Otherwise (file absent, `"status": "completed"`, or older than 24 hours), start fresh.

**After each round**: overwrite the state file. **On completion**: set `"status": "completed"`.

## Reviewer Independence Protocol

The reviewer must be context-naive on every round. Prior-round summaries, fix lists, and executor explanations are not evidence; they are a source of confirmation bias. If the reviewer is told what changed, scores tend to drift upward even when the manuscript itself has not materially improved.

Rules:
- Every round starts with `mcp__codex__codex`, not `mcp__codex__codex-reply`.
- Never pass a prior threadId into the next review prompt.
- Never include "since last round", "we fixed", "after applying", or any fix summary in the reviewer prompt.
- The only acceptable evidence of improvement is the current `.tex` source and compiled PDF.
- If a fix cannot be observed in the files, the reviewer should not be told it happened.
- If recovery metadata is needed, store the returned threadId for crash recovery only; do not use it to preserve review context.

Set `REVIEWER_BIAS_GUARD = false` only if you explicitly want the legacy, context-carrying behavior for debugging.

## Workflow

### Step 0: Preserve Original

```bash
cp paper/main.pdf paper/main_round0_original.pdf
```

### Step 1: Collect Paper Text

Concatenate all section files into a single text block for the review prompt:

```bash
# Collect all sections in order
for f in paper/sections/*.tex; do
    echo "% === $(basename $f) ==="
    cat "$f"
done > /tmp/paper_full_text.txt
```

### Step 2: Round 1 Review

Send the full paper text AND compiled PDF to GPT-5.4 xhigh:

```
mcp__codex__codex:
  model: gpt-5.4
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    You are reviewing a [VENUE] paper. Please provide a detailed, structured review.

    ## Paper Files:
    - LaTeX source: [list all section .tex files]
    - Compiled PDF: paper/main.pdf
    - Figures: [list figure files]

    Read BOTH the LaTeX source (for content/logic) AND the compiled PDF (for visual presentation).

    ## Review Instructions
    Please act as a senior ML reviewer ([VENUE] level). Provide:
    1. **Overall Score** (1-10, where 6 = weak accept, 7 = accept)
    2. **Summary** (2-3 sentences)
    3. **Strengths** (bullet list, ranked)
    4. **Weaknesses** (bullet list, ranked: CRITICAL > MAJOR > MINOR)
    5. **For each CRITICAL/MAJOR weakness**: A specific, actionable fix
    6. **Missing References** (if any)
    7. **Visual Review** (from the PDF):
       - Figure quality: readable? labels legible? colors distinguishable in grayscale?
       - Figure-caption alignment: does each caption match its figure?
       - Layout: orphaned headers, awkward page breaks, figures far from references?
       - Table formatting: aligned columns, consistent decimals, bold for best results?
       - Visual consistency: same color scheme across all figures?
    8. **Verdict**: Ready for submission? Yes / Almost / No

    Focus on: theoretical rigor, claims vs evidence alignment, writing clarity,
    self-containedness, notation consistency, AND visual presentation quality.
```

Save the threadId for Round 2.

### Step 2b: Human Checkpoint (if enabled)

**Skip if `HUMAN_CHECKPOINT = false`.**

Present the review results and wait for user input:

```
📋 Round 1 review complete.

Score: X/10 — [verdict]
Key weaknesses (by severity):
1. [CRITICAL] ...
2. [MAJOR] ...
3. [MINOR] ...

Reply "go" to implement all fixes, give custom instructions, "skip 2" to skip specific fixes, or "stop" to end.
```

Parse user response same as `/auto-review-loop`: approve / custom instructions / skip / stop.

### Step 3: Implement Round 1 Fixes

Parse the review and implement fixes by severity:

**Priority order:**
1. CRITICAL fixes (assumption mismatches, internal contradictions)
2. MAJOR fixes (overclaims, missing content, notation issues)
3. MINOR fixes (if time permits)

**Common fix patterns:**

| Issue | Fix Pattern |
|-------|-------------|
| Assumption-model mismatch | Rewrite assumption to match the model, add formal proposition bridging the gap |
| Overclaims | Soften language: "validate" → "demonstrate practical relevance", "comparable" → "qualitatively competitive" |
| Missing metrics | Add quantitative table with honest parameter counts and caveats |
| Theorem not self-contained | Add "Interpretation" paragraph listing all dependencies |
| Notation confusion | Rename conflicting symbols globally, add Notation paragraph |
| Missing references | Add to `references.bib`, cite in appropriate locations |
| Theory-practice gap | Explicitly frame theory as idealized; add synthetic validation subsection |
| Proof gap (theory papers) | Run `/proof-checker` if PROOF_AUDIT.md doesn't exist yet; fix FATAL/CRITICAL issues |
| Writing clutter / passive voice | Apply sciwrite 5-pass audit: clutter extraction → active voice → sentence architecture → keyword consistency → numerical integrity. See `paper-write` Step 5 |
| Number mismatch (paper vs results) | Run `/paper-claim-audit` if PAPER_CLAIM_AUDIT.md doesn't exist; fix any `number_mismatch` or `aggregation_mismatch` claims |
| Keyword inconsistency | The "Banana Rule": if Methods says "obese group", Results must not say "heavier group". Extract key terms, verify consistency across all sections |

### Step 4: Recompile Round 1

```bash
cd paper && latexmk -C && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
cp main.pdf main_round1.pdf
```

Verify: 0 undefined references, 0 undefined citations.

### Step 4.5: Restatement Regression Test

After every recompilation, rerun a theorem-statement consistency check so fix rounds cannot reintroduce appendix drift. **Run this after Step 4 and again after Step 7 before the final format check.**

**Scope**
- Compare only theorem/lemma/proposition/corollary statements, not proof bodies.
- Classify files by `main.tex` input order: files before `\appendix` are main body; files after `\appendix` are appendix.

**Normalized comparison logic**
- Strip comments, `\label{...}`, `\ref{...}`, `\eqref{...}`, `\cite...{...}`, and whitespace-only differences.
- Collapse formatting-only macros such as `\emph{}`, `\textbf{}`, `\textit{}`, `\mathrm{}`, `\mathbf{}`, `\mathcal{}`, and `\operatorname{}` to their contents.
- Preserve quantifiers, case splits, assumptions, and the literal names of defined objects.
- Compare by theorem label when available; otherwise compare by theorem type and order.
- Flag any change in hypotheses, case splits, quantifier order, or terminology (`stationary` vs `terminal`) as regression drift.

```bash
python3 - <<'PY'
import re
def normalize(s):
    s = re.sub(r'%.*', '', s)
    s = re.sub(r'\\label\{[^}]*\}', '', s)
    s = re.sub(r'\\(?:ref|eqref|cref|Cref|cite[a-zA-Z]*)\{[^}]*\}', '', s)
    s = re.sub(r'\\(?:emph|textbf|textit|mathrm|mathbf|mathsf|mathcal|operatorname)\{([^{}]*)\}', r'\1', s)
    s = re.sub(r'\\begin\{[^}]+\}|\\end\{[^}]+\}', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip().lower()
# Compare normalized theorem blocks from the current main-body files
# against their appendix restatements. Any mismatch blocks completion.
PY
```

**Empirical motivation:** in a real submission run, a key theorem had a multi-case split in the main text but a single-case statement in the appendix; a key variable was named one way in main and another in appendix. These drifted multiple times across fix rounds because no automated check caught regression.

**Optional deeper check: `/proof-checker --restatement-check`**

The inline Python check above is the default and is sufficient for routine main-vs-appendix consistency. For broader coverage, you may additionally invoke `/proof-checker --restatement-check` (added in PR #189), which extends the comparison to:

- Restatements in summary tables, abstract, "Key Contributions" lists, and discussion sections (not just main vs appendix).
- Six named drift signatures classified by reviewer: `conditional_loss`, `scope_change`, `quantifier_loss`, `regime_envelope_change`, `constant_change`, `variable_rename`.
- Structured findings emitted as `details.restatement_drift[]` in `PROOF_AUDIT.json`, suitable for downstream tooling or audit trails.

This is advisory only — the inline Step 4.5 check remains the default and continues to run on every loop round. Consider invoking `/proof-checker --restatement-check` when (a) you suspect cross-location drift outside the main↔appendix axis (e.g., abstract overclaim relative to theorem statement), or (b) you want reviewer-graded drift signatures rather than raw string mismatches. Running both is supported and they are independent: the inline check fails fast on string drift, the proof-checker pass surfaces semantic-class drift.

### Step 5: Round 2 Review

If `REVIEWER_BIAS_GUARD = true` (default), use a **fresh** `mcp__codex__codex` thread for Round 2. Do not reuse the Round 1 threadId for prompting. Save the returned threadId only for recovery bookkeeping.

```
mcp__codex__codex:
  model: gpt-5.4
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    You are reviewing a [VENUE] paper. This is a fresh, zero-context review.
    Ignore any prior review rounds, prior fix lists, or executor explanations.
    Judge the paper only from the current LaTeX source and compiled PDF.

    ## Paper Files:
    - LaTeX source: [list all section .tex files]
    - Compiled PDF: paper/main.pdf
    - Figures: [list figure files]

    Read BOTH the LaTeX source (for content/logic) AND the compiled PDF (for visual presentation).

    ## Review Instructions
    Please act as a senior ML reviewer ([VENUE] level). Provide:
    1. **Overall Score** (1-10, where 6 = weak accept, 7 = accept)
    2. **Summary** (2-3 sentences)
    3. **Strengths** (bullet list, ranked)
    4. **Weaknesses** (bullet list, ranked: CRITICAL > MAJOR > MINOR)
    5. **For each CRITICAL/MAJOR weakness**: A specific, actionable fix
    6. **Missing References** (if any)
    7. **Visual Review** (from the PDF):
       - Figure quality: readable? labels legible? colors distinguishable in grayscale?
       - Figure-caption alignment: does each caption match its figure?
       - Layout: orphaned headers, awkward page breaks, figures far from references?
       - Table formatting: aligned columns, consistent decimals, bold for best results?
       - Visual consistency: same color scheme across all figures?
    8. **Verdict**: Ready for submission? Yes / Almost / No

    Focus on: theoretical rigor, claims vs evidence alignment, writing clarity,
    self-containedness, notation consistency, and visual presentation quality.
```

If `REVIEWER_BIAS_GUARD = false` (legacy debugging only), use `mcp__codex__codex-reply` with the saved threadId; this is **not** the recommended path.

### Step 5.5: Kill Argument Exercise (theory papers only)

Run this only if the paper is theory-heavy (≥5 `\begin{theorem}|\begin{lemma}|\begin{proposition}|\begin{corollary}` environments in the source) and only on the final scheduled round (`current_round == MAX_ROUNDS`).

This is a late-stage adversarial check. It must always use **fresh** `mcp__codex__codex` threads, never `codex-reply`, and it must not reuse any prior review context.

**Thread 1: Attack**
- Use a fresh thread with only the current paper files.
- Prompt: "Construct the single best argument to reject this paper in 200 words. Focus on theorem validity, assumption mismatch, missing proof obligations, limit-order ambiguity, and claim/evidence gaps. Do not reference prior rounds or fixes."

**Thread 2: Defense**
- Use a second fresh thread with the current paper files plus the attack memo.
- Prompt: "Now defend the paper against the attack memo. For each rejection point, classify it as already fixed, partially fixed, or still unresolved, and cite the current files. Do not reuse prior review context."

**Merge rule**
- Dedupe attack points against the Round 2 weakness list by semantic overlap.
- Append any novel unresolved attack point to the Step 6 fix list before implementation.
- If the defense cannot refute a point, keep it at the original severity or raise it by one level if it exposes a main-theorem or core-assumption failure.
- If the defense shows the issue is already fixed in the current files, only downgrade after verifying the file evidence.
- Record both memos in `PAPER_IMPROVEMENT_LOG.md`.
- If `HUMAN_CHECKPOINT = true`, include the merged findings in the checkpoint summary before asking the user to proceed.

This phase feeds directly into Step 6. The attack/defense findings must be merged before the final recompile.

**Empirical motivation:** in a real submission run, after several rounds of standard improvement (score 7-8/10), the kill-argument exercise surfaced framing weaknesses that no prior review caught (e.g., a setting being mostly conditional rather than truly general, or a baseline being irrelevant to real systems). Author rebuttal forced explicit scope qualifications in abstract and discussion.

### Step 5b: Human Checkpoint (if enabled)

**Skip if `HUMAN_CHECKPOINT = false`.** Same as Step 2b — present Round 2 review, wait for user input.

### Step 6: Implement Round 2 Fixes

Same process as Step 3. Typical Round 2 fixes:
- Add controlled synthetic experiments validating theory
- Further soften any remaining overclaims
- Formalize informal arguments (e.g., truncation → formal proposition)
- Strengthen limitations section

### Step 7: Recompile Round 2

```bash
cd paper && latexmk -C && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
cp main.pdf main_round2.pdf
```

### Step 8: Format Check

After the final recompilation, run a **location-aware** format compliance check.

```bash
# If the log lacks file/line data, rerun the final compile once with -file-line-error.
cd paper && latexmk -pdf -file-line-error -interaction=nonstopmode -halt-on-error main.tex
```

```bash
# 1. Page count vs venue limit
PAGES=$(pdfinfo paper/main.pdf | grep Pages | awk '{print $2}')
echo "Pages: $PAGES (limit: 9 main body for ICLR/NeurIPS)"

# 2. Duplicate labels: HARD BLOCK
DUP_LABELS=$(grep -Rho "\\\\label{[^}]*}" paper/main.tex paper/sections 2>/dev/null | sort | uniq -d || true)
if [ -n "$DUP_LABELS" ]; then
    echo "Duplicate labels found (BLOCKING):"
    echo "$DUP_LABELS"
fi

# 3. Overfull warnings with location classification
OVERFULLS=$(grep -n "Overfull \\\\hbox" paper/main.log 2>/dev/null || true)

# Main body = source files before \appendix in main.tex.
# Appendix = source files after \appendix, or files whose path contains "appendix".
# Bibliography = paper.bbl, references.bib, or bibliography-generated output.
MAIN_BODY_OVERFULL=$(echo "$OVERFULLS" | grep -v -E 'appendix|paper\.bbl|references\.bib' || true)
APPENDIX_OVERFULL=$(echo "$OVERFULLS" | grep -E 'appendix' || true)
BIB_OVERFULL=$(echo "$OVERFULLS" | grep -E 'paper\.bbl|references\.bib' || true)

echo "Main-body overfulls (any size BLOCKS):"
echo "$MAIN_BODY_OVERFULL"
echo "Appendix overfulls (>10pt blocks):"
echo "$APPENDIX_OVERFULL"
echo "Bibliography overfulls (>20pt blocks):"
echo "$BIB_OVERFULL"
```

**Stop criteria:**
- Any duplicate label blocks completion.
- Any overfull in the main body blocks completion, regardless of size.
- Appendix overfulls block completion only if they exceed 10pt or are visibly clipping.
- Bibliography overfulls block completion only if they exceed 20pt or are visibly clipping.
- Underfull hboxes remain warnings unless they create obvious layout damage.

**Auto-fix patterns (location-aware):**

| Issue | Fix |
|-------|-----|
| Main-body overfull in equation | Split with `aligned` / `split` / `multline`, or shorten notation |
| Main-body overfull in table | Reduce font, resize table, or break table across rows |
| Main-body overfull in text | Rephrase; do not hide it with global `\sloppy` |
| Appendix overfull ≤ 10pt | Warn only unless visibly clipping |
| Appendix overfull > 10pt | Apply the same fix if the spill is visible |
| Bibliography overfull ≤ 20pt | Warn only unless caused by malformed entry or clipping |
| Bibliography overfull > 20pt | Fix malformed entry, URL, or DOI formatting |
| Over page limit | Move content to appendix, compress tables, reduce figure sizes |

**Location-aware interpretation:**
- Classify by the source file reported in the `-file-line-error` log.
- If a warning cannot be classified, treat it as main body and fix it.

**Empirical motivation:** in a real submission run, dozens of overfull hbox warnings (the largest well over 100pt in an appendix proof) survived multiple improvement rounds because the previous blanket "overfull > 10pt blocks" rule was too lax and treated all locations equally.

### Step 9: Document Results

Create `PAPER_IMPROVEMENT_LOG.md` in the paper directory:

```markdown
# Paper Improvement Log

## Score Progression

| Round | Score | Verdict | Key Changes |
|-------|-------|---------|-------------|
| Round 0 (original) | X/10 | No/Almost/Yes | Baseline |
| Round 1 | Y/10 | No/Almost/Yes | [summary of fixes] |
| Round 2 | Z/10 | No/Almost/Yes | [summary of fixes] |

## Round 1 Review & Fixes

<details>
<summary>GPT-5.4 xhigh Review (Round 1)</summary>

[Full raw review text, verbatim]

</details>

### Fixes Implemented
1. [Fix description]
2. [Fix description]
...

## Round 2 Review & Fixes

<details>
<summary>GPT-5.4 xhigh Review (Round 2)</summary>

[Full raw review text, verbatim]

</details>

### Fixes Implemented
1. [Fix description]
2. [Fix description]
...

## PDFs
- `main_round0_original.pdf` — Original generated paper
- `main_round1.pdf` — After Round 1 fixes
- `main_round2.pdf` — Final version after Round 2 fixes
```

### Step 9: Summary

Report to user:
- Score progression table
- Number of CRITICAL/MAJOR/MINOR issues fixed per round
- Final page count
- Remaining issues (if any)

### Feishu Notification (if configured)

After each round's review AND at final completion, check `~/.claude/feishu.json`:
- **After each round**: Send `review_scored` — "Round N: X/10 — [key changes]"
- **After final round**: Send `pipeline_done` — score progression table + final page count
- If config absent or mode `"off"`: skip entirely (no-op)

## Output

```
paper/
├── main_round0_original.pdf    # Original
├── main_round1.pdf             # After Round 1
├── main_round2.pdf             # After Round 2 (final)
├── main.pdf                    # = main_round2.pdf
└── PAPER_IMPROVEMENT_LOG.md    # Full review log with scores
```

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- **Preserve all PDF versions** — user needs to compare progression
- **Save FULL raw review text** — do not summarize or truncate GPT-5.4 responses
- **Reviewer independence (Round 2+)**: when `REVIEWER_BIAS_GUARD = true` (default), use a **fresh** `mcp__codex__codex` thread for every review round; never use `mcp__codex__codex-reply` and never include "since last round" / fix summaries in the prompt. See the Reviewer Independence Protocol section above.
- **Always recompile after fixes** — verify 0 errors before proceeding
- **Do not fabricate experimental results** — synthetic validation must describe methodology, not invent numbers
- **Respect the paper's claims** — soften overclaims rather than adding unsupported new claims
- **Global consistency** — when renaming notation or softening claims, check ALL files (abstract, intro, method, experiments, theory sections, conclusion, tables, figure captions)

## Typical Score Progression

Based on end-to-end testing on a 9-page ICLR 2026 theory paper:

| Round | Score | Key Improvements |
|-------|-------|-----------------|
| Round 0 | 4/10 (content) | Baseline: assumption-model mismatch, overclaims, notation issues |
| Round 1 | 6/10 (content) | Fixed assumptions, softened claims, added interpretation, renamed notation |
| Round 2 | 7/10 (content) | Added synthetic validation, formal truncation proposition, stronger limitations |
| Round 3 | 5→8.5/10 (format) | Removed hero fig, appendix, compressed conclusion, fixed overfull hbox |

**+4.5 points across 3 rounds** (2 content + 1 format) is typical for a well-structured but rough first draft. Final: 8 pages main body, 0 overfull hbox, ICLR-compliant.

## Review Tracing

After each `mcp__codex__codex` or `mcp__codex__codex-reply` reviewer call, save the trace following `shared-references/review-tracing.md`. Use `tools/save_trace.sh` or write files directly to `.aris/traces/<skill>/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).
