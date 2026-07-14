# Citation Discipline and Hallucination Prevention

Use this reference only when the built-in DBLP/CrossRef workflow in `paper-write` is not enough.

This is an intentionally longer reference. It is not meant to replace the main workflow. Instead, it gives stricter standards for handling citations when:

- the title, authors, year, or venue are ambiguous,
- multiple papers could match the same description,
- DBLP / CrossRef do not return a sufficiently clean result,
- you need to verify that a specific factual claim really comes from the cited paper,
- or you need to clean and standardize a bibliography in a more disciplined way.

> **Quick map**: pre-search filter → `Pre-Search Verification Protocol` (this
> file); submission-time bibliography audit → [`/citation-audit`](../citation-audit/SKILL.md);
> numerical-claim audit → [`/paper-claim-audit`](../paper-claim-audit/SKILL.md).

## Contents

- [Why Citation Verification Matters](#why-citation-verification-matters)
- [Useful Sources and APIs](#useful-sources-and-apis)
- [Standard Verification Workflow](#standard-verification-workflow)
- [How to Add an Entry to the Bibliography](#how-to-add-an-entry-to-the-bibliography)
- [BibTeX Management Rules](#bibtex-management-rules)
- [Common Entry Templates](#common-entry-templates)
- [Common Failures and Troubleshooting](#common-failures-and-troubleshooting)
- [Final Verification Checklist](#final-verification-checklist)

## Why Citation Verification Matters

### Typical Citation Hallucination Patterns

The dangerous case is usually not a wildly fake citation. It is a citation that looks *plausible enough* to slip through:

- real authors plus a fake title,
- a real title plus the wrong year,
- a real arXiv ID plus the wrong venue,
- a real topic plus a non-existent DOI,
- or a preprint version and published version silently merged into one entry.

These mistakes are easy to miss by eye and disproportionately damaging during submission, review, and rebuttal.

### Consequences

If citation quality is weak, the mild consequences include:

- reviewers conclude the related-work section is unreliable,
- the bibliography looks messy and exposes a low-trust workflow,
- claims appear unsupported because the cited source does not actually say what the paper attributes to it.

The more serious consequences include:

- being called out for hallucinated references,
- surfacing compliance problems in desk checks or later review,
- and creating an avoidable trust crisis around the paper.

### Core Principle

**Never generate citations from memory.**

If a citation cannot be verified programmatically or from trusted project materials:

- mark it explicitly as unresolved,
- tell the user,
- and do not fabricate a plausible-looking BibTeX entry.

## Useful Sources and APIs

### Primary Sources

| Source | Best Use | Strengths | Caveats |
|--------|----------|-----------|---------|
| DBLP | CS/ML conference papers, BibTeX retrieval | Strong structure, strong venue metadata | Some preprints are better covered by arXiv |
| CrossRef | DOI lookup, BibTeX content negotiation | Official metadata source, ideal when DOI exists | Quality depends on DOI registration |
| Semantic Scholar | Paper search, citation graph, abstract lookup | Good discovery experience for ML literature | Free access may be rate limited |
| arXiv | Preprint lookup | Strong coverage for ML preprints | Not a substitute for formal publication metadata |
| OpenAlex | Open metadata graph, cross-checking | Broad coverage and useful as a second source | Structure may differ from DBLP conventions |

### How to Choose

Common decision logic:

```text
Need to search ML papers -> Semantic Scholar / DBLP
Already have a DOI -> CrossRef content negotiation
Only have an arXiv clue -> arXiv + CrossRef / Semantic Scholar for cross-checking
Need a second verification source -> OpenAlex / Semantic Scholar / arXiv
```

### About Google Scholar

Google Scholar is not the default verification backbone here. Do not treat “I found something by hand in Scholar” as the same thing as clean, trustworthy, structured metadata.

## Standard Verification Workflow

### Five-Step Process

```text
1. SEARCH   -> find candidate papers
2. VERIFY   -> confirm the paper exists in at least two trustworthy sources
3. RETRIEVE -> get BibTeX programmatically
4. VALIDATE -> confirm the claim you cite is really supported by the paper
5. ADD      -> add the entry to the bibliography with clean keys and formatting
```

### Pre-Search Verification Protocol

This is the **fast filter** that runs between Step 1 (SEARCH) and Step 2 (full
VERIFY). It catches LLM-hallucinated references at search time — before
fabricated arXiv IDs / DOIs / titles propagate into idea-creator, novelty-check,
landscape surveys, or downstream writing.

The protocol is implemented by `verify_papers.py` (canonical name; helper
path resolved per `integration-contract.md` §2, Policy D1). The script is
called by `/research-lit` (Step 1.5, mandatory), and is referenced by
`/idea-creator` and `/novelty-check` as a required filter on cited papers.

**Three-layer fallback:**

1. **arXiv API batch verify** — `arxiv.org/api/query?id_list=...` confirms up
   to 40 arXiv IDs per request. Cheapest, most authoritative; always run first
   when arXiv IDs are present.
2. **CrossRef DOI lookup** — `api.crossref.org/works/{doi}` confirms the DOI
   resolves. Run when arXiv ID is absent or arXiv check returned `unverified`.
3. **Semantic Scholar fuzzy title search** — `api.semanticscholar.org/graph/v1/paper/search`
   with normalized fuzzy match (default threshold 0.6 word overlap, max(words1, words2)).
   Run only when no arXiv ID and (no DOI **or** DOI failed verification).

**Per-paper status (one of four):**

- `verified` — at least one layer confirmed existence
- `unverified` — all applicable layers ran cleanly and found no match
- `verify_pending` — any layer hit a transient failure (timeout, 5xx, rate
  limit) and no earlier layer verified; **do NOT count against hallucination
  rate**
- `error` — the input entry itself was malformed (no arXiv, no DOI, no title)

**Top-level verdict** (aligns loosely with `assurance-contract.md`):

- `PASS` — hallucination rate ≤ threshold (default 0.20) and no pending
- `WARN` — hallucination rate > threshold or any pending
- `BLOCKED` — input/output/cache prerequisites missing
- `ERROR` — tool itself crashed

**Retention rule (over silent removal).** Unverified papers must remain in
downstream output tagged `[UNVERIFIED]` so the user can audit what was
filtered. Silent removal hides search-quality problems. Verified papers are
tagged `✅` with the verification method (`arxiv` / `crossref` / `s2` /
`s2_fallback_from_doi`).

**High-hallucination warning.** When more than 20 % of terminal results
(verified + unverified, excluding pending) come back `unverified`, surface
`high_hallucination_rate` to the user. This is a signal that the search query
or upstream source is producing fabricated entries — re-run with narrower
terms before continuing.

**Caching.** Default cache scope is per-project at
`<project>/.aris/cache/verify_papers.json` with 30-day TTL. Cache keys use
canonical identifier priority: `arxiv:{id_without_version}` →
`doi:{lowercase}` → `title:{sha1_of_normalized_title}[:16]`. The cache value
preserves all known identifiers so the same paper found through different
search paths reconciles correctly.

**CrossRef User-Agent.** Set `ARIS_VERIFY_EMAIL` to your institutional email
to reduce CrossRef rate-limit risk. Default is a placeholder
(`aris-research@anonymous.local`) — fine for low-volume use, but CrossRef
prefers a real contact for higher polite-pool throughput.

**When NOT to use this protocol.** This is search-time filtering, not
submission-time auditing. It does not replace `/citation-audit` (which checks
already-written `.bib` entries against DBLP/CrossRef metadata + cite-context)
or `/paper-claim-audit` (which verifies numerical claims against raw result
files). Run pre-search verification on candidate lists; run the audit skills
before submission.

**Invocation contract** (callers — `/research-lit`, `/idea-creator`,
`/novelty-check` — must follow). Resolve `$VERIFY_PAPERS` via the
canonical chain in `integration-contract.md` §2, then invoke under
the Policy D1 fallback. The full copy-safe snippet:

```bash
# 1. Resolve $VERIFY_PAPERS via the canonical strict-safe chain (§2).
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
if [ -z "${ARIS_REPO:-}" ] && [ -f "$HOME/.aris/repo" ]; then
    ARIS_REPO=$(cat "$HOME/.aris/repo" 2>/dev/null) || true
fi
VERIFY_PAPERS=".aris/tools/verify_papers.py"
[ -f "$VERIFY_PAPERS" ] || VERIFY_PAPERS="tools/verify_papers.py"
[ -f "$VERIFY_PAPERS" ] || { [ -n "${ARIS_REPO:-}" ] && VERIFY_PAPERS="$ARIS_REPO/tools/verify_papers.py"; }
[ -f "$VERIFY_PAPERS" ] || VERIFY_PAPERS=""

# 2. Invoke (Policy D1 fallback wraps invocation failure too).
verify_ok=false
if [ -n "$VERIFY_PAPERS" ]; then
  if python3 "$VERIFY_PAPERS" --input candidate_papers.json --output verified_papers.json; then
    verify_ok=true
  fi
fi
if [ "$verify_ok" = "false" ]; then
  command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 unavailable; BLOCKED." >&2; exit 1; }
  echo "WARN: verify_papers.py unresolved or invocation failed; emitting [UNVERIFIED] fallback." >&2
  python3 - <<'PY'
import json
cands = json.load(open('candidate_papers.json'))
out = {
  'verdict': 'WARN',
  'reason_code': 'verify_papers_unavailable',
  'summary': 'verify_papers.py helper unresolved or invocation failed; all candidates tagged [UNVERIFIED] for audit visibility.',
  'papers': [dict(p, status='unverified', method='none') for p in cands],
}
with open('verified_papers.json', 'w') as f:
  json.dump(out, f, indent=2)
PY
fi
```

`candidate_papers.json` schema:

```json
[
  {"id": "p1", "arxiv_id": "2307.03172", "doi": null, "title": "Lost in the Middle"},
  {"id": "p2", "arxiv_id": null, "doi": "10.1145/...", "title": null},
  {"id": "p3", "arxiv_id": null, "doi": null, "title": "Some Paper Title"}
]
```

`verified_papers.json` schema (top-level `verdict` + per-paper `status` —
see helper docstring for the full envelope).

### Step 1: Search

Prefer **specific searches**, not broad topic words.

Good query patterns:

- `paper title + first author`
- `method name + dataset + first author`
- `claim keyword + author`
- exact phrases from the title

While searching, record:

- title,
- authors,
- year,
- DOI,
- arXiv ID,
- venue / journal.

If multiple similar papers appear, do not add anything to `.bib` yet. First compare title details, year, and author order.

### Step 2: Verify Existence

In the ideal case, confirm the same paper in at least two sources:

- Semantic Scholar + CrossRef,
- DBLP + DOI,
- arXiv + Semantic Scholar,
- DBLP + OpenAlex.

The minimum standard for “this is the same paper” is:

- highly matching title,
- matching first author,
- matching or explainable year,
- matching DOI and/or arXiv ID.

If you only found the paper in one place, the citation is still not very stable.

### Step 3: Retrieve BibTeX Programmatically

Preferred order:

1. direct DBLP `.bib`,
2. DOI content negotiation,
3. manual completion only if the metadata base is already trustworthy.

DBLP pattern:

```bash
curl -s "https://dblp.org/search/publ/api?q=TITLE+AUTHOR&format=json&h=3"
curl -s "https://dblp.org/rec/{key}.bib"
```

CrossRef / DOI pattern:

```bash
curl -sLH "Accept: application/x-bibtex" "https://doi.org/{doi}"
```

If both DBLP and DOI fail, move to explicit placeholder handling instead of guessing.

### Step 4: Validate the Claim

This is the step people most often skip and the step that matters the most.

Before writing claims such as:

- “X first proved …”
- “Y showed that …”
- “Prior work found …”
- “Z outperformed B on benchmark A …”

check that the cited paper really supports that statement.

The minimum standard is:

- the claim is directly supported by the title, abstract, or introduction,
- or you have read the relevant section, table, theorem, or figure in the paper itself.

Do **not**:

- assume a paper supports your claim because the title sounds related,
- inherit a claim from someone else’s related-work section without checking,
- confuse “this paper is about the same topic” with “this paper establishes this exact statement.”

### Step 5: Add the Entry

Only after Steps 1-4 are complete should the entry go into `.bib`.

Check before adding:

- Is the entry type correct?
- Are the authors complete?
- Are the year and venue accurate?
- Does the citation key match the project style?
- Is this a duplicate of an existing entry?

## How to Add an Entry to the Bibliography

### Recommended Decision Tree

```text
Is there already a project-local .bib entry?
  Yes -> reuse it, then verify it
  No  -> continue

Can DBLP provide a direct .bib entry?
  Yes -> use DBLP
  No  -> continue

Do you have a DOI?
  Yes -> use DOI content negotiation
  No  -> continue

Can you confirm the paper in two trustworthy sources with enough metadata?
  Yes -> manually complete an entry from trusted metadata
  No  -> use an explicit placeholder and report it to the user
```

### Placeholder Policy

If verification fails, leave an explicit placeholder such as:

```latex
% TODO: verify before submission
\cite{PLACEHOLDER_author2024_verify}
```

Or mark uncertainty inside the `.bib` file:

```bibtex
% [VERIFY] could not confirm DOI / venue / exact title
```

The principle is:

- make uncertainty visible,
- keep bad metadata out of the final draft,
- and report unresolved citations before finalization.

## BibTeX Management Rules

### BibTeX vs BibLaTeX

This `insleep`-derived workflow still prioritizes compatibility with existing conference templates. It does not force a move to BibLaTeX.

Still, you should know the tradeoff:

| Aspect | BibTeX | BibLaTeX |
|--------|--------|----------|
| Unicode support | Weaker | Better |
| Entry types | Standard | Richer |
| Backend | `bibtex` | `biber` |
| Compatibility with older venue templates | Usually stronger | Not always safe |

In this skill pack, if the template is already fixed, prefer compatibility over modernization.

### Citation Key Format

Prefer a stable key format:

```text
firstauthor_year_keyword
```

For example:

```text
vaswani_2017_attention
devlin_2019_bert
brown_2020_language
```

If the project already uses a different key style, preserve consistency rather than mixing styles.

### Keep Only Cited Entries

Do not let `references.bib` become a dumping ground.

Rules:

- keep only entries that are actually cited,
- remove duplicates,
- remove abandoned keys,
- and choose explicitly between preprint and published versions when both exist.

### When to Prefer the Published Version

Prefer the formal published version when:

- a conference or journal version clearly exists,
- you need stable venue information for related work,
- page / volume / publisher metadata matters for submission quality.

Keeping the arXiv version can still be appropriate when:

- the work is not formally published yet,
- the community primarily cites the preprint,
- or the specific version matters for the content you are citing.

## Common Entry Templates

### Conference Paper

```bibtex
@inproceedings{vaswani_2017_attention,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam and Parmar, Niki and
            Uszkoreit, Jakob and Jones, Llion and Gomez, Aidan N. and
            Kaiser, Lukasz and Polosukhin, Illia},
  booktitle = {Advances in Neural Information Processing Systems},
  year = {2017}
}
```

### Journal Article

```bibtex
@article{hochreiter_1997_long,
  title = {Long Short-Term Memory},
  author = {Hochreiter, Sepp and Schmidhuber, J{\"u}rgen},
  journal = {Neural Computation},
  volume = {9},
  number = {8},
  pages = {1735--1780},
  year = {1997}
}
```

### arXiv Preprint

```bibtex
@misc{brown_2020_language,
  title = {Language Models are Few-Shot Learners},
  author = {Brown, Tom and Mann, Benjamin and Ryder, Nick and others},
  year = {2020},
  eprint = {2005.14165},
  archiveprefix = {arXiv},
  primaryclass = {cs.CL}
}
```

## Common Failures and Troubleshooting

### Case 1: No Results Found

Check:

- Was the title misspelled?
- Was the author misspelled?
- Is the query too broad?
- Should the search use an exact phrase instead?

Useful fixes:

- add the first author,
- add the year,
- search with a distinctive title phrase rather than a broad topic term.

### Case 2: DOI Does Not Resolve Cleanly

Possible reasons:

- the DOI exists but is not well connected through CrossRef,
- the DOI is not the best lookup path for this paper,
- the work mainly exists as an arXiv preprint.

Useful fixes:

- return to DBLP,
- cross-check the DOI in Semantic Scholar / OpenAlex,
- manually complete an entry from trusted metadata only when the metadata is already reliable.

### Case 3: Several Papers Look Similar

This is one of the most dangerous situations.

Check:

- author order,
- year,
- title wording,
- abstract-level claim,
- and, if needed, the PDF front page or the relevant section.

Until those match, do not assume any of them is the correct paper.

### Case 4: BibTeX Compilation Errors

Common causes:

- missing commas,
- unmatched braces,
- unescaped special characters,
- Unicode that does not play well with the template.

Check:

- whether each field ends correctly,
- whether title text needs LaTeX escaping,
- whether accented names are encoded safely.

### Case 5: The Same Paper Exists Under Two Keys

Fix it by:

- choosing one canonical key,
- updating all in-text citations,
- and deleting the duplicate entry.

Do not leave two nearly identical entries in the final bibliography.

## Final Verification Checklist

Before treating a citation as complete, verify:

- [ ] the paper was confirmed in at least two trustworthy sources,
- [ ] the DOI or arXiv ID was checked,
- [ ] the BibTeX was retrieved programmatically or completed from trusted metadata,
- [ ] the entry type is correct (`@inproceedings`, `@article`, `@misc`, etc.),
- [ ] the author list is complete and well formatted,
- [ ] the year and venue were checked,
- [ ] the citation key matches the project style,
- [ ] the specific claim you cite is actually supported by the paper,
- [ ] any unresolved uncertainty is marked with `[VERIFY]` or an explicit placeholder.

## Output Discipline: Verification Lives in the Trace, Not in Prose

Two rules on how verification shows up in what the reader sees (adapted from
Anthropic's Claude Science `literature-review` skill, Apache-2.0):

- **Never write a "citations verified" line in the output.** Not as an opener,
  not as a footer, not as a subtitle — "All DOIs verified", "no retraction
  flags", "bibliography checked" are process narration. Verification is
  something that happens in your tool trace (the `verify_papers` run, the DBLP
  lookups, the audit JSON); the reader infers it from citations that resolve
  and claims that hold up. A reply or section whose content is "I verified
  things" is not content. (ARIS-specific: the machine-readable verification
  record belongs in the audit artifact — `CITATION_AUDIT.json`, traces — never
  as reassurance prose in the paper or report body.)
- **A style/consistency lint runs ONCE, as a lint — not as a loop-until-clean
  gate.** Run it on the full draft, fix what it lists in a single editing
  pass, and move on; do not re-run until it returns clean. A lint that becomes
  a convergence loop burns rounds polishing cosmetics while real
  (cross-model-review) gates wait. Quality/correctness convergence belongs to
  the reviewer loops, not to lints.

## Bottom Line

**When a citation is uncertain, leave an explicit gap instead of silently inventing metadata.**
