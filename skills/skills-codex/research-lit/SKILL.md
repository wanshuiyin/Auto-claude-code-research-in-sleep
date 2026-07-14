---
name: "research-lit"
description: "Search and analyze research papers, find related work, summarize key ideas. Use when user says \"find papers\", \"related work\", \"literature review\", \"what does this paper say\", or needs to understand academic papers."
---

# Research Literature Review

Research topic: $ARGUMENTS

## Constants

- **PAPER_LIBRARY** — Local directory containing user's paper collection (PDFs). Check these paths in order:
  1. `papers/` in the current project directory
  2. `literature/` in the current project directory
  3. Custom path specified by user in `AGENTS.md` under `## Paper Library`
- **MAX_LOCAL_PAPERS = 20** — Maximum number of local PDFs to scan (read first 3 pages each). If more are found, prioritize by filename relevance to the topic.
- **SOURCES = `all`** — Which literature sources to search. Options: `zotero`, `obsidian`, `local`, `web`, `semantic-scholar`, `deepxiv`, `exa`, `gemini`, `openalex`, `all`. Full source table and selection rules: see `## Data Sources` below.
- **ARXIV_DOWNLOAD = false** — When `true`, download top 3-5 most relevant arXiv PDFs to PAPER_LIBRARY after search. When `false` (default), only fetch metadata (title, abstract, authors) via arXiv API — no files are downloaded.
- **ARXIV_MAX_DOWNLOAD = 5** — Maximum number of PDFs to download when `ARXIV_DOWNLOAD = true`.
- **REVIEWER_BACKEND = `codex`** — Default reviewer route for optional literature synthesis cross-checks. Use `--reviewer: oracle-pro` only when explicitly requested; if Oracle is unavailable, warn and continue with Codex xhigh or local synthesis.

> 💡 Overrides:
> - `/research-lit "topic" — paper library: ~/my_papers/` — custom local PDF path
> - `/research-lit "topic" — sources: zotero, local` — only search Zotero + local PDFs
> - `/research-lit "topic" — sources: web` — only search the web (skip all local)
> - `/research-lit "topic" — sources: web, semantic-scholar` — also search Semantic Scholar for published venue papers
> - `/research-lit "topic" — sources: all, deepxiv` — use default sources plus DeepXiv
> - `/research-lit "topic" — arxiv download: true` — download top relevant arXiv PDFs
> - `/research-lit "topic" — arxiv download: true, max download: 10` — download up to 10 PDFs

## Data Sources

This skill checks multiple sources **in priority order**.

### Source Selection

Parse `$ARGUMENTS` for a `— sources:` directive:
- **If `— sources:` is specified**: Only search the listed sources (comma-separated). Valid values: `zotero`, `obsidian`, `local`, `web`, `semantic-scholar`, `deepxiv`, `exa`, `gemini`, `openalex`, `all`.
- **If not specified**: Default to `all` — search every available source in priority order (`semantic-scholar`, `deepxiv`, `exa`, `gemini`, and `openalex` are excluded from `all`; they must be explicitly listed).

Examples:
```
/research-lit "diffusion models"                        → all (default)
/research-lit "diffusion models" — sources: all         → all
/research-lit "diffusion models" — sources: zotero      → Zotero only
/research-lit "diffusion models" — sources: zotero, web → Zotero + web
/research-lit "diffusion models" — sources: local       → local PDFs only
/research-lit "topic" — sources: obsidian, local, web   → skip Zotero
/research-lit "topic" — sources: web, semantic-scholar  → web + Semantic Scholar API
/research-lit "topic" — sources: deepxiv                → DeepXiv only
/research-lit "topic" — sources: all, deepxiv           → default sources + DeepXiv
/research-lit "topic" — sources: all, semantic-scholar  → default sources + Semantic Scholar API
/research-lit "topic" — sources: exa                    → Exa only (broad web + content extraction)
/research-lit "topic" — sources: all, exa               → default sources + Exa web search
/research-lit "topic" — sources: gemini                 → Gemini only (AI-powered broad discovery)
/research-lit "topic" — sources: all, gemini            → default sources + Gemini discovery
/research-lit "topic" — sources: openalex               → OpenAlex only (open citation graph + institutions)
/research-lit "topic" — sources: all, openalex          → default sources + OpenAlex citation graph
```

### Source Table

| Priority | Source | ID | How to detect | What it provides |
|----------|--------|----|---------------|-----------------|
| 1 | **Zotero** (via MCP) | `zotero` | Try calling any `mcp__zotero__*` tool — if unavailable, skip | Collections, tags, annotations, PDF highlights, BibTeX, semantic search |
| 2 | **Obsidian** (via MCP) | `obsidian` | Try calling any `mcp__obsidian-vault__*` tool — if unavailable, skip | Research notes, paper summaries, tagged references, wikilinks |
| 3 | **Local PDFs** | `local` | `Glob: papers/**/*.pdf, literature/**/*.pdf` | Raw PDF content (first 3 pages) |
| 4 | **Web search** | `web` | Always available (WebSearch) | arXiv, Semantic Scholar, Google Scholar |
| 5 | **Semantic Scholar API** | `semantic-scholar` | `$S2_FETCHER` resolves (canonical name `semantic_scholar_fetch.py`, per integration-contract §2 Codex chain) | Published venue papers (IEEE, ACM, Springer) with structured metadata: citation counts, venue info, TLDR. **Only runs when explicitly requested** |
| 6 | **DeepXiv CLI** | `deepxiv` | `$DEEPXIV_FETCHER` resolves (canonical name `deepxiv_fetch.py`, per integration-contract §2) **and** `deepxiv` CLI present | Progressive paper retrieval: search, brief, head, section, trending, web search. **Only runs when explicitly requested** |
| 7 | **Exa Search** | `exa` | `$EXA_FETCHER` resolves (canonical name `exa_search.py`, per integration-contract §2); fetcher handles `exa-py` SDK + API key internally | AI-powered broad web search with content extraction (highlights, text, summaries). Covers blogs, docs, news, companies, and research papers beyond arXiv/S2. **Only runs when explicitly requested** |
| 8 | **Gemini** (MCP / CLI) | `gemini` | `mcp__gemini-cli__ask-gemini` is available, or `gemini` CLI is installed | AI-powered broad literature discovery that decomposes topics into sub-problems, aliases, and variants. **Only runs when explicitly requested** |
| 9 | **OpenAlex** | `openalex` | `$OPENALEX_FETCHER` resolves (canonical name `openalex_fetch.py`, per integration-contract §2 Codex chain) and Python `requests` is importable | Open citation graph with institutional affiliations, funding data, and broad work metadata. **Only runs when explicitly requested** |

> If the user explicitly requests Zotero or Obsidian and that source is not configured, stop and tell the user how to enable it. Only sources that were not requested may be skipped silently.

## Workflow

### Per-source/per-paper fan-out

Retrieval and extraction are breadth-bound. Use fresh `spawn_agent` shards when
delegation is available, or the same work sequentially otherwise. Every shard
is read-only and returns
`{"shard_id": ..., "entries": [{"payload": ..., "dedup_key": "<DOI/arXiv/id>"}]}`.
The parent invokes every resolved source, unions results, mechanically dedups on
canonical IDs, and writes once. Shards do not rank paper quality. Source
verification remains deterministic; optional Codex synthesis review is
same-family provisional. See
[`fan-out-pattern.md`](../shared-references/fan-out-pattern.md).

### Step 0a: Search Zotero Library (if available)

**If the user explicitly requested Zotero and the Zotero MCP is not configured, stop and ask the user to configure it. Otherwise skip this step entirely.**

Try calling a Zotero MCP tool (e.g., search). If it succeeds:

1. **Search by topic**: Use the Zotero search tool to find papers matching the research topic
2. **Read collections**: Check if the user has a relevant collection/folder for this topic
3. **Extract annotations**: For highly relevant papers, pull PDF highlights and notes — these represent what the user found important
4. **Export BibTeX**: Get citation data for relevant papers (useful for `/paper-write` later)
5. **Compile results**: For each relevant Zotero entry, extract:
   - Title, authors, year, venue
   - User's annotations/highlights (if any)
   - Tags the user assigned
   - Which collection it belongs to

> 📚 Zotero annotations are gold — they show what the user personally highlighted as important, which is far more valuable than generic summaries.

### Step 0b: Search Obsidian Vault (if available)

**If the user explicitly requested Obsidian and the Obsidian MCP is not configured, stop and ask the user to configure it. Otherwise skip this step entirely.**

Try calling an Obsidian MCP tool (e.g., search). If it succeeds:

1. **Search vault**: Search for notes related to the research topic
2. **Check tags**: Look for notes tagged with relevant topics (e.g., `#diffusion-models`, `#paper-review`)
3. **Read research notes**: For relevant notes, extract the user's own summaries and insights
4. **Follow links**: If notes link to other relevant notes (wikilinks), follow them for additional context
5. **Compile results**: For each relevant note:
   - Note title and path
   - User's summary/insights
   - Links to other notes (research graph)
   - Any frontmatter metadata (paper URL, status, rating)

> 📝 Obsidian notes represent the user's **processed understanding** — more valuable than raw paper content for understanding their perspective.

### Step 0c: Scan Local Paper Library

Before searching online, check if the user already has relevant papers locally:

1. **Locate library**: Check PAPER_LIBRARY paths for PDF files
   ```
   Glob: papers/**/*.pdf, literature/**/*.pdf
   ```

2. **De-duplicate against Zotero**: If Step 0a found papers, skip any local PDFs already covered by Zotero results (match by filename or title).

3. **Filter by relevance**: Match filenames and first-page content against the research topic. Skip clearly unrelated papers.

4. **Summarize relevant papers**: For each relevant local PDF (up to MAX_LOCAL_PAPERS):
   - Read first 3 pages (title, abstract, intro)
   - Extract: title, authors, year, core contribution, relevance to topic
   - Flag papers that are directly related vs tangentially related

5. **Build local knowledge base**: Compile summaries into a "papers you already have" section. This becomes the starting point — external search fills the gaps.

> 📚 If no local papers are found, skip to Step 1. If the user has a comprehensive local collection, the external search can be more targeted (focus on what's missing).

### Step 1: Search (external)
- Use WebSearch to find recent papers on the topic
- Check arXiv, Semantic Scholar, Google Scholar
- Focus on papers from last 2 years unless studying foundational work
- **De-duplicate**: Skip papers already found in Zotero, Obsidian, or local library

**arXiv API search** (always runs, no download by default):

Resolve `$ARXIV_FETCHER` via the canonical strict-safe Codex chain
(see [`shared-references/integration-contract.md`](../shared-references/integration-contract.md) §2):

```bash
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
ARXIV_FETCHER=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/arxiv_fetch.py" ] && ARXIV_FETCHER="$ARIS_REPO/tools/arxiv_fetch.py"
[ -z "$ARXIV_FETCHER" ] && [ -f tools/arxiv_fetch.py ] && ARXIV_FETCHER="tools/arxiv_fetch.py"
[ -z "$ARXIV_FETCHER" ] && [ -f ~/.codex/skills/arxiv/arxiv_fetch.py ] && ARXIV_FETCHER="$HOME/.codex/skills/arxiv/arxiv_fetch.py"

if [ -n "$ARXIV_FETCHER" ]; then
  # Search arXiv API for structured results (title, abstract, authors, categories).
  if python3 "$ARXIV_FETCHER" search "QUERY" --max 10; then
    echo "D2 contribution: arxiv (helper invocation exit 0)" >&2
  else
    echo "WARN: arxiv_fetch.py invocation failed; D2 aggregate continues with WebSearch results." >&2
  fi
else
  echo "WARN: arxiv_fetch.py not resolved; falling back to WebSearch for arXiv hits." >&2
fi
```

If `$ARXIV_FETCHER` is empty (D2 graceful degradation), fall back to WebSearch for arXiv (same as before).

The arXiv API returns structured metadata (title, abstract, full author list, categories, dates) — richer than WebSearch snippets. Merge these results with WebSearch findings and de-duplicate.

**Semantic Scholar API search** (only when `semantic-scholar` is in sources):

When the user explicitly requests `— sources: semantic-scholar` or `— sources: web, semantic-scholar`, search for published venue papers beyond arXiv:

```bash
# Re-resolve $ARIS_REPO + $S2_FETCHER (SKILL bash blocks may run in separate shells).
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
S2_FETCHER=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/semantic_scholar_fetch.py" ] && S2_FETCHER="$ARIS_REPO/tools/semantic_scholar_fetch.py"
[ -z "$S2_FETCHER" ] && [ -f tools/semantic_scholar_fetch.py ] && S2_FETCHER="tools/semantic_scholar_fetch.py"
[ -z "$S2_FETCHER" ] && [ -f ~/.codex/skills/semantic-scholar/semantic_scholar_fetch.py ] && S2_FETCHER="$HOME/.codex/skills/semantic-scholar/semantic_scholar_fetch.py"

if [ -n "$S2_FETCHER" ]; then
    if python3 "$S2_FETCHER" search "QUERY" --max 10 --fields title,authors,year,venue,citationCount,externalIds,tldr,url; then
      echo "D2 contribution: semantic_scholar (helper invocation exit 0)" >&2
    else
      echo "WARN: semantic_scholar_fetch.py invocation failed; D2 aggregate continues." >&2
    fi
else
    echo "Semantic Scholar unavailable: $S2_FETCHER unresolved; skipping this optional source." >&2
fi
```

Why use Semantic Scholar? Many IEEE/ACM journal papers are not on arXiv. S2 fills the gap for published venue-only papers with citation counts and venue metadata.

De-duplication between arXiv and S2:
- Match by arXiv ID first (`externalIds.ArXiv`), then normalized title.
- If a paper appears in both and S2 has venue / DOI / citation metadata, use S2 as authoritative metadata while keeping the arXiv PDF link.
- S2 results without `externalIds.ArXiv` are venue-only papers and should be preserved as unique value.

**DeepXiv search** (only when `deepxiv` is in sources):

When the user explicitly requests `— sources: deepxiv` (or includes `deepxiv` in a combined source list), use the DeepXiv adapter for progressive retrieval:

```bash
# Re-resolve $ARIS_REPO + $DEEPXIV_FETCHER (SKILL bash blocks may run in separate shells).
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
DEEPXIV_FETCHER=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/deepxiv_fetch.py" ] && DEEPXIV_FETCHER="$ARIS_REPO/tools/deepxiv_fetch.py"
[ -z "$DEEPXIV_FETCHER" ] && [ -f tools/deepxiv_fetch.py ] && DEEPXIV_FETCHER="tools/deepxiv_fetch.py"
[ -z "$DEEPXIV_FETCHER" ] && [ -f ~/.codex/skills/deepxiv/deepxiv_fetch.py ] && DEEPXIV_FETCHER="$HOME/.codex/skills/deepxiv/deepxiv_fetch.py"

if [ -n "$DEEPXIV_FETCHER" ]; then
    if python3 "$DEEPXIV_FETCHER" search "QUERY" --max 10; then
      echo "D2 contribution: deepxiv (helper invocation exit 0)" >&2
      python3 "$DEEPXIV_FETCHER" paper-brief ARXIV_ID || echo "WARN: deepxiv paper-brief failed" >&2
      python3 "$DEEPXIV_FETCHER" paper-head ARXIV_ID || echo "WARN: deepxiv paper-head failed" >&2
      python3 "$DEEPXIV_FETCHER" paper-section ARXIV_ID "Experiments" || echo "WARN: deepxiv paper-section failed" >&2
    else
      echo "WARN: deepxiv_fetch.py search invocation failed; D2 aggregate continues." >&2
    fi
elif command -v deepxiv >/dev/null 2>&1; then
    deepxiv search "QUERY" --limit 10 --format json
    deepxiv paper ARXIV_ID --brief --format json
    deepxiv paper ARXIV_ID --head --format json
    deepxiv paper ARXIV_ID --section "Experiments" --format json
    echo "D2 contribution: deepxiv (CLI fallback)" >&2
else
    echo "DeepXiv unavailable: $DEEPXIV_FETCHER unresolved and no deepxiv CLI; skipping this optional source." >&2
fi
```

If `deepxiv_fetch.py` or the `deepxiv` CLI is unavailable, skip this source gracefully and continue with the remaining requested sources.

**De-duplication against other sources**:
- Match by arXiv ID first
- Fall back to normalized title when needed
- Keep one canonical paper entry and record `deepxiv` as an additional source when it overlaps with web/arXiv findings

**Exa search** (only when `exa` is in sources):

When the user explicitly requests `— sources: exa` (or includes `exa` in a combined source list), use the Exa tool for broad AI-powered web search with content extraction:

```bash
# Re-resolve $ARIS_REPO + $EXA_FETCHER (SKILL bash blocks may run in separate shells).
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
EXA_FETCHER=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/exa_search.py" ] && EXA_FETCHER="$ARIS_REPO/tools/exa_search.py"
[ -z "$EXA_FETCHER" ] && [ -f tools/exa_search.py ] && EXA_FETCHER="tools/exa_search.py"
[ -z "$EXA_FETCHER" ] && [ -f ~/.codex/skills/exa-search/exa_search.py ] && EXA_FETCHER="$HOME/.codex/skills/exa-search/exa_search.py"

if [ -n "$EXA_FETCHER" ]; then
  exa_contributed=false
  # Search for research papers with highlights.
  if python3 "$EXA_FETCHER" search "QUERY" --max 10 --category "research paper" --content highlights; then
    exa_contributed=true
  else
    echo "WARN: exa_search.py research-paper invocation failed; D2 aggregate continues." >&2
  fi
  # Search for broader web content (blogs, docs, news).
  if python3 "$EXA_FETCHER" search "QUERY" --max 10 --content highlights; then
    exa_contributed=true
  else
    echo "WARN: exa_search.py broad-web invocation failed; D2 aggregate continues." >&2
  fi
  [ "$exa_contributed" = "true" ] && echo "D2 contribution: exa (at least one invocation exit 0)" >&2
else
  echo "Exa unavailable: \$EXA_FETCHER unresolved; skipping this optional source." >&2
fi
```

If `exa_search.py` or the `exa-py` SDK is unavailable, skip this source gracefully and continue with the remaining requested sources.

**De-duplication against other sources**:
- Match by URL first, then normalized title
- If Exa returns an arXiv paper already found by other sources, prefer structured metadata from arXiv/S2
- Exa results from non-academic domains (blogs, docs, news) are unique value not covered by other sources

**Gemini search** (only when `gemini` is in sources):

When the user explicitly requests `— sources: gemini` (or includes `gemini` in a combined source list), use Gemini for AI-powered broad literature discovery.

**Priority 1 — Gemini MCP** (preferred): Call `mcp__gemini-cli__ask-gemini` with the search prompt:

```
mcp__gemini-cli__ask-gemini({
  prompt: 'You are a research literature scout. Search comprehensively for papers on: "QUERY"

IMPORTANT CONSTRAINTS:
1. Search from MULTIPLE angles — decompose the topic into sub-problems, aliases, neighboring tasks, and common benchmark/settings variants.
2. Prefer papers that are genuinely relevant, not merely keyword-adjacent.
3. Include top venues, journals, surveys, recent preprints, and papers with code when available.
4. Focus on papers from 2022 onward unless older foundational work is necessary.

For EACH paper found, provide ALL of the following:
- Title: [exact title]
- Authors: [full author list]
- Year: [publication year]
- Venue: [exact conference/journal name + year, or "arXiv preprint"]
- arXiv ID: [format 2401.12345, or "N/A"]
- DOI: [if available, or "N/A"]
- Code URL: [GitHub/GitLab link if available, or "No code"]
- Summary: [one-sentence core contribution]

Find at least 15 papers.',
  model: 'auto-gemini-3'
})
```

**Priority 2 — Gemini CLI fallback** (if MCP unavailable): Use `gemini -p "...same prompt..." 2>/dev/null` via Bash (timeout: 120s).

If both MCP and CLI are unavailable, skip this source gracefully and continue with the remaining requested sources.

**Why use Gemini?** Gemini provides AI-driven discovery that goes beyond keyword matching — it decomposes topics, explores naming variants, and surfaces papers that traditional API-based searches may miss. It fills a different retrieval niche from structured database queries.

**De-duplication against other sources**:
- Match by arXiv ID first, DOI second, normalized title third
- If Gemini returns a paper already found by Semantic Scholar, prefer S2's citation count and venue metadata
- If Gemini returns a paper already found by arXiv, prefer arXiv's structured metadata
- Do not use Gemini-reported citation counts; they may be inaccurate

**OpenAlex search** (only when `openalex` is in sources):

When the user explicitly requests `— sources: openalex` (or includes `openalex` in a combined source list), use OpenAlex API for comprehensive academic metadata:

```bash
# Re-resolve $ARIS_REPO + $OPENALEX_FETCHER (SKILL bash blocks may run in separate shells).
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
OPENALEX_FETCHER=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/openalex_fetch.py" ] && OPENALEX_FETCHER="$ARIS_REPO/tools/openalex_fetch.py"
[ -z "$OPENALEX_FETCHER" ] && [ -f tools/openalex_fetch.py ] && OPENALEX_FETCHER="tools/openalex_fetch.py"
[ -z "$OPENALEX_FETCHER" ] && [ -f ~/.codex/skills/openalex/openalex_fetch.py ] && OPENALEX_FETCHER="$HOME/.codex/skills/openalex/openalex_fetch.py"

# Skip OpenAlex when the helper or its optional dependency is unavailable.
if [ -z "$OPENALEX_FETCHER" ] || ! python3 -c "import requests" >/dev/null 2>&1; then
  echo "OpenAlex source not available (openalex_fetch.py unresolved or 'requests' module missing); skipping." >&2
else
  if python3 "$OPENALEX_FETCHER" search "QUERY" --max 10 \
      --year "2022-" \
      --type article \
      --sort relevance; then
    echo "D2 contribution: openalex (helper invocation exit 0)" >&2
  else
    echo "WARN: openalex_fetch.py invocation failed; D2 aggregate continues with remaining sources." >&2
  fi
fi
```

If `openalex_fetch.py` is not found or the `requests` module is missing, skip this source gracefully and continue with the remaining requested sources.

**Why use OpenAlex?** OpenAlex provides an open citation graph, institutional affiliations, funding data, and broad work metadata across disciplines.

**De-duplication against other sources**:
- Match by DOI first, then arXiv ID, then normalized title
- If OpenAlex and Semantic Scholar overlap, prefer S2 for citation counts and venue metadata
- If OpenAlex and arXiv overlap, prefer arXiv's PDF link and metadata while retaining OpenAlex's citation and institution data

**Optional PDF download** (only when `ARXIV_DOWNLOAD = true`):

After all sources are searched and papers are ranked by relevance:
```bash
# Re-resolve $ARXIV_FETCHER (SKILL bash blocks may run in separate shells).
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
ARXIV_FETCHER=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/arxiv_fetch.py" ] && ARXIV_FETCHER="$ARIS_REPO/tools/arxiv_fetch.py"
[ -z "$ARXIV_FETCHER" ] && [ -f tools/arxiv_fetch.py ] && ARXIV_FETCHER="tools/arxiv_fetch.py"
[ -z "$ARXIV_FETCHER" ] && [ -f ~/.codex/skills/arxiv/arxiv_fetch.py ] && ARXIV_FETCHER="$HOME/.codex/skills/arxiv/arxiv_fetch.py"

# Download top N most relevant arXiv papers; skip silently if helper unresolved.
[ -n "$ARXIV_FETCHER" ] && python3 "$ARXIV_FETCHER" download ARXIV_ID --dir papers/
```
- Only download papers ranked in the top ARXIV_MAX_DOWNLOAD by relevance
- Skip papers already in the local library
- 1-second delay between downloads (rate limiting)
- Verify each PDF > 10 KB

### Step 2: Analyze Each Paper
For each relevant paper (from all sources), extract:
- **Problem**: What gap does it address?
- **Method**: Core technical contribution (1-2 sentences)
- **Results**: Key numbers/claims
- **Relevance**: How does it relate to our work?
- **Source**: Where we found it (Zotero/Obsidian/local/web) — helps user know what they already have vs what's new

### Step 3: Synthesize
- Group papers by approach/theme
- Identify consensus vs disagreements in the field
- Find gaps that our work could fill
- If Obsidian notes exist, incorporate the user's own insights into the synthesis

### Step 4: Output
Present as a structured literature table:

```
| Paper | Venue | Method | Key Result | Relevance to Us | Source |
|-------|-------|--------|------------|-----------------|--------|
```

Plus a narrative summary of the landscape (3-5 paragraphs).

If Zotero BibTeX was exported, include a `references.bib` snippet for direct use in paper writing.

### Step 5: Save (if requested)
- Save paper PDFs to `literature/` or `papers/`
- Update related work notes in project memory
- If Obsidian is available, optionally create a literature review note in the vault

If `— composed: <canonical-report-path>` is present, return/fold the table,
landscape, and gaps into that report instead of writing a standalone literature
summary. Standalone remains the default; `— standalone` wins and an existing
report never activates composed mode. Keep reusable PDFs/BibTeX and traces. See
[`output-composition.md`](../shared-references/output-composition.md).

### Step 6: Update Research Wiki

If the project has an active research wiki, update it after producing the literature review:

1. Add or update the topic page with the final paper table, grouped themes, and open gaps.
2. Link each paper to its canonical source and local PDF path if available.
3. Record which sources were used: Zotero, Obsidian, local PDFs, arXiv, Semantic Scholar, DeepXiv, Exa, or broader web.
4. Mark unresolved search gaps and papers requiring follow-up reading.
5. Follow the wiki integration contract in [`shared-references/integration-contract.md`](../shared-references/integration-contract.md).
6. When the wiki helper is available, rebuild `query_pack.md` after updating literature entries so `/idea-creator` can reuse the latest gaps and failed directions.

If the wiki path or format is unclear, ask before writing. Do not invent a wiki location.

## Key Rules
- Always include paper citations (authors, year, venue)
- Distinguish between peer-reviewed and preprints
- Be honest about limitations of each paper
- Note if a paper directly competes with or supports our approach
- If a user-requested Zotero or Obsidian source is unavailable, stop and report the missing configuration instead of silently degrading.
- Only unrequested optional sources may be skipped automatically.
- Zotero/Obsidian tools may have different names depending on how the user configured the MCP server (e.g., `mcp__zotero__search` or `mcp__zotero-mcp__search_items`). Try the most common patterns and adapt.
