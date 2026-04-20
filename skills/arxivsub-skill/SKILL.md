---
name: arxivsub-skill
description: >
  Academic paper search assistant that queries the arXivSub API to find the latest research papers
  from arXiv and major AI/CV conferences (CVPR, ICCV, ICLR, ICML, NeurIPS, AAAI, MICCAI).
  Use this skill whenever the user wants to search for academic papers, find recent research,
  look up conference publications, discover what's new in a research area, or explore literature
  on any AI/ML/CV topic. Trigger even for casual phrasing like "find papers on X", "what are
  the latest papers about Y", "search arXiv for Z", or "any recent work on W".
---

# arxivsub-skill

Search academic papers via the arXivSub API.

Two bundled scripts handle all processing: `scripts/search.py` (API fetch + parse) and `scripts/fetch.py` (index/detail retrieval).

---

## Language Rule

**Always respond in the same language the user is using.**

---

## Step 0: Authentication

The API key is read automatically by `search.py` from the environment — never ask the user for it and never pass it as a CLI argument.

If `search.py` exits with a non-zero code mentioning `ARXIVSUB_SKILL_KEY`, tell the user (in their language) to set it up via **one** of these methods:

1. Export as a shell environment variable (add to `~/.zshrc` or `~/.bashrc` for persistence):
   ```
   export ARXIVSUB_SKILL_KEY=your_key_here
   ```
2. Add to a `.env` file in the working directory:
   ```
   ARXIVSUB_SKILL_KEY=your_key_here
   ```

Their API key is found on the Skills page of the arXivSub website.

---

## Step 1: Show Search Parameters and Execute

Before calling the API, briefly show the interpreted parameters in one line (in the user's language), then proceed immediately without waiting:

> Searching: query=`"..."`, locations=`[...]`, time=`...`, limit=`...`

Only pause to ask for confirmation if the search intent is genuinely ambiguous (e.g. the user named a term that could mean multiple very different topics).

---

## Step 2: Fetch and Parse with search.py

Run `scripts/search.py` via bash (omit `--arxiv-days` / `--conf-years` if not applicable):

```bash
python3 <SKILL_DIR>/scripts/search.py \
  --query "<search terms>" \
  --locations arxiv CVPR NeurIPS \
  --limit 10 \
  --arxiv-days 7 \
  --conf-years 2024 2025
```

The script fetches the API, parses the response, and writes full paper details to `./tmp/arxivsub_papers.json`. It prints `quota_remaining`, `total_papers`, and the output path to stdout.

---

## Step 3: Filter and Rank

Get the concise index (id, title, what_about) to identify the most relevant papers:

```bash
python3 <SKILL_DIR>/scripts/fetch.py ./tmp/arxivsub_papers.json --for-ranking
```

Read the returned index and select the **top 5–10** paper IDs using this priority:
1. **Relevance first** — how directly the paper addresses the user's query
2. **Recency as tiebreaker** — among equally relevant papers, prefer the most recent

---

## Step 4: Fetch Full Details and Respond

Fetch full details for the selected papers:

```bash
python3 <SKILL_DIR>/scripts/fetch.py ./tmp/arxivsub_papers.json <id1> <id2> ...
```

Use the returned full paper details to compose the response. **Never mention files, scripts, or internal mechanics.**

### Output structure (translate headers to user's language):

**[Research Findings]** — Synthesize insights. Answer the user's question directly.

**[Recommended Papers]** — For each paper, use the full details to write a substantive description (not just `what_about`). Cover: what problem it solves, the key method or contribution, and notable results or significance. Typically 3–5 sentences.

```
**[Title]**
📍 [conference / arXiv] · [year if available]
👥 [first_author] ([first_aff]) · [last_author] ([last_aff])
📄 [synthesized description based on full paper details]
🔗 [pdf_url]
```

At the bottom, show quota in user's language as subscript:
English: `Daily quota remaining: N searches` / Chinese: `当日剩余搜索额度：N 次`

---

## Key Rules

- `locations` is **case-sensitive**: `arxiv`, `CVPR`, `ICCV`, `ICLR`, `ICML`, `NeurIPS`, `AAAI`, `MICCAI`
- Show parameters as a one-liner before calling the API; only ask for confirmation if the intent is ambiguous
- If `search.py` exits with a non-zero code or stderr contains an error, classify and handle it:
  - **Retryable** (network timeout, temporary server error): inform the user and offer to retry automatically
  - **Needs user intervention**:
    - Quota exhausted → tell user their daily quota is used up, no retry
    - Auth failure / missing key → direct to Step 0 setup instructions
    - Empty results → suggest broadening the query (fewer locations, wider date range, looser terms)
    - JSON parse failure → report it as an unexpected error and ask user to try again later
- Never output raw JSON or expose internal mechanics