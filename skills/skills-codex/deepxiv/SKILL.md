---
name: "deepxiv"
description: "Search and progressively read open-access academic papers through DeepXiv. Use when the user wants layered paper access, section-level reading, trending papers, or DeepXiv-backed literature retrieval."
---

# DeepXiv Paper Search & Progressive Reading

Search topic or paper ID: $ARGUMENTS

## Role & Positioning

DeepXiv is the progressive-reading literature source:

| Skill | Best for |
|------|----------|
| `/arxiv` | Direct preprint search and PDF download |
| `/semantic-scholar` | Published venue metadata, citation counts, DOI links |
| `/deepxiv` | Layered reading: search → brief → head → section, plus trending and web search |

Use DeepXiv when you want to inspect papers incrementally instead of loading the full text immediately.

## Constants

- **FETCH_SCRIPT** — `$ARIS_REPO/tools/deepxiv_fetch.py` from the ARIS repo recorded by the Codex install manifest. If unavailable, fall back to the raw `deepxiv` CLI.
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

Locate the adapter. Prefer the Codex managed install manifest when present, then fall back to the same project/global copy-install lookup style as the Claude skill:

```bash
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null)}"
SCRIPT=""
[ -n "$ARIS_REPO" ] && [ -f "$ARIS_REPO/tools/deepxiv_fetch.py" ] && SCRIPT="$ARIS_REPO/tools/deepxiv_fetch.py"
[ -z "$SCRIPT" ] && [ -f tools/deepxiv_fetch.py ] && SCRIPT="tools/deepxiv_fetch.py"
[ -z "$SCRIPT" ] && [ -f ~/.codex/skills/deepxiv/deepxiv_fetch.py ] && SCRIPT="$HOME/.codex/skills/deepxiv/deepxiv_fetch.py"
[ -n "$SCRIPT" ] && python3 "$SCRIPT" --help
```

If the adapter is unavailable, fall back to raw `deepxiv` commands.

### Step 3: Execute the Minimal Command

```bash
[ -n "$SCRIPT" ] && python3 "$SCRIPT" search "QUERY" --max MAX_RESULTS
[ -n "$SCRIPT" ] && python3 "$SCRIPT" paper-brief ARXIV_ID
[ -n "$SCRIPT" ] && python3 "$SCRIPT" paper-head ARXIV_ID
[ -n "$SCRIPT" ] && python3 "$SCRIPT" paper-section ARXIV_ID "SECTION_NAME"
[ -n "$SCRIPT" ] && python3 "$SCRIPT" trending --days 7 --max MAX_RESULTS
[ -n "$SCRIPT" ] && python3 "$SCRIPT" wsearch "QUERY"
[ -n "$SCRIPT" ] && python3 "$SCRIPT" sc "SEMANTIC_SCHOLAR_ID"
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
