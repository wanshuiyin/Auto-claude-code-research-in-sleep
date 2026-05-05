---
name: kill-argument
description: "Two-thread adversarial review: a fresh reviewer constructs the strongest 200-word rejection memo, then a second fresh reviewer defends the paper point-by-point and surfaces still-unresolved critical issues. Use when user says \"kill argument\", \"adversarial review\", \"hostile review\", \"rebuttal preparation\", \"reviewer-2 simulation\", or before submitting a theory paper that has already passed standard review rounds."
argument-hint: [paper-directory]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, mcp__codex__codex
---

# Kill Argument Exercise: Adversarial Attack-Defense Review

Stress-test the headline claims of a paper against the strongest possible rejection argument: **$ARGUMENTS**

## Why This Exists

Standard score-based reviews (`/peer-review`, `/research-review`, `/auto-paper-improvement-loop`) tend to produce **balanced** weakness lists.  Each weakness gets ~equal attention, ranked CRITICAL > MAJOR > MINOR.  Empirically, this misses one specific failure mode: the **single most damaging argument** a reviewer would write in a rejection paragraph — the one sentence that, if a senior area chair reads it, kills the paper.

A balanced reviewer might list "scope-overclaim risk" as MAJOR alongside 3-5 other MAJORs, never quite committing.  An adversarial reviewer **must commit**: their entire job is to convince the area chair to reject in 200 words.

This skill runs that adversarial pass deliberately, then forces a second fresh reviewer to defend point-by-point, classify each rejection as already-fixed / partially-fixed / still-unresolved, and surface what's actually load-bearing.

**Empirical motivation** (NeurIPS 2026 D-LLM theory paper, April 2026): after 5 standard improvement rounds settling at score 7-8/10, kill-argument surfaced two framing weaknesses no prior review caught — "width-w is mostly conditional" and "CRF irrelevant to real D-LLMs".  Author rebuttal forced explicit scope qualifications in abstract and discussion that weren't visible from the score-based reviews alone.

## How This Differs From Other Review Skills

| Skill | What it asks the reviewer | Output |
|-------|---------------------------|--------|
| `/peer-review` | "Score this paper, list weaknesses by severity" | balanced weakness list |
| `/research-review` | "Deep technical review of methods + claims" | structured deep critique |
| `/proof-checker` | "Is this theorem actually proved?" | per-step proof obligation audit |
| `/paper-claim-audit` | "Does the paper report numbers truthfully?" | per-claim evidence verification |
| `/citation-audit` | "Are citations real and used in correct context?" | per-entry KEEP/FIX/REPLACE/REMOVE |
| **`/kill-argument`** | **"Write the single strongest rejection paragraph; then defend it."** | **attack memo + per-point defense + unresolved surfaced** |

This skill is **complementary**, not a replacement.  Run after standard reviews when you want to know what the worst-case reviewer paragraph would look like, before camera-ready or rebuttal preparation.

## When To Use

- After 1-2 rounds of `/auto-paper-improvement-loop` settled at a stable score, but before submission.  Surfaces what additional fixes would close the headline-attack gap.
- During rebuttal preparation, to predict reviewer-2's strongest objection so you can prepare the response in advance.
- For theory papers with a high-level title that may oversimplify the actual theorem (the most common reject-attack pattern).
- For papers where a reviewer might attack scope, assumption-vs-claim mismatch, missing proof obligations, or evidence-vs-headline gaps.

This skill is most valuable for **theory papers** with ≥5 theorem-class environments (so the headline depends on real proof obligations).  For empirical papers without theorems, use `/peer-review` instead.

## Constants

- **REVIEWER_MODEL** = `gpt-5.5` (default; specify `gpt-5.4` if you want the older default).  Reviewer reasoning effort = `xhigh`.
- **CONTEXT_POLICY** = `fresh` (REVIEWER_BIAS_GUARD).  Each thread is a fresh `mcp__codex__codex` call.  **Never** use `mcp__codex__codex-reply`.  No prior review summary, fix list, or executor explanation enters either prompt.
- **ATTACK_LENGTH** = approximately 200 words (do not exceed 250).  Single coherent argument, not a list.
- **DEFENSE_DECOMPOSITION** = 3-7 atomic rejection points extracted from the attack memo.  Each gets its own classification.
- **CLASSIFICATION** = `already_fixed` / `partially_fixed` / `still_unresolved`.
- **OUTPUT** = `KILL_ARGUMENT.md` (human-readable) + `KILL_ARGUMENT.json` (machine-readable) in the paper directory.

## Workflow

### Step 1: Discover paper files

Locate the paper directory and inventory the source.

```bash
PAPER_DIR="$ARGUMENTS"   # e.g., paper-overleaf/ or paper/
cd "$PAPER_DIR"

# Find the LaTeX entry point
ENTRY=$(grep -lE '^\\documentclass' *.tex 2>/dev/null | head -1)
echo "Entry: $ENTRY"

# Find all source files codex should read
find . -name "*.tex" -not -path "./.git/*" 2>/dev/null
find . -name "*.bib" -not -path "./.git/*" 2>/dev/null
find figures/ -name "*.pdf" -o -name "*.png" 2>/dev/null
ls -la *.pdf 2>/dev/null  # compiled PDF
```

If a compiled PDF is missing, the skill should still run on .tex source alone, but the prompt should mention this so the reviewer doesn't waste cycles trying to extract from a non-existent PDF.

### Step 2: Attack memo (Thread 1, fresh codex)

Invoke `mcp__codex__codex` (NOT `codex-reply`) with the following prompt structure:

```
mcp__codex__codex:
  model: gpt-5.5
  config: {"model_reasoning_effort": "xhigh"}
  sandbox: read-only
  cwd: <paper directory>
  prompt: |
    You are simulating a hostile NeurIPS / ICLR / ICML reviewer for a paper.
    This is a kill-argument adversarial check — your task is NOT to give a
    balanced review but to construct the **single strongest argument for
    rejecting this paper**.

    ## Files to read
    - LaTeX entry: <ENTRY>
    - All section files under sections/ or wherever they live
    - Macro files (math_commands.tex, etc.)
    - Compiled PDF: <main.pdf> (if available)

    Read the source carefully. Do not consult any prior reviews, fix lists,
    or summaries; this must be a fresh, zero-context adversarial pass.

    ## Your task
    Construct the single best argument to reject this paper in approximately
    200 words. Your goal is to write the worst-case rejection memo a senior
    NeurIPS area chair would produce after reading the paper.

    Focus on these axes (pick the most damaging combination, do not list all):
    1. Theorem validity: are central theorems actually proved as stated?
    2. Assumption-vs-claim mismatch: does the body silently retreat to a
       narrower object than the title/abstract advertise?
    3. Missing proof obligations: is a fundamental lemma invoked but not
       proved (e.g., concentration, generic position, prefactor envelope)
       that the headline depends on?
    4. Limit-order ambiguity: are limits in K/n/d/eps composed in a way the
       paper does not commit to?
    5. Claim-vs-evidence gap: is the empirical/numerical evidence too narrow
       to support the breadth of the stated theorem or take-away?
    6. Scope overclaim: does the title or abstract sell a result substantially
       broader than what the body proves?

    ## Constraints
    - Approximately 200 words total (do NOT exceed 250).
    - Single argument, not a list — pick the most damaging line of attack
      and develop it.
    - Cite specific file:line locations or equation numbers when accusing.
    - Tone: dispassionate but uncompromising. Do NOT hedge. Do NOT acknowledge
      mitigations the paper might have made elsewhere. This is the rejection
      paragraph; the defense gets the next pass.
    - Do NOT reference prior review rounds, fix lists, or any context outside
      the current paper files.

    Output: just the rejection memo, nothing else.
```

Save the returned `threadId` for the trace; do NOT pass it to Thread 2.  Save the attack memo verbatim — both Thread 2 and the human-readable report use it.

### Step 3: Defense memo (Thread 2, fresh codex with attack + paper)

Invoke a second `mcp__codex__codex` call (still NOT `codex-reply` — Thread 2 is independent of Thread 1's codex history):

```
mcp__codex__codex:
  model: gpt-5.5
  config: {"model_reasoning_effort": "xhigh"}
  sandbox: read-only
  cwd: <paper directory>
  prompt: |
    You are defending a paper against a hostile reviewer's rejection memo.
    This is the defense pass of a kill-argument adversarial check. Fresh,
    zero-context defense; do not reference any prior reviews / fix lists.

    ## Paper files
    [list paths same as Step 2]

    ## The hostile reviewer's rejection memo (the "attack")
    > <attack memo verbatim from Thread 1>

    ## Your task
    The attack is one continuous argument, but it makes multiple distinct
    rejection points that you must defend separately. Decompose the attack
    into its atomic rejection points (3-7 of them), then for each point
    classify it:

    - already_fixed: the current paper text already mitigates this point
      (cite specific file:line evidence)
    - partially_fixed: paper has some response but not enough to refute
      the attack as written
    - still_unresolved: paper has no effective response

    For each rejection point, output:
    ### Point P_n: <short label>
    **Attack claim**: <the specific accusation, ~30 words>
    **Verdict**: already_fixed | partially_fixed | still_unresolved
    **Defense evidence**: <cite file:line, ~50 words>
    **Severity if unresolved**: critical | major | minor
    **If unresolved, recommended fix**: <one specific actionable sentence>

    After per-point analysis, output:

    ## Summary
    Total rejection points: N
    - already_fixed: X
    - partially_fixed: Y
    - still_unresolved: Z

    ## Net assessment
    <one short paragraph: does the defense as a whole survive the attack,
    or is the attack effective at the headline level? Be honest — if Y or Z
    > 0 and they hit the headline, say so.>

    ## Top action items (in priority order, max 3)
    1. ...
    2. ...
    3. ...

    ## Constraints
    - Do NOT consult any prior round reviews or fix lists. Defense must be
      made strictly from current paper files.
    - If the defense cannot refute a point, do NOT minimize — keep severity
      honest.
    - If a point reflects an author-chosen position (e.g., conscious title
      scope decision), classify as partially_fixed with a note that the
      position is intentional, but say whether this position is sustainable
      under the attack.
    - Be specific. No flattery, no hedging.
```

Save the returned `threadId`.

### Step 4: Write KILL_ARGUMENT.md and KILL_ARGUMENT.json

Compose the human-readable report `<paper-dir>/KILL_ARGUMENT.md`:

```markdown
# Kill Argument Report — <paper title>

**Date**: <YYYY-MM-DD>
**Reviewer model**: gpt-5.5 xhigh, fresh threads (no codex-reply)
**Attack thread**: <threadId 1>
**Defense thread**: <threadId 2>

## Net verdict

<paragraph from defense memo's "Net assessment">

## Attack memo (verbatim)

> <attack memo from Thread 1>

## Defense memo (per-point)

<copy verbatim from Thread 2>

## Top action items

<copy from Thread 2>

## Recommendation

If P_4 (or whatever still_unresolved critical) is research-level, record
it as a known open problem in the conclusion / limitations. If it is
writing-level, queue for next /auto-paper-improvement-loop round.
```

Compose the machine-readable `<paper-dir>/KILL_ARGUMENT.json`:

```json
{
  "skill": "kill-argument",
  "verdict": "PASS | WARN | FAIL",
  "summary": "<one-line summary>",
  "attack_thread_id": "<...>",
  "defense_thread_id": "<...>",
  "reviewer_model": "gpt-5.5",
  "reviewer_reasoning": "xhigh",
  "generated_at": "<UTC ISO-8601>",
  "details": {
    "attack_memo": "<verbatim>",
    "decomposed_points": [
      {
        "id": "P_1",
        "label": "<short label>",
        "attack_claim": "<...>",
        "verdict": "already_fixed | partially_fixed | still_unresolved",
        "defense_evidence": "<file:line citation>",
        "severity_if_unresolved": "critical | major | minor",
        "recommended_fix": "<...>"
      }
    ],
    "counts": {
      "already_fixed": <int>,
      "partially_fixed": <int>,
      "still_unresolved": <int>
    },
    "net_assessment": "<defense memo's net assessment>",
    "top_action_items": ["...", "...", "..."]
  }
}
```

Verdict mapping:
- `PASS`: 0 still_unresolved AND ≤1 partially_fixed at critical severity → defense fully survives.
- `WARN`: ≥1 partially_fixed at critical, OR ≥1 still_unresolved at major.
- `FAIL`: ≥1 still_unresolved at critical → headline attack effective; defense does not survive.

### Step 5: Print summary

To the user:

```
🗡  Kill Argument complete.

  Attack: <one-sentence summary of the rejection thrust>

  Defense breakdown:
    already_fixed:     X
    partially_fixed:   Y
    still_unresolved:  Z   ← critical: <names>

  Verdict: <PASS / WARN / FAIL>

  Top action items:
  1. ...
  2. ...
  3. ...

  Full report: <paper-dir>/KILL_ARGUMENT.md
```

## Output Contract

- `<paper-dir>/KILL_ARGUMENT.md` — human-readable report
- `<paper-dir>/KILL_ARGUMENT.json` — machine-readable ledger
- `.aris/traces/kill-argument/<date>_runNN/` — per-thread codex traces (Attack memo + Defense memo)
- Optional: applied fixes if user explicitly requests; default is **detect-only, do not auto-modify**.

## Key Rules

- **Fresh thread per call.**  Both Attack and Defense use `mcp__codex__codex`, never `codex-reply`.  Thread 1 and Thread 2 must not share codex context.
- **Zero prior context.**  Neither thread receives prior round reviews, fix lists, executor summaries, or improvement-loop logs.
- **Attack must commit.**  Single argument, ~200 words.  No "consider also" hedge.  The whole value is in forcing the reviewer to pick the most damaging line.
- **Defense must classify, not minimize.**  `still_unresolved` is honest if the paper has no effective response.  Don't downgrade to `partially_fixed` unless evidence is real.
- **Author-chosen positions** (e.g., deliberate title scope, deliberate omission of qualifier): mark `partially_fixed` with note that the position is intentional, AND say whether the position is sustainable under the attack.  Don't auto-grade as `already_fixed` just because it's intentional.
- **Detect-only by default.**  Do not edit paper .tex files.  The recommendation is informational; the human decides whether and how to act.

## When NOT to Use

- Empirical papers without theorems / scope claims — `/peer-review` is more useful.
- Very early drafts where the headline isn't stable yet — fix the headline first.
- Papers with ongoing experiments — wait until results stabilize, then run.
- Inside `/auto-paper-improvement-loop` Step 5.5 — that already runs this protocol on the final scheduled round.

## Review Tracing

After each `mcp__codex__codex` reviewer call, save the trace following `shared-references/review-tracing.md`.  Use `tools/save_trace.sh` or write files directly to `.aris/traces/kill-argument/<date>_run<NN>/`.  Both threads' raw responses should be preserved.

## Notes

This skill was extracted as a standalone primitive from `/auto-paper-improvement-loop` Step 5.5 in May 2026, after the protocol proved valuable in surfacing headline-vs-body scope gaps that score-based reviews missed.  The attack-then-defense pattern was kept exactly because of empirical evidence that asking one model to "write the rejection memo" produces qualitatively different feedback than asking it to "review and grade" — the former forces commitment, the latter encourages hedging.
