# Integration Contract

When one ARIS skill delegates work to another (or to persistent project
state), the coupling must be **engineered**, not assumed. This document
formalizes what every cross-skill integration inside ARIS must provide.

Rule of thumb: **SKILL.md prose can *describe* an integration; it cannot
*guarantee* one.** Any integration whose silent failure would damage the
research result needs the components below. Prose-only "MUST invoke X"
has repeatedly failed in practice — the executor skips under context
pressure and the caller has no way to detect it.

## Known failure mode (why this contract exists)

Two bugs in the same week, same pathology:

1. **Assurance gate bypass (2026-04-21).** `/paper-writing` ran at
   `— effort: beast` silently skipped `/proof-checker`,
   `/paper-claim-audit`, and `/citation-audit` because each phase's
   content detector could return negative and the outer prose said
   "audit is optional."
2. **Research wiki ingest no-op (2026-04-21).** `/research-wiki init`
   created `research-wiki/papers/` but no paper ever landed there:
   `/arxiv`, `/alphaxiv`, `/deepxiv`, `/semantic-scholar`, `/exa-search`,
   raw `Read`/`WebFetch` — none carried a wiki-ingest hook, and the two
   that did (`/research-lit`, `/idea-creator`) only had soft prose
   ("optional and automatic").

Both bugs ship through the same gap: **one skill "called" another via
prose without a canonical helper, a concrete artifact, or a verifier**.

## Required components

Every integration between two ARIS skills (or between a skill and a
persistent project artifact) must provide all six:

### 1. Activation predicate — single, explicit, observable

A one-line test that says "does this integration fire in this context?"
Must be observable from outside the LLM (a file exists, an argument is
set, an environment variable is present). Not a vibe, not "probably
relevant."

- ✅ `if [ -d research-wiki/ ]`
- ✅ `if assurance == "submission"`
- ❌ "if the user seems to want this"

### 2. Canonical helper — one implementation, not copy-pasted

The business logic lives in **exactly one place** — a script under
`tools/`, or a single subcommand of an existing helper. Every caller
invokes the same entrypoint, but every caller must also resolve
**where** that entrypoint lives, because the helper may sit at any of:

- `<project>/.aris/tools/<helper>` — symlinked by `install_aris.sh` (Phase 0, #174)
- `<project>/tools/<helper>` — manual copy or running from inside the ARIS repo
- `$ARIS_REPO/tools/<helper>` — env var or auto-resolved from the install manifest

So callers MUST use a resolution chain, not a hard-coded path. Pattern:

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null)}"
HELPER=".aris/tools/<helper>"
[ -f "$HELPER" ] || HELPER="tools/<helper>"
[ -f "$HELPER" ] || { [ -n "${ARIS_REPO:-}" ] && HELPER="$ARIS_REPO/tools/<helper>"; }
[ -f "$HELPER" ] || { echo "WARN: <helper> not found; rerun bash tools/install_aris.sh, set ARIS_REPO, or copy the helper to tools/. Skipping this step." >&2; HELPER=""; }
# ... then: [ -n "$HELPER" ] && python3 "$HELPER" <subcommand> ...
```

- ✅ Resolved-via-chain invocation: `python3 "$WIKI_SCRIPT" ingest_paper <root> --arxiv-id <id>` (where `$WIKI_SCRIPT` was set by the chain above with `<helper>=research_wiki.py`)
- ✅ `bash tools/verify_paper_audits.sh <paper> --assurance submission` (helpers under `tools/` that are only run from inside the ARIS repo can stay as plain `tools/...`; the resolution chain only applies to helpers invoked from a downstream user project)
- ❌ Hard-coded `python3 tools/research_wiki.py …` from a downstream skill that may run in a project without `tools/` on disk — it silently exits 2 and the caller proceeds with no side effect, which is exactly the failure mode that left a real user's `research-wiki/` empty for a week.
- ❌ N skills each paraphrasing the same 10-line bash snippet. When one drifts, they all drift.

If the same 3+ lines of prose appear in more than two SKILL.md files,
factor them into a helper.

### 3. Concrete artifact or log entry

Successful execution must leave an observable side effect: a file, a
JSON record, a log line. The artifact is the receipt — something a
third party (verifier, code reviewer, human auditor) can inspect to
answer "did this integration run?"

- ✅ `paper/PROOF_AUDIT.json` with the 6-state verdict schema
- ✅ `research-wiki/papers/<slug>.md` + `research-wiki/log.md` append
- ❌ "the model said it ran"

### 4. Visible checklist — for long workflows

If the integration fires inside a multi-step workflow (paper-writing
Phase 6, idea-discovery Phase 7, etc.), render a **visible checkbox
block** at the start of the phase so the executor has to confront each
row before claiming done. Prose-only "MUST" inside a long SKILL.md is
the first thing to get skipped.

```
📋 Submission audits required before Final Report:
   [ ] 1. /proof-checker   → paper/PROOF_AUDIT.json
   [ ] 2. /paper-claim-audit → paper/PAPER_CLAIM_AUDIT.json
   [ ] 3. /citation-audit  → paper/CITATION_AUDIT.json
   [ ] 4. bash tools/verify_paper_audits.sh paper/ --assurance submission
   [ ] 5. Block Final Report iff verifier exit code != 0
```

Cheap, and empirically resists lazy skipping. Skip only for single-step
invocations (one-off skills like `/arxiv 2501.12345`).

### 5. Backfill / repair command — explicit manual fallback

An escape hatch for when the integration didn't fire. Users must be
able to run a command that **declares** the missed inputs and ingests
them retroactively. Prefer explicit arguments over trace-scanning — the
helper should not have to guess what to backfill.

- ✅ `/research-wiki sync --arxiv-ids 2501.12345,1706.03762`
- ✅ `/research-wiki sync --from-file ids.txt`
- ⚠️ `/research-wiki sync` that scans `.aris/traces/` for arxiv IDs —
     only as a best-effort secondary mode, not the primary UX, and
     clearly labeled as heuristic.

### 6. Verifier or diagnostic (only when load-bearing)

If silent failure of this integration would damage the research result
(wrong numbers shipped to a conference, claims unsupported by
evidence, citations in wrong context), a verifier script must exist
whose exit code is the source of truth for downstream gates.

- ✅ `tools/verify_paper_audits.sh` — exit 1 blocks Final Report
- ✅ `tools/verify_wiki_coverage.sh` — diagnostic only, reports gaps
     but does not block (coverage is not load-bearing on any research
     outcome)

Verifiers must be **external processes** (not LLM self-report), must
validate **concrete artifacts** (§3) against a schema, and must emit a
structured report callers can parse.

A diagnostic-only verifier (no exit-1 blocking) is still valuable — it
surfaces drift to humans. But do not market a diagnostic as a gate.

## Anti-patterns to refuse in review

When reviewing a new integration proposal, reject any of:

- **"Optional and automatic"** — contradicts itself; if it's automatic,
  it's not optional. Pick one and mean it.
- **"The skill will intelligently decide"** — indecision surface, not
  a predicate (§1).
- **"Copy the following 10 lines into each caller"** — missing helper
  (§2); will drift within a month.
- **"The reviewer can see from the logs that..."** — if the evidence is
  unstructured logs, write a schema and make it an artifact (§3).
- **"Users should remember to..."** — missing backfill (§5); humans
  don't reliably remember.
- **"Trust the LLM to self-report completion"** — missing verifier (§6)
  when the failure is load-bearing.

## Known ARIS integrations under this contract

| Integration | Predicate | Helper | Artifact | Checklist | Backfill | Verifier |
|---|---|---|---|---|---|---|
| Submission audits (`max`/`beast`) | `paper/.aris/assurance.txt = submission` | `verify_paper_audits.sh` + 3 audit skills emit JSON | `paper/PROOF_AUDIT.json`, `PAPER_CLAIM_AUDIT.json`, `CITATION_AUDIT.json` + `paper/.aris/audit-verifier-report.json` | Phase 6.0 pre-flight checklist | Rerun the failed audit | `verify_paper_audits.sh` (exit 1 blocks) |
| Research wiki ingest | `research-wiki/` exists | `research_wiki.py ingest_paper` | `research-wiki/papers/<slug>.md` + `log.md` entry | Step in each paper-reading skill | `research_wiki.py sync --arxiv-ids …` | `verify_wiki_coverage.sh` (diagnostic) |
| paper-illustration-image2 finalization | `tools/paper_illustration_image2.py preflight --workspace <cwd>` returns `ok=true` | `paper_illustration_image2.py` (`preflight`, `finalize`, `verify`) | `figures/ai_generated/figure_final.png`, `latex_include.tex`, `review_log.json` | Step 0 checklist in `paper-illustration-image2` | `paper_illustration_image2.py finalize --workspace <cwd> --best-image <png>` | `paper_illustration_image2.py verify` (diagnostic, exit 1 on missing artifacts) |

When adding a new cross-skill integration, add a row to the table above
and confirm all six columns are populated.

## See Also

- `shared-references/assurance-contract.md` — implementation of the
  paper-writing submission gate under this contract
- `shared-references/reviewer-independence.md` — the adjacent contract
  for cross-model review (executor never filters reviewer inputs)
- `tools/verify_paper_audits.sh`, `tools/research_wiki.py ingest_paper`,
  `tools/verify_wiki_coverage.sh` — current canonical helpers
