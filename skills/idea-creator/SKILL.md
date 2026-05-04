---
name: idea-creator
description: Generate and rank research ideas given a broad direction. Use when user says "找idea", "brainstorm ideas", "generate research ideas", "what can we work on", or wants to explore a research area for publishable directions.
argument-hint: [research-direction]
allowed-tools: Bash(*), Read, Write, Grep, Glob, WebSearch, WebFetch, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Research Idea Creator

Generate publishable research ideas for: $ARGUMENTS

## Overview

Given a broad research direction from the user, systematically generate, validate, and rank concrete research ideas. This skill composes with `/research-lit`, `/novelty-check`, and `/research-review` to form a complete idea discovery pipeline.

## Constants

- **PILOT_MAX_HOURS = 2** — Skip any pilot estimated to take > 2 hours per GPU. Flag as "needs manual pilot".
- **PILOT_TIMEOUT_HOURS = 3** — Hard timeout: kill pilots exceeding 3 hours. Collect partial results if available.
- **MAX_PILOT_IDEAS = 3** — Pilot at most 3 ideas in parallel. Additional ideas are validated on paper only.
- **MAX_TOTAL_GPU_HOURS = 8** — Total GPU budget for all pilots combined.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for brainstorming and review. Must be an OpenAI model (e.g., `gpt-5.4`, `o3`, `gpt-4o`).
- **REVIEWER_BACKEND = `codex`** — Default: Codex MCP (xhigh). Override with `— reviewer: oracle-pro` for GPT-5.4 Pro via Oracle MCP. See `shared-references/reviewer-routing.md`.
- **OUTPUT_DIR = `idea-stage/`** — All idea-stage outputs go here. Create the directory if it doesn't exist.

> 💡 Override via argument, e.g., `/idea-creator "topic" — pilot budget: 4h per idea, 20h total`.

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

### Phase 2: Idea Generation (brainstorm with external LLM)

Use the external LLM via Codex MCP for divergent thinking:

```
mcp__codex__codex:
  model: REVIEWER_MODEL
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    You are a senior ML researcher brainstorming research ideas.

    Research direction: [user's direction]

    Here is the current landscape:
    [paste landscape map from Phase 1]

    Key gaps identified:
    [paste gaps from Phase 1]

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

### Phase 3: First-Pass Filtering

For each generated idea, quickly evaluate:

1. **Feasibility check**: Can we actually run this experiment with available resources?
   - Compute requirements (estimate GPU-hours)
   - Data availability
   - Implementation complexity
   - Skip ideas requiring > 1 week of GPU time or unavailable datasets

2. **Novelty quick-check**: For each idea, do 2-3 targeted searches to see if it's already been done. Full `/novelty-check` comes later for survivors.

3. **Impact estimation**: Would a reviewer care about the result?
   - "So what?" test: if the experiment succeeds, does it change how people think?
   - Is the finding actionable or just interesting?

Eliminate ideas that fail any of these. Typically 8-12 ideas reduce to 4-6.

### Phase 4: Deep Validation (for top ideas)

For each surviving idea, run a deeper evaluation:

1. **Novelty check**: Use the `/novelty-check` workflow (multi-source search + GPT-5.4 cross-verification) for each idea

2. **Critical review**: Use GPT-5.4 via `mcp__codex__codex-reply` (same thread):
   ```
   Here are our top ideas after filtering:
   [paste surviving ideas with novelty check results]

   For each, play devil's advocate:
   - What's the strongest objection a reviewer would raise?
   - What's the most likely failure mode?
   - How would you rank these for a top venue submission?
   - Which 2-3 would you actually work on?
   ```

3. **Combine rankings**: Merge your assessment with GPT-5.4's ranking. Select top 2-3 ideas for pilot experiments.

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

```markdown
# Research Idea Report

**Direction**: [user's research direction]
**Generated**: [date]
**Ideas evaluated**: X generated → Y survived filtering → Z piloted → W recommended

## Landscape Summary
[3-5 paragraphs on the current state of the field]

## Recommended Ideas (ranked)

### Idea 1: [title]
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
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../shared-references/output-language.md)** — respect the project's language setting

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

After each `mcp__codex__codex` or `mcp__codex__codex-reply` reviewer call, save the trace following `shared-references/review-tracing.md`. Use `tools/save_trace.sh` or write files directly to `.aris/traces/<skill>/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).
