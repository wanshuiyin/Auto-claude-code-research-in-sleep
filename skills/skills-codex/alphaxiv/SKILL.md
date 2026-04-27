---
name: alphaxiv
description: Quick single-paper lookup via AlphaXiv LLM-optimized summaries with tiered source fallback. Use when user says "explain this paper", "summarize paper", pastes an arXiv/AlphaXiv URL, or provides a bare arXiv ID for quick understanding - not for broad literature search.
argument-hint: [arxiv-id-or-url]
allowed-tools: Bash(*), Read, Write, WebFetch, Glob
---

# AlphaXiv Paper Lookup

Lookup paper: $ARGUMENTS

> Quick single-paper reader with tiered source fallback (overview → full markdown → LaTeX source). Powered by [AlphaXiv](https://alphaxiv.org).

## Role & Positioning

This skill is the **quick single-paper reader** that returns LLM-optimized summaries:

| Skill | Source | Best for |
|-------|--------|----------|
| `/arxiv` | arXiv API | Batch search, PDF download, metadata |
| `/deepxiv` | DeepXiv SDK | Progressive section-level reading |
| `/semantic-scholar` | S2 API | Published venue metadata, citation counts |
| **`/alphaxiv`** | **alphaxiv.org** | **Instant LLM-optimized summary of one paper, with LaTeX source fallback** |

**Do NOT use this skill for** topic discovery, broad literature search, or multi-paper surveys — use `/research-lit` or `/arxiv` instead.

## Constants

- **OVERVIEW_URL** = `https://alphaxiv.org/overview/{PAPER_ID}.md`
- **ABS_URL** = `https://alphaxiv.org/abs/{PAPER_ID}.md`
- **ARXIV_SRC_URL** = `https://arxiv.org/src/{PAPER_ID}`

> Overrides (append to arguments):
> - `/alphaxiv 2401.12345` — quick overview
> - `/alphaxiv "https://arxiv.org/abs/2401.12345"` — auto-extract ID
> - `/alphaxiv 2401.12345 - depth: src` — force LaTeX source inspection
> - `/alphaxiv 2401.12345 - depth: abs` — force full markdown

## Workflow

### Step 1: Parse Arguments & Extract Paper ID

Parse `$ARGUMENTS` to extract a bare arXiv paper ID. Accept these input formats:

- `https://arxiv.org/abs/2401.12345` or `https://arxiv.org/abs/2401.12345v2`
- `https://arxiv.org/pdf/2401.12345`
- `https://alphaxiv.org/overview/2401.12345`
- `https://alphaxiv.org/abs/2401.12345`
- `2401.12345` or `2401.12345v2`

Strip version suffixes (`v1`, `v2`, ...) for API calls. Store as `PAPER_ID`.

Parse optional directives:
- **`- depth: overview|abs|src`**: force a specific tier instead of cascading

### Step 2: Fetch AlphaXiv Overview (Tier 1 — Fastest)

Fetch the structured overview from `https://alphaxiv.org/overview/{PAPER_ID}.md`.

This returns a **structured, LLM-optimized report** designed for machine consumption. Use this as the default and preferred source.

If the overview answers the user's question, **stop here**. Do not fetch deeper tiers unnecessarily.

If the request fails (HTTP 404 — paper not yet processed) or the content is insufficient, proceed to Step 3.

### Step 3: Fetch Full AlphaXiv Markdown (Tier 2 — More Detail)

Fetch the full paper markdown from `https://alphaxiv.org/abs/{PAPER_ID}.md`.

This provides the full paper body as markdown. Use when the user needs:
- Specific methodology details
- Detailed experimental results
- Particular sections not covered in the overview

If this still does not answer the question, proceed to Step 4.

### Step 4: Fetch arXiv LaTeX Source (Tier 3 — Deepest)

When the overview and full markdown are both insufficient (e.g., the user asks about equations, proofs, appendix details, or implementation specifics), download the paper's LaTeX source from `https://arxiv.org/src/{PAPER_ID}`.

The source is a `.tar.gz` archive. Download it to a temporary directory, extract it, and list the `.tex` files inside.

Then inspect **only** the files needed to answer the question. Prioritize:

1. Top-level `*.tex` files (usually the main document)
2. Files referenced by `\input{}` or `\include{}`
3. Appendices, tables, or sections directly related to the user's question

**Do NOT read the entire source tree by default.** Read selectively.

Temporary source artifacts live under `/tmp`. Do not rely on persistence.

### Step 5: Present Results

#### Default Answer Shape

```markdown
## [Paper Title]

- **arXiv**: [PAPER_ID] — https://arxiv.org/abs/[PAPER_ID]
- **Source depth**: overview | abs | src

### Summary
[2-3 sentence summary]

### Key Points
- [point 1]
- [point 2]
- [point 3]

### Answer to Your Question
[Direct answer if the user asked a specific question]
```

If the user only asks for one specific detail, answer it directly — skip the full template.

#### Suggest Follow-Up Skills

```text
/arxiv "PAPER_ID" - download          - download the PDF to local library
/deepxiv "PAPER_ID" - section: Methods  - read a specific section progressively
/research-lit "related topic"        - multi-source literature survey
/novelty-check "idea from paper"     - verify novelty against this paper's area
```

## Update Research Wiki (if active)

**Required when `research-wiki/` exists in the project**; skip silently
otherwise. After presenting the paper summary, ingest the single paper
that was read:

```
if [ -d research-wiki/ ]:
    ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null)}"
    WIKI_SCRIPT=""
    [ -n "$ARIS_REPO" ] && [ -f "$ARIS_REPO/tools/research_wiki.py" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"
    [ -z "$WIKI_SCRIPT" ] && [ -f tools/research_wiki.py ] && WIKI_SCRIPT="tools/research_wiki.py"
    [ -z "$WIKI_SCRIPT" ] && [ -f ~/.codex/skills/research-wiki/research_wiki.py ] && WIKI_SCRIPT="$HOME/.codex/skills/research-wiki/research_wiki.py"
    [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ \
        --arxiv-id "<paper_arxiv_id>" \
        [--thesis "<one-line thesis from the Tier 1 overview>"]
```

The helper handles metadata fetch, slug, dedup, page creation, index
rebuild, and log append — **do not handwrite `papers/<slug>.md`**. See
[`shared-references/integration-contract.md`](../shared-references/integration-contract.md).
If wiki was not present at read time, the user can backfill via
`python3 "$WIKI_SCRIPT" sync research-wiki/ --arxiv-ids <id>` after resolving `WIKI_SCRIPT` as above.

## Key Rules

- **Overview first**: `overview` is the fastest path and must always be tried before deeper tiers. Only escalate when needed.
- **Minimal reads**: At `src` tier, read only the files that answer the question. Full-tree reads waste tokens.
- **Cross-platform**: When downloading and extracting the source archive, prefer cross-platform approaches (e.g., Python stdlib) over platform-specific commands to ensure Windows/WSL compatibility.
- **No PDF parsing**: This skill reads structured markdown and LaTeX source, not raw PDFs. For PDF content, suggest `/arxiv` with download.
- **Rate limiting**: arXiv source download may rate-limit. If HTTP 429 occurs, wait 5 seconds and retry once. If still blocked, report the error and suggest `/deepxiv` as alternative.
- **Complementary, not competing**: This skill complements `/arxiv` (search + download) and `/deepxiv` (progressive reading). Do not re-implement their functionality.

## Integration with Other Skills

### As enrichment in `/research-lit`

`/research-lit` can use this skill's Tier 1 (overview) as a fast enrichment step between search and deep analysis. After finding arXiv papers in Step 1, fetch AlphaXiv overviews to quickly assess relevance before committing to full-text reads:

```
Step 1: Search → list of arXiv IDs
Step 1.5: AlphaXiv overview for top 5-8 papers (this skill, Tier 1 only)
Step 2: Deep analysis only for papers that pass the relevance filter
```

This saves significant tokens by filtering out marginally relevant papers before deep reading.

### As follow-up from other skills

After `/research-lit`, `/novelty-check`, or `/idea-discovery` surface a specific paper, users can invoke `/alphaxiv PAPER_ID` for a fast deep-dive without re-running the full survey.
