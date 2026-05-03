---
name: paper-write
description: "Draft LaTeX paper section by section from an outline. Use when user says \"写论文\", \"write paper\", \"draft LaTeX\", \"开始写\", or wants to generate LaTeX content from a paper plan."
argument-hint: [venue-or-section]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch, mcp__codex__codex, mcp__codex__codex-reply
---

# Paper Write: Section-by-Section LaTeX Generation

Draft a LaTeX paper based on: **$ARGUMENTS**

## Constants

- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for section review. Must be an OpenAI model.
- **TARGET_VENUE = `ICLR`** — Default venue. Supported: `ICLR`, `NeurIPS`, `ICML`, `CVPR` (also ICCV/ECCV), `ACL` (also EMNLP/NAACL), `AAAI`, `ACM` (ACM MM, SIGIR, KDD, CHI, etc.), `IEEE_JOURNAL` (IEEE Transactions / Letters, e.g., T-PAMI, JSAC, TWC, TCOM, TSP, TIP), `IEEE_CONF` (IEEE conferences, e.g., ICC, GLOBECOM, INFOCOM, ICASSP). Determines style file and formatting.
- **ANONYMOUS = true** — If true, use anonymous author block. Set `false` for camera-ready. Note: most IEEE venues do NOT use anonymous submission — set `false` for IEEE.
- **MAX_PAGES = 9** — Main body page limit. For ML conferences: counts from first page to end of Conclusion section, references and appendix NOT counted. **For IEEE venues: references ARE counted toward the page limit.** Typical limits: IEEE journal = no strict limit (but 12-14 pages typical for Transactions, 4-5 for Letters), IEEE conference = 5-8 pages including references.
- **DBLP_BIBTEX = true** — Fetch real BibTeX from DBLP/CrossRef instead of LLM-generated entries. Eliminates hallucinated citations. Zero install required. Set `false` to use legacy behavior (LLM search + `[VERIFY]` markers).

## Inputs

1. **PAPER_PLAN.md** — outline with claims-evidence matrix, section plan, figure plan (from `/paper-plan`)
2. **NARRATIVE_REPORT.md** — the research narrative (primary source of content)
3. **Generated figures** — PDF/PNG files in `figures/` (from `/paper-figure`)
4. **LaTeX includes** — `figures/latex_includes.tex` (from `/paper-figure`)
5. **Bibliography** — existing `.bib` file, or will create one

If no PAPER_PLAN.md exists, ask the user to run `/paper-plan` first or provide a brief outline.

## Orchestra-Guided Writing Overlay

Keep the existing `insleep` workflow, file layout, and defaults. Use the shared references below only when they improve writing quality:

- Read `../shared-references/writing-principles.md` before drafting the Abstract, Introduction, Related Work, or when prose feels generic.
- Read `../shared-references/venue-checklists.md` during the final write-up and submission-readiness pass.
- Read `../shared-references/citation-discipline.md` only when the built-in DBLP/CrossRef workflow is insufficient.

These references are support material, not extra workflow phases.

## Templates

### Venue-Specific Setup

The skill includes conference templates in `templates/`. Select based on TARGET_VENUE:

**ICLR:**
```latex
\documentclass{article}
\usepackage{iclr2026_conference,times}
% \iclrfinalcopy  % Uncomment for camera-ready
```

**NeurIPS:**
```latex
\documentclass{article}
\usepackage[preprint]{neurips_2025}
% \usepackage[final]{neurips_2025}  % Camera-ready
```

**ICML:**
```latex
\documentclass[accepted]{icml2025}
% Use [accepted] for camera-ready
```

**IEEE Journal** (Transactions, Letters):
```latex
\documentclass[journal]{IEEEtran}
\usepackage{cite}  % IEEE uses \cite{}, NOT natbib
% Author block uses \author{Name~\IEEEmembership{Member,~IEEE}}
```

**IEEE Conference** (ICC, GLOBECOM, INFOCOM, ICASSP, etc.):
```latex
\documentclass[conference]{IEEEtran}
\usepackage{cite}  % IEEE uses \cite{}, NOT natbib
% Author block uses \IEEEauthorblockN / \IEEEauthorblockA
```

### Project Structure

Generate this file structure:

```
paper/
├── main.tex                    # master file (includes sections)
├── iclr2026_conference.sty     # or neurips_2025.sty / icml2025.sty / IEEEtran.cls + IEEEtran.bst
├── math_commands.tex           # shared math macros
├── references.bib              # bibliography (filtered — only cited entries)
├── sections/
│   ├── 0_abstract.tex
│   ├── 1_introduction.tex
│   ├── 2_related_work.tex
│   ├── 3_method.tex            # or preliminaries, setup, etc.
│   ├── 4_experiments.tex
│   ├── 5_conclusion.tex
│   └── A_appendix.tex          # proof details, extra experiments
└── figures/                    # symlink or copy from project figures/
```

**Section files are FLEXIBLE**: If the paper plan has 6-8 sections, create corresponding files (e.g., `4_theory.tex`, `5_experiments.tex`, `6_analysis.tex`, `7_conclusion.tex`).

## Workflow

### Step 0: Backup and Clean

If `paper/` already exists, back up to `paper-backup-{timestamp}/` before overwriting. Never silently destroy existing work.

**CRITICAL: Clean stale files.** When changing section structure (e.g., 5 sections → 7 sections), delete section files that are no longer referenced by `main.tex`. Stale files (e.g., old `5_conclusion.tex` left behind when conclusion moved to `7_conclusion.tex`) cause confusion and waste space.

### Step 1: Initialize Project

1. Create `paper/` directory
2. Copy venue template from `templates/` — the template already includes:
   - All standard packages (amsmath, hyperref, cleveref, booktabs, etc.)
   - Theorem environments with `\crefname{assumption}` fix
   - Anonymous author block
3. Generate `math_commands.tex` with paper-specific notation
4. Create section files matching PAPER_PLAN structure

**Author block (anonymous mode):**
```latex
\author{Anonymous Authors}
```

### Step 2: Generate math_commands.tex

Create shared math macros based on the paper's notation:

```latex
% math_commands.tex — shared notation
\newcommand{\R}{\mathbb{R}}
\newcommand{\E}{\mathbb{E}}
\DeclareMathOperator*{\argmin}{arg\,min}
\DeclareMathOperator*{\argmax}{arg\,max}
% Add paper-specific notation here
```

### Step 3: Write Each Section

Process sections in order. For each section:

1. **Read the plan** — what claims, evidence, citations belong here
2. **Read NARRATIVE_REPORT.md** — extract relevant content, findings, and quantitative results
3. **Draft content** — write complete LaTeX (not placeholders)
4. **Insert figures/tables** — use snippets from `figures/latex_includes.tex`
5. **Add citations** — for ML conferences (ICLR/NeurIPS/ICML/CVPR/ACL/AAAI): use `\citep{}` / `\citet{}` (natbib). **For IEEE venues**: use `\cite{}` (numeric style via `cite` package). Never mix natbib and cite commands.

Before drafting the front matter, re-read the one-sentence contribution from `PAPER_PLAN.md`. The Abstract and Introduction should make that takeaway obvious before the reader reaches the full method.

#### Section-Specific Guidelines

**§0 Abstract:**
- Use the 5-part flow from `../shared-references/writing-principles.md`: what, why hard, how, evidence, strongest result
- Must be self-contained (understandable without reading the paper)
- Start with the paper's specific contribution, not generic field-level background
- Include one concrete quantitative result
- 150-250 words (check venue limit)
- No citations, no undefined acronyms
- No `\begin{abstract}` — that's in main.tex

**§1 Introduction:**
- Open with a compelling hook (1-2 sentences, problem motivation)
- State the gap clearly ("However, ...")
- Give a brief approach overview before the reader gets lost in details
- List 2-4 specific, falsifiable contributions as a numbered or bulleted list
- Preview the strongest result early instead of saving it for the experiments section
- End with a brief roadmap ("The rest of this paper is organized as...")
- Include the main result figure if space allows
- Target: 1-1.5 pages
- Methods should begin by page 2-3 at the latest

**§2 Related Work:**
- **MINIMUM 1 full page** (3-4 substantive paragraphs). Short related work sections are a common reviewer complaint.
- Organize by category using `\paragraph{Category Name.}`
- Organize methodologically, by assumption class, or by research question; do not write paper-by-paper mini-summaries
- Each category: 1 paragraph summarizing the line of work + 1-2 sentences positioning this paper
- Do NOT just list papers — synthesize and compare
- End each paragraph with how this paper relates/differs

**§3 Method / Preliminaries / Setup:**
- Define notation early (reference math_commands.tex)
- Use `\begin{definition}`, `\begin{theorem}` environments for formal statements
- For theory papers: include proof sketches of key results in main body, full proofs in appendix
- For theory papers: include a **comparison table** of prior bounds vs. this paper
- Include algorithm pseudocode if applicable (`algorithm2e` or `algorithmic`)
- Target: 1.5-2 pages

**§4 Experiments:**
- Start with experimental setup (datasets, baselines, metrics, implementation details)
- Main results table/figure first
- Then ablations and analysis
- Every claim from the introduction must have supporting evidence here
- For each major experiment, make explicit what claim it supports and what the reader should notice
- Target: 2.5-3 pages

**§5 Conclusion:**
- Summarize contributions (NOT copy-paste from intro — rephrase)
- Limitations (be honest — reviewers appreciate this)
- Future work (1-2 concrete directions)
- Ethics statement and reproducibility statement (if venue requires)
- Target: 0.5 pages

**Appendix:**
- Proof details (full proofs of main-body theorems)
- Additional experiments, ablations
- Implementation details, hyperparameter tables
- Additional visualizations

### Step 3.5: Theory Paper Consistency Pass (theory papers only)

Run this pass after drafting all sections and before building the bibliography.

**Trigger heuristic:** treat the paper as theory-heavy if `PAPER_PLAN.md` labels it as theory/analysis, or if the drafted sections contain 5 or more formal result environments (`\begin{theorem}`, `\begin{lemma}`, `\begin{proposition}`, `\begin{corollary}`).

**Proof source search:** search the workspace for any standalone full-proof source file whose name or contents indicate a canonical proof version (`proof`, `appendix`, `full`, `complete`, `supplement`, `supplementary`). If such a file exists, prompt the user exactly:

`Inline full proofs from {file}? [Y/n]`

Default to `Y`.

If the user accepts:
- import the full theorem/lemma statement plus proof block into the appendix source (`A_appendix.tex` or the appendix file named by the plan)
- use the main-body theorem statement as the canonical public statement; the appendix copy must match it unless the main-body statement is being revised in the same pass
- do **not** leave placeholders such as "see supplementary proof document" or "proof omitted for brevity"
- preserve theorem labels, equation labels, and proof structure exactly
- keep the main body proof sketches short, but never let the appendix be a sketch-only placeholder when a full proof source exists

If no standalone full-proof source exists:
- use proof sketches only when they are actually written as proof sketches, not placeholders
- do not fabricate an external proof document reference

**Restatement audit:**
- Compare every theorem/lemma/proposition statement that is restated in the appendix against the main-body version
- Do not diff proof bodies; only audit statements, hypotheses, case splits, quantifiers, domains, notation, variable names, and terminology for defined objects
- Treat `stationary` vs `terminal`, changed assumption names, or missing case splits as mismatches unless explicitly documented
- If the appendix needs different wording, add an explicit notation bridge instead of silently renaming concepts
- Resolve all mismatches before Step 4

**Empirical motivation:** in a real theory-paper run, the default behavior generated `"see supplementary proof document"` placeholders in the appendix. The author had to manually pull hundreds of lines of full proofs from a standalone proofs file (e.g. `proof_full.tex`). Without this pass, theory papers ship with sketch-only appendices that fail at theory venues.

### Step 4: Build Bibliography

**CRITICAL: Only include entries that are actually cited in the paper.**

1. Scan all citation references in the drafted sections (`\citep{}`/`\citet{}` for ML conferences, `\cite{}` for IEEE venues)
2. Build a citation key list
3. For each citation key:
   - Check existing `.bib` files in the project/narrative docs
   - If not found and **DBLP_BIBTEX = true**, use the verified fetch chain below
   - If not found and **DBLP_BIBTEX = false**, search arXiv/Scholar for correct BibTeX
   - **NEVER fabricate BibTeX entries** — mark unknown ones with `[VERIFY]` comment
4. Write `references.bib` containing ONLY cited entries (no bloat)

#### Verified BibTeX Fetch (when DBLP_BIBTEX = true)

Three-step fallback chain — zero install, zero auth, all real BibTeX:

**Step A: DBLP (best quality — full venue, pages, editors)**
```bash
# 1. Search by title + first author
curl -s "https://dblp.org/search/publ/api?q=TITLE+AUTHOR&format=json&h=3"
# 2. Extract DBLP key from result (e.g., conf/nips/VaswaniSPUJGKP17)
# 3. Fetch real BibTeX
curl -s "https://dblp.org/rec/{key}.bib"
```

**Step B: CrossRef DOI (fallback — works for arXiv preprints)**
```bash
# If paper has a DOI or arXiv ID (arXiv DOI = 10.48550/arXiv.{id})
curl -sLH "Accept: application/x-bibtex" "https://doi.org/{doi}"
```

**Step C: Mark `[VERIFY]` (last resort)**
If both DBLP and CrossRef return nothing, mark the entry with `% [VERIFY]` comment. Do NOT fabricate.

**Why this matters:** LLM-generated BibTeX frequently hallucinates venue names, page numbers, or even co-authors. DBLP and CrossRef return publisher-verified metadata. Upstream skills (`/research-lit`, `/novelty-check`) may mention papers from LLM memory — this fetch chain is the gate that prevents hallucinated citations from entering the final `.bib`.

If the DBLP/CrossRef flow is not enough, load `../shared-references/citation-discipline.md` for stricter fallback rules before adding placeholders.

**Automated bib cleaning** — use this Python pattern to extract only cited entries:

```python
import re
# 1. Grep all \citep{...}, \citet{...}, and \cite{...} from all .tex files
# 2. Extract unique keys (handle multi-cite like \citep{a,b,c} or \cite{a,b,c})
# 3. Parse the full .bib file, keep only entries whose key is in the cited set
# 4. Write the filtered bib
```

This prevents bib bloat (e.g., 948 lines → 215 lines in testing).

**Enforced Bib Hygiene Validation** — run immediately after the filtered `references.bib` is written.

```bash
python3 - <<'PY'
import io, json, re, sys, urllib.parse, urllib.request
from pathlib import Path

try:
    import bibtexparser
except ImportError:
    sys.exit("Missing dependency: pip install bibtexparser")

ROOT = Path("paper")
tex_paths = [ROOT / "main.tex", *sorted((ROOT / "sections").glob("*.tex"))]
tex = "\n".join(p.read_text(errors="ignore") for p in tex_paths if p.exists())

cited = set()
for m in re.finditer(r'\\cite[a-zA-Z]*\{([^}]*)\}', tex):
    cited.update(k.strip() for k in m.group(1).split(',') if k.strip())

with (ROOT / "references.bib").open() as fh:
    bib = bibtexparser.load(fh)

entries = {e["ID"]: e for e in bib.entries}
dead = sorted(set(entries) - cited)
if dead:
    print("DEAD ENTRIES:")
    for key in dead:
        print("  ", key)

def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()

def dblp_hits(title):
    q = urllib.parse.quote(title)
    url = f"https://dblp.org/search/publ/api?q={q}&format=json&h=3"
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
    return [h.get("info", {}) for h in data.get("result", {}).get("hits", {}).get("hit", [])]

def crossref_entry(doi):
    req = urllib.request.Request(f"https://doi.org/{doi}", headers={"Accept": "application/x-bibtex"})
    with urllib.request.urlopen(req, timeout=20) as r:
        parsed = bibtexparser.loads(r.read().decode("utf-8", "ignore"))
    return parsed.entries[0] if parsed.entries else {}

for key in sorted(cited & set(entries)):
    e = entries[key]
    title = e.get("title", "").strip("{}")
    hits = dblp_hits(title) if title else []
    hit = hits[0] if hits else None
    source = "DBLP"
    if hit is None and e.get("doi"):
        try:
            hit = crossref_entry(e["doi"])
            source = "CrossRef"
        except Exception:
            hit = None
    if hit is None:
        print(f"VERIFY {key}: no DBLP/CrossRef hit")
        continue

    issues = []
    year_a = str(e.get("year", "")).strip()
    year_b = str(hit.get("year", "")).strip()
    if year_a and year_b and year_a != year_b:
        issues.append(f"year {year_a} != {year_b}")

    venue_a = e.get("journal") or e.get("booktitle") or ""
    venue_b = hit.get("journal") or hit.get("booktitle") or hit.get("venue") or ""
    if norm(venue_a) and norm(venue_b) and norm(venue_a) != norm(venue_b):
        issues.append(f"venue {venue_a} != {venue_b}")

    authors_a = [norm(a) for a in re.split(r'\s+and\s+', e.get("author", "")) if a.strip()]
    authors_b = [norm(a) for a in re.split(r'\s+and\s+', hit.get("author", "")) if a.strip()]
    if authors_a and authors_b and authors_a[:2] != authors_b[:2]:
        issues.append("author list differs")

    if issues:
        print(f"MISMATCH {key} ({source}): " + "; ".join(issues))
PY
```

If `DEAD ENTRIES` is printed, remove those keys from `references.bib` before continuing.
If `VERIFY` or `MISMATCH` is printed, do not invent metadata:
- prefer DBLP when it returns a clear hit
- if DBLP misses and a DOI is available, fall back to CrossRef
- if both disagree or still cannot verify, keep the entry only with a `% [VERIFY]` marker
- uncited entries must be deleted, not left behind as dead bibliography bloat

**Citation reachability rule:** an entry is dead if its key does not appear in any `\cite...{}` command in `paper/main.tex` or any `paper/sections/*.tex` file.

**Empirical motivation:** in a real submission run, several dead bib entries sat in `references.bib` for many improvement rounds, and at least one entry had a key/year mismatch. Neither was flagged by the existing automated cleaning.

**Citation verification rules (from claude-scholar + Imbad0202):**
1. Every BibTeX entry must have: author, title, year, venue/journal
2. Prefer published venue versions over arXiv preprints (if published)
3. Use consistent key format: `{firstauthor}{year}{keyword}` (e.g., `ho2020denoising`)
4. Double-check year and venue for every entry
5. Remove duplicate entries (same paper with different keys)

### Step 5: Scientific Writing Quality Pass (5 audit passes)

After drafting all sections, run five sequential audit passes. Based on Sainani's "Writing in the Sciences" methodology: every word must earn its place.

**Pass 1: Clutter Extraction** — Strip sentences to cleanest components.

| Cluttered phrase | Replace with |
|------------------|--------------|
| Due to the fact that | Because |
| In order to | To |
| A number of | Several |
| It is worth noting that | (delete — just state the point) |
| It is important to note that | (delete) |
| At the present time | Now |
| On the basis of | Based on |
| In light of the fact that | Because |
| Have an effect on | Affect |
| Give rise to | Cause |

Also remove redundancies: "completely eliminate" → "eliminate", "future plans" → "plans", "unexpected surprise" → "surprise".

Remove AI-isms: delve, pivotal, landscape, tapestry, underscore, noteworthy, intriguingly.

**Pass 2: Active Voice and Verb Vitality** — Identify who did what.

- Spot passive: "to-be" verb + past participle ("was observed", "were analyzed")
- Convert: find the actor, reconstruct as Subject–Verb–Object
- Resurrect smothered verbs (nominalizations):
  - "We made an investigation" → "We investigated"
  - "Failure of the system occurs" → "The system fails"
  - "Provides a description of" → "Describes"

Passive voice IS acceptable for: established facts, methods where agent is irrelevant, or when required by venue style.

**Pass 3: Sentence Architecture** — Structure and flow.

- Flag sentences > 40 words for splitting
- Ensure subject and verb are close together (no long parenthetical insertions between them)
- Put familiar context first, new information later
- Place the most important point near the end of the sentence
- Let each paragraph do one job
- Don't start consecutive sentences with "This" or "We"
- Check paragraph transitions — each paragraph's first sentence should connect to the previous

**Pass 4: Keyword Consistency** — The Banana Rule.

**Do not call a "banana" an "elongated yellow fruit" to avoid repetition.** If the Methods say "obese group," the Results must not switch to "heavier group." Synonym variation for technical terms forces the reader to wonder whether a new category has been introduced.

- Extract all key terms from Method section (group names, variable names, technique names, abbreviations)
- Verify exact same terms appear in Results, Discussion, Tables, Figure captions
- Flag every synonym substitution for a defined term
- Acronym austerity: flag non-standard acronyms created only for convenience; verify every acronym is defined at first use

**Pass 5: Numerical and Citation Integrity**

- Does sample size (N) in Abstract match Table 1?
- Do percentages in Results match raw numbers in Tables?
- Are significant figures consistent and appropriate?
- Do Figure graphics match Table values?
- Flag statistics cited only through secondary sources (reviews, textbooks) — recommend verifying primary source

### Step 6: Cross-Review with REVIEWER_MODEL

Send the complete draft to GPT-5.4 xhigh:

```
mcp__codex__codex:
  model: gpt-5.4
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    Review this [VENUE] paper draft (main body, excluding appendix).

    Focus on:
    1. Does each claim from the intro have supporting evidence?
    2. Is the writing clear, concise, and free of AI-isms?
    3. Any logical gaps or unclear explanations?
    4. Does it fit within [MAX_PAGES] pages (to end of Conclusion)?
    5. Is related work sufficiently comprehensive (≥1 page)?
    6. For theory papers: are proof sketches adequate?
    7. Are figures/tables clearly described and properly referenced?
    8. Would a skim reader understand the contribution from the title, abstract, introduction, and Figure 1?

    For each issue, specify: severity (CRITICAL/MAJOR/MINOR), location, and fix.

    [paste full draft text]
```

Apply CRITICAL and MAJOR fixes. Document MINOR issues for the user.

### Step 7: Reverse Outline Test (from Research-Paper-Writing-Skills)

After drafting all sections:

1. **Extract topic sentences** — pull the first sentence of every paragraph
2. **Read them in sequence** — they should form a coherent narrative on their own
3. **Check claim coverage** — every claim from the Claims-Evidence Matrix must appear
4. **Check evidence mapping** — every experiment/figure must support a stated claim
5. **Fix gaps** — if a topic sentence doesn't advance the story, rewrite the paragraph

### Step 8: Final Checks

Before declaring done:

- [ ] All `\ref{}` and `\label{}` match (no undefined references)
- [ ] All citation commands (`\citep{}`/`\citet{}` for ML conferences, `\cite{}` for IEEE) have corresponding BibTeX entries
- [ ] No author information in anonymous mode
- [ ] Figure/table numbering is correct
- [ ] Page count within MAX_PAGES (main body to Conclusion end)
- [ ] No TODO/FIXME/XXX markers left in the text
- [ ] No `[VERIFY]` markers left unchecked
- [ ] Abstract is self-contained (understandable without reading the paper)
- [ ] Title is specific and informative (not generic)
- [ ] Related work is ≥1 full page
- [ ] references.bib contains ONLY cited entries (no bloat)
- [ ] **No stale section files** — every .tex in `sections/` is `\input`ed by `main.tex`
- [ ] **Section files match main.tex** — file numbering and `\input` paths are consistent
- [ ] Venue-specific required sections/checklists satisfied (read `../shared-references/venue-checklists.md` if needed)
- [ ] A skim reader can recover the main claim from the title, abstract, introduction, and Figure 1/captions

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.
- **Do NOT generate author names, emails, or affiliations** — use anonymous block or placeholder
- **Write complete sections, not outlines** — the output should be compilable LaTeX
- **One file per section** — modular structure for easy editing
- **Every claim must cite evidence** — cross-reference the Claims-Evidence Matrix
- **Compile-ready** — the output should compile with `latexmk` without errors (modulo missing figures)
- **No over-claiming** — use hedging language ("suggests", "indicates") for weak evidence
- **Venue style matters** — ML conferences (ICLR/NeurIPS/ICML) use `natbib` (`\citep`/`\citet`); **IEEE venues use `cite` package (`\cite{}`, numeric)**. Never mix.
- **Page limit rules differ by venue** — ML conferences: main body to Conclusion, references/appendix NOT counted. **IEEE: references ARE counted toward the page limit.**
- **Clean bib** — references.bib must only contain entries that are actually `\cite`d
- **Section count is flexible** — match PAPER_PLAN structure, don't force into 5 sections
- **Backup before overwrite** — never destroy existing `paper/` directory without backing up
- **Front-load the contribution** — do not hide the payoff until the experiments or appendix

## Writing Quality Reference

- `../shared-references/writing-principles.md` — story framing, abstract/introduction patterns, sentence-level clarity, reviewer reading order
- `../shared-references/venue-checklists.md` — ICLR/NeurIPS/ICML/IEEE submission requirements to check before declaring done
- `../shared-references/citation-discipline.md` — stricter fallback for ambiguous citations

Keep using the reverse-outline test and anti-inflation polish from the main workflow above; the shared references are there to improve quality without adding a new phase.

## Acknowledgements

Writing methodology adapted from [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills) (CCF award-winning methodology). Citation verification from [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) and [Imbad0202/academic-research-skills](https://github.com/Imbad0202/academic-research-skills). This hybrid pack's writing-guidance overlay is adapted from Orchestra Research's paper-writing materials.
