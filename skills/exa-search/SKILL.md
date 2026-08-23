---
name: exa-search
description: Broad web search with content extraction. Use when user says "exa search", "web search with content", "find similar pages", or needs broad web results beyond academic databases (arXiv, Semantic Scholar).
argument-hint: "[search-query-or-url]"
allowed-tools: Read, Write
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - **This skill was rewritten**: the upstream version required the Exa API (`EXA_API_KEY` + `exa-py`).
>   This edition uses Cursor's native **WebSearch** + **WebFetch** tools instead — same role
>   (broad web search + content extraction), no key. If you DO have an Exa key and want the
>   original engine, use the upstream skill at `$ARIS_REPO/skills/exa-search/SKILL.md`.
> - `/x "args"` = load `skills/x/SKILL.md` from this pack; `$ARGUMENTS` = the user's instruction text.

# Broad Web Search (Cursor-native engine)

Search query: $ARGUMENTS

## Role & Positioning

The **broad web search** source with content extraction:

| Skill | Best for |
|------|----------|
| `/arxiv` | Direct preprint search and PDF download |
| `/semantic-scholar` | Published venue papers (IEEE, ACM, Springer), citation counts |
| `/deepxiv` | Layered reading: search, brief, section map, section reads |
| `/exa-search` | Broad web search: blogs, docs, news, companies, research papers — with content extraction |

Use this when you need results beyond academic databases, or when you want page content extracted alongside search results.

## Constants

- **MAX_RESULTS = 10** — Default number of results to present.
- **ENGINE** — Cursor `WebSearch` (discovery) + `WebFetch` (content extraction).

> Overrides (append to arguments):
> - `/exa-search "RAG pipelines" — max: 5` — top 5 results
> - `/exa-search "diffusion models" — category: research paper` — research papers only
> - `/exa-search "startup funding" — category: news, start date: 2025-01-01` — recent news
> - `/exa-search "transformer" — content: text, max chars: 8000` — full text mode
> - `/exa-search "transformer" — content: summary` — summarized content
> - `/exa-search "transformer" — domains: arxiv.org,huggingface.co` — domain filter
> - `/exa-search "https://arxiv.org/abs/2301.07041" — similar` — find similar pages

## Workflow

### Step 1: Parse Arguments

Parse `$ARGUMENTS` for:
- **query**: The search query (required) or a URL (for `similar` mode)
- **similar**: If present, use find-similar mode
- **max**: Override MAX_RESULTS
- **category**: `research paper`, `news`, `company`, `personal site`, `financial report`, `people`
- **content**: `highlights` (default), `text`, `summary`, `none`
- **max chars**: Max characters for content extraction
- **domains** / **exclude domains**: Comma-separated domain filters
- **include text** / **exclude text**: Phrases that must / must not appear
- **start date** / **end date**: ISO 8601 date bounds

### Step 2: Execute Search (WebSearch)

Compose the search query from the parsed arguments:

- **category** → append a category hint: `research paper` → `arxiv OR paper OR "proceedings"`;
  `news` → `news`; `company` → `company OR startup`; etc.
- **domains** → issue one WebSearch per domain with `site:<domain> <query>` (cap at 3 domains),
  merge results; **exclude domains** → drop matching hits after search.
- **include text** → quote the phrase inside the query; **exclude text** → drop matching hits.
- **start/end date** → append the year(s) to the query AND verify hit dates after fetch;
  drop out-of-range hits. (Native date operators are not guaranteed — verify, don't trust.)

Run `WebSearch` with the composed query. If fewer than `max` usable hits return, run one
reformulated follow-up search (synonyms / narrower phrase) and merge.

**Find-similar mode**: `WebFetch` the given URL first, extract its title + 3-5 key phrases,
then `WebSearch` those phrases (excluding the source domain) and present the closest matches.

### Step 3: Extract Content (WebFetch)

Per the **content** mode:

- `none` — present search snippets only.
- `highlights` (default) — `WebFetch` the top 5 hits; extract the 2-3 passages most relevant
  to the query (respect `max chars` if set).
- `text` — `WebFetch` each presented hit; include the main body text up to `max chars` (default 8000).
- `summary` — `WebFetch` each presented hit; write a 3-5 sentence summary yourself.

Skip fetch failures gracefully (paywalls, timeouts) — note `[content unavailable]` for that hit.

### Step 4: Present Results

Format results as a structured table:

```
| # | Title | Authors | Venue/Publisher | URL | Date | Key Content |
|---|-------|---------|-----------------|-----|------|-------------|
```

For each result:
- Show title and URL
- Show published date if available
- Show highlights, text excerpt, or summary depending on content mode
- Flag particularly relevant results
- **For `category: "research paper"` hits only** — also record authors (from the fetched page,
  or parse from the snippet) and venue/publisher (from the page or the hosting domain). These
  are needed by Step 6's wiki hook; if either is unavailable for a hit, skip wiki ingest for
  that one hit and log a note.

### Step 5: Offer Follow-up

After presenting results, suggest:
- **Deepen**: "I can fetch full text for any of these results"
- **Find similar**: "I can find pages similar to any result"
- **Narrow**: "I can re-search with domain/date/text filters"

### Step 6: Update Research Wiki (if active, research-paper results only)

**Required when `research-wiki/` exists AND the search returned results of
`category: "research paper"`**; skip silently otherwise. General web results
(blog posts, docs, news) are **not** ingested — the wiki is for papers only.

When the predicates hold, resolve `$WIKI_SCRIPT` per the canonical chain at
[`shared-references/wiki-helper-resolution.md`](../shared-references/wiki-helper-resolution.md)
(Variant B — warn-and-skip). For each research paper hit, try to recover an arXiv ID
from the URL (`arxiv.org/abs/<id>`); if present, use `--arxiv-id`. Otherwise fall back
to manual metadata:

```bash
if [ -d research-wiki/ ] and query category was "research paper":
    cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
    ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null)}"
    if [ -z "${ARIS_REPO:-}" ] && [ -f "$HOME/.aris/repo" ]; then
      ARIS_REPO=$(cat "$HOME/.aris/repo" 2>/dev/null) || true
    fi
    WIKI_SCRIPT=".aris/tools/research_wiki.py"
    [ -f "$WIKI_SCRIPT" ] || WIKI_SCRIPT="tools/research_wiki.py"
    [ -f "$WIKI_SCRIPT" ] || { [ -n "${ARIS_REPO:-}" ] && WIKI_SCRIPT="$ARIS_REPO/tools/research_wiki.py"; }
    [ -f "$WIKI_SCRIPT" ] || {
      echo "WARN: research_wiki.py not found; search results delivered, wiki ingest skipped. Fix: set ~/.aris/repo or export ARIS_REPO, or cp <ARIS-repo>/tools/research_wiki.py tools/." >&2
      WIKI_SCRIPT=""
    }
    [ -n "$WIKI_SCRIPT" ] && for each research-paper hit in results:
        if URL matches arxiv.org/abs/<id>:
            python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ \
                --arxiv-id "<id>"
        else:
            python3 "$WIKI_SCRIPT" ingest_paper research-wiki/ \
                --title "<title>" --authors "<authors joined by , >" \
                --year <year> --venue "<venue or publisher>"
```

The helper handles slug / dedup / page / index / log — **do not handwrite
`papers/<slug>.md`**. See
[`shared-references/integration-contract.md`](../shared-references/integration-contract.md).

## Key Rules

- Default to `highlights` content mode for a good balance of speed and context
- Use `category: "research paper"` when the user is clearly looking for academic content
- Use `text` content mode when the user needs full page content
- Combine with `/arxiv` or `/semantic-scholar` for comprehensive literature coverage
- **Degradation note vs upstream Exa**: neural similarity search and strict date/category
  filters are approximated (query composition + post-filtering). For citation-grade
  literature coverage, prefer `/arxiv`, `/semantic-scholar`, `/openalex`.
