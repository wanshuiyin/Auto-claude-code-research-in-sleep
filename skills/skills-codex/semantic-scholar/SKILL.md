---
name: semantic-scholar
description: Search published venue papers (IEEE, ACM, Springer, etc.) via Semantic Scholar API. Complements /arxiv (preprints) with citation counts, venue metadata, and TLDR. Use when user says "search semantic scholar", "find IEEE papers", "find journal papers", "venue papers", "citation search", or wants published literature beyond arXiv preprints.
argument-hint: query-or-paper-id
allowed-tools: Bash(*), Read, Write
---

# Semantic Scholar Paper Search

Search topic or paper ID: $ARGUMENTS

## Role & Positioning

This skill is the **published venue** counterpart to `/arxiv`:

| Skill | Source | Best for |
|-------|--------|----------|
| `/arxiv` | arXiv API | Latest preprints, cutting-edge unrefereed work |
| `/semantic-scholar` | Semantic Scholar API | **Published** journal/conference papers (IEEE, ACM, Springer, etc.) with citation counts, venue info, TLDR |

**Do NOT duplicate arXiv's job.** If results contain an `externalIds.ArXiv` field, the paper is also on arXiv — note this but do not re-fetch from arXiv.

## Constants

- **MAX_RESULTS = 10** — Default number of search results.
- **FETCH_SCRIPT** — `$ARIS_REPO/tools/semantic_scholar_fetch.py` from the ARIS repo recorded by the Codex install manifest. Fall back to inline Python if not found.
- **DEFAULT_FILTERS** — For general research queries, apply these by default to reduce noise:
  - `--fields-of-study "Computer Science,Engineering"`
  - `--publication-types JournalArticle,Conference`

> Overrides (append to arguments):
> - `/semantic-scholar "topic" - max: 20` — return up to 20 results
> - `/semantic-scholar "topic" - type: journal` — only journal articles
> - `/semantic-scholar "topic" - type: conference` — only conference papers
> - `/semantic-scholar "topic" - min-citations: 50` — only highly-cited papers
> - `/semantic-scholar "topic" - year: 2022-` — papers from 2022 onward
> - `/semantic-scholar "topic" - fields: all` — remove default field-of-study filter
> - `/semantic-scholar "topic" - sort: citations` — bulk search sorted by citation count
> - `/semantic-scholar "DOI:10.1109/..."` — fetch a single paper by DOI

## Workflow

### Step 1: Parse Arguments

Parse `$ARGUMENTS` for directives:

- **Query or ID**: main search term, or a paper identifier:
  - DOI: `10.1109/TWC.2024.1234567`
  - Semantic Scholar ID: `f9314fd99be5f2b1b3efcfab87197d578160d553`
  - ArXiv: `ARXIV:2006.10685`
  - Corpus: `CorpusId:219792180`
- **`- max: N`**: override MAX_RESULTS
- **`- type: journal|conference|review|all`**: map to `--publication-types`
- **`- min-citations: N`**: map to `--min-citations`
- **`- year: RANGE`**: map to `--year` (e.g. `2022-`, `2020-2024`)
- **`- fields: FIELDS`**: override `--fields-of-study` (use `all` to remove filter)
- **`- sort: citations|date`**: use `search-bulk` with `--sort citationCount:desc` or `publicationDate:desc`

If the argument matches a DOI pattern (`10.XXXX/...`), a Semantic Scholar ID (40-char hex), or a prefixed ID (`ARXIV:...`, `CorpusId:...`), skip search and go directly to Step 3.

### Step 2: Search Papers

Locate the fetch script:

```bash
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null)}"
SCRIPT=""
[ -n "$ARIS_REPO" ] && [ -f "$ARIS_REPO/tools/semantic_scholar_fetch.py" ] && SCRIPT="$ARIS_REPO/tools/semantic_scholar_fetch.py"
[ -z "$SCRIPT" ] && SCRIPT=$(find tools/ -name "semantic_scholar_fetch.py" 2>/dev/null | head -1)
[ -z "$SCRIPT" ] && SCRIPT=$(find ~/.codex/skills/semantic-scholar/ -name "semantic_scholar_fetch.py" 2>/dev/null | head -1)
```

**Standard search** (default — relevance-ranked):

```bash
[ -n "$SCRIPT" ] && python3 "$SCRIPT" search "QUERY" --max MAX_RESULTS \
  --fields-of-study "Computer Science,Engineering" \
  --publication-types JournalArticle,Conference
```

**Bulk search** (when `- sort:` is specified, or MAX_RESULTS > 100):

```bash
[ -n "$SCRIPT" ] && python3 "$SCRIPT" search-bulk "QUERY" --max MAX_RESULTS \
  --sort citationCount:desc \
  --fields-of-study "Computer Science" \
  --year "2020-"
```

If `semantic_scholar_fetch.py` is not found, fall back to inline Python using `urllib` against `https://api.semanticscholar.org/graph/v1/paper/search`.

**Recommended filter combos** (from testing):

| Goal | Flags |
|------|-------|
| High-quality journal papers | `--publication-types JournalArticle --min-citations 10` |
| CS/EE papers, recent | `--fields-of-study "Computer Science,Engineering" --year "2022-"` |
| Foundational / high-impact | `search-bulk --sort citationCount:desc --fields-of-study "Computer Science"` |
| Conference papers only | `--publication-types Conference` |

> **Note**: `--venue` requires exact venue names (e.g. "IEEE Transactions on Signal Processing"), not partial matches like "IEEE". Avoid using `--venue` in automated flows — prefer `--publication-types` + `--fields-of-study`.

### Step 3: Fetch Details for a Specific Paper

When a single paper ID is requested:

```bash
[ -n "$SCRIPT" ] && python3 "$SCRIPT" paper "PAPER_ID"
```

Where PAPER_ID can be:
- DOI: `10.1109/TSP.2021.3071210`
- ArXiv: `ARXIV:2006.10685`
- CorpusId: `CorpusId:219792180`
- S2 ID: `f9314fd99be5f2b1b3efcfab87197d578160d553`

### Step 4: De-duplicate Against arXiv

For each result, check `externalIds.ArXiv`:
- If present → paper is also on arXiv. Note this in output but do NOT re-fetch via `/arxiv`.
- If absent → paper is **venue-only** (e.g. IEEE without preprint). This is the unique value of this skill.

### Step 5: Present Results

Present results as a table:

```text
| # | Title | Venue | Year | Citations | Authors | Type |
|---|-------|-------|------|-----------|---------|------|
| 1 | Deep Learning Enabled... | IEEE Trans. Signal Process. | 2021 | 1364 | Xie et al. | Journal |
```

For each paper, also show:
- **DOI link**: `https://doi.org/DOI` (for IEEE/ACM papers, this is the canonical link)
- **Open Access PDF**: if `openAccessPdf.url` is non-empty, show it
- **TLDR**: if available, show the one-line summary
- **Also on arXiv**: if `externalIds.ArXiv` exists, note the arXiv ID

### Step 6: Detailed Summary

For each paper (or top 5 if many results):

```markdown
## [Title]

- **Venue**: [venue name] ([publicationVenue.type]: journal/conference)
- **Year**: [year] | **Citations**: [citationCount]
- **Authors**: [full author list]
- **DOI**: [doi link]
- **Fields**: [fieldsOfStudy]
- **TLDR**: [tldr.text if available]
- **Abstract**: [abstract]
- **Open Access**: [openAccessPdf.url or "Not available"]
- **Also on arXiv**: [ArXiv ID if exists, else "No"]
```

### Step 7: Update Research Wiki (if active)

**Required when `research-wiki/` exists in the project**; skip silently
otherwise. Ingest the papers presented to the user. For results with an
`externalIds.ArXiv` field, use `--arxiv-id`; for venue-only papers (no
arXiv mirror — common for IEEE/ACM), fall back to manual metadata:

```
if [ -d research-wiki/ ]:
    WIKI_SCRIPT=""
    [ -n "$ARIS_REPO" ] && [ -f "$ARIS_REPO/tools/research_wiki.py" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"
    [ -z "$WIKI_SCRIPT" ] && [ -f tools/research_wiki.py ] && WIKI_SCRIPT="tools/research_wiki.py"
    [ -z "$WIKI_SCRIPT" ] && [ -f ~/.codex/skills/research-wiki/research_wiki.py ] && WIKI_SCRIPT="$HOME/.codex/skills/research-wiki/research_wiki.py"
    for each paper in results:
        if paper.externalIds.ArXiv:
            [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ \
                --arxiv-id "<ArXiv>"
        else:
            [ -n "$WIKI_SCRIPT" ] && python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ \
                --title "<title>" --authors "<authors joined by , >" \
                --year <year> --venue "<venue>" \
                [--external-id-doi "<externalIds.DOI>"]
```

The helper handles slug / dedup / page / index / log — **do not
handwrite `papers/<slug>.md`**. See
[`shared-references/integration-contract.md`](../shared-references/integration-contract.md).
Backfill with `/research-wiki sync --arxiv-ids <id1>,<id2>,...` for
arXiv-available papers.

### Step 8: Final Output

Summarize what was done:

- `Found N published papers for "query"`
- `Filters applied: [publication types, fields, year range, etc.]`
- `N papers are venue-only (not on arXiv)`
- `Wiki-ingested N papers` (if `research-wiki/` was present)

Suggest follow-up skills:

```text
/arxiv "topic"           - search arXiv preprints (complements this search)
/research-lit "topic"    - multi-source review: Zotero + local PDFs + arXiv + S2
/novelty-check "idea"    - verify novelty against literature
```

## Key Rules

- **Default to filtered search**: Always apply `--fields-of-study` and `--publication-types` unless user says `- fields: all`. Without filters, S2 returns cross-discipline noise (linguistics, psychology, etc.).
- **Citation count is gold**: S2's citation data is its main advantage over arXiv. Always show `citationCount` prominently and use it to rank/prioritize results.
- **Venue metadata matters**: Show `venue` and `publicationVenue.type` (journal vs conference) — this helps users assess paper quality.
- **DOI is the canonical ID for published papers**: Always show DOI links for IEEE/ACM/Springer papers.
- **Rate limiting**: S2 API without key is heavily rate-limited (~1 req/s, strict cooldown). If HTTP 429 occurs, wait and retry. Recommend users set `SEMANTIC_SCHOLAR_API_KEY` env var for higher limits (free at https://www.semanticscholar.org/product/api#api-key-form).
- **TLDR may be null**: Some publishers (notably IEEE) elide the TLDR field. Fall back to showing the first sentence of the abstract.
- **openAccessPdf may be empty**: Many IEEE papers are closed access. Always provide the DOI link as fallback.
- If the S2 API is unreachable, suggest using `/arxiv` or `/research-lit "topic" - sources: web` as fallback.
