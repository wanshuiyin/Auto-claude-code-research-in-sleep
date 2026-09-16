# Proof Audit Output Contract

Use this format for saved audits. Keep chat-only audits shorter but preserve
the same verdict and issue semantics.

## Markdown Audit

```md
# Proof Audit

Target: <file/section/task>
Verdict: PASS | WARN | FAIL | BLOCKED | NOT_APPLICABLE
Claim status: PROVABLE AS STATED | PROVABLE AFTER WEAKENING / EXTRA ASSUMPTION | NOT CURRENTLY JUSTIFIED
Reviewer backend: llm-chat-deepseek | local-executor-fallback | local-codex-fallback
Reviewer model: <model name or unknown>

## Claim Restatement

<explicit statement with assumptions, quantifiers, domains, and conclusion>

## Obligation Ledger

| ID | Obligation | Location | Status | Notes |
|----|------------|----------|--------|-------|

## Issues

| ID | Severity | Category | Location | Summary | Minimal repair |
|----|----------|----------|----------|---------|----------------|

## Counterexample Pass

<attempts, successful counterexamples, or candidates>

## Recommended Repair

<minimal honest fix: add derivation, add assumption, weaken claim, add reference, or split lemma>

## Remaining Risks

<what was not checked or still depends on external material>
```

## Issue Record

For each serious issue, include:

```md
### I<n>: <short title>

- Severity: FATAL | CRITICAL | MAJOR | MINOR
- Category: <taxonomy label>
- Status: INVALID | UNJUSTIFIED | UNDERSTATED | OVERSTATED | UNCLEAR
- Impact: GLOBAL | LOCAL | COSMETIC
- Location: <file:line or section>
- Claimed step: <what the proof asserts>
- Problem: <why it does not follow>
- Counterexample: YES | NO | CANDIDATE, with details
- Downstream effect: <what breaks>
- Minimal repair: <add derivation / add assumption / weaken claim / cite result and verify conditions>
```

## Optional JSON Artifact

Write the machine-readable audit to the RUN DIRECTORY as
`prompts/<run-id>/PROOF_ORCHESTRATOR_AUDIT.json`, and only when a caller or
formal workflow requests one. Never write `<paper-dir>/PROOF_AUDIT.json` —
that path is `/proof-checker`'s canonical submission artifact, and this skill
must not create, overwrite, or shadow it. A proof-orchestrator audit is
additional evidence for the run, not a submission verdict.

Use paths relative to the run directory for files inside it. Use absolute
paths for files outside it.

```json
{
  "audit_skill": "proof-orchestrator",
  "audit_mode": "deepseek-second-opinion",
  "verdict": "PASS | WARN | FAIL | NOT_APPLICABLE | BLOCKED | ERROR",
  "reason_code": "all_proofs_complete | minor_gaps | critical_gap | no_theorems | source_unreadable | reviewer_error",
  "summary": "One-line verdict summary.",
  "audited_input_hashes": {
    "main.tex": "sha256:..."
  },
  "generated_at": "<UTC ISO-8601>",
  "reviewer_backend": "llm-chat-deepseek | local-executor-fallback | local-codex-fallback",
  "reviewer_model": "deepseek-v4-pro | deepseek-chat | deepseek-reasoner | unknown",
  "review_independence": "cross-family | same-family | none",
  "acceptance_status": "provisional-evidence-only",
  "executor_family": "<claude | gpt | other>",
  "reviewer_family": "<deepseek | gpt | claude | unknown>",
  "raw_reviewer_verdict": "<the reviewer's own verdict before any executor validation, or null>",
  "details": {
    "theorems_audited": 0,
    "issues": [
      {
        "id": "I1",
        "severity": "FATAL|CRITICAL|MAJOR|MINOR",
        "category": "QUANTIFIER_ERROR",
        "location": "sections/theory.tex:L182",
        "note": "..."
      }
    ]
  }
}
```

## Verdict Mapping

- `NOT_APPLICABLE`: no theorem, lemma, proposition, corollary, or proof content.
- `BLOCKED`: required source is unreadable or missing.
- `PASS`: all proof obligations discharged.
- `WARN`: only minor issues, or major issues with explicit justification that the main conclusion survives.
- `FAIL`: any fatal or critical issue, or a major issue that may affect the main conclusion.
- `ERROR`: audit machinery failed.

## Independence Labeling

`review_independence` is derived, never asserted: `cross-family` only when the
verified reviewer model family differs from the executor's family (see
`deepseek-routing.md` for the verification requirement); `same-family` when
they match; `none` for `local-executor-fallback` / `local-codex-fallback`.
A `PASS` from a `same-family` or `none` review is provisional evidence for the
run and can never satisfy a cross-family acceptance gate — `acceptance_status`
stays `provisional-evidence-only` in every case; formal acceptance belongs to
`/proof-checker` and the paper workflows.
