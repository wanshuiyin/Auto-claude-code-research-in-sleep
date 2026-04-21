# Effort Contract

## Overview

Every ARIS skill accepts an optional `effort` parameter that controls how much work the system does. This affects breadth, depth, iterations, and coverage — but **never** the quality of cross-model review.

```
/any-skill "args" — effort: lite | balanced | max | beast
```

Default: `balanced` (current behavior, zero change for existing users).

## Hard Invariants (NEVER changed by effort)

| Setting | Value | Why |
|---------|-------|-----|
| Codex reasoning_effort | **xhigh** | Reviewer quality is non-negotiable |
| DBLP/CrossRef citations | **on** | Citation integrity is non-negotiable |
| Reviewer independence | **on** | Cross-model protocol is non-negotiable |
| Experiment integrity | **on** | Fraud prevention is non-negotiable |
| Sanity check | **on** | Safety is non-negotiable |
| **Mandatory audit emission** | **always** | At `assurance: submission`, every mandatory audit emits a verdict (PASS/WARN/FAIL/NOT_APPLICABLE/BLOCKED/ERROR). Silent skip is forbidden. See `assurance-contract.md`. |
| AUTO_PROCEED | **user decides** | Orthogonal to effort |
| difficulty | **user decides** | Orthogonal to effort |
| `assurance` | **derived from `effort`** (see Assurance Axis below) | Audit strictness is a separate axis from depth |

## Four Levels

### `lite` (~0.4x tokens)
For budget-constrained users or quick explorations. Minimum viable depth.
Implies `assurance: draft` (see below).

### `balanced` (1x tokens) — DEFAULT
Current ARIS behavior. What existing users get today. No breakage.
Implies `assurance: draft`.

### `max` (~2.5x tokens)
Go deeper than defaults. More papers, more ideas, more rounds, more detail.
Implies `assurance: submission` — mandatory audits are load-bearing.

### `beast` (~5-8x tokens)
No budget limit. Every knob to maximum. For top-venue submission sprints.
Implies `assurance: submission` — mandatory audits are load-bearing and the
final report is tagged `submission-ready` only when the verifier agrees.

## Assurance Axis (separate concern from `effort`)

Audit strictness lives on a second axis, `assurance`. Full contract:
**`shared-references/assurance-contract.md`**.

```
— assurance: draft | submission
```

Default mapping (if `assurance` not given explicitly):

| `effort` | implied `assurance` | Behavior |
|----------|---------------------|----------|
| `lite` | `draft` | Audits run only if content detector matches; silent skip allowed |
| `balanced` | `draft` | Same as lite — current behavior, zero breakage |
| `max` | `submission` | Every mandatory audit emits a verdict; verifier blocks Final Report on FAIL/BLOCKED/ERROR/STALE |
| `beast` | `submission` | Same as max + final report tagged `submission-ready` |

User can override independently:
- `— effort: balanced, assurance: submission` → normal depth, strict audits
- `— effort: beast, assurance: draft` → maximum depth, no audit gate (legal but discouraged for real submissions)

**Why split the axes?** Historically `effort: beast` did not enforce audits — phases like `/proof-checker`, `/paper-claim-audit`, `/citation-audit` were gated by content detectors that allowed silent skip. A user reported `effort: beast` produced a "draft-quality" paper with all three submission gates skipped. The split makes audit strictness independently verifiable and stops conflating "do more work" with "be more rigorous."

## Per-Skill Profiles

### Discovery & Planning

| Skill | Dimension | lite | balanced | max | beast |
|-------|-----------|------|----------|-----|-------|
| research-lit | papers found | 6-8 | 10-15 | 18-25 | 40-50 |
| research-lit | query variants | 2 | 5 | 8 | 15+ |
| research-lit | deep reads | 3 | 5-8 | 8 | 15+ |
| idea-creator | ideas generated | 4-6 | 8-12 | 12-16 | 20-30 |
| idea-creator | pilots | 1-2 | 2-3 | 3-4 | 5-6 |
| novelty-check | claims checked | 2-3 | 3-4 | 4-6 | all |
| novelty-check | closest works | top-3 | top-5 | top-8 | top-10+ |
| research-refine | max rounds | 3 | 5 | 7 | 10+ |
| research-refine | papers considered | 8 | 15 | 24 | 30+ |
| experiment-plan | core experiments | 3 | 5 | 7 | 10+ |
| experiment-plan | seeds | 1 | 3 | 5 | 5 |
| experiment-plan | baseline families | 2 | 3 | 4 | 5+ |

### Execution

| Skill | Dimension | lite | balanced | max | beast |
|-------|-----------|------|----------|-----|-------|
| experiment-bridge | scope | sanity + main | main + basic ablation | + top ablation + robustness | full suite + cross-validation |
| run-experiment | launches | smoke + main | smoke + multi-seed | + dry run + manifest | full config + multi-GPU parallel |
| monitor-experiment | depth | latest log | log + JSON | + W&B + anomaly | real-time + auto-alert + trend |
| analyze-results | findings | 3 | 5 | 8 | full-dimensional + stat tests |
| ablation-planner | ablations | 2-3 | 4-5 | 6-8 | 10+ |

### Review

| Skill | Dimension | lite | balanced | max | beast |
|-------|-----------|------|----------|-----|-------|
| auto-review-loop | max rounds | 2 | 3-4 | 6 | 8+ (until converged) |
| auto-review-loop | fixes per round | 1-2 | 3-4 | 4-6 | all actionable |
| research-review | passes | 1 | 1 + follow-up | 1 + 2 follow-ups | 2 independent + cross-compare |
| experiment-audit | depth | skip | basic 4 checks | full 6 checks | line-by-line + reproduce |

### Writing & Rebuttal

| Skill | Dimension | lite | balanced | max | beast |
|-------|-----------|------|----------|-----|-------|
| paper-plan | outline reviews | 0 | 1 | 2 | 3 |
| paper-plan | citations/section | 2-3 | 4-5 | 5-8 | 8+ |
| paper-figure | caption reviews | 1 | 1 | 2 | 3 |
| paper-write | abstract variants | 1 | 1 | 2 | 3 |
| paper-write | related work depth | shallow | standard | deep | exhaustive |
| paper-compile | fix attempts | 2 | 3 | 4 | until zero warnings |
| auto-paper-improvement | rounds | 1 | 2 | 3 | 5 |
| paper-illustration | render iterations | 2 | 3 | 5 | 7 |
| rebuttal | draft rounds | 1 | 2 | 3 | 5 |
| rebuttal | stress tests | 0-1 | 1 | 2 | 3 |

## How to Read Effort in a Skill

Add this to the Constants section of each skill:

```markdown
## Constants

- **EFFORT = `balanced`** — Work intensity. Options: `lite`, `balanced`, `max`, `beast`. Override: `— effort: max`
```

Then adjust numeric constants based on effort level. Example:

```
Parse $ARGUMENTS for `— effort:` directive.
If not specified, default to `balanced`.

Adjust constants:
  if effort == "lite":     MAX_PAPERS = 8,  MAX_IDEAS = 6,  MAX_ROUNDS = 2
  if effort == "balanced": MAX_PAPERS = 15, MAX_IDEAS = 12, MAX_ROUNDS = 4
  if effort == "max":      MAX_PAPERS = 25, MAX_IDEAS = 16, MAX_ROUNDS = 6
  if effort == "beast":    MAX_PAPERS = 50, MAX_IDEAS = 30, MAX_ROUNDS = 8
```

## Transparency

Every skill should print its effort configuration at the start:

```
⚡ [effort: max] papers=25, ideas=16, rounds=6 | Codex: xhigh (always)
```

## Precedence

```
explicit concrete knob (e.g., review_rounds: 2)
  > explicit dimension override
    > overall effort level
      > skill default (balanced)
```

Example: `— effort: beast, review_rounds: 3` → everything beast except review capped at 3.

For the `assurance` axis, precedence is independent:
```
explicit `assurance: ...` directive
  > effort-implied default (lite/balanced → draft, max/beast → submission)
    > skill default (draft)
```

Example: `— effort: balanced, assurance: submission` → normal depth knobs but submission-gate audit enforcement.

## Token Cost Estimation

| Level | LLM tokens | GPU/wall-clock | Best for |
|-------|-----------|----------------|----------|
| lite | ~0.4x | ~0.5x | Quick exploration, budget users |
| balanced | 1x | 1x | Normal research workflow |
| max | ~2.5x | ~2x | Serious submission prep |
| beast | ~5-8x | ~3-4x | Top-venue final sprint |
