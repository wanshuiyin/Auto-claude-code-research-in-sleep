---
name: research-lit
description: Search and analyze research papers, find related work, summarize key ideas. Use when user says "find papers", "related work", "literature review", "what does this paper say", or needs to understand academic papers.
argument-hint: [paper-topic-or-url]
allowed-tools: Bash(*), Read, Glob, Grep, WebSearch, WebFetch, Write, Agent, mcp__zotero__*, mcp__obsidian-vault__*
---

# Research Literature Review

Research topic: $ARGUMENTS

## Constants


- **REVIEWER_BACKEND = `codex`** — Default: Codex MCP (xhigh). Override with `— reviewer: oracle-pro` for GPT-5.4 Pro via Oracle MCP. See `shared-references/reviewer-routing.md`.
- **PAPER_LIBRARY** — Local directory containing user's paper collection (PDFs). Check these paths in order:
  1. `papers/` in the current project directory
  2. `literature/` in the current project directory
  3. Custom path specified by user in `CLAUDE.md` under `## Paper Library`
- **MAX_LOCAL_PAPERS = 20** — Maximum number of local PDFs to scan (read first 3 pages each). If more are found, prioritize by filename relevance to the topic.
- **ARXIV_DOWNLOAD = false** — When `true`, download top 3-5 most relevant arXiv PDFs to PAPER_LIBRARY after search. When `false` (default), only fetch metadata (title, abstract, authors) via arXiv API — no files are downloaded.
- **ARXIV_MAX_DOWNLOAD = 5** — Maximum number of PDFs to download when `ARXIV_DOWNLOAD = true`.

> 💡 Overrides:
> - `/research-lit "topic" — paper library: ~/my_papers/` — custom local PDF path
> - `/research-lit "topic" — sources: zotero, local` — only search Zotero + local PDFs
> - `/research-lit "topic" — sources: zotero` — only search Zotero
> - `/research-lit "topic" — sources: web` — only search the web (skip all local)
> - `/research-lit "topic" — sources: web, semantic-scholar` — also search Semantic Scholar for published venue papers (IEEE, ACM, etc.)
> - `/research-lit "topic" — sources: deepxiv` — only search via DeepXiv progressive retrieval
> - `/research-lit "topic" — sources: all, deepxiv` — use default sources plus DeepXiv
> - `/research-lit "topic" — arxiv download: true` — download top relevant arXiv PDFs
> - `/research-lit "topic" — arxiv download: true, max download: 10` — download up to 10 PDFs

## Data Sources

This skill checks multiple sources **in priority order**. All are optional — if a source is not configured or not requested, skip it silently.

### Source Selection

Parse `$ARGUMENTS` for a `— sources:` directive:
- **If `— sources:` is specified**: Only search the listed sources (comma-separated). Valid values: `zotero`, `obsidian`, `local`, `web`, `semantic-scholar`, `deepxiv`, `exa`, `all`.
- **If not specified**: Default to `all` — search every available source in priority order (`semantic-scholar`, `deepxiv`, and `exa` are **excluded** from `all`; they must be explicitly listed).

Examples:
```
/research-lit "diffusion models"                                    → all (default, no S2)
/research-lit "diffusion models" — sources: all                     → all (default, no S2)
/research-lit "diffusion models" — sources: zotero                  → Zotero only
/research-lit "diffusion models" — sources: zotero, web             → Zotero + web
/research-lit "diffusion models" — sources: local                   → local PDFs only
/research-lit "topic" — sources: obsidian, local, web               → skip Zotero
/research-lit "topic" — sources: web, semantic-scholar              → web + S2 API (IEEE/ACM venue papers)
/research-lit "topic" — sources: deepxiv                            → DeepXiv only
/research-lit "topic" — sources: all, deepxiv                       → default sources + DeepXiv
/research-lit "topic" — sources: all, semantic-scholar              → all + S2 API
/research-lit "topic" — sources: exa                               → Exa only (broad web + content extraction)
/research-lit "topic" — sources: all, exa                          → default sources + Exa web search
```

### Source Table

| Priority | Source | ID | How to detect | What it provides |
|----------|--------|----|---------------|-----------------|
| 1 | **Zotero** (via MCP) | `zotero` | Try calling any `mcp__zotero__*` tool — if unavailable, skip | Collections, tags, annotations, PDF highlights, BibTeX, semantic search |
| 2 | **Obsidian** (via MCP) | `obsidian` | Try calling any `mcp__obsidian-vault__*` tool — if unavailable, skip | Research notes, paper summaries, tagged references, wikilinks |
| 3 | **Local PDFs** | `local` | `Glob: papers/**/*.pdf, literature/**/*.pdf` | Raw PDF content (first 3 pages) |
| 4 | **Web search** | `web` | Always available (WebSearch) | arXiv, Semantic Scholar, Google Scholar |
| 5 | **Semantic Scholar API** | `semantic-scholar` | `tools/semantic_scholar_fetch.py` exists | Published venue papers (IEEE, ACM, Springer) with structured metadata: citation counts, venue info, TLDR. **Only runs when explicitly requested** via `— sources: semantic-scholar` or `— sources: web, semantic-scholar` |
| 6 | **DeepXiv CLI** | `deepxiv` | `tools/deepxiv_fetch.py` and installed `deepxiv` CLI | Progressive paper retrieval: search, brief, head, section, trending, web search. **Only runs when explicitly requested** via `— sources: deepxiv` or `— sources: all, deepxiv` |
| 7 | **Exa Search** | `exa` | `tools/exa_search.py` and installed `exa-py` SDK | AI-powered broad web search with content extraction (highlights, text, summaries). Covers blogs, docs, news, companies, and research papers beyond arXiv/S2. **Only runs when explicitly requested** via `— sources: exa` or `— sources: all, exa` |

> **Graceful degradation**: If no MCP servers are configured, the skill works exactly as before (local PDFs + web search). Zotero and Obsidian are pure additions.

## Workflow

### Step 0a: Search Zotero Library (if available)

**Skip this step entirely if Zotero MCP is not configured.**

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

**Skip this step entirely if Obsidian MCP is not configured.**

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

Locate the fetch script and search arXiv directly:
```bash
# Try to find arxiv_fetch.py
SCRIPT=$(find tools/ -name "arxiv_fetch.py" 2>/dev/null | head -1)
# If not found, check ARIS install
[ -z "$SCRIPT" ] && SCRIPT=$(find ~/.claude/skills/arxiv/ -name "arxiv_fetch.py" 2>/dev/null | head -1)

# Search arXiv API for structured results (title, abstract, authors, categories)
python3 "$SCRIPT" search "QUERY" --max 10
```

If `arxiv_fetch.py` is not found, fall back to WebSearch for arXiv (same as before).

The arXiv API returns structured metadata (title, abstract, full author list, categories, dates) — richer than WebSearch snippets. Merge these results with WebSearch findings and de-duplicate.

**Semantic Scholar API search** (only when `semantic-scholar` is in sources):

When the user explicitly requests `— sources: semantic-scholar` (or `— sources: web, semantic-scholar`), search for published venue papers beyond arXiv:

```bash
S2_SCRIPT=$(find tools/ -name "semantic_scholar_fetch.py" 2>/dev/null | head -1)
[ -z "$S2_SCRIPT" ] && S2_SCRIPT=$(find ~/.claude/skills/semantic-scholar/ -name "semantic_scholar_fetch.py" 2>/dev/null | head -1)

# Search for published CS/Engineering papers with quality filters
python3 "$S2_SCRIPT" search "QUERY" --max 10 \
  --fields-of-study "Computer Science,Engineering" \
  --publication-types "JournalArticle,Conference"
```

If `semantic_scholar_fetch.py` is not found, skip silently.

**Why use Semantic Scholar?** Many IEEE/ACM journal papers are NOT on arXiv. S2 fills the gap for published venue-only papers with citation counts and venue metadata.

**De-duplication between arXiv and S2**: Match by arXiv ID (S2 returns `externalIds.ArXiv`):
- If a paper appears in both: check S2's `venue`/`publicationVenue` — if it has been published in a journal/conference (e.g. IEEE TWC, JSAC), use S2's metadata (venue, citationCount, DOI) as the authoritative version, since the published version supersedes the preprint. Keep the arXiv PDF link for download.
- If the S2 match has no venue (still just a preprint indexed by S2): keep the arXiv version as-is.
- S2 results without `externalIds.ArXiv` are **venue-only papers** not on arXiv — these are the unique value of this source.

**DeepXiv search** (only when `deepxiv` is in sources):

When the user explicitly requests `— sources: deepxiv` (or includes `deepxiv` in a combined source list), use the DeepXiv adapter for progressive retrieval:

```bash
python3 tools/deepxiv_fetch.py search "QUERY" --max 10
```

Then deepen only for the most relevant papers:

```bash
python3 tools/deepxiv_fetch.py paper-brief ARXIV_ID
python3 tools/deepxiv_fetch.py paper-head ARXIV_ID
python3 tools/deepxiv_fetch.py paper-section ARXIV_ID "Experiments"
```

If `tools/deepxiv_fetch.py` or the `deepxiv` CLI is unavailable, skip this source gracefully and continue with the remaining requested sources.

**Why use DeepXiv?** It is useful when a broad search should be followed by staged reading rather than immediate full-paper loading. This reduces unnecessary context while still surfacing structure, TLDRs, and the most relevant sections.

**De-duplication against arXiv and S2**:
- Match by arXiv ID first, DOI second, normalized title third
- If DeepXiv and arXiv refer to the same preprint, keep one canonical paper row and record `deepxiv` as an additional source
- If DeepXiv overlaps with S2 on a published paper, prefer S2 venue/citation metadata in the final table, but keep DeepXiv-derived section notes when they add value

**Exa search** (only when `exa` is in sources):

When the user explicitly requests `— sources: exa` (or includes `exa` in a combined source list), use the Exa tool for broad AI-powered web search with content extraction:

```bash
EXA_SCRIPT=$(find tools/ -name "exa_search.py" 2>/dev/null | head -1)

# Search for research papers with highlights
python3 "$EXA_SCRIPT" search "QUERY" --max 10 --category "research paper" --content highlights

# Search for broader web content (blogs, docs, news)
python3 "$EXA_SCRIPT" search "QUERY" --max 10 --content highlights
```

If `tools/exa_search.py` or the `exa-py` SDK is unavailable, skip this source gracefully and continue with the remaining requested sources.

**Why use Exa?** Exa provides AI-powered search across the broader web (blogs, documentation, news, company pages) with built-in content extraction. It fills a gap between academic databases (arXiv, S2) and generic WebSearch by returning richer content with each result.

**De-duplication against arXiv, S2, and DeepXiv**:
- Match by URL first, then normalized title
- If Exa returns an arXiv paper already found by arXiv/S2, prefer the structured metadata from those sources
- Exa results from non-academic domains (blogs, docs, news) are unique value not covered by other sources

**Optional PDF download** (only when `ARXIV_DOWNLOAD = true`):

After all sources are searched and papers are ranked by relevance:
```bash
# Download top N most relevant arXiv papers
python3 "$SCRIPT" download ARXIV_ID --dir papers/
```
- Only download papers ranked in the top ARXIV_MAX_DOWNLOAD by relevance
- Skip papers already in the local library
- 1-second delay between downloads (rate limiting)
- Verify each PDF > 10 KB

### Step 1.5: Verify References (anti-hallucination)

**This step is mandatory.** Before analyzing papers, verify that every paper found in Step 1 actually exists. LLM-based search agents can hallucinate plausible-looking paper titles, arXiv IDs, and DOIs. See `shared-references/citation-discipline.md` for the full verification protocol.

**Batch verification** (run as a single script to verify all papers at once):

```python
import urllib.request, json, time, urllib.parse, sys

def verify_arxiv_batch(ids, batch_size=40):
    """Verify arXiv IDs exist via arXiv API. Returns {id: bool}."""
    results = {}
    for i in range(0, len(ids), batch_size):
        batch = [x for x in ids[i:i+batch_size] if x]
        url = f"https://export.arxiv.org/api/query?id_list={','.join(batch)}&max_results={len(batch)}"
        try:
            resp = urllib.request.urlopen(url, timeout=30).read().decode()
            for aid in batch:
                results[aid] = f"<id>http://arxiv.org/abs/{aid}</id>" in resp
        except Exception as e:
            for aid in batch:
                results[aid] = None  # unknown
        time.sleep(1)
    return results

def verify_doi(doi):
    """Verify DOI exists via CrossRef. Returns True/False."""
    try:
        url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
        req = urllib.request.Request(url, headers={"User-Agent": "ARIS-ResearchLit/1.0 (mailto:research@example.com)"})
        urllib.request.urlopen(req, timeout=15)
        return True
    except:
        return False

def verify_title_s2(title):
    """Search Semantic Scholar to verify paper exists by title. Returns (bool, metadata)."""
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(title[:200])}&limit=3&fields=title,year,venue,externalIds"
        resp = json.loads(urllib.request.urlopen(url, timeout=15).read())
        for p in resp.get("data", []):
            # Fuzzy title match: lowercase, strip punctuation, check overlap
            t1 = ''.join(c for c in title.lower() if c.isalnum() or c == ' ')
            t2 = ''.join(c for c in p["title"].lower() if c.isalnum() or c == ' ')
            words1, words2 = set(t1.split()), set(t2.split())
            overlap = len(words1 & words2) / max(len(words1), 1)
            if overlap > 0.6:
                return True, p
        return False, None
    except:
        return False, None  # S2 rate limit or error — mark as unknown
```

**Verification rules:**

1. **arXiv papers**: Batch-verify ALL arXiv IDs via arXiv API before proceeding. Remove any ID that returns no match.
2. **DOI-only papers**: Verify each DOI via CrossRef API. If DOI fails, fall back to Semantic Scholar title search.
3. **No arXiv ID and no DOI**: Verify via Semantic Scholar title search. If S2 also fails, tag as `[UNVERIFIED]`.
4. **NEVER silently include unverified papers.** Every paper in the output must be either `✅ Verified` or `⚠️ UNVERIFIED` (with reason).
5. **NEVER fabricate DOIs.** If you don't have a real DOI from a search result or API response, leave the DOI field empty. Do not guess or reconstruct DOIs from memory.
6. **High hallucination rate trigger**: If >20% of papers fail verification, warn the user: "⚠️ High hallucination rate detected ({N}% failed). Re-running search with more specific queries."

**Output of this step**: A verified paper list with verification status:
```
✅ 2307.03172 — Lost in the Middle (arXiv confirmed)
✅ 10.1016/j.eswa.2025.128404 — AgentAI (CrossRef confirmed)
⚠️ UNVERIFIED — "Some Paper Title" (arXiv ID not found, S2 no match) → REMOVED
```

### Step 2: Analyze Each Paper
For each **verified** paper (from all sources), extract:
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

### Step 6: Update Research Wiki (if active)

**This step is optional and automatic.** Skip entirely if `research-wiki/` does not exist in the project.

```
if research-wiki/ directory exists:
    for each top relevant paper found (up to 8-12):
        1. Generate slug: python3 tools/research_wiki.py slug "<title>" --author "<last>" --year <year>
        2. Create page: research-wiki/papers/<slug>.md with structured schema
           (node_id, title, authors, year, venue, tags, one-line thesis, problem/gap,
            method, key results, limitations, reusable ingredients, open questions)
        3. Add edges to graph/edges.jsonl for relationships to existing wiki papers:
           python3 tools/research_wiki.py add_edge research-wiki/ --from "paper:<slug>" --to "<target>" --type <type> --evidence "<text>"
        4. Update gap_map.md if new gaps are identified
    Rebuild query pack:
        python3 tools/research_wiki.py rebuild_query_pack research-wiki/
    Log:
        python3 tools/research_wiki.py log research-wiki/ "research-lit ingested N papers"
else:
    skip — no wiki, no action, no error
```

## Key Rules
- Always include paper citations (authors, year, venue)
- Distinguish between peer-reviewed and preprints
- Be honest about limitations of each paper
- Note if a paper directly competes with or supports our approach
- **Never fail because a MCP server is not configured** — always fall back gracefully to the next data source
- Zotero/Obsidian tools may have different names depending on how the user configured the MCP server (e.g., `mcp__zotero__search` or `mcp__zotero-mcp__search_items`). Try the most common patterns and adapt.
- **Anti-hallucination**: Step 1.5 is mandatory. Never skip verification. Never fabricate DOIs, arXiv IDs, or paper metadata. When uncertain, leave the field empty and tag as `[UNVERIFIED]`. See `shared-references/citation-discipline.md` for the full protocol.
