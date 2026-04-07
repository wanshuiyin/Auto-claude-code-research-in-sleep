---
name: research-wiki
description: "Persistent research knowledge base that accumulates papers, ideas, experiments, claims, and their relationships. Inspired by Karpathy's LLM Wiki. Use when user says \"知识库\", \"research wiki\", \"add paper\", \"wiki query\", \"查知识库\", or wants to build/query a persistent field map."
argument-hint: [subcommand: ingest|query|update|lint|stats|init]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch, LlmReview
---

# Research Wiki: Persistent Research Knowledge Base

Subcommand: **$ARGUMENTS**

## Helper Setup (Auto-Fallback)

This skill ships with a Python helper (`research_wiki.py`) for deterministic operations (slug generation, edge dedup, query_pack budget enforcement). **If Python is unavailable, all operations fall back to direct LLM execution.**

**Step 0: Extract and test the helper.**

```bash
# Extract bundled helper to project wiki directory
WIKI_ROOT="research-wiki"
HELPER="$WIKI_ROOT/research_wiki.py"

# If helper doesn't exist yet, the LLM should write it from bundled resources
# via: read_file on the bundled resource, then write to $HELPER

# Test if Python3 is available
if python3 --version > /dev/null 2>&1; then
    echo "PYTHON_MODE=helper"
else
    echo "PYTHON_MODE=fallback"
fi
```

**If `PYTHON_MODE=helper`**: use `python3 research_wiki.py <subcommand>` for init, slug, add_edge, rebuild_query_pack, stats, log.

**If `PYTHON_MODE=fallback`**: perform all operations directly using bash/write/edit tools. Follow the exact same schema and rules below, but execute each step manually.

## Overview

The research wiki is a persistent, per-project knowledge base that accumulates structured knowledge across the entire ARIS research lifecycle. Unlike one-off literature surveys, the wiki **compounds** — every paper read, idea tested, experiment run, and review received makes it smarter.

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

Edges are stored in `graph/edges.jsonl` only. The `## Connections` section on each page is **auto-generated** — never hand-edit it.

## Wiki Directory Structure

```
research-wiki/
  research_wiki.py       # helper script (auto-extracted)
  index.md               # categorical index (auto-generated)
  log.md                 # append-only timeline
  gap_map.md             # field gaps with stable IDs
  query_pack.md          # compressed summary for /idea-creator (max 8000 chars)
  papers/
    <slug>.md
  ideas/
    <idea_id>.md
  experiments/
    <exp_id>.md
  claims/
    <claim_id>.md
  graph/
    edges.jsonl           # relationship graph
```

## Subcommands

### `/research-wiki init`

**Helper mode**: `python3 research_wiki.py init research-wiki`

**Fallback mode**: Create directories and empty files manually:
```bash
mkdir -p research-wiki/{papers,ideas,experiments,claims,graph}
echo "# Research Wiki Index" > research-wiki/index.md
echo "# Research Wiki Log" > research-wiki/log.md
echo "# Gap Map" > research-wiki/gap_map.md
echo "# Query Pack" > research-wiki/query_pack.md
touch research-wiki/graph/edges.jsonl
```

### `/research-wiki ingest "<paper title>" — arxiv: <id>`

1. **Fetch metadata** — use arXiv/DBLP/Semantic Scholar
2. **Generate slug**:
   - Helper: `python3 research_wiki.py slug "<title>" --author "<last>" --year 2025`
   - Fallback: `<author_last><year>_<keyword>` (lowercase, underscores)
3. **Check dedup** — if `papers/<slug>.md` exists, update instead
4. **Create page** — `papers/<slug>.md` with schema below
5. **Add edges**:
   - Helper: `python3 research_wiki.py add_edge research-wiki --from paper:<slug> --to <target> --type extends`
   - Fallback: append JSON line to `graph/edges.jsonl` manually (check dedup first!)
6. **Rebuild query_pack**:
   - Helper: `python3 research_wiki.py rebuild_query_pack research-wiki`
   - Fallback: regenerate `query_pack.md` manually (STRICT 8000 char budget)
7. **Log**: append timestamped entry to `log.md`

**Paper page schema:**

```markdown
---
type: paper
node_id: paper:<slug>
title: "<full title>"
authors: ["First Author", "Second Author"]
year: 2025
venue: arXiv
tags: [tag1, tag2]
relevance: core  # core | related | peripheral
created_at: <ISO 8601>
---

# One-line thesis

[Single sentence]

## Problem / Gap

## Method

## Key Results

## Limitations / Failure Modes

## Reusable Ingredients

## Open Questions

## Connections

[AUTO-GENERATED from edges.jsonl]

## Relevance to This Project
```

### `/research-wiki query "<topic>"`

Generate `query_pack.md` with **hard budget (max 8000 chars)**:

| Section | Budget | Content |
|---------|--------|---------|
| Project direction | 300 chars | From CLAUDE.md or RESEARCH_BRIEF.md |
| Top 5 gaps | 1200 chars | From gap_map.md |
| Failed ideas | 1400 chars | **Always included** — highest anti-repetition value |
| Top papers | 1800 chars | 8-12 pages ranked by relevance |
| Active chains | 900 chars | Limitation → opportunity chains |
| Open unknowns | 500 chars | Unresolved questions |

- Helper: `python3 research_wiki.py rebuild_query_pack research-wiki --max-chars 8000`
- Fallback: build manually, count characters, truncate to 8000

### `/research-wiki update <node_id> — <field>: <value>`

Update a specific entity, then rebuild query_pack and append to log.

### `/research-wiki lint`

Check for: orphan pages, stale claims, contradictions, missing connections, dead ideas, sparse pages. Output `LINT_REPORT.md`.

### `/research-wiki stats`

- Helper: `python3 research_wiki.py stats research-wiki`
- Fallback: count files in each directory and grep for status fields

## Key Rules

- **One source of truth for relationships**: `graph/edges.jsonl`. Page `Connections` sections are auto-generated.
- **Canonical node IDs everywhere**: `paper:<slug>`, `idea:<id>`, `exp:<id>`, `claim:<id>`.
- **Failed ideas are the most valuable memory.** Never prune from query_pack.
- **query_pack.md is hard-budgeted** at 8000 chars.
- **Append to log.md for every mutation.**
- **Reviewer independence applies.** Pass file paths only to cross-model reviews.
- **Helper vs fallback is transparent.** The wiki format is identical regardless of which mode is used. Users can switch freely.
