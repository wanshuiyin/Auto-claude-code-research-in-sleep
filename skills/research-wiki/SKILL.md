---
name: research-wiki
description: "Persistent research knowledge base that accumulates papers, ideas, experiments, claims, and their relationships across the entire research lifecycle. Inspired by Karpathy's LLM Wiki pattern. Use when user says \"知识库\", \"research wiki\", \"add paper\", \"wiki query\", \"查知识库\", or wants to build/query a persistent field map."
argument-hint: [subcommand: init|ingest|sync|query|update|lint|stats]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch, mcp__codex__codex, mcp__codex__codex-reply
---

# Research Wiki: Persistent Research Knowledge Base

Subcommand: **$ARGUMENTS**

## Overview

The research wiki is a persistent, per-project knowledge base that accumulates structured knowledge across the entire ARIS research lifecycle. Unlike one-off literature surveys that are used and forgotten, the wiki **compounds** — every paper read, idea tested, experiment run, and review received makes the wiki smarter.

Inspired by [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): compile knowledge once, keep it current, don't re-derive on every query.

## Core Concepts

### Four Entity Types

| Entity | Directory | Node ID format | What it represents |
|--------|-----------|---------------|--------------------|
| **Paper** | `papers/` | `paper:<slug>` | A published or preprint research paper |
| **Idea** | `ideas/` | `idea:<id>` | A research idea (proposed, tested, or failed) |
| **Experiment** | `experiments/` | `exp:<id>` | A concrete experiment run with results |
| **Claim** | `claims/` | `claim:<id>` | A testable scientific claim with evidence status |

### Typed Relationships (`graph/edges.jsonl`)

| Edge type | From → To | Meaning |
|-----------|-----------|---------|
| `extends` | paper → paper | Builds on prior work |
| `contradicts` | paper → paper | Disagrees with results/claims |
| `addresses_gap` | paper\|idea → gap | Targets a known field gap |
| `inspired_by` | idea → paper | Idea sourced from this paper |
| `tested_by` | idea\|claim → exp | Tested in this experiment |
| `supports` | exp → claim\|idea | Experiment confirms claim |
| `invalidates` | exp → claim\|idea | Experiment disproves claim |
| `supersedes` | paper → paper | Newer work replaces older |

Edges are stored in `graph/edges.jsonl` only. The `## Connections` section on each page is **auto-generated** from the graph — never hand-edit it.

## Wiki Directory Structure

```
research-wiki/
  index.md               # categorical index (auto-generated)
  log.md                 # append-only timeline
  gap_map.md             # field gaps with stable IDs (G1, G2, ...)
  query_pack.md          # compressed summary for /idea-creator (auto-generated, max 8000 chars)
  papers/
    <slug>.md            # one page per paper
  ideas/
    <idea_id>.md         # one page per idea
  experiments/
    <exp_id>.md          # one page per experiment
  claims/
    <claim_id>.md        # one page per testable claim
  graph/
    edges.jsonl          # materialized current relationship graph
```

## Subcommands

## Helper resolution (run before any subcommand below)

All wiki operations except plain directory bootstrap go through a single
canonical helper, `tools/research_wiki.py`. Skills that touch the wiki
must resolve `$WIKI_SCRIPT` via the chain below — never hard-code
`python3 tools/research_wiki.py …`. Hard-coding silently fails when
the project does not have `tools/` on disk (the post-`install_aris.sh`
default), which is exactly the failure mode that left a real user's
`research-wiki/` empty for a week.

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null)}"
WIKI_SCRIPT=".aris/tools/research_wiki.py"
[ -f "$WIKI_SCRIPT" ] || WIKI_SCRIPT="tools/research_wiki.py"
[ -f "$WIKI_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"; }
[ -f "$WIKI_SCRIPT" ] || {
  echo "ERROR: research_wiki.py not found at .aris/tools/, tools/, or \$ARIS_REPO/tools/." >&2
  echo "       Fix one of:" >&2
  echo "         1. rerun 'bash tools/install_aris.sh' from the ARIS repo (creates .aris/tools symlink)" >&2
  echo "         2. export ARIS_REPO=<path-to-ARIS-repo>" >&2
  echo "         3. cp <ARIS-repo>/tools/research_wiki.py tools/" >&2
  exit 1
}
```

`/research-wiki` itself is the wiki tool — if the helper is missing the
skill **hard-fails**. Caller skills that update the wiki as a side
effect (`/idea-creator`, `/result-to-claim`, `/research-lit`, `/arxiv`,
`/alphaxiv`, `/deepxiv`, `/semantic-scholar`, `/exa-search`) use the
same chain but **warn-and-skip** instead of hard-failing — their
primary output (idea list, claim verdict, paper summary) must still be
delivered to the user.

### `/research-wiki init`

Initialize the wiki for the current project. After resolving
`$WIKI_SCRIPT` per the chain above:

```bash
python3 "$WIKI_SCRIPT" init research-wiki/
```

The helper creates `research-wiki/{papers,ideas,experiments,claims,graph}/`
plus `index.md`, `log.md`, `gap_map.md`, **`query_pack.md`**, and
`graph/edges.jsonl`, then appends `"Wiki initialized"` to `log.md`.

(Earlier versions of this skill described a prose-only init that
omitted `query_pack.md` — that drifted from the helper and made
`/idea-creator`'s Phase 0 query-pack check fall through to a
`rebuild_query_pack` invocation that, under the old hard-coded path,
silently failed. Delegating init to the helper is the single source of
truth for the wiki schema.)

### `/research-wiki ingest "<paper title>" — arxiv: <id>`

Add a paper to the wiki. This subcommand is thin wrapping around
`python3 "$WIKI_SCRIPT" ingest_paper …`, which is the single
implementation of paper ingest in ARIS (per
[`shared-references/integration-contract.md`](../shared-references/integration-contract.md)
— one helper, no copies). The helper does all of:

1. **Fetch metadata** — queries the arXiv Atom API when `--arxiv-id` is given
2. **Generate slug** — `<first_author_last_name><year>_<keyword>`
3. **Check dedup** — skip an existing page unless `--update-on-exist`
4. **Create page** — `papers/<slug>.md` with the schema below
5. **Rebuild `index.md`** and `query_pack.md`
6. **Append `log.md`**

Edge extraction (step 5/8 in the old manual flow) is **not** in
`ingest_paper`; do it as a follow-up with `add_edge` per relationship
identified:

```bash
# arXiv-known paper
python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ \
    --arxiv-id 2501.12345 --thesis "One-line claim from abstract."

# Venue paper with no arXiv mirror
python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ \
    --title "Attention Is All You Need" \
    --authors "Ashish Vaswani, Noam Shazeer, …" --year 2017 --venue "NeurIPS"

# Manual edge after ingest
python3 "$WIKI_SCRIPT" add_edge research-wiki/ \
    --from "paper:vaswani2017_attention_all_you" \
    --to "paper:chen2025_factorized_gap" \
    --type "extends" --evidence "Section 3.2: adapts the encoder block …"
```

Other skills (`/research-lit`, `/arxiv`, `/alphaxiv`, `/deepxiv`,
`/semantic-scholar`, `/exa-search`) call the same helper directly in
their own last step — they don't re-route through `/research-wiki
ingest` as a subcommand, so they don't need an LLM roundtrip.

### `/research-wiki sync — arxiv-ids <id1>,<id2>,...`

Batch backfill: ingest one or more arXiv IDs that were read earlier
without being ingested (e.g., because `research-wiki/` was set up after
the reading happened, or a hook didn't fire).

```bash
# Explicit list
python3 "$WIKI_SCRIPT" sync research-wiki/ \
    --arxiv-ids 2310.06770,1706.03762

# From a file (one id per line, # comments ok)
python3 "$WIKI_SCRIPT" sync research-wiki/ --from-file ids.txt
```

Dedup is handled per-id; already-ingested papers are skipped silently.
This is the recommended **manual repair** step (see integration
contract §5 Backfill). `sync` does not scan session traces — callers
declare the ids explicitly.

**Paper page schema** (exactly what `ingest_paper` emits — do not
handwrite alternative fields; `lint` will flag drift):

```markdown
---
type: paper
node_id: paper:<slug>
title: "<full title>"
authors: ["First A. Author", "Second B. Author"]
year: 2025
venue: "arXiv"
external_ids:
  arxiv: "2501.12345"
  doi: null
  s2: null
tags: ["tag1", "tag2"]
added: 2026-04-07T10:12:00Z
---

# <full title>

## One-line thesis

[Single sentence capturing the paper's core contribution]

## Problem / Gap

## Method

## Key Results

## Assumptions

## Limitations / Failure Modes

## Reusable Ingredients

[Techniques, datasets, or insights that could be repurposed]

## Open Questions

## Claims

[Reference claim pages: claim:C1, claim:C2, etc.]

## Connections

[AUTO-GENERATED from graph/edges.jsonl — do not edit manually]

## Relevance to This Project

[Why this paper matters for our specific research direction]
```

_Additionally, when the paper was ingested via `--arxiv-id` and the arXiv
API returned an abstract, the helper appends an `## Abstract (original)`
section after `Relevance to This Project` containing the raw abstract
text as a blockquote. Manual ingests (no `--arxiv-id`) do not include
this section._

### `/research-wiki query "<topic>"`

Generate `query_pack.md` — a compressed, context-window-friendly summary:

**Fixed budget (max 8000 chars / ~2000 tokens):**

| Section | Budget | Content |
|---------|--------|---------|
| Project direction | 300 chars | From CLAUDE.md or RESEARCH_BRIEF.md |
| Top 5 gaps | 1200 chars | From gap_map.md, ranked by: unresolved + linked ideas + failed experiments |
| Paper clusters | 1600 chars | 3-5 clusters by tag overlap, 2-3 sentences each |
| Failed ideas | 1400 chars | **Always included** — highest anti-repetition value |
| Top papers | 1800 chars | 8-12 pages ranked by: linked gaps, linked ideas, centrality, relevance flag |
| Active chains | 900 chars | limitation → opportunity relationship chains |
| Open unknowns | 500 chars | Unresolved questions across the wiki |

**Pruning priority** (when over budget): low-ranked papers > cluster detail > chain detail. **Never prune** failed ideas or top gaps first.

**Key rule:** Read from short fields only (frontmatter, one-line thesis, gap summary, failure note). Do not summarize full page bodies every time.

### `/research-wiki update <node_id> — <field>: <value>`

Update a specific entity:

```
/research-wiki update paper:chen2025 — relevance: core
/research-wiki update idea:001 — outcome: negative
/research-wiki update claim:C1 — status: invalidated
```

After any update: rebuild `query_pack.md`, update `log.md`.

### `/research-wiki lint`

Health check the wiki:

1. **Orphan pages** — entities with zero edges
2. **Stale claims** — claims with `status: reported` older than 14 days
3. **Contradictions** — claims with both `supports` and `invalidates` edges
4. **Missing connections** — papers sharing 2+ tags but no explicit relationship
5. **Dead ideas** — `stage: proposed` ideas that were never tested
6. **Sparse pages** — pages with 3+ empty sections

Output a `LINT_REPORT.md` with suggested fixes.

### `/research-wiki stats`

Quick overview:

```
📚 Research Wiki Stats
Papers: 28 (12 core, 10 related, 6 peripheral)
Ideas: 7 (2 active, 3 failed, 1 partial, 1 succeeded)
Experiments: 12
Claims: 15 (5 supported, 3 invalidated, 7 reported)
Edges: 64
Gaps: 8 (3 unresolved)
Last updated: 2026-04-07T10:12:00Z
```

## Integration with Existing Workflows

All paper-reading skills follow the same **integration contract** (see
[`shared-references/integration-contract.md`](../shared-references/integration-contract.md)):

- single predicate — `[ -d research-wiki/ ]`
- single canonical helper — `python3 "$WIKI_SCRIPT" ingest_paper …` after resolving `$WIKI_SCRIPT` via the chain at the top of this SKILL
- concrete artifact — `papers/<slug>.md` + `log.md` entry
- backfill — `sync --arxiv-ids …`
- diagnostic — `tools/verify_wiki_coverage.sh`

### Hook 1: After `/research-lit` finds papers

```
# At end of research-lit, after synthesis:
if research-wiki/ exists AND $WIKI_SCRIPT resolved (chain at top of this SKILL):
    for paper in top_relevant_papers (limit 8-12):
        python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ \
            --arxiv-id <id> [--thesis "..."] [--tags "..."]
        for each explicit relation to existing wiki paper:
            python3 "$WIKI_SCRIPT" add_edge research-wiki/ \
                --from "paper:<slug>" --to "<target>" \
                --type <extends|contradicts|addresses_gap|...> \
                --evidence "..."
    log "research-lit ingested N papers"
elif research-wiki/ exists but $WIKI_SCRIPT did not resolve:
    warn "wiki update skipped — research_wiki.py unreachable; rerun install_aris.sh"
```

Each paper-reading skill ships its own Step "Update Research Wiki (if
active)" that calls the same helper once per paper it touched. The
business logic is not duplicated — only the loop over that skill's
specific result set differs.

### Hook 2: `/idea-creator` reads AND writes wiki

**Before ideation:**
```
if research-wiki/query_pack.md exists (and < 7 days old):
    prepend query_pack to landscape context
    treat failed ideas as banlist
    treat top gaps as search seeds
    still run fresh literature search for last 3-6 months
```

**After ideation (THIS IS CRITICAL — without it, ideas/ stays empty):**
```
for idea in all_generated_ideas (recommended + killed):
    /research-wiki upsert_idea(idea)
    for paper_id in idea.based_on:
        add_edge(idea.node_id, paper_id, "inspired_by")
    for gap_id in idea.target_gaps:
        add_edge(idea.node_id, gap_id, "addresses_gap")
rebuild query_pack
log "idea-creator wrote N ideas to wiki"
```

### Hook 3: After `/result-to-claim` verdict

```
# Create experiment page
exp_id = upsert_experiment(experiment_data)

# Update each claim's status
for claim_id in resolved_claims:
    if verdict == "yes":
        set_claim_status(claim_id, "supported")
        add_edge(exp_id, claim_id, "supports")
    elif verdict == "partial":
        set_claim_status(claim_id, "partial")
        add_edge(exp_id, claim_id, "supports")  # partial
    else:
        set_claim_status(claim_id, "invalidated")
        add_edge(exp_id, claim_id, "invalidates")

# Update idea outcome
update_idea(active_idea_id, outcome=verdict)

# If failed, record WHY for future ideation
if verdict in ("no", "partial"):
    update_idea failure_notes with specific metrics and reasons

rebuild query_pack
log "result-to-claim: exp_id updated, verdict=..."
```

## Re-ideation Trigger

After significant wiki updates, suggest re-running `/idea-creator`:

- ≥5 new papers ingested since last ideation
- ≥3 new failed/partial ideas since last ideation
- New contradiction discovered in the graph
- New gap identified that no existing idea addresses

The system suggests but does not auto-trigger. User decides.

## Key Rules

- **One source of truth for relationships**: `graph/edges.jsonl`. Page `Connections` sections are auto-generated views.
- **Canonical node IDs everywhere**: `paper:<slug>`, `idea:<id>`, `exp:<id>`, `claim:<id>`, `gap:<id>`. Never use raw titles or inconsistent shorthands.
- **Failed ideas are the most valuable memory.** Never prune them from query_pack.
- **query_pack.md is hard-budgeted** at 8000 chars. Deterministic generation, not open-ended summarization.
- **Append to log.md for every mutation.** The log is the audit trail.
- **Reviewer independence applies.** When the wiki is read by cross-model review skills, pass file paths only — do not summarize wiki content for the reviewer.

## Acknowledgements

Inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — "compile knowledge once, keep it current, don't re-derive on every query."
