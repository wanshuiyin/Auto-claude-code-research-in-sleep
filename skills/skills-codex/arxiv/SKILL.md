---
name: "arxiv"
description: "Search, download, and summarize academic papers from arXiv. Use when user says \"search arxiv\", \"download paper\", \"fetch arxiv\", \"arxiv search\", \"get paper pdf\", or wants to find and save papers from arXiv to the local paper library."
---

# arXiv Paper Search & Download

Search topic or arXiv paper ID: $ARGUMENTS

## Constants

- **PAPER_DIR** - Local directory to save downloaded PDFs. Default: `papers/` in the current project directory.
- **MAX_RESULTS = 10** - Default number of search results.
- **ARXIV_FETCHER** — canonical name `arxiv_fetch.py`, resolved per
  [`shared-references/integration-contract.md`](../shared-references/integration-contract.md) §2
  (Codex-side chain: `$ARIS_REPO/tools/` → `tools/` → `~/.codex/skills/arxiv/`).
- **ARIS_PY_RUNNER** — `tools/uv_run_helper.sh`; it executes the helper with the
  locked `tools/uv-runtime` project. Never invoke the system `python3`.
  Policy D1 — if either helper is unresolved, use the web retrieval fallback or
  stop with explicit remediation; do not run inline Python.

> Overrides (append to arguments):
> - `/arxiv "attention mechanism" - max: 20` - return up to 20 results
> - `/arxiv "2301.07041" - download` - download a specific paper by ID
> - `/arxiv "query" - dir: literature/` - save PDFs to a custom directory
> - `/arxiv "query" - download: all` - download all result PDFs

## Workflow

### Step 1: Parse Arguments

Parse `$ARGUMENTS` for directives:

- **Query or ID**: main search term or a bare arXiv ID such as `2301.07041` or `cs/0601001`
- **`- max: N`**: override MAX_RESULTS (e.g., `- max: 20`)
- **`- dir: PATH`**: override PAPER_DIR (e.g., `- dir: literature/`)
- **`- download`**: download the first result's PDF after listing
- **`- download: all`**: download PDFs for all results

If the argument matches an arXiv ID pattern (`YYMM.NNNNN` or `category/NNNNNNN`), skip the search and go directly to Step 3.

### Step 2: Search arXiv

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
ARIS_PY_RUNNER=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/uv_run_helper.sh" ] && ARIS_PY_RUNNER="$ARIS_REPO/tools/uv_run_helper.sh"
[ -z "$ARIS_PY_RUNNER" ] && [ -f tools/uv_run_helper.sh ] && ARIS_PY_RUNNER="tools/uv_run_helper.sh"
```

**If both paths are non-empty**, run:

```bash
bash "$ARIS_PY_RUNNER" "$ARXIV_FETCHER" search "QUERY" --max MAX_RESULTS
```

If either path is unresolved, report it and use the available web retrieval tool
for discovery. Do not silently switch to an ambient Python environment.

Present results as a table:

```text
| # | arXiv ID   | Title               | Authors        | Date       | Category |
|---|------------|---------------------|----------------|------------|----------|
| 1 | 2301.07041 | Attention Is All... | Vaswani et al. | 2017-06-12 | cs.LG    |
```

### Step 3: Fetch Details for a Specific ID

When a single paper ID is requested (either directly or from Step 2):

```bash
[ -n "$ARXIV_FETCHER" ] && [ -n "$ARIS_PY_RUNNER" ] && \
  bash "$ARIS_PY_RUNNER" "$ARXIV_FETCHER" search "id:ARXIV_ID" --max 1
```

Display: title, all authors, categories, full abstract, published date, PDF URL, abstract URL.

### Step 4: Download PDFs

When download is requested, for each paper ID to download:

```bash
[ -n "$ARXIV_FETCHER" ] && [ -n "$ARIS_PY_RUNNER" ] && \
  bash "$ARIS_PY_RUNNER" "$ARXIV_FETCHER" download ARXIV_ID --dir PAPER_DIR
```

After each download:

- Confirm file size > 10 KB (reject smaller files - likely an error HTML page)
- Add a 1-second delay between consecutive downloads to avoid rate limiting
- Report: `Downloaded: papers/2301.07041.pdf (842 KB)`

### Step 5: Summarize

For each paper (downloaded or fetched by API):

```markdown
## [Title]

- **arXiv**: [ID] - [abs_url]
- **Authors**: [full author list]
- **Date**: [published]
- **Categories**: [cs.LG, cs.AI, ...]
- **Abstract**: [full abstract]
- **Key contributions** (extracted from abstract):
  - [contribution 1]
  - [contribution 2]
  - [contribution 3]
- **Local PDF**: papers/[ID].pdf (if downloaded)
```

### Step 6: Update Research Wiki (if active)

If the project has an active research wiki, update it after search or download:

1. Add each accepted paper to the canonical paper table.
2. Record arXiv ID, title, authors, abstract URL, PDF URL, local PDF path, and source query.
3. Follow the integration contract in [`shared-references/integration-contract.md`](../shared-references/integration-contract.md).
4. If the wiki path or schema is unclear, ask before writing rather than inventing a location.

### Step 7: Final Output

Summarize what was done:

- `Found N papers for "query"`
- `Downloaded: papers/2301.07041.pdf (842 KB)` (for each download)
- Any warnings (rate limit hit, file too small, already exists)

Suggest follow-up skills:

```text
/research-lit "topic"     - multi-source review: Zotero + Obsidian + local PDFs + web
/novelty-check "idea"     - verify your idea is novel against these papers
```

## Key Rules

- Always show the arXiv ID prominently - users need it for citations and reproducibility
- Verify downloaded PDFs: file must be > 10 KB; warn and delete if smaller
- Rate limit: wait 1 second between consecutive PDF downloads; retry once after 5 seconds on HTTP 429
- Never overwrite an existing PDF at the same path - skip it and report "already exists"
- Handle both arXiv ID formats: new (`2301.07041`) and old (`cs/0601001`)
- PAPER_DIR is created automatically if it does not exist
- If the arXiv API is unreachable, report the error clearly and suggest using `/research-lit` with `- sources: web` as a fallback
