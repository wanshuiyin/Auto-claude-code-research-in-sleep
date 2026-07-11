# Assurance Contract

ARIS audits emit machine-readable verdicts. The `assurance` axis decides whether
those verdicts are advisory (draft mode) or load-bearing gates (submission mode).
This contract is referenced by `paper-writing`, `paper-claim-audit`, `citation-audit`,
`proof-checker`, and the external verifier (canonical name `verify_paper_audits.sh`;
callers resolve the actual path via `integration-contract.md` §2).

## Why a separate axis from `effort`

Historically `effort` (lite/balanced/max/beast) was conflated with audit strictness.
The result: `effort: beast` did not guarantee mandatory audits ran — phases were
gated by content detectors (e.g. `if \begin{theorem} exists`) and could silently
skip. A user reported `effort: beast` produced a "draft-quality" paper with all
three submission-gate audits skipped.

The fix is to split the concerns:

| Axis | Controls | Default |
|------|----------|---------|
| `effort` | depth/cost (papers, rounds, ideation) | `balanced` |
| `assurance` | audit strictness — silent-skip-allowed vs verdict-required | derived from `effort` (see mapping) |

Override either independently: `— effort: balanced, assurance: submission` is
legal and means "normal depth, but every audit must emit a verdict before
finalization."

## Assurance Levels

### `draft` — current behavior, no breakage
- Audits run only if their content detector matches.
- Silent skip allowed.
- `paper-writing` Phase 6 produces a final report regardless.
- For: rapid iteration, exploratory drafts, early-stage research.

### `submission` — load-bearing audits
- All mandatory audits **must** emit a verdict (one of the 6 below).
- Silent skip is **forbidden**.
- `paper-writing` Phase 6 invokes `verify_paper_audits.sh` (resolved per
  `integration-contract.md` §2); non-zero exit blocks Final Report.
- The Final Report tags itself `submission-ready: yes/no` based on verifier output.
- For: conference / journal submission, anything you'd put your name on.

## Default Mapping (derived if `assurance` not given)

| `effort` | implied `assurance` |
|----------|---------------------|
| `lite` | `draft` |
| `balanced` | `draft` |
| `max` | `submission` |
| `beast` | `submission` |

This means a user passing only `— effort: beast` automatically gets full audit
enforcement — matching their intent ("turn everything up"). Users wanting
strict audits at lower depth pass `— assurance: submission` explicitly.

## Verdict State Machine

Every mandatory audit must emit exactly one of these — never silent skip:

| Verdict | Meaning | Audit ran? | Submission-blocking? |
|---------|---------|-----------|----------------------|
| `PASS` | All checks passed | Yes | No |
| `WARN` | Issues found, none disqualifying | Yes | No |
| `FAIL` | Disqualifying issues found | Yes | **Yes** |
| `NOT_APPLICABLE` | Detector negative; nothing to audit (e.g., no theorems in paper, no `\cite`s, no numeric claims) | Audit phase ran, child audit invocation may have been skipped | No |
| `BLOCKED` | Audit should apply but prerequisites are missing or unsupported (e.g., paper has numeric claims but no `results/` directory; paper cites references but `.bib` missing) | Could not complete | **Yes** |
| `ERROR` | Audit invocation failed (network, timeout, malformed reviewer output) | Attempted but errored | **Yes** at submission |

### Why `NOT_APPLICABLE` is not the same as `SKIP`

`NOT_APPLICABLE` means **the audit phase ran**, the detector returned negative,
and a verdict artifact was written documenting "we checked, there's nothing to
verify." This is verifiable from outside the LLM — the artifact file exists.

A silent skip leaves no record. There's no way to distinguish "we checked and
there was nothing" from "we forgot." This contract makes that distinction
mandatory.

### Why `BLOCKED` is more dangerous than `NOT_APPLICABLE`

`BLOCKED` means the audit *should* have run but cannot. Example: a paper claims
`accuracy = 89.2%` but has no `results/` directory to verify against. That's not
"nothing to audit" — that's "we cannot verify a load-bearing claim." Treating
this as `SKIP` masks the danger; `BLOCKED` surfaces it and blocks submission.

## Required Audit Artifact Schema

Every mandatory audit must write a JSON artifact (and may also write a
human-readable Markdown sibling). The JSON must contain at minimum:

```json
{
  "audit_skill": "paper-claim-audit",       // citation-audit, proof-checker, etc.
  "verdict": "PASS",                         // one of the 6 above
  "reason_code": "all_numbers_match",        // skill-specific short string
  "summary": "Verified 23 numeric claims against 4 result files; no mismatches.",
  "audited_input_hashes": {
    "main.tex":                          "sha256:a3f8...",
    "sections/5.evidence.tex":           "sha256:b2d1...",
    "/Users/me/project/results/run_2026_04_19.json": "sha256:c9e4..."
  },
  "trace_path": ".aris/traces/paper-claim-audit/2026-04-21_run01/",
  "thread_id":  "019dae73-fc12-4ab8-...",
  "executor_model": "claude-opus-4-8",
  "executor_family": "anthropic",
  "reviewer_model": "gpt-5.6-sol",
  "reviewer_family": "openai",
  "review_independence": "cross-family",
  "acceptance_status": "accepted",
  "reviewer_reasoning": "xhigh",
  "generated_at": "2026-04-21T14:23:01Z",
  "details": {
    // skill-specific structured data
  }
}
```

Field semantics:

- **`audited_input_hashes`** — SHA256 of every file the audit consumed.
  - Keys are **paths relative to the paper directory** (the argument
    passed to `verify_paper_audits.sh`) for files inside it, or
    **absolute paths** for files outside it (e.g. `../results/run.json`
    is legal but `/Users/me/project/results/run.json` is more portable).
    Do NOT prefix in-paper files with `paper/` — the verifier already
    resolves relative to the paper dir and `paper/paper/main.tex` will
    false-fail. The verifier rehashes the current files and flags `STALE`
    if any hash changed since the audit ran. (User edited `main.tex`
    after running `paper-claim-audit`? The next verifier run will catch it.)
- **`trace_path`** — directory containing the full reviewer prompt + response
  pair, per `review-tracing.md`. Required for mandatory audits — not optional.
- **`thread_id` or `agent_id`** — durable reviewer handle. MCP routes use a
  thread ID; Codex `spawn_agent` routes use an agent ID. At least one is required.
- **`reviewer_model`** + **`reviewer_reasoning`** — proves cross-family review
  invariant was honored.
- **`review_independence`** — `same-family`, `cross-family`, or `deterministic`.
  `deterministic` is valid ONLY for what a process can actually decide
  (compilation, schema validity, hash freshness, test suites) — the audit
  aggregator REJECTS a deterministic label on the four semantic paper audits
  (proof / claims / citations / attack), which only a cross-family model
  review can accept.
  **`acceptance_status`** is `provisional` for same-family review and
  `accepted` for cross-family/deterministic review; neither field rewrites the
  substantive verdict.
- **`generated_at`** — UTC ISO-8601 timestamp.

## Verifier Contract

`verify_paper_audits.sh <paper-dir>` (canonical name; resolved per
`integration-contract.md` §2) is the single source of truth for
"are mandatory audits complete and current?" It must:

1. Locate the paper-writing manifest (which mandatory audits applied this run).
2. For each, check artifact JSON exists at expected path.
3. Validate artifact JSON against required-fields schema (above).
4. Verify `verdict` is one of the 6 allowed values.
5. Recompute SHA256 of every file in `audited_input_hashes`; flag `STALE` if any
   mismatches.
6. Verify `trace_path` exists and is non-empty.
7. Output a structured JSON report and exit 0 (all green) or 1 (any FAIL /
   BLOCKED / ERROR / STALE / missing artifact).

The report also emits `overall_assurance`: `blocked` for a blocking condition,
`provisional` when green artifacts include same-family or legacy-unspecified
review, and `accepted` only when all green artifacts are cross-family or
deterministic. Provisional remains exit 0 but must never be presented as
submission-ready yes.

Phase 6 of `paper-writing` invokes the verifier; at `assurance: submission`,
non-zero exit blocks Final Report generation.

## Subskill Contract: "Always Emit, Never Block"

Child audit skills (`paper-claim-audit`, `citation-audit`, `proof-checker`)
follow this contract:

- **Always emit a verdict artifact**, even on detector-negative or error paths.
- **Never block** the parent's flow themselves — they only emit verdicts.
- **The parent skill** (`paper-writing` Phase 6 + verifier) decides whether a
  given verdict blocks finalization. This decision lives in *one* place
  (`assurance` axis + verifier), not duplicated across child skills.

Earlier wording in `paper-claim-audit` and `citation-audit` (e.g., "audit is
advisory, never blocking") referred to this division of labor — but conflicted
with `paper-writing`'s declaration that they were "mandatory submission gates."
This contract resolves the conflict: child = always emit; parent = decides
blocking based on assurance level.

## Examples

### Theory paper, beast effort
```
— effort: beast    (implies assurance: submission)
```
- `proof-checker` runs, audits theorems → `PASS` or `WARN` or `FAIL`
- `paper-claim-audit` runs, finds numbers → `PASS`
- `citation-audit` runs, audits refs → `PASS`
- Verifier: all green
- Final Report: `submission-ready: yes`

### Position paper (no theorems, no numbers, no experiments), beast effort
```
— effort: beast    (implies assurance: submission)
```
- `proof-checker` invoked → no theorems found → emits `NOT_APPLICABLE`
- `paper-claim-audit` invoked → no numeric claims → emits `NOT_APPLICABLE`
- `citation-audit` invoked → audits refs → `PASS`
- Verifier: all green (NOT_APPLICABLE is not blocking)
- Final Report: `submission-ready: yes` with note "no theorems / no numeric claims to audit"

### Empirical paper missing raw results, beast effort
```
— effort: beast
```
- `proof-checker` → `NOT_APPLICABLE`
- `paper-claim-audit` invoked → finds claims like `accuracy = 89.2%` but
  `results/` is empty → emits `BLOCKED` with reason_code `no_raw_evidence`
- `citation-audit` → `PASS`
- Verifier: exit 1 (BLOCKED is submission-blocking)
- Final Report: **refuses to finalize**; surfaces "Mandatory audit BLOCKED:
  paper-claim-audit cannot verify numeric claims — no raw result files found.
  Add results/ or downgrade to `— assurance: draft`."

### Stale audit (user edited paper after running audits)
- User runs `/paper-writing` at beast → all audits PASS, files written
- User edits `sec/5.evidence.tex` to change a number
- User reruns the verifier (or re-finalizes)
- Verifier rehashes → `audited_input_hashes` mismatch → `STALE` flag → exit 1
- Final Report: refuses; instructs user to rerun `paper-claim-audit` and
  `citation-audit` before re-finalizing.

## Backward Compatibility

- Users on `effort: balanced` (default) get `assurance: draft` — **identical
  current behavior, no breakage**.
- Users explicitly using `effort: max` or `effort: beast` automatically get
  `assurance: submission` — matching their intent.
- Users wanting the old "beast = depth only, no audit enforcement" can pass
  `— effort: beast, assurance: draft` (explicit override). This combination is
  legal but discouraged for actual submissions.

## See Also

- `effort-contract.md` — depth/cost axis (separate concern)
- `review-tracing.md` — trace artifact protocol (referenced by `trace_path`)
- `reviewer-independence.md` — cross-model review invariant
- `tools/verify_paper_audits.sh` — external verifier implementation
