---
name: result-to-claim
description: Use when experiments complete to judge what claims the results support, what they don't, and what evidence is still missing. Codex MCP evaluates results against intended claims and routes to next action (pivot, supplement, or confirm). Use after experiments finish — before writing the paper or running ablations.
argument-hint: [experiment-description-or-wandb-run]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, mcp__codex__codex, mcp__codex__codex-reply
---

# Result-to-Claim Gate

> 🔒 **Do not wrap this skill in `/loop`, `/schedule`, or `CronCreate`.** It is
> verdict-bearing — it judges whether results support a claim. Re-running that
> verdict on a wall-clock timer adds no new signal (the verdict changes only
> when the *results* change, not when the clock ticks). What you actually want
> to schedule is the *external wait that precedes it* — experiments done → then
> run this gate **once**. See
> [`shared-references/external-cadence.md`](../shared-references/external-cadence.md).

Experiments produce numbers; this gate decides what those numbers *mean*. Collect results from available sources, get a Codex judgment, then auto-route based on the verdict.

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

### Step 1.5: Deterministic evidence pre-check (before spending a Codex call)

For every claim that cites a specific number + a source file, verify the evidence
*exists* mechanically — no model call — to catch **hallucinated evidence** before
the jury runs (see [`shared-references/evidence-precheck.md`](../shared-references/evidence-precheck.md)).

**1. Build the claims list.** From the cited numbers and their result files, write
`[{"id", "value", "source"}, ...]` to `.aris/claims.json` (`source` is the result
file/glob relative to the project root; `value` is the cited number or string).

**2. Run the pre-check — this is a real step, not a suggestion.** Execute the block
below (resolver per integration-contract §2, **Policy B**: warn-and-skip if the helper
is unresolved — never block the audit):

```bash
# Policy B = warn-and-skip: nothing here may abort the audit. cd is non-fatal, the
# helper run is explicitly non-blocking, no pipefail-fragile pipe.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" 2>/dev/null || true
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
EVIDENCE_CHECK=".aris/tools/evidence_check.py"
[ -f "$EVIDENCE_CHECK" ] || EVIDENCE_CHECK="tools/evidence_check.py"
[ -f "$EVIDENCE_CHECK" ] || { [ -n "${ARIS_REPO:-}" ] && EVIDENCE_CHECK="$ARIS_REPO/tools/evidence_check.py"; }
[ -f "$EVIDENCE_CHECK" ] || EVIDENCE_CHECK=""

mkdir -p .aris
if [ -n "$EVIDENCE_CHECK" ]; then
    # NB: evidence_check exits 1 when it FINDS hallucinated evidence (value_not_found /
    # path_missing) — that is the useful signal, NOT a failure. So judge success by
    # whether valid JSON was produced, never by exit code. `|| true` keeps set -e calm.
    python3 "$EVIDENCE_CHECK" . --batch .aris/claims.json > .aris/evidence_precheck.json 2>.aris/evidence_precheck.err || true
    if [ -s .aris/evidence_precheck.json ] && python3 -c "import json,sys;json.load(open('.aris/evidence_precheck.json'))" 2>/dev/null; then
        cat .aris/evidence_precheck.json
    else
        echo "WARN: evidence_check produced no valid output (see .aris/evidence_precheck.err);" >&2
        echo "      pre-check skipped (Policy B); the Codex jury still runs." >&2
    fi
else
    echo "WARN: evidence_check.py not resolved at .aris/tools/, tools/, or \$ARIS_REPO/tools/." >&2
    echo "      Pre-check skipped (Policy B); the Codex jury still runs. Fix: rerun" >&2
    echo "      bash tools/install_aris.sh, export ARIS_REPO, or copy the helper to tools/." >&2
fi
```

The output is `{"results": [{id, value, source, status, ...}], "summary": {status: n}}`
with `status ∈ {verified, value_not_found, path_missing, unparseable}`.

**3. Act on the statuses.** Any claim returned `value_not_found` or `path_missing` is
**hallucinated evidence** — mark it `claim_supported: no` with
`integrity_status: evidence_not_found` immediately; do NOT spend a Codex call defending a
number that isn't in the data. `unparseable` claims (no usable value/source) just go to
the jury normally.

**4. Carry the per-claim status into Step 2.** Feed a small
`evidence pre-check: <id> → verified | value_not_found | path_missing | unparseable`
table (from `.aris/evidence_precheck.json`) into the Step-2 Codex prompt so the jury knows
which claims have real evidence to read. If the pre-check was skipped (helper unresolved),
say so in that slot rather than omitting it.

`verified` here means only that the cited evidence **exists** — whether it
**supports** the claim is still the Codex jury's call in Step 2 (a deterministic
gate DRIVES, it does not ACQUIT).

### Step 2: Codex Judgment

Send the collected results to Codex for objective evaluation:

```
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    RESULT-TO-CLAIM EVALUATION

    I need you to judge whether experimental results support the intended claim.

    Intended claim: [the claim these experiments test]

    Experiments run:
    [list experiments with method, dataset, metrics]

    Results:
    [paste key numbers, comparison deltas, significance]

    Evidence pre-check (deterministic, from Step 1.5):
    [per-claim: <id> → verified | value_not_found | path_missing.
     A value_not_found/path_missing means the cited number is NOT in its result
     file — treat that claim as having no evidence; do not defend it. `verified`
     means the number exists in the file — YOU still judge whether it supports
     the claim.]

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

Extract structured fields from Codex response:

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
2. Update CLAUDE.md Pipeline Status
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

If `research-wiki/` exists, resolve `$WIKI_SCRIPT` per the canonical
chain documented in
[`shared-references/wiki-helper-resolution.md`](../shared-references/wiki-helper-resolution.md)
(Variant B — warn-and-skip for caller skills). The verdict / idea-outcome
page edits below run on raw markdown and don't need the helper, but edges,
query-pack rebuild, and the log line do. **This skill never edits a claim's
`status` field and never creates a claim node** — claims are born (and their
proof `status` set) by `/proof-checker`; here we only attach experiment edges.

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null)}"
WIKI_SCRIPT=".aris/tools/research_wiki.py"
[ -f "$WIKI_SCRIPT" ] || WIKI_SCRIPT="tools/research_wiki.py"
[ -f "$WIKI_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"; }
[ -f "$WIKI_SCRIPT" ] || {
  echo "WARN: research_wiki.py not found; verdict will be reported but wiki edges/query-pack/log will be skipped. Fix: bash tools/install_aris.sh, export ARIS_REPO, or cp <ARIS-repo>/tools/research_wiki.py tools/." >&2
  WIKI_SCRIPT=""
}
```

```
if research-wiki/ exists:
    # 1. Create/refresh the experiment node FIRST (verdict OWNER → --update-on-exist so
    #    a re-judge overwrites the stale verdict). The supports/invalidates edges in #2
    #    point FROM exp:<id>, and add_edge does NOT verify node existence — so GATE those
    #    edges on the experiment node having been born (EXP_NODE_OK), else they'd dangle
    #    (the exact bug this closes). On failure: warn, skip the wiki edges, still report.
    EXP_NODE_OK=0
    if [ -n "$WIKI_SCRIPT" ]; then
      if python3 "$WIKI_SCRIPT" add_experiment research-wiki/ \
           --slug "<exp_id>" --idea "idea:<active_idea>" \
           --verdict "<yes|partial|no>" --confidence "<high|medium|low>" \
           --date "<date>" --hardware "<hw>" --duration "<dur>" \
           --metrics "<key metrics>" --reasoning "<one-line why this verdict>" \
           --provenance "<EXPERIMENT_AUDIT.md / run dir>" --update-on-exist; then
        EXP_NODE_OK=1   # page written + idea--tested_by-->exp edge + index/query_pack rebuilt
      else
        echo "WARN: add_experiment failed for <exp_id>; skipping wiki edges (verdict still reported)." >&2
      fi
    fi

    # 2. Record empirical support as EDGES ONLY — and ONLY when the exp node was born
    #    ([ "$EXP_NODE_OK" = 1 ]), so no edge dangles off a missing node. Never edit the
    #    claim page's `status`: that is the PROOF axis (verified / refuted / unproven /
    #    sound-modulo-imports / drafted / retracted), owned by /proof-checker (the claim
    #    birth point) — "supported"/"invalidated" are NOT valid claim statuses. The claim
    #    target should ALREADY be born by /proof-checker; add_edge does not verify it.
    for each claim resolved by this verdict (only if [ "$EXP_NODE_OK" = 1 ]):
        if verdict == "yes":
            python3 "$WIKI_SCRIPT" add_edge research-wiki/ --from "exp:<id>" --to "claim:<cid>" --type supports --evidence "<metric>"
        elif verdict == "partial":
            python3 "$WIKI_SCRIPT" add_edge research-wiki/ --from "exp:<id>" --to "claim:<cid>" --type supports --evidence "partial: <metric>"
        else:
            python3 "$WIKI_SCRIPT" add_edge research-wiki/ --from "exp:<id>" --to "claim:<cid>" --type invalidates --evidence "<why>"

    # 3. Update idea outcome (raw markdown, helper-free)
    Update research-wiki/ideas/<idea_id>.md:
      - outcome: positive | mixed | negative
      - If negative: fill "Failure / Risk Notes" and "Lessons Learned"
      - If positive: fill "Actual Outcome" and "Reusable Components"

    # 4. Rebuild + log (only if $WIKI_SCRIPT resolved)
    [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" rebuild_query_pack research-wiki/
    [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" log research-wiki/ "result-to-claim: exp:<id> verdict=<verdict> for idea:<idea_id>"

    # 5. Re-ideation suggestion
    Count failed/partial ideas since last /idea-creator run.
    If >= 3: print "💡 3+ ideas tested since last ideation. Consider re-running /idea-creator — the wiki now knows what doesn't work."
```

## Rules

- **Codex is the judge, not CC.** CC collects evidence and routes; Codex evaluates. This prevents post-hoc rationalization.
- Do not inflate claims beyond what the data supports. If Codex says "partial", do not round up to "yes".
- A single positive result on one dataset does not support a general claim. Be honest about scope.
- If `confidence` is low, treat the judgment as inconclusive and add experiments rather than committing to a claim.
- If Codex MCP is unavailable (call fails), CC makes its own judgment and marks it `[pending Codex review]` — do not block the pipeline.
- Always record the verdict and reasoning in findings.md, regardless of outcome.

## Review Tracing

After each `mcp__codex__codex` or `mcp__codex__codex-reply` reviewer call, save the trace following `shared-references/review-tracing.md` (Policy C — forensic; never silently skip). Use `save_trace.sh` (resolved per the chain in `shared-references/integration-contract.md` §2) or write files directly to `.aris/traces/<skill>/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).
