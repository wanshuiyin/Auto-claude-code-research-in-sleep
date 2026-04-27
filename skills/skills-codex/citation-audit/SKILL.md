---
name: citation-audit
description: "Zero-context verification that every bibliographic entry in the paper is real, correctly attributed, and used in a context the cited paper actually supports. Uses a fresh cross-model reviewer with web/DBLP/arXiv lookup to catch hallucinated authors, wrong years, fabricated venues, version mismatches, and wrong-context citations (cite present but the cited paper does not establish the claim). Use when user says \"审查引用\", \"check citations\", \"citation audit\", \"verify references\", \"引用核对\", or before submission to ensure bibliography integrity."
argument-hint: [paper-directory-or-bib-file]
allowed-tools: Bash(*), Read, Grep, Glob, Edit, Write, Agent, WebSearch, WebFetch
---

# Citation Audit

Verify every `\cite{...}` in a paper against three independent layers:

1. **Existence** — the cited paper actually exists at the claimed arXiv ID / DOI / venue.
2. **Metadata correctness** — author names, year, venue, and title match canonical sources (DBLP, arXiv, ACL Anthology, Nature, OpenReview, etc.).
3. **Context appropriateness** — the cited paper actually supports the claim it is being used to support in the manuscript.

This skill is the fourth layer of \aris{}'s evidence-and-claim assurance, complementing `experiment-audit` (code), `result-to-claim` (science verdict), and `paper-claim-audit` (numerical claims). Together they form a bottom-up integrity stack from raw evaluation code to manuscript bibliography.

## When to Use This Skill

**Run before submission.** The right gating point is:
- After `paper-write` has produced the LaTeX draft and bib file
- After `paper-claim-audit` has verified numerical claims
- Before final `paper-compile` for submission

**Do not** run this on a half-written draft — most of the work is in cross-checking each `\cite` against context, which is wasted on placeholder text.

## What This Skill Catches

The dangerous citation problems are **not** wildly fake citations — those are easy to spot. The dangerous ones are:

- **Wrong-context citations**: real paper, but the cited claim is not what that paper actually establishes (e.g., citing Self-Refine to support "self-feedback produces correlated errors" — Self-Refine actually argues the opposite).
- **Author hallucinations**: anonymous-author placeholders that slipped through, missing co-authors, wrong order.
- **Title drift**: arXiv v1 vs v3 with different titles silently merged.
- **Venue confusion**: arXiv preprint cited but the official venue is now CVPR/ICML/NeurIPS — using the wrong record.
- **Year mismatch**: arXiv 2023 preprint with 2024 conference acceptance, year reported inconsistently.
- **Phantom DOIs**: DOI looks real but does not resolve.
- **Self-citation drift**: your own prior work cited with year off by one.

## Constants

- **REVIEWER_MODEL = `gpt-5.4`** — Used via Codex MCP. Default for cross-model review with web access.
- **CONTEXT_POLICY = `fresh`** — Each audit run uses a new reviewer thread (REVIEWER_BIAS_GUARD). Never `codex-reply`.
- **WEB_SEARCH = required** — The reviewer must perform real web/DBLP/arXiv lookups, not pattern-match from memory.
- **OUTPUT = `CITATION_AUDIT.md`** — Human-readable per-entry verdict report.
- **STATE = `CITATION_AUDIT.json`** — Machine-readable verdict ledger consumable by downstream tools.

## Workflow

### Step 1: Discover bib file and section files

Locate:
- `references.bib` (or `paper.bib` / similar) under the paper directory
- All `*.tex` files containing `\cite{...}` calls (typically `sec/` or `sections/`)

If multiple bib files exist, audit each separately.

### Step 2: Extract all (cite-key, context) pairs

For each `\cite{key1,key2,...}` invocation in the paper:
- Record the cite key
- Record the file + line number
- Record the surrounding sentence (≥ 1 full sentence around the cite, for context check)

Output a flat list of `(key, file, line, surrounding_sentence)` tuples.

Also build the inverse: for each bib entry, the list of all places it is cited.

Save the extracted contexts to `paper/.aris/citation-audit/contexts.txt` so the reviewer can read it directly. Use the paper-dir-relative path `.aris/citation-audit/contexts.txt` when recording the file in `audited_input_hashes`; do not stage under `/tmp` or other transient locations that the verifier cannot rehash later.

### Step 3: Send each entry to fresh cross-model reviewer

For each bib entry, launch a fresh Codex reviewer agent. Do not reuse the same reviewer across entries.

```
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    You are auditing a bibliographic entry. Use web/DBLP/arXiv search.

    ## Bib entry
    @article{key2024example,
      author = {...}, title = {...}, journal = {...}, year = {...}, ...
    }

    ## Where this entry is cited in the paper
    [paste extracted contexts]

    For this entry, verify:
    1. EXISTENCE: does this paper exist at the claimed arXiv ID / DOI / venue?
       Output: YES / NO / UNCERTAIN, with the verifying URL.
    2. METADATA: are author names, year, venue, title correct?
       For each, output: correct / wrong: should be ... / typo: ...
    3. CONTEXT: for each use, does the cited paper actually support the surrounding claim?
       Output per-use: SUPPORTS / WEAK / WRONG, with one-sentence reasoning.

    VERDICT: KEEP / FIX / REPLACE / REMOVE
    - KEEP: entry is clean, all uses are appropriate
    - FIX: metadata needs correction; uses are appropriate
    - REPLACE: cite is wrong-context, find a different paper that actually supports the claim
    - REMOVE: entry is hallucinated or unsupportable

    Be honest. If you cannot verify online, say UNCERTAIN; do not guess.
```

Save the response to `.aris/traces/citation-audit/<date>_runNN/<key>.md` per the review-tracing protocol.

### Step 4: Aggregate verdicts

Build `CITATION_AUDIT.json` following the schema defined in **"Submission
Artifact Emission"** below (single authoritative schema for this file).
Per-entry ledger data goes under `details.per_entry`, not under a
top-level `entries` field. The top-level `verdict` is a single overall
value (PASS / WARN / FAIL / NOT_APPLICABLE / BLOCKED / ERROR) derived
from per-entry verdicts per the decision table in "Submission Artifact
Emission"; the top-level `summary` is a one-line human-readable string.

Concretely, `details` carries the per-entry ledger:

```json
"details": {
  "total_entries": 29,
  "counts": { "KEEP": 11, "FIX": 14, "REPLACE": 3, "REMOVE": 1 },
  "per_entry": [
    {
      "key": "lu2024aiscientist",
      "verdict": "KEEP",
      "axis_failures": [],
      "uses": [
        {"file": "sections/1.intro.tex", "line": 11, "verdict": "SUPPORTS"},
        {"file": "sections/6.related.tex", "line": 8, "verdict": "SUPPORTS"}
      ]
    },
    {
      "key": "madaan2023selfrefine",
      "verdict": "FIX",
      "axis_failures": ["CONTEXT"],
      "uses": [
        {"file": "sections/2.overview.tex", "line": 42, "verdict": "WRONG",
         "note": "Self-Refine demonstrates iterative improvement, not correlated errors"},
        {"file": "sections/6.related.tex", "line": 13, "verdict": "SUPPORTS"}
      ]
    }
  ]
}
```

See "Submission Artifact Emission" for the full artifact (top-level
fields `audit_skill`, `verdict`, `reason_code`, `summary`,
`audited_input_hashes`, `trace_path`, `thread_id`, `reviewer_model`,
`reviewer_reasoning`, `generated_at`, `details`).

### Step 5: Generate human-readable report

Write `CITATION_AUDIT.md`:

```markdown
# Citation Audit Report

**Date**: 2026-04-19
**Bib file**: references.bib
**Total entries**: 29

## Summary
| Verdict | Count |
|---------|------|
| KEEP    | 11   |
| FIX     | 14   |
| REPLACE | 3    |
| REMOVE  | 1    |

## Priority Fixes (CRITICAL — apply before submission)

### REMOVE: hidden2025aiscientistpitfalls
- Author listed as "Anonymous" — actual authors are Luo, Kasirzadeh, Shah
- Title is incomplete
- ACTION: Replace key with `luo2025aiscientistpitfalls`, update authors and title

### REPLACE-CONTEXT: madaan2023selfrefine in sec/2.overview.tex:42
- Cited to support: "single-model self-refinement can produce correlated errors"
- Self-Refine paper actually demonstrates iterative IMPROVEMENT, not correlated errors
- ACTION: Rewrite the sentence; cite Self-Refine for "self-feedback loop" framing instead

[... continues for each entry ...]

## All-Clean Entries (no action needed)

[list of KEEP keys]
```

### Step 6: Apply fixes (interactive)

For each FIX/REPLACE/REMOVE verdict, prompt the user:

```
Fix [key]?
  Change: <description of change>
  Files affected: references.bib + sec/X.tex:Y
[Apply / Skip / Defer]
```

If `AUTO_APPLY = true`, apply all FIX-level changes (metadata corrections only). REPLACE and REMOVE always require human approval — they involve content changes.

### Step 7: Recompile and verify

```bash
latexmk -C && latexmk -pdf -interaction=nonstopmode main.tex
```

Confirm:
- No new `Citation undefined` warnings
- No `Reference undefined` warnings
- Page count unchanged or only minimally affected by metadata fixes

## Key Rules

- **Fresh reviewer thread per audit run** — never reuse prior review context
- **Web access required** — the reviewer must do real lookups, not memory pattern-match
- **Wrong-context > metadata** — a real paper used to support a wrong claim is more dangerous than a typo in author name
- **REPLACE/REMOVE require human approval** — never auto-modify content claims
- **Always emit, never block** — this skill always writes `CITATION_AUDIT.json` with a verdict; the decision to block finalization lives in `paper-writing` Phase 6 + `tools/verify_paper_audits.sh`, driven by the `assurance` level. See "Submission Artifact Emission" below.
- **Run once per submission** — the audit is wall-clock expensive (web lookups for each entry); not for every save

## Comparison with Other Audit Skills

| Skill | What it audits | What it catches |
|-------|---------------|-----------------|
| `/experiment-audit` | Evaluation code | Fake ground truth, self-normalized scores, phantom results |
| `/result-to-claim` | Result-to-claim mapping | Claims unsupported by evidence |
| `/paper-claim-audit` | Numerical claims in manuscript | Number inflation, best-seed cherry-pick, config mismatch |
| `/citation-audit` | Bibliographic entries | Hallucinated refs, wrong-context citations, metadata errors |

Together: code → result → numerical claim → cited claim. Each layer has cross-family review with no executor in the validator path.

## Known Limitations

- **DBLP coverage gap**: very recent papers (< 2 weeks) may not yet be in DBLP. Reviewer should fall back to arXiv.
- **Pre-print vs published**: when both exist, reviewer should prefer the published venue (ICML 2024 over arXiv 2401.xxxxx) but flag both.
- **Anthology vs OpenReview**: NeurIPS/ICLR papers have OpenReview entries before official proceedings; both are valid sources.
- **Multi-author truncation**: bib entries with 6+ authors using `and others` are conventional and not flagged unless the truncation hides a co-author the user explicitly cares about.

## Review Tracing

After each reviewer agent call, save the trace following `shared-references/review-tracing.md`. Use `tools/save_trace.sh` or write files directly to `.aris/traces/citation-audit/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).

## Output Contract

- `CITATION_AUDIT.md` (human-readable report) at paper root
- `CITATION_AUDIT.json` (machine-readable ledger; schema below) at paper root
- `.aris/traces/citation-audit/<date>_runNN/` (per-entry review traces)
- Optional: applied fixes to `references.bib` + `sec/*.tex` (with --apply flag)

## Submission Artifact Emission

This skill **always** writes `paper/CITATION_AUDIT.json`, regardless of
caller or detector outcome. A paper with no `.bib` file or no `\cite{...}`
usage emits verdict `NOT_APPLICABLE`; silent skip is forbidden.
`paper-writing` Phase 6 and `tools/verify_paper_audits.sh` both rely on
this artifact existing at a predictable path.

The artifact conforms to the schema in `shared-references/assurance-contract.md`:

```json
{
  "audit_skill":      "citation-audit",
  "verdict":          "PASS | WARN | FAIL | NOT_APPLICABLE | BLOCKED | ERROR",
  "reason_code":      "all_entries_keep | metadata_drift | wrong_context | hallucinated | ...",
  "summary":          "One-line human-readable verdict summary.",
  "audited_input_hashes": {
    "references.bib":             "sha256:...",
    "main.tex":                   "sha256:...",
    "sections/3.related.tex":     "sha256:..."
  },
  "trace_path":       ".aris/traces/citation-audit/<date>_run<NN>/",
  "thread_id":        "<codex mcp thread id>",
  "reviewer_model":   "gpt-5.4",
  "reviewer_reasoning": "xhigh",
  "generated_at":     "<UTC ISO-8601>",
  "details": {
    "total_entries":  <int>,
    "per_entry":      [ { "key": "madaan2023selfrefine",
                          "verdict": "KEEP | FIX | REPLACE | REMOVE",
                          "axis_failures": [ "CONTEXT" | "METADATA" | "EXISTENCE" ],
                          "note": "..." }, ... ]
  }
}
```

### `audited_input_hashes` scope

Hash the **declared input set** actually passed to this audit: the `.bib`
file, `main.tex`, and every `sections/*.tex` file that supplied citation
contexts. Do NOT hash extracted contexts from `/tmp` or other transient
paths — if you need to stage extracted contexts, materialize them under
`paper/.aris/` so the verifier can rehash reproducibly. Do NOT hash
repo-wide unions or the reviewer's self-reported opened subset.

**Path convention** (must match `tools/verify_paper_audits.sh`): keys are
**paths relative to the paper directory** (no `paper/` prefix — the
verifier already resolves relative to the paper dir; prefixing produces
`paper/paper/...` and false-fails as STALE). Use **absolute paths** for
any file outside the paper dir.

### Verdict decision table

| Input state                                                    | Verdict          | `reason_code` example |
|----------------------------------------------------------------|------------------|-----------------------|
| No `.bib` file or no `\cite{...}` usage                        | `NOT_APPLICABLE` | `no_citations`        |
| `.bib` file referenced but unreadable / missing                | `BLOCKED`        | `bib_unreadable`      |
| Every entry KEEP, all three axes green                         | `PASS`           | `all_entries_keep`    |
| Only FIX verdicts (metadata drift, no context errors)          | `WARN`           | `metadata_drift`      |
| Any REPLACE or REMOVE (wrong-context or hallucinated entry)    | `FAIL`           | `wrong_context`       |
| Web lookups timed out / reviewer invocation failed             | `ERROR`          | `reviewer_error`      |

### Thread independence

Every invocation uses a fresh reviewer agent. Never reuse `send_input` across
different bibliography entries. Do not accept prior audit outputs (PROOF_AUDIT,
PAPER_CLAIM_AUDIT, EXPERIMENT_LOG) as input — the fresh thread preserves
reviewer independence per `shared-references/reviewer-independence.md`.

This skill never blocks by itself; `paper-writing` Phase 6 plus the
verifier decide whether the verdict blocks finalization based on the
`assurance` level.

## See Also

- `/paper-claim-audit` — sibling skill for numerical claim verification
- `/experiment-audit` — sibling skill for evaluation code integrity
- `/result-to-claim` — claim verdict assignment from results
- `shared-references/citation-discipline.md` — protocol document for citation hygiene
- `shared-references/reviewer-independence.md` — cross-model review constraints
