# Assurance Contract

ARIS audits emit machine-readable verdicts. The `assurance` axis decides whether those verdicts are advisory in draft mode or load-bearing gates in submission mode.

This contract is referenced by `paper-writing`, `paper-claim-audit`, `citation-audit`, `proof-checker`, and the external verifier `tools/verify_paper_audits.sh`.

## Why a separate axis from `effort`

`effort` controls depth and cost. `assurance` controls audit strictness.

| Axis | Controls | Default |
|------|----------|---------|
| `effort` | depth/cost, papers, rounds, ideation | `balanced` |
| `assurance` | audit strictness, silent-skip allowed vs verdict required | derived from `effort` |

Override either independently. For example, `— effort: balanced, assurance: submission` means normal depth but every audit must emit a verdict before finalization.

## Assurance Levels

### `draft`

- Audits run only if their content detector matches.
- Silent skip is allowed.
- `paper-writing` can produce a final report without the submission verifier.
- Use for rapid iteration and early drafts.

### `submission`

- All mandatory audits must emit a verdict.
- Silent skip is forbidden.
- `paper-writing` runs `tools/verify_paper_audits.sh`.
- A non-zero verifier exit blocks the Final Report.
- The Final Report marks `submission-ready: yes/no` from verifier output.

## Default Mapping

| `effort` | implied `assurance` |
|----------|---------------------|
| `lite` | `draft` |
| `balanced` | `draft` |
| `max` | `submission` |
| `beast` | `submission` |

Users who want strict audits at lower depth should pass `— assurance: submission`.

## Verdict State Machine

Every mandatory audit must emit exactly one of these verdicts:

| Verdict | Meaning | Submission-blocking? |
|---------|---------|----------------------|
| `PASS` | All checks passed | No |
| `WARN` | Issues found, none disqualifying | No |
| `FAIL` | Disqualifying issues found | Yes |
| `NOT_APPLICABLE` | Detector negative; nothing to audit | No |
| `BLOCKED` | Audit should apply but prerequisites are missing | Yes |
| `ERROR` | Audit invocation failed | Yes |

`NOT_APPLICABLE` means the audit phase ran and wrote an artifact documenting that there was nothing to verify. It is not the same as a silent skip.

`BLOCKED` means the audit should have run but could not, such as numeric claims with no raw result files.

## Required Audit Artifact Schema

Every mandatory audit must write a JSON artifact, and may also write a Markdown sibling:

```json
{
  "audit_skill": "paper-claim-audit",
  "verdict": "PASS",
  "reason_code": "all_numbers_match",
  "summary": "Verified 23 numeric claims against 4 result files; no mismatches.",
  "audited_input_hashes": {
    "main.tex": "sha256:a3f8...",
    "sections/5_evidence.tex": "sha256:b2d1..."
  },
  "trace_path": ".aris/traces/paper-claim-audit/2026-04-21_run01/",
  "agent_id": "019dae73-fc12-4ab8-...",
  "reviewer_model": "gpt-5.4",
  "reviewer_reasoning": "xhigh",
  "generated_at": "2026-04-21T14:23:01Z",
  "details": {}
}
```

Field rules:

- `audit_skill` identifies the child audit skill.
- `verdict` is one of the six allowed verdicts.
- `audited_input_hashes` contains SHA256 hashes for every file consumed by the audit.
- In-paper paths are relative to the paper directory passed to the verifier.
- Files outside the paper directory may use absolute paths.
- `trace_path` points to the saved reviewer trace.
- `agent_id` is the Codex reviewer id when a reviewer agent was used.
- `reviewer_model` and `reviewer_reasoning` document the reviewer route.
- `generated_at` is UTC ISO-8601.

## Verifier Contract

`tools/verify_paper_audits.sh <paper-dir>` is the single source of truth for mandatory audit completeness. It must:

1. Locate expected audit artifacts.
2. Validate JSON required fields.
3. Verify each verdict is allowed.
4. Recompute `audited_input_hashes` and flag stale artifacts.
5. Verify `trace_path` exists when required.
6. Exit 0 only when all mandatory audits are green.

At `assurance: submission`, `paper-writing` must treat verifier exit 1 as blocking.

## Subskill Contract

Child audit skills follow this contract:

- Always emit a verdict artifact, even on detector-negative or error paths.
- Never decide final submission readiness themselves.
- The parent skill and verifier decide whether a verdict blocks finalization.

## Backward Compatibility

The default `effort: balanced` maps to `assurance: draft`, preserving normal draft behavior. `effort: max` and `effort: beast` imply `assurance: submission` unless the user explicitly overrides with `assurance: draft`.
