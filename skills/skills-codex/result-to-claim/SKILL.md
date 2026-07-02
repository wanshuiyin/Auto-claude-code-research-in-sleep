---
name: result-to-claim
description: Use when experiments complete to judge what claims the results support, what they don't, and what evidence is still missing. A secondary Codex agent evaluates results against intended claims and routes to next action (pivot, supplement, or confirm). Use after experiments finish — before writing the paper or running ablations.
argument-hint: [experiment-description-or-wandb-run]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit
---

# Result-to-Claim Gate

Experiments produce numbers; this gate decides what those numbers *mean*. Collect results from available sources, get a secondary Codex judgment, then auto-route based on the verdict.

## Context: $ARGUMENTS

## When to Use

- After a set of experiments completes (main results, not just sanity checks)
- Before committing to claims in a paper or review response
- When results are ambiguous and you need an objective second opinion

## Workflow

### Step 1: Collect Results

Gather experiment data from whatever sources are available in the project:

1. **W&B** (preferred): `wandb.Api().run("<entity>/<project>/<run_id>").history()` — metrics, training curves, comparisons
2. **EXPERIMENT_LOG.md**: full results table with baselines and verdicts
3. **EXPERIMENT_TRACKER.md**: check which experiments are DONE vs still running
4. **Log files**: `ssh server "tail -100 /path/to/training.log"` if no other source
5. **`idea-stage/docs/research_contract.md`** (legacy fallback: `docs/research_contract.md`): intended claims and experiment design

Assemble the key information:
- What experiments were run (method, dataset, config)
- Main metrics and baseline comparisons (deltas)
- The intended claim these experiments were designed to test
- Any known confounds or caveats

### Step 2: Codex Judgment

Send the collected results to a secondary Codex agent for objective evaluation:

```text
spawn_agent:
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
    [baseline numbers and sources — reproduced or from paper]

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

### Step 3: Parse and Normalize

Extract structured fields from the secondary Codex response:

```markdown
- claim_supported: yes | partial | no
- what_results_support: "..."
- what_results_dont_support: "..."
- missing_evidence: "..."
- suggested_claim_revision: "..."
- next_experiments_needed: "..."
- confidence: high | medium | low
```

### Step 3.5: Check Experiment Integrity (if audit exists)

**Skip this step if `EXPERIMENT_AUDIT.json` does not exist.**

```
if EXPERIMENT_AUDIT.json exists:
    read integrity_status from file
    attach to verdict output:
        integrity_status: pass | warn | fail

    if integrity_status == "fail":
        append to verdict: "[INTEGRITY CONCERN] — audit found issues, see EXPERIMENT_AUDIT.md"
        downgrade confidence to "low" regardless of Codex judgment

    if integrity_status == "warn":
        append to verdict: "[INTEGRITY: WARN] — audit flagged potential issues"
else:
    integrity_status = "unavailable"
    verdict is labeled "provisional — no integrity audit run"
    (this does NOT block anything — pipeline continues normally)
```

See `shared-references/experiment-integrity.md` for the full integrity protocol.

### Step 4: Route Based on Verdict

#### `no` — Claim not supported

1. Record postmortem in findings.md (Research Findings section):
   - What was tested, what failed, hypotheses for why
   - Constraints for future attempts (what NOT to try again)
2. Update the project pipeline status in `AGENTS.md` or project notes
3. Decide whether to pivot to next idea from IDEA_CANDIDATES.md or try an alternative approach

#### `partial` — Claim partially supported

1. Update the working claim to reflect what IS supported
2. Record the gap in findings.md
3. Design and run supplementary experiments to fill evidence gaps
4. Re-run result-to-claim after supplementary experiments complete
5. **Multiple rounds of `partial` on the same claim** → record analysis in findings.md, consider whether to narrow the claim scope or switch ideas

#### `yes` — Claim supported

1. Record confirmed claim in project notes
2. If ablation studies are incomplete → trigger `/ablation-planner`
3. If all evidence is in → ready for paper writing

### Step 5: Update Research Wiki (if active)

**Skip this step entirely if `research-wiki/` does not exist.**

```
if research-wiki/ exists:
    # Resolve the helper (Codex chain). If unavailable, skip wiki writes; still report verdict.
    ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null)}"
    WIKI_SCRIPT=""
    [ -n "$ARIS_REPO" ] && [ -f "$ARIS_REPO/tools/research_wiki.py" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"
    [ -z "$WIKI_SCRIPT" ] && [ -f tools/research_wiki.py ] && WIKI_SCRIPT="tools/research_wiki.py"
    [ -z "$WIKI_SCRIPT" ] && [ -f ~/.codex/skills/research-wiki/research_wiki.py ] && WIKI_SCRIPT="$HOME/.codex/skills/research-wiki/research_wiki.py"
    [ -n "$WIKI_SCRIPT" ] || echo "WARN: research_wiki.py unreachable; skipping wiki writes (verdict still reported)." >&2

    # 1. Create/refresh the experiment node FIRST (verdict OWNER → --update-on-exist so a
    #    re-judge overwrites the stale verdict). The supports/invalidates edges in #2 point
    #    FROM exp:<id> and add_edge does NOT verify node existence, so only add them if the
    #    experiment node was born (EXP_NODE_OK); otherwise skip the wiki edges.
    EXP_NODE_OK=0
    [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" add_experiment research-wiki/ \
         --slug "<exp_id>" --idea "idea:<active_idea>" \
         --verdict "<yes|partial|no>" --confidence "<high|medium|low>" \
         --date "<date>" --hardware "<hw>" --duration "<dur>" \
         --metrics "<key metrics>" --reasoning "<one-line why this verdict>" \
         --provenance "<EXPERIMENT_AUDIT.md / run dir>" --update-on-exist && EXP_NODE_OK=1

    # 2. Record empirical support as EDGES ONLY, and ONLY if EXP_NODE_OK. NEVER edit a
    #    claim page's `status`: that is the PROOF axis (verified / refuted / unproven /
    #    sound-modulo-imports / drafted / retracted), owned by /proof-checker (the claim
    #    birth point) — the ARIS helper REJECTS "supported"/"partial"/"invalidated".
    if [ "$EXP_NODE_OK" = 1 ]:
        for each claim resolved by this verdict:
            if verdict == "yes":
                python3 "$WIKI_SCRIPT" add_edge research-wiki/ --from "exp:<id>" --to "claim:<cid>" --type supports --evidence "<metric>"
            elif verdict == "partial":
                python3 "$WIKI_SCRIPT" add_edge research-wiki/ --from "exp:<id>" --to "claim:<cid>" --type supports --evidence "partial: <metric>"
            else:
                python3 "$WIKI_SCRIPT" add_edge research-wiki/ --from "exp:<id>" --to "claim:<cid>" --type invalidates --evidence "<why>"

    # 3. Update idea outcome (raw markdown, helper-free — preserves the rich idea body)
    Update research-wiki/ideas/<idea_id>.md:
      - outcome: positive | mixed | negative
      - If negative: fill "Failure / Risk Notes" and "Lessons Learned"
      - If positive: fill "Actual Outcome" and "Reusable Components"

    # 4. Rebuild + log (reflect the new edges; only if WIKI_SCRIPT resolved)
    [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" rebuild_query_pack research-wiki/
    [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" log research-wiki/ "result-to-claim: exp:<id> verdict=<verdict> for idea:<idea_id>"

    # 5. Re-ideation suggestion
    Count failed/partial ideas since last /idea-creator run.
    If >= 3: print "💡 3+ ideas tested since last ideation. Consider re-running /idea-creator — the wiki now knows what doesn't work."
```

## Rules

- **The secondary Codex agent is the judge, not the local executor.** The local executor collects evidence and routes; the reviewer agent evaluates. This prevents post-hoc rationalization.
- Do not inflate claims beyond what the data supports. If Codex says "partial", do not round up to "yes".
- A single positive result on one dataset does not support a general claim. Be honest about scope.
- If `confidence` is low, treat the judgment as inconclusive and add experiments rather than committing to a claim.
- If reviewer delegation is unavailable, make the best local judgment you can and mark it `[pending external review]` - do not block the pipeline.
- Always record the verdict and reasoning in findings.md, regardless of outcome.

## Review Tracing

After the secondary Codex judgment, save a trace following `../shared-references/review-tracing.md`. Write files directly to `.aris/traces/result-to-claim/<date>_run<NN>/` and include the prompt, raw reviewer response, parsed verdict, routing action, and whether the result is `[pending external review]`. Respect the `--- trace:` parameter when present (default: `full`).
