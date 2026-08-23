---
name: gemini-search
description: AI-powered multi-angle literature discovery. Use when user says "gemini search", "AI literature scout", "multi-angle paper search", or wants discovery beyond exact-keyword arXiv/Semantic Scholar queries.
argument-hint: "[search-query]"
allowed-tools: Read, Write
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - **This skill was rewritten**: the upstream version required the Gemini CLI/MCP
>   (`GEMINI_API_KEY` or Google login). This edition performs the same "literature scout"
>   procedure natively: the agent decomposes the topic into sub-problems/aliases and runs
>   multi-angle **WebSearch** + **arXiv API** sweeps. If you DO have the Gemini CLI configured,
>   the upstream skill lives at `$ARIS_REPO/skills/gemini-search/SKILL.md`.
> - `/x "args"` = load `skills/x/SKILL.md` from this pack; `$ARGUMENTS` = the user's instruction text.

# AI Literature Scout (multi-angle discovery)

Search query: $ARGUMENTS

## Role & Positioning

This skill is the **AI-driven broad discovery** source:

| Skill | Source | Best for |
|-------|--------|----------|
| `/arxiv` | arXiv API | Latest preprints, exact keyword search |
| `/semantic-scholar` | S2 API | Published venue papers, citation counts |
| `/openalex` | OpenAlex API | Citation graph, affiliations, funding |
| `/exa-search` | WebSearch engine | Broad web: blogs, docs, news, companies |
| `/gemini-search` | **This scout procedure** | **Multi-angle discovery** — decomposes the topic into sub-problems, naming variants, and neighboring tasks that exact-keyword searches miss |

## Constants

- **MAX_RESULTS = 15** — Target number of papers.
- **MIN_YEAR = 2022** — Default minimum publication year. Override with `— year: 2020-`.
- **MIN_ANGLES = 4** — Minimum distinct search angles to sweep.

> Overrides (append to arguments):
> - `/gemini-search "topic" — max: 20` — request up to 20 papers
> - `/gemini-search "topic" — year: 2020-` — papers from 2020 onward
> - `/gemini-search "topic" — code-only` — only papers with open-source code
> - `/gemini-search "topic" — venues: NeurIPS,ICML,ICLR` — focus on specific venues

## Workflow

### Step 1: Parse Arguments

Parse `$ARGUMENTS` for: **query** (required), **max**, **year**, **code-only**, **venues**.

### Step 2: Decompose the Topic (the scout step)

Before searching, explicitly write out (as working notes, not final output):

1. **Sub-problems** — 2-4 constituent problems of the topic
2. **Aliases & naming variants** — synonyms, older/newer names, acronym expansions
3. **Neighboring tasks** — adjacent problems whose methods transfer
4. **Benchmark/setting variants** — common datasets, eval settings, domain-specific forms

This decomposition IS the value of this skill — do not skip it.

### Step 3: Multi-Angle Sweep

For each angle from Step 2 (at least MIN_ANGLES, cap ~8 searches total):

- **WebSearch**: `<angle phrase> paper arxiv <year hint>` — surfaces papers, blog roundups,
  "awesome" lists, and survey repos that exact keyword search misses.
- **arXiv API** (no key, for precision): 
  `http://export.arxiv.org/api/query?search_query=all:"<angle phrase>"&max_results=10&sortBy=relevance`
  via curl/python one-liner (see `/arxiv` Step 2 fallback for the exact snippet).
- If **venues** filter is set, add the venue names to the WebSearch queries.
- If **code-only**, additionally search `<angle> github code` and keep only hits with repos.

Aggregate and de-duplicate by title/arXiv ID.

### Step 4: Normalize Results

For each paper, normalize to:

```
{
  title, authors, year, venue,
  arxiv_id,    // "N/A" if not available
  doi,         // "N/A" if not available
  code_url,    // "No code" if not available
  summary      // one-sentence contribution
}
```

**Verification rule**: for any paper whose metadata came only from a web snippet (not from
the arXiv API), verify title/year via the arXiv API or `/semantic-scholar` before presenting.
Drop papers you cannot verify exist — never present a paper from memory alone.

### Step 5: Present Results

```
| # | Title | Venue | Year | Code | Summary |
|---|-------|-------|------|------|---------|
| 1 | ... | NeurIPS 2024 | 2024 | [GitHub](url) | ... |
```

For each paper, also show **arXiv ID** and **DOI** when available. Group by sub-problem
angle so the user sees the coverage map, and note angles that returned nothing.

### Step 6: Offer Follow-up

```text
/semantic-scholar "topic"    — citation counts for the found papers
/arxiv "arXiv:XXXX.XXXXX"   — fetch specific preprint details
/research-lit "topic"        — full multi-source literature review
/novelty-check "idea"       — verify novelty against literature
```

## Key Rules

- **The decomposition is mandatory** — a single-angle search defeats this skill's purpose; use `/arxiv` for that.
- **Discovery, not a database.** Always cross-verify titles/venues/years via arXiv API or `/semantic-scholar` before presenting. Never emit papers purely from model memory.
- **No citation counts from memory.** Use `/semantic-scholar` for authoritative citation data.
- **Budget**: cap at ~8 searches per invocation; prefer reformulating over exhaustive sweeps.
- If WebSearch is unavailable, fall back to arXiv-API-only sweeps and note the reduced web coverage.
