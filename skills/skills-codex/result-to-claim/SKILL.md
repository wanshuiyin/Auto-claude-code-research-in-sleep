---
name: result-to-claim
description: "Judge what completed experiment results actually support, what remains unsupported, and what evidence is missing. Use after main experiments finish and before locking paper claims. Do not use for generic result summarization or ablation design; use `analyze-results` or `ablation-planner` then."
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent
---

# Result-to-Claim Gate

Experiments produce numbers; this gate decides what those numbers *mean*. Collect results from available sources, get an objective judgment, then route based on the verdict.

## Context: $ARGUMENTS

## Routing Boundaries

- Use this skill after main experiments complete and the task is to decide what claims are defensible.
- Use `analyze-results` for descriptive result analysis, tables, and comparisons without a claims gate.
- Use `ablation-planner` after this gate when the main claims are supported and the next need is reviewer-facing ablation design.
- Use `research-review` for broader critique that is not centered on claims support.

## Constants

- **REVIEWER_MODEL = `gpt-5.4`** - Used via a secondary Codex agent for objective claim assessment.

## When to Use

- After a set of experiments completes (main results, not just sanity checks)
- Before committing to claims in a paper or review response
- When results are ambiguous and you need an objective second opinion

## Workflow

### Step 1: Collect Results

Gather experiment data from whatever sources are available in the project:

1. **W&B** (preferred): `wandb.Api().run("<entity>/<project>/<run_id>").history()` - metrics, training curves, comparisons
2. **`EXPERIMENT_LOG.md`** - full results table with baselines and verdicts
3. **`EXPERIMENT_TRACKER.md`** - check which experiments are done vs still running
4. **Log files** - `ssh server "tail -100 /path/to/training.log"` if no other source
5. **`docs/research_contract.md`** or project notes - intended claims and experiment design

Assemble the key information:

- What experiments were run (method, dataset, config)
- Main metrics and baseline comparisons (deltas)
- The intended claim these experiments were designed to test
- Any known confounds or caveats

### Step 2: Secondary Codex Judgment

Send the collected results to a secondary Codex agent for objective evaluation:

```text
spawn_agent:
  model: REVIEWER_MODEL
  reasoning_effort: xhigh
  message: |
    RESULT-TO-CLAIM EVALUATION

    I need you to judge whether experimental results support the intended claim.

    Intended claim: [the claim these experiments test]

    Experiments run:
    [list experiments with method, dataset, metrics]

    Results:
    [paste key numbers, comparison deltas, significance]

    Baselines:
    [baseline numbers and sources - reproduced or from paper]

    Known caveats:
    [any confounding factors, limited datasets, missing comparisons]

    Please evaluate:
    1. claim_supported: yes | partial | no
    2. what_results_support: what the data actually shows
    3. what_results_dont_support: where the data falls short of the claim
    4. missing_evidence: specific evidence gaps
    5. suggested_claim_revision: if the claim should be strengthened, weakened, or reframed
    6. next_experiments_needed: specific experiments to fill gaps (if any)
    7. confidence: high | medium | low

    Be honest. Do not inflate claims beyond what the data supports.
    A single positive result on one dataset does not support a general claim.
```

If delegation is unavailable, run the same evaluation locally and mark the verdict `[pending external review]` instead of blocking the pipeline.

### Step 3: Parse and Normalize

Extract structured fields from the response:

```markdown
- claim_supported: yes | partial | no
- what_results_support: "..."
- what_results_dont_support: "..."
- missing_evidence: "..."
- suggested_claim_revision: "..."
- next_experiments_needed: "..."
- confidence: high | medium | low
```

### Step 4: Route Based on Verdict

#### `no` - Claim not supported

1. Record a postmortem in `findings.md`:
   - What was tested, what failed, and hypotheses for why
   - Constraints for future attempts (what **not** to try again)
2. Update the project pipeline status in project notes
3. Decide whether to pivot to the next idea from `IDEA_CANDIDATES.md` or try an alternative approach

#### `partial` - Claim partially supported

1. Update the working claim to reflect what **is** supported
2. Record the gap in `findings.md`
3. Design and run supplementary experiments to fill evidence gaps
4. Re-run `/result-to-claim` after supplementary experiments complete
5. If the same claim gets multiple `partial` verdicts, record the analysis in `findings.md` and consider narrowing the claim scope or switching ideas

#### `yes` - Claim supported

1. Record the confirmed claim in project notes
2. If ablation studies are incomplete, trigger `/ablation-planner`
3. If all evidence is in, move to paper writing

## Rules

- **The secondary Codex agent is the judge, not the local executor.** The local executor collects evidence and routes; the reviewer agent evaluates. This prevents post-hoc rationalization.
- Do not inflate claims beyond what the data supports. If the verdict says `partial`, do not round up to `yes`.
- A single positive result on one dataset does not support a general claim. Be honest about scope.
- If `confidence` is low, treat the judgment as inconclusive and add experiments rather than committing to a claim.
- If reviewer delegation is unavailable, make the best local judgment you can and mark it `[pending external review]`.
- Always record the verdict and reasoning in `findings.md`, regardless of outcome.
