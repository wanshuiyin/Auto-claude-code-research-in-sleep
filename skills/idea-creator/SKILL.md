---
name: idea-creator
description: Generate and rank research ideas given a broad direction. Use when user says "找idea", "brainstorm ideas", "generate research ideas", "what can we work on", or wants to explore a research area for publishable directions.
argument-hint: [research-direction]
allowed-tools: Bash(*), Read, Write, Grep, Glob, WebSearch, WebFetch, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply, mcp__manual_review__review, mcp__manual_review__review_reply
---

# Research Idea Creator

Generate publishable research ideas for: $ARGUMENTS

## Overview

Given a broad research direction from the user, systematically generate, validate, and rank concrete research ideas. Standalone, Phase 1's landscape survey is **inline** (WebSearch — it does not invoke `/research-lit`); Phases 4-5 invoke `/novelty-check`, `/run-experiment`, and `/monitor-experiment` for validation and pilots. For the full sub-skill pipeline (`/research-lit` → idea generation → `/novelty-check` → `/research-review`), run `/idea-discovery` (Workflow 1), which orchestrates this skill.

## Constants

- **PILOT_MAX_HOURS = 2** — Skip any pilot estimated to take > 2 hours per GPU. Flag as "needs manual pilot".
- **PILOT_TIMEOUT_HOURS = 3** — Hard timeout: kill pilots exceeding 3 hours. Collect partial results if available.
- **MAX_PILOT_IDEAS = 3** — Pilot at most 3 ideas in parallel. Additional ideas are validated on paper only.
- **MAX_TOTAL_GPU_HOURS = 8** — Total GPU budget for all pilots combined.
- **REVIEWER_MODEL = `gpt-5.5`** — Default model for the Codex backend. Must be an OpenAI model (e.g., `gpt-5.5`, `o3`, `gpt-4o`). Manual backend uses whatever model the user chooses, **but it must be a non-Claude model** — the executor is Claude, so pasting into any Claude product makes Claude judge Claude and voids the cross-model invariant (see `shared-references/reviewer-routing.md`).
- **REVIEWER_BACKEND = `codex`** — Default: Codex MCP (xhigh). Override with `— reviewer: oracle-pro` for Oracle MCP, or `— reviewer: manual` for Manual Review MCP. If manual-review MCP is unavailable, stop and print the install command; do not fall back to Codex. See `shared-references/reviewer-routing.md`.
- **OUTPUT_DIR = `idea-stage/`** — All idea-stage outputs go here. Create the directory if it doesn't exist.

> 💡 Override via argument, e.g., `/idea-creator "topic" — pilot budget: 4h per idea, 20h total`.

## Reviewer Calling Convention

When calling the reviewer for idea evaluation, branch on REVIEWER_BACKEND:

**If REVIEWER_BACKEND = `codex`:**
  Use `mcp__codex__codex` for new review threads.
  Use `mcp__codex__codex-reply` for follow-up rounds (reuse threadId).

**If REVIEWER_BACKEND = `manual`:**
  Use `mcp__manual_review__review` for new review threads with:
    prompt: [exact same prompt that would go to Codex]
    config: {"model_reasoning_effort": "xhigh"}
  Save the returned `threadId`.
  Use `mcp__manual_review__review_reply` for follow-up rounds with:
    threadId: [saved manual-review threadId]
    prompt: [follow-up prompt]
    config: {"model_reasoning_effort": "xhigh"}

Content fidelity: the manual reviewer should see the same substantive bundle
content Codex would read. If the manual UI supports file upload / attachment,
reuse the same bundle file; otherwise paste the bundle contents inline because
remote web UIs cannot read your local filesystem paths. Review tracing applies
equally to both backends.

## Workflow

### Phase 0: Load Research Wiki (if active)

**Skip this phase entirely if `research-wiki/` does not exist.**

If `research-wiki/` exists, resolve the canonical helper using the
shared resolution chain (see `../research-wiki/SKILL.md` for the
contract):

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null)}"
WIKI_SCRIPT=".aris/tools/research_wiki.py"
[ -f "$WIKI_SCRIPT" ] || WIKI_SCRIPT="tools/research_wiki.py"
[ -f "$WIKI_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"; }
[ -f "$WIKI_SCRIPT" ] || {
  echo "WARN: research_wiki.py not found at .aris/tools/, tools/, or \$ARIS_REPO/tools/." >&2
  echo "      The idea-creation primary output (idea ranking) will still be produced." >&2
  echo "      Wiki integration (load query_pack, write idea pages, add edges, rebuild query_pack) will be skipped." >&2
  echo "      Fix: rerun 'bash tools/install_aris.sh', export ARIS_REPO, or 'cp <ARIS-repo>/tools/research_wiki.py tools/'." >&2
  WIKI_SCRIPT=""
}
```

```
if research-wiki/query_pack.md exists AND is less than 7 days old:
    Read query_pack.md and use it as initial landscape context:
    - Treat listed gaps as priority search seeds
    - Treat failed ideas as a banlist (do NOT regenerate similar ideas)
    - Treat top papers as known prior work (do not re-search them)
    Still run Phase 1 below for papers from the last 3-6 months (wiki may be stale)
else if research-wiki/ exists but query_pack.md is stale or missing:
    if [ -n "$WIKI_SCRIPT" ]: python3 "$WIKI_SCRIPT" rebuild_query_pack research-wiki/
    Then read query_pack.md as above
```

### Phase 1: Landscape Survey (5-10 min)

Map the research area to understand what exists and where the gaps are.

1. **Scan local paper library first**: Check `papers/` and `literature/` in the project directory for existing PDFs. Read first 3 pages of relevant papers to build a baseline understanding before searching online. This avoids re-discovering what the user already knows.

2. **Search recent literature** using WebSearch:
   - Top venues in the last 2 years (NeurIPS, ICML, ICLR, ACL, EMNLP, etc.)
   - Recent arXiv preprints (last 6 months)
   - Use 5+ different query formulations
   - Read abstracts and introductions of the top 10-15 papers

2. **Build a landscape map**:
   - Group papers by sub-direction / approach
   - Identify what has been tried and what hasn't
   - Note recurring limitations mentioned in "Future Work" sections
   - Flag any open problems explicitly stated by multiple papers

3. **Identify structural gaps**:
   - Methods that work in domain A but haven't been tried in domain B
   - Contradictory findings between papers (opportunity for resolution)
   - Assumptions that everyone makes but nobody has tested
   - Scaling regimes that haven't been explored
   - Diagnostic questions that nobody has asked

### Phase 1.5: Parallel lens fan-out (Tier-aware) — breadth, not verdict

Idea generation benefits from **breadth**: more independent analytic angles
surface more candidate ideas. This skill fans out *candidate generation*
across analytic **lenses**, then funnels every candidate through the single
Phase-4 cross-model jury. Fan-out widens the jury's input; it never makes the
accept/reject decision. This follows
[`shared-references/fan-out-pattern.md`](../shared-references/fan-out-pattern.md);
the verdict stays cross-model per
[`shared-references/acceptance-gate.md`](../shared-references/acceptance-gate.md)
(idea novelty/quality is a Type-B verdict — same-family generation is fine,
same-family *acquittal* is not).

**Lenses** (the structural-gap angles from Phase 1, step 3):
`method-transfer` (works in domain A, untried in B) · `contradiction`
(conflicting findings to resolve) · `untested-assumption` (everyone assumes,
nobody tested) · `scaling-regime` (unexplored regime) · `diagnostic`
(question nobody asked). This set is a floor, not a ceiling — add a
domain-specific lens when the direction warrants.

**Tier-portable dispatch** (the Phase-4 jury downstream is identical on every tier):
- **Tier 1** (Workflow available): spawn one **Claude subagent per lens**;
  each runs the Phase-1 survey *through its lens* and the Phase-2 generation
  prompt *restricted to that lens*, returning candidates as structured output.
- **Tier 2** (Agent tool, no Workflow): spawn the same per-lens subagents via
  the Agent tool.
- **Tier 3** (no spawning): enumerate the lenses sequentially in one pass —
  the original single-thread behavior, made explicit. No capability assumed.

> **Why the lens shards are Claude, not Codex.** Generation is candidate
> production, not a verdict, so same-family is safe — and Codex MCP is
> **serial** (concurrent codex calls hang), so spending its scarce capacity
> on parallel generation is both unsafe-to-parallelize and wasteful. Reserve
> Codex for the one Phase-4 jury call. On Tier 1/2 the lens subagents are the
> generators; the single Phase-2 codex brainstorm below still runs once as an
> optional cross-model *seed* (a generator, not a judge), and its ideas join
> the merged pool.

**Per-shard output** (the generation-fan-out schema from
[`fan-out-pattern.md`](../shared-references/fan-out-pattern.md) — `shard_id` +
`candidates[]` + per-item `dedup_key`):
```json
{"shard_id": "<lens id>", "candidates": [{"summary": "...", "hypothesis": "...",
  "mve": "...", "contribution_type": "...", "risk": "...", "effort": "...",
  "dedup_key": "<hypothesis slug — the mechanical-dedup identity>"}]}
```

**Merge + mechanical dedup**: union all lenses' ideas; cluster near-identical
ideas by hypothesis (mechanical similarity only — **never** drop one for being
"weak"; weakness is a Phase-4 verdict, not a merge step). The deduped union is
the candidate set that enters Phase 3.

### Phase 2: Idea Generation (brainstorm with external LLM)

Use the selected reviewer backend (see Reviewer Calling Convention) for divergent thinking.

For the `codex` backend, **do not inline the full landscape + gaps prompt**
once it stops being tiny. Write the full brainstorming request to
`idea-stage/codex_brainstorm_bundle.md`, then keep the MCP prompt short:

```
mcp__codex__codex:
  model: REVIEWER_MODEL
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    Read the idea-generation bundle at <absolute path to
    idea-stage/codex_brainstorm_bundle.md> and follow all instructions in it.
```

*For `manual` backend:* use `mcp__manual_review__review` with the same bundle
contents. If the manual-review UI supports attachments, attach
`idea-stage/codex_brainstorm_bundle.md`; otherwise paste the bundle contents
inline. Save the returned `threadId` for Phase 4 follow-up.

Bundle contents:

```
    You are a senior ML researcher brainstorming research ideas.

    Research direction: [user's direction]

    Here is the current landscape:
    [write the Phase-1 landscape map into this bundle file]

    Key gaps identified:
    [write the Phase-1 gap summary into this bundle file]

    Generate 8-12 concrete research ideas. For each idea:
    1. One-sentence summary
    2. Core hypothesis (what you expect to find and why)
    3. Minimum viable experiment (what's the cheapest way to test this?)
    4. Expected contribution type: empirical finding / new method / theoretical result / diagnostic
    5. Risk level: LOW (likely works) / MEDIUM (50-50) / HIGH (speculative)
    6. Estimated effort: days / weeks / months

    Prioritize ideas that are:
    - Testable with moderate compute (8x RTX 3090 or less)
    - Likely to produce a clear positive OR negative result (both are publishable)
    - Not "apply X to Y" unless the application reveals genuinely surprising insights
    - Differentiated from the 10-15 papers above

    Be creative but grounded. A great idea is one where the answer matters regardless of which way it goes.
```

Save the threadId for follow-up.

### Phase 3: Mechanical consolidation + objective feasibility gate

> **This phase does NOT judge idea quality, novelty, or impact.** Those are
> Type-B verdicts reserved for the Phase-4 cross-model jury (see
> [`shared-references/acceptance-gate.md`](../shared-references/acceptance-gate.md)).
> Eliminating ideas here on a same-family novelty or impact call would
> pre-filter the jury's input with same-family quality judgment — exactly
> what [`fan-out-pattern.md`](../shared-references/fan-out-pattern.md) forbids.
> Phase 3 only (a) finishes the mechanical dedup from the fan-out merge and
> (b) drops ideas that are **objectively** out of budget. Everything else
> passes through **annotated, not eliminated** — the jury decides.

1. **Objective feasibility gate (Type-A — safe same-model)**: drop an idea
   ONLY on a mechanical, budget-based fact:
   - estimated compute > 1 week of available GPU time, OR
   - requires a dataset that is provably unavailable.
   These are objective resource facts. Do **not** drop on "implementation
   looks complex" — annotate complexity as `effort_note` instead.

2. **Novelty signal — ANNOTATE, do not eliminate**: for each surviving idea,
   do 2-3 targeted searches and attach a `prior_work` note (what looks
   related, with links). This is *input for the jury*, not a filter. The
   authoritative novelty verdict is Phase 4's `/novelty-check` (multi-source +
   cross-model). Do **not** drop an idea here because it "might already be
   done."

3. **Impact signal — ANNOTATE, do not eliminate**: attach a one-line
   `so_what` note (why the result would matter either way). Do **not** drop on
   a same-family "a reviewer wouldn't care" call — "would a reviewer care?" is
   *precisely* the question the Phase-4 cross-model devil's-advocate asks.
   Forward the note; let the jury rule.

Every feasible, non-duplicate idea — carrying its `prior_work`, `so_what`, and
`effort_note` annotations — proceeds to Phase 4. Typically only the
budget-infeasible are dropped; the cross-model jury, not the executor, does
the quality narrowing.

### Phase 4: Deep Validation (the cross-model jury)

**This is the jury.** It receives the FULL annotated candidate set from
Phase 3 (Phase 3 no longer pre-narrows on quality), and the **cross-model
reviewer — not the executor — does the quality/novelty narrowing.** Run the
steps in this order so the cheap cross-model triage gates the expensive
per-idea novelty search:

1. **Cross-model triage (devil's advocate) — ranks ALL candidates first.**
   Use the selected reviewer backend (see Reviewer Calling Convention). For
   `codex`, use `mcp__codex__codex-reply` (same thread). For `manual`, use
   `mcp__manual_review__review_reply` with the saved threadId. For the
   `codex` backend, write the full annotated candidate set to
   `idea-stage/codex_triage_bundle.md` and send only a path-based follow-up:
   ```
   Read the idea-triage bundle at <absolute path to
   idea-stage/codex_triage_bundle.md> and follow all instructions in it.
   ```
   For the `manual` backend, attach that same bundle if possible; otherwise
   paste its contents inline. Bundle contents:
   ```
   Here is the full annotated candidate set (deduped, budget-feasible):
   [write all candidates with their prior_work / so_what / effort_note notes]

   For each, play devil's advocate:
   - What's the strongest objection a reviewer would raise?
   - What's the most likely failure mode?
   - Is the prior_work note a real novelty problem, or differentiable?
   - How would you rank these for a top venue submission?
   - Which 2-3 would you actually work on, and why?
   ```
   The reviewer's ranking is the authoritative quality verdict. The executor
   does not eliminate candidates on its own taste before or instead of this.

2. **Novelty check — on the reviewer's top picks only.** Run the
   `/novelty-check` workflow (multi-source search + cross-model verification)
   on the ideas the triage ranked worth pursuing. This bounds the expensive
   multi-source search to the survivors instead of every candidate, while
   keeping the novelty verdict cross-model.

3. **Select for pilots**: take the top 2-3 ideas that survive both the
   cross-model triage and the novelty check forward to Phase 5.

### Phase 5: Parallel Pilot Experiments (for top 2-3 ideas)

Before committing to a full research effort, run cheap pilot experiments to get empirical signal. This is the key differentiator from paper-only validation.

1. **Design pilots**: For each top idea, define the minimal experiment that would give a positive or negative signal:
   - Single seed, small scale (e.g., small dataset subset, fewer epochs)
   - Target: 30 min - PILOT_MAX_HOURS per pilot on 1 GPU
   - **Estimate GPU-hours BEFORE launching.** If estimated time > PILOT_MAX_HOURS, reduce scale (fewer epochs, smaller subset) or flag as "needs manual pilot"
   - Clear success metric defined upfront (e.g., "if metric improves by > 1%, signal is positive")

2. **Deploy in parallel**: Use `/run-experiment` to launch pilots on different GPUs simultaneously:
   ```
   GPU 0: Pilot for Idea 1
   GPU 1: Pilot for Idea 2
   GPU 2: Pilot for Idea 3
   ```
   Use `run_in_background: true` to launch all at once.

3. **Collect results**: Use `/monitor-experiment` to check progress. If any pilot exceeds PILOT_TIMEOUT_HOURS, kill it and collect partial results. Once all pilots complete (or timeout), compare:
   - Which ideas showed positive signal?
   - Which showed null/negative results? (eliminate or deprioritize)
   - Any surprising findings that suggest a pivot?
   - Total GPU-hours consumed (track against MAX_TOTAL_GPU_HOURS budget)

4. **Re-rank based on empirical evidence**: Update the idea ranking using pilot results. An idea with strong pilot signal jumps ahead of a theoretically appealing but untested idea.

Note: Skip this phase if the ideas are purely theoretical or if no GPU is available. Flag skipped ideas as "needs pilot validation" in the report.

### Phase 6: Output — Ranked Idea Report

Write a structured report to `idea-stage/IDEA_REPORT.md`:

**Lead every recommended idea with its method, in plain language.** Before any hypothesis, novelty score, or claim, state in 2–4 concrete steps what we actually build / train / run — no jargon, no claim-IDs. The reader must understand *what we do* before *what we claim*; claims (hypothesis, validation, expected outcome) come after and read as the method's acceptance criteria.

```markdown
# Research Idea Report

**Direction**: [user's research direction]
**Generated**: [date]
**Ideas evaluated**: X generated → Y survived filtering → Z piloted → W recommended

## Landscape Summary
[3-5 paragraphs on the current state of the field]

## Recommended Ideas (ranked)

### Idea 1: [title]
- **Method (what we actually do)**: [2–4 concrete steps in plain language — what we build / train / run. No jargon, no claim-IDs, no hypothesis yet. Lead with this so the reader grasps the approach first.]
- **Hypothesis**: [one sentence]
- **Minimum experiment**: [concrete description]
- **Expected outcome**: [what success/failure looks like]
- **Novelty**: X/10 — closest work: [paper]
- **Feasibility**: [compute, data, implementation estimates]
- **Risk**: LOW/MEDIUM/HIGH
- **Contribution type**: empirical / method / theory / diagnostic
- **Pilot result**: [POSITIVE: metric +X% / NEGATIVE: no signal / SKIPPED: needs GPU]
- **Reviewer's likely objection**: [strongest counterargument]
- **Why we should do this**: [1-2 sentences]

### Idea 2: [title]
...

## Eliminated Ideas (for reference)
| Idea | Reason eliminated |
|------|-------------------|
| ... | Already done by [paper] |
| ... | Requires > 1 week GPU time |
| ... | Result wouldn't be interesting either way |

## Pilot Experiment Results
| Idea | GPU | Time | Key Metric | Signal |
|------|-----|------|------------|--------|
| Idea 1 | GPU 0 | 45 min | +2.3% CE | POSITIVE |
| Idea 2 | GPU 1 | 30 min | -0.1% CE | NEGATIVE |
| Idea 3 | GPU 2 | 1.5 hr | +0.8% CE | WEAK POSITIVE |

## Suggested Execution Order
1. Start with Idea 1 (positive pilot signal, lowest risk)
2. Idea 3 as backup (weak signal, may need larger scale to confirm)
3. Idea 2 eliminated by pilot — negative result documented

## Next Steps
- [ ] Scale up Idea 1 to full experiment (multi-seed, full dataset)
- [ ] If confirmed, invoke /auto-review-loop for full iteration
```

## Phase 7: Write Ideas to Research Wiki (if active)

**Skip this phase entirely if `research-wiki/` does not exist.**

This is critical for spiral learning — without it, `ideas/` stays empty and re-ideation has no memory.

`$WIKI_SCRIPT` was resolved in Phase 0 above. If Phase 0 did not run
(no `research-wiki/`), this phase is skipped. If Phase 0 ran but the
resolution chain failed to find the helper (`$WIKI_SCRIPT` is empty),
the page-write step still runs (idea pages are plain markdown the
agent writes directly), but the edge / query-pack / log steps that
require the helper are skipped with a single warning.

```
if research-wiki/ exists:
    for each idea in recommended_ideas + eliminated_ideas:
        1. Create page: research-wiki/ideas/<idea_id>.md
           - node_id: idea:<id>
           - stage: proposed (or: piloted, archived)
           - outcome: unknown (or: negative, mixed, positive)
           - based_on: [paper:<slug>, ...]
           - target_gaps: [gap:<id>, ...]
           - Include: hypothesis, proposed method, expected outcome
           - If pilot was run: actual outcome, failure notes, reusable components

        2. Add edges (only if $WIKI_SCRIPT resolved):
           [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" add_edge research-wiki/ --from "idea:<id>" --to "paper:<slug>" --type inspired_by --evidence "..."
           [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" add_edge research-wiki/ --from "idea:<id>" --to "gap:<id>" --type addresses_gap --evidence "..."

    Rebuild query pack (only if $WIKI_SCRIPT resolved):
        [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" rebuild_query_pack research-wiki/
    Log (only if $WIKI_SCRIPT resolved):
        [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" log research-wiki/ "idea-creator wrote N ideas (M recommended, K eliminated)"

    if [ -z "$WIKI_SCRIPT" ]:
        echo "WARN: idea pages were written but edges / query_pack / log were skipped because research_wiki.py is unreachable (see Phase 0 warning above)." >&2
```

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Composition Protocol](../shared-references/output-composition.md)** — see composed-mode note below
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)** — maintain `MANIFEST.md` only above the 15-artifact threshold (not "log every output")
> - **[Output Language Protocol](../shared-references/output-language.md)** — respect the project's language setting

> **Composed mode** — if invoked with `— composed: <canonical-report-path>` (e.g.
> `/idea-discovery` passes `— composed: idea-stage/IDEA_REPORT.md`), that report is the
> single canonical deliverable: fold the literature survey, novelty notes, and any
> external-review conclusions into it as sections/appendices instead of emitting
> `LIT_LANDSCAPE.md` / `RESEARCH_REVIEW.md` / `MANIFEST.md` alongside. Pilot scratch is
> disposable (keep the script + one results file; delete launcher logs and redundant
> `*_summary.json`); review traces stay in `.aris/traces/…` and the report cites the
> path. **Default (no `— composed:` directive): standalone — write `IDEA_REPORT.md` and
> any other documented files as normal.** Never infer composed mode from a report file
> merely existing. Full rules:
> [`shared-references/output-composition.md`](../shared-references/output-composition.md).

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- The user provides a DIRECTION, not an idea. Your job is to generate the ideas.
- Quantity first, quality second: brainstorm broadly, then filter ruthlessly.
- A good negative result is just as publishable as a positive one. Prioritize ideas where the answer matters regardless of direction.
- Don't fall in love with any idea before validating it. Be willing to kill ideas.
- Always estimate compute cost. An idea that needs 1000 GPU-hours is not actionable for most researchers.
- "Apply X to Y" is the lowest form of research idea. Push for deeper questions.
- Include eliminated ideas in the report — they save future time by documenting dead ends.
- **If the user's direction is too broad (e.g., "NLP", "computer vision", "reinforcement learning"), STOP and ask them to narrow it.** A good direction is 1-2 sentences specifying the problem, domain, and constraint — e.g., "factorized gap in discrete diffusion LMs" or "sample efficiency of offline RL with image observations". Without sufficient specificity, generated ideas will be too vague to run experiments on.
- **Anti-hallucination for cited papers.** When the landscape survey or novelty justification cites specific papers, every cited paper must pass pre-search verification (`verify_papers.py`, canonical name resolved per [`shared-references/integration-contract.md`](../shared-references/integration-contract.md) §2; 3-layer arXiv / CrossRef / S2 fallback inside the helper itself). Policy D1 (primary + degraded-output fallback): if the helper is unresolved **or** its invocation fails, mark candidates `[UNVERIFIED]` and continue rather than dropping or guessing. Never fabricate arXiv IDs, DOIs, or titles from memory. Full protocol in [`shared-references/citation-discipline.md`](../shared-references/citation-discipline.md) § Pre-Search Verification Protocol.

## Composing with Other Skills

After this skill produces the ranked report:
```
/idea-creator "direction"     → ranked ideas
/novelty-check "top idea"     → deep novelty verification (already done in Phase 4, but user can re-run)
/research-review "top idea"   → external critical feedback
implement                     → write code
/run-experiment               → deploy to GPU
/auto-review-loop             → iterate until submission-ready
```

## Review Tracing

After each reviewer call (`mcp__codex__codex`, `mcp__codex__codex-reply`, `mcp__manual_review__review`, or `mcp__manual_review__review_reply`), save the trace following `shared-references/review-tracing.md` (Policy C — forensic; never silently skip). Use `save_trace.sh` (resolved per the chain in `shared-references/integration-contract.md` §2) or write files directly to `.aris/traces/<skill>/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).
