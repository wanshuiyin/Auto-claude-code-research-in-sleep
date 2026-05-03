---
name: citation-audit
description: "Zero-context verification that every bibliographic entry in the paper is real, correctly attributed, and used in a context the cited paper actually supports. Uses a fresh cross-model reviewer with web/DBLP/arXiv lookup to catch hallucinated authors, wrong years, fabricated venues, version mismatches, and wrong-context citations (cite present but the cited paper does not establish the claim). Use when user says \"审查引用\", \"check citations\", \"citation audit\", \"verify references\", \"引用核对\", or before submission to ensure bibliography integrity."
argument-hint: "[paper-directory-or-bib-file] [--uncited]"
allowed-tools: Bash(*), Read, Grep, Glob, Edit, Write, Agent, mcp__codex__codex, WebSearch, WebFetch
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

Define two protocol sets used throughout the rest of the workflow: `cited_keys` is the set of unique cite keys appearing in any `\cite{...}` invocation across the audited `*.tex` files (de-duplicated), and `bib_keys` is the set of keys parsed from the audited bib file(s). `cited_keys` drives Step 3 (audit only cited entries); `bib_keys \ cited_keys` is the uncited residual surfaced by the `--uncited` opt-in.

If the user passed `--uncited`, also compute the set difference `bib_keys \ cited_keys` here and stash it for use in Steps 5 and the JSON aggregation; see "Uncited Entry Detection (opt-in)" below for the protocol. The set-diff is a string operation only and does not consume reviewer budget.

Save the extracted contexts to `paper/.aris/citation-audit/contexts.txt` so the reviewer can read it directly. Use the paper-dir-relative path `.aris/citation-audit/contexts.txt` when recording the file in `audited_input_hashes`; do not stage under `/tmp` or other transient locations that the verifier cannot rehash later.

### Step 3: Send each entry to fresh cross-model reviewer

For each **cited** bib entry — i.e., each key in `cited_keys` with at least one extracted citation context — invoke `mcp__codex__codex` (NOT `codex-reply` — fresh thread per entry, or batch with explicit per-entry isolation). Do **not** send entries in `bib_keys \ cited_keys` to the reviewer; those are detect-only and surface only when `--uncited` is explicitly enabled (see "Uncited Entry Detection" below).

```
mcp__codex__codex:
  model: gpt-5.4
  config: {"model_reasoning_effort": "xhigh"}
  sandbox: read-only
  prompt: |
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
**Bib file(s)**: references.bib
**Total entries**: 29

## Summary
| Verdict | Count |
|---------|------|
| KEEP    | 11   |
| FIX     | 14   |
| REPLACE | 3    |
| REMOVE  | 1    |

## Priority Fixes (CRITICAL — apply before submission)

### REMOVE: anon2025placeholder
- Author listed as "Anonymous" — canonical record exists with real authors and full title
- Title is incomplete
- ACTION: Replace key with the canonical citekey, update authors and title

### REPLACE-CONTEXT: example2023priorwork in sec/2.overview.tex:42
- Cited to support a specific technical claim
- The cited paper actually demonstrates a different (related but distinct) phenomenon
- ACTION: Rewrite the sentence; cite the prior work for what it actually establishes

[... continues for each entry ...]

## All-Clean Entries (no action needed)

[list of KEEP keys]
```

When `--uncited` is set, append the following section after "All-Clean Entries":

```markdown
## Uncited Entries (opt-in)

The following bib entries are present in the audited bib file(s) but are not referenced by any `\cite{...}` in the paper body:

- `author2010example` — suggestion: prune (uncited; no local evidence of intent)
- `someone2015othercite` — suggestion: prune (uncited; no local evidence of intent)
- `third2024todo` — suggestion: check (a `% TODO: cite third2024todo` comment was found in `sections/3.related.tex`)

This section is detect-only; it does not change the top-level verdict.
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

## Uncited Entry Detection (opt-in)

**Default**: disabled. Existing users see no behavior change — only `\cite{...}` keys are audited, and bib entries with no `\cite` reference in the manuscript are silently ignored.

**Opt-in**: pass `--uncited` on invocation. The skill then performs a set-diff after Step 2 and reports bib entries that appear in any audited bib file(s) but are not cited anywhere in the paper. Detect-only — uncited entries are **not** sent to the cross-model reviewer, so there is no extra reviewer/web-lookup cost.

### Why opt-in
This skill's headline output is the three-axis audit on cited entries. Surfacing uncited bib entries by default would (a) change long-form output for every existing run, and (b) noise up the verdict for users who intentionally maintain a superset bib file (e.g., shared lab bib, in-progress section reorder where the cite has been removed but the entry intentionally retained). The flag preserves zero behavior change for existing callers.

### Effect when enabled

When `--uncited` is set:

- `CITATION_AUDIT.md` gains a `## Uncited Entries (opt-in)` section listing the keys with a one-line suggestion each: `prune` (entry is dead weight; recommend deleting) or `check` (entry might be intentional; flag for user review). Default suggestion is `prune`; only emit `check` when there is concrete local evidence (e.g., a TODO comment in a `.tex` file mentioning the key, or a recently removed `\cite` visible in `git diff`). Do not infer intent from the bib key string alone.
- `CITATION_AUDIT.json` `details` gains an `uncited_entries` array; see "Submission Artifact Emission" below for the schema.
- The top-level `verdict` is **unchanged**: uncited entries do not upgrade or downgrade the PASS / WARN / FAIL / etc. classification. The `reason_code` and `summary` are likewise unchanged in shape; only the `details.uncited_entries` field appears.
- Verifier gates and downstream skills (`paper-writing` Phase 6, `tools/verify_paper_audits.sh`) MUST NOT treat the presence of `uncited_entries` as a blocking signal.

### When opt-in is appropriate

- Pre-submission cleanup (drop dead bib entries before sharing camera-ready ZIP).
- Shared lab bib file where the paper uses a subset and the user wants to confirm what is in scope.
- Recurring audits where the user has previously seen the uncited count and wants to track whether it changed.

### Fallback when bib enumeration fails

If `--uncited` is enabled but full bib-key enumeration fails (e.g., malformed bib syntax that the parser cannot recover), the cited-entry audit must still proceed if at all possible. In that case:

- Do **not** alter the top-level `verdict`, `reason_code`, or `summary`.
- Emit `details.uncited_entries` as an empty array `[]`.
- Add `details.uncited_entries_status: "unavailable"` plus a one-line note explaining why (e.g., `"bib parser could not enumerate keys; cited-entry audit completed normally"`).
- Verifier gates and downstream skills MUST treat `unavailable` the same as the field being absent: not blocking.

If the bib file cannot be read well enough to audit even the cited entries, fall back to the existing `BLOCKED` / `bib_unreadable` path defined in the verdict decision table; this is the same behavior as the no-flag default.

## Key Rules

- **Fresh reviewer thread per audit run** — never reuse prior review context
- **Web access required** — the reviewer must do real lookups, not memory pattern-match
- **Wrong-context > metadata** — a real paper used to support a wrong claim is more dangerous than a typo in author name
- **REPLACE/REMOVE require human approval** — never auto-modify content claims
- **Always emit, never block** — this skill always writes `CITATION_AUDIT.json` with a verdict; the decision to block finalization lives in `paper-writing` Phase 6 + `tools/verify_paper_audits.sh`, driven by the `assurance` level. See "Submission Artifact Emission" below.
- **Run once per submission** — the audit is wall-clock expensive (web lookups for each entry); not for every save
- **Uncited detection is opt-in only** — never auto-enable; never block on uncited entries; existing callers must observe identical output if they do not pass `--uncited`

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

After each `mcp__codex__codex` reviewer call, save the trace following `shared-references/review-tracing.md`. Use `tools/save_trace.sh` or write files directly to `.aris/traces/citation-audit/<date>_run<NN>/`. Respect the `--- trace:` parameter (default: `full`).

## Output Contract

- `CITATION_AUDIT.md` (human-readable report) at paper root
- `CITATION_AUDIT.json` (machine-readable ledger; schema below) at paper root
- `.aris/traces/citation-audit/<date>_runNN/` (per-entry review traces)
- Optional: applied fixes to `references.bib` + `sec/*.tex` (with `--apply` flag)
- Optional: `details.uncited_entries` field in JSON + `## Uncited Entries (opt-in)` MD section (with `--uncited` flag; field absent and section omitted when flag is unset)

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
    "total_entries":  <int>,                 // count of audited cited entries (= |cited_keys|), NOT the bib-file size
    "per_entry":      [ { "key": "madaan2023selfrefine",
                          "verdict": "KEEP | FIX | REPLACE | REMOVE",
                          "axis_failures": [ "CONTEXT" | "METADATA" | "EXISTENCE" ],
                          "note": "..." }, ... ]
  }
}
```

### Optional: `details.uncited_entries` (only when `--uncited` is set)

```json
"details": {
  ...
  "uncited_entries": [
    {"key": "<bibkey>", "suggestion": "prune" | "check", "note": "..."}
  ],
  "uncited_entries_status": "ok" | "unavailable"
}
```

Field semantics:
- Both fields are **omitted entirely** when the flag is not set. The default schema does not include either key.
- When the flag is set and the set-diff completes normally, `uncited_entries_status` is `"ok"` and `uncited_entries` lists the detected keys (possibly empty if every bib entry is cited).
- When the flag is set but bib-key enumeration fails (per "Fallback when bib enumeration fails" above), `uncited_entries_status` is `"unavailable"` and `uncited_entries` is `[]`. Downstream consumers MUST treat `"unavailable"` identically to the field being absent: not blocking.
- Downstream consumers MUST treat absence of either field as the only valid default state and MUST NOT raise on missing.
- `suggestion` is advisory only; the verifier and `paper-writing` Phase 6 do not block on it.

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

The `--uncited` flag does **not** appear in this table: uncited entries are advisory only and never alter the top-level verdict or reason_code. They surface exclusively through `details.uncited_entries` and the optional MD section.

### Thread independence

Every invocation uses a fresh `mcp__codex__codex` thread. Never
`codex-reply`. Do not accept prior audit outputs (PROOF_AUDIT,
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
