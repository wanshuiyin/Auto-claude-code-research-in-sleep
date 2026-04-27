---
name: "arxiv"
description: "Search, download, and summarize academic papers from arXiv. Use when user says \"search arxiv\", \"download paper\", \"fetch arxiv\", \"arxiv search\", \"get paper pdf\", or wants to find and save papers from arXiv to the local paper library."
---

# arXiv Paper Search & Download

Search topic or arXiv paper ID: $ARGUMENTS

## Constants

- **PAPER_DIR** - Local directory to save downloaded PDFs. Default: `papers/` in the current project directory.
- **MAX_RESULTS = 10** - Default number of search results.
- **FETCH_SCRIPT** - `$ARIS_REPO/tools/arxiv_fetch.py` from the ARIS repo recorded by the Codex install manifest. Fall back to inline Python if not found.

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

Locate the fetch script. Prefer the Codex managed install manifest when present, then fall back to the same project/global copy-install lookup style as the Claude skill:

```bash
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null)}"
export ARIS_REPO
SCRIPT=$(python3 -c "
import pathlib
import os
candidates = [
    pathlib.Path(os.environ['ARIS_REPO']) / 'tools' / 'arxiv_fetch.py'
    if os.environ.get('ARIS_REPO') else None,
    pathlib.Path('tools/arxiv_fetch.py'),
    pathlib.Path.home() / '.codex' / 'skills' / 'arxiv' / 'arxiv_fetch.py',
]
for p in [c for c in candidates if c is not None]:
    if p.exists():
        print(p)
        break
" 2>/dev/null)
```

**If SCRIPT is found**, run:

```bash
python3 "$SCRIPT" search "QUERY" --max MAX_RESULTS
```

**If SCRIPT is not found**, fall back to inline Python:

```bash
python3 - <<'PYEOF'
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2005/Atom"
query = urllib.parse.quote("QUERY")
url = (f"http://export.arxiv.org/api/query"
       f"?search_query={query}&start=0&max_results=MAX_RESULTS"
       f"&sortBy=relevance&sortOrder=descending")
with urllib.request.urlopen(url, timeout=30) as r:
    root = ET.fromstring(r.read())
papers = []
for entry in root.findall(f"{{{NS}}}entry"):
    aid = entry.findtext(f"{{{NS}}}id", "").split("/abs/")[-1].split("v")[0]
    title = (entry.findtext(f"{{{NS}}}title", "") or "").strip().replace("\n", " ")
    abstract = (entry.findtext(f"{{{NS}}}summary", "") or "").strip().replace("\n", " ")
    authors = [a.findtext(f"{{{NS}}}name", "") for a in entry.findall(f"{{{NS}}}author")]
    published = entry.findtext(f"{{{NS}}}published", "")[:10]
    cats = [c.get("term", "") for c in entry.findall(f"{{{NS}}}category")]
    papers.append({
        "id": aid,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "published": published,
        "categories": cats,
        "pdf_url": f"https://arxiv.org/pdf/{aid}.pdf",
        "abs_url": f"https://arxiv.org/abs/{aid}",
    })
print(json.dumps(papers, ensure_ascii=False, indent=2))
PYEOF
```

Present results as a table:

```text
| # | arXiv ID   | Title               | Authors        | Date       | Category |
|---|------------|---------------------|----------------|------------|----------|
| 1 | 2301.07041 | Attention Is All... | Vaswani et al. | 2017-06-12 | cs.LG    |
```

### Step 3: Fetch Details for a Specific ID

When a single paper ID is requested (either directly or from Step 2):

```bash
[ -n "$SCRIPT" ] && python3 "$SCRIPT" search "id:ARXIV_ID" --max 1
# or fallback:
python3 -c "
import urllib.request, xml.etree.ElementTree as ET
NS = 'http://www.w3.org/2005/Atom'
url = 'http://export.arxiv.org/api/query?id_list=ARXIV_ID'
with urllib.request.urlopen(url, timeout=30) as r:
    root = ET.fromstring(r.read())
# print full details ...
"
```

Display: title, all authors, categories, full abstract, published date, PDF URL, abstract URL.

### Step 4: Download PDFs

When download is requested, for each paper ID to download:

```bash
# Using fetch script:
[ -n "$SCRIPT" ] && python3 "$SCRIPT" download ARXIV_ID --dir PAPER_DIR

# Fallback:
mkdir -p PAPER_DIR && python3 -c "
import pathlib
import sys
import urllib.request

out = pathlib.Path('PAPER_DIR/ARXIV_ID.pdf')
if out.exists():
    print(f'Already exists: {out}')
    sys.exit(0)
req = urllib.request.Request(
    'https://arxiv.org/pdf/ARXIV_ID.pdf',
    headers={'User-Agent': 'arxiv-skill/1.0'},
)
with urllib.request.urlopen(req, timeout=60) as r:
    out.write_bytes(r.read())
print(f'Downloaded: {out} ({out.stat().st_size // 1024} KB)')
"
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
