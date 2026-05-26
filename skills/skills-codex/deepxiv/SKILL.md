---
name: "deepxiv"
description: "Search and progressively read open-access academic papers through DeepXiv. Use when the user wants layered paper access, section-level reading, trending papers, or DeepXiv-backed literature retrieval."
---

# DeepXiv Paper Search & Progressive Reading

Search topic or paper ID: $ARGUMENTS

## Role & Positioning

DeepXiv is the progressive-reading literature source:

| Skill | Source | Best for |
|-------|--------|----------|
| `/arxiv` | arXiv API | Batch search, PDF download, metadata |
| **`/deepxiv`** | **DeepXiv SDK** | **Progressive section-level reading** |
| `/semantic-scholar` | S2 API | Published venue metadata, citation counts |
| `/alphaxiv` | alphaxiv.org | Instant LLM-optimized summary of one paper, with LaTeX source fallback |

Use DeepXiv when you want to inspect papers incrementally instead of loading the full text immediately.

## Constants

- **DEEPXIV_FETCHER** — canonical name `deepxiv_fetch.py`, resolved per
  [`shared-references/integration-contract.md`](../shared-references/integration-contract.md) §2
  (Codex-side chain: `$ARIS_REPO/tools/` → `tools/` → `~/.codex/skills/deepxiv/`).
  Policy D1 — if unresolved (canonical chain exhausted), fall back to raw `deepxiv` CLI.
- **MAX_RESULTS = 10** — Default number of search results.

> Overrides (append to arguments):
> - `/deepxiv "agent memory" - max: 5`
> - `/deepxiv "2409.05591" - brief`
> - `/deepxiv "2409.05591" - head`
> - `/deepxiv "2409.05591" - section: Introduction`
> - `/deepxiv "trending" - days: 14 - max: 10`
> - `/deepxiv "karpathy" - web`
> - `/deepxiv "258001" - sc`

## Setup

DeepXiv is optional:

```bash
pip install deepxiv-sdk
```

On first use, `deepxiv` auto-registers a free token and stores it in `~/.env`.

## Workflow

### Step 1: Parse Arguments

Parse `$ARGUMENTS` for:

- a paper topic, arXiv ID, or Semantic Scholar ID
- `- max: N`
- `- brief`
- `- head`
- `- section: NAME`
- `- trending`
- `- days: 7|14|30`
- `- web`
- `- sc`

If the input looks like an arXiv ID and no explicit mode is provided, default to `brief`.

### Step 2: Locate the Adapter

Resolve `$DEEPXIV_FETCHER` via the canonical strict-safe Codex chain
(see [`shared-references/integration-contract.md`](../shared-references/integration-contract.md) §2):

```bash
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
DEEPXIV_FETCHER=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/deepxiv_fetch.py" ] && DEEPXIV_FETCHER="$ARIS_REPO/tools/deepxiv_fetch.py"
[ -z "$DEEPXIV_FETCHER" ] && [ -f tools/deepxiv_fetch.py ] && DEEPXIV_FETCHER="tools/deepxiv_fetch.py"
[ -z "$DEEPXIV_FETCHER" ] && [ -f ~/.codex/skills/deepxiv/deepxiv_fetch.py ] && DEEPXIV_FETCHER="$HOME/.codex/skills/deepxiv/deepxiv_fetch.py"

# Smoke test (optional): resolved-but-non-functional adapter is not currently auto-demoted.
if [ -n "$DEEPXIV_FETCHER" ]; then
  echo "DeepXiv adapter resolved at: $DEEPXIV_FETCHER" >&2
else
  echo "DeepXiv adapter unresolved (canonical chain exhausted); raw deepxiv CLI fallback will be used." >&2
fi
```

If the adapter is unresolved, fall back to raw `deepxiv` commands.

### Step 3: Execute the Minimal Command

```bash
[ -n "$DEEPXIV_FETCHER" ] && python3 "$DEEPXIV_FETCHER" search "QUERY" --max MAX_RESULTS
[ -n "$DEEPXIV_FETCHER" ] && python3 "$DEEPXIV_FETCHER" paper-brief ARXIV_ID
[ -n "$DEEPXIV_FETCHER" ] && python3 "$DEEPXIV_FETCHER" paper-head ARXIV_ID
[ -n "$DEEPXIV_FETCHER" ] && python3 "$DEEPXIV_FETCHER" paper-section ARXIV_ID "SECTION_NAME"
[ -n "$DEEPXIV_FETCHER" ] && python3 "$DEEPXIV_FETCHER" trending --days 7 --max MAX_RESULTS
[ -n "$DEEPXIV_FETCHER" ] && python3 "$DEEPXIV_FETCHER" wsearch "QUERY"
[ -n "$DEEPXIV_FETCHER" ] && python3 "$DEEPXIV_FETCHER" sc "SEMANTIC_SCHOLAR_ID"
```

Fallbacks:

```bash
deepxiv search "QUERY" --limit MAX_RESULTS --format json
deepxiv paper ARXIV_ID --brief --format json
deepxiv paper ARXIV_ID --head --format json
deepxiv paper ARXIV_ID --section "SECTION_NAME" --format json
deepxiv trending --days 7 --limit MAX_RESULTS --output json
deepxiv wsearch "QUERY" --output json
deepxiv sc "SEMANTIC_SCHOLAR_ID" --output json
```

### Step 4: Present Results

For search results, present a compact literature table. For paper reads, summarize the title, authors, date, TLDR, and the next recommended depth step.

### Step 5: Escalate Depth Only When Needed

Use the progression:

1. `search`
2. `paper-brief`
3. `paper-head`
4. `paper-section`

Only read the full paper when the user explicitly needs it.

### Step 6: Update Research Wiki (if active)

If the project has an active research wiki and the user is building a literature set, add DeepXiv findings as source-backed entries with arXiv/Semantic Scholar IDs, retrieved sections, and the recommended next depth step.

Follow [`shared-references/integration-contract.md`](../shared-references/integration-contract.md). If the wiki path or schema is unclear, ask before writing.

## Key Rules

- Prefer the adapter script over raw `deepxiv` commands when available.
- If DeepXiv is missing, give the install command and suggest `/arxiv` or `/research-lit "topic" - sources: web`.
- Use DeepXiv as an additive source, not a replacement for existing ARIS literature tooling.
- If the result overlaps with a published venue paper from Semantic Scholar, keep the richer venue metadata in the final summary.
