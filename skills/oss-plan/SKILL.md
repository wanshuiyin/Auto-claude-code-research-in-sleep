---
name: oss-plan
description: Convert an open-source hardening audit into an executable implementation plan. Use when the user says "turn this audit into a plan", "make a checklist", "write a GitHub issue", or wants a PR-ready checklist with acceptance criteria and commands.
argument-hint: [audit-path-or-scope]
allowed-tools: Read, Grep, Glob, Write
---

# OSS Plan

Turn audit findings into a staged implementation plan that is ready to paste into a GitHub issue or PR description.

## Context: $ARGUMENTS

## Input Contract

- Primary input: `OSS_AUDIT.md`.
- Optional input: user constraints, milestone boundaries, contributor capacity, or "only do P0/P1".
- Fallback: if `OSS_AUDIT.md` is missing, derive a minimal audit summary from the repository and clearly label it as reconstructed.

## Output Contract

Create or update `OSS_PLAN.md` in the repository root. The file must contain:

1. Scope summary: what this hardening pass covers and excludes.
2. A staged checklist that can be pasted into a GitHub issue or PR description.
3. For every checklist item:
   - Purpose
   - Change points
   - Acceptance criteria
   - Suggested command(s)
   - Estimated impact radius
4. An explicit execution order with stop points.

Use this item shape exactly:

```markdown
- [ ] Add CLI regression tests
  Purpose: protect the main user flow before refactoring.
  Change points: `tests/test_cli.py`, `src/cli.py`.
  Acceptance criteria: happy-path and invalid-input flows pass locally and in CI.
  Suggested commands: `python -m unittest`, `python src/cli.py --help`.
  Estimated impact radius: low; test-only plus light CLI guard changes.
```

Also include a short "minimum shippable subset" section for contributors who only have one small PR available.

## Non-goals

- Do not implement code changes in this step.
- Do not pad the plan with aspirational work unrelated to the audit.
- Do not turn one small repo improvement into a multi-quarter roadmap.

## Workflow

### Step 1: Read and normalize the audit

- Collapse duplicate findings.
- Merge recommendations that touch the same files or commands.
- Separate foundational work from follow-on polish.

### Step 2: Build an execution order

Prefer this dependency order unless the repository clearly needs a different one:

1. Safety and correctness
2. Minimal structural refactor
3. Tests
4. CI
5. Docs and metadata

### Step 3: Write checklist items

Each item should be independently reviewable. If an item feels too big for one PR, split it.

Good checklist items are:

- file-specific
- command-aware
- acceptance-testable
- small enough to review

### Step 4: Mark stop points

Add explicit pause points such as:

- Stop after refactor if behavior changed unexpectedly.
- Stop after tests if mocks are not trustworthy yet.
- Stop before CI if local commands still fail nondeterministically.

## Failure Handling

- If the audit is incomplete, keep the plan narrow and call out the missing audit areas.
- If estimated impact is uncertain, say so and recommend a smaller first PR.
- If the repo has no runnable command, mark "establish reproducible local run command" as the first checklist item.

## Done Criteria

- `OSS_PLAN.md` can be copied directly into GitHub with minimal editing.
- Every item includes purpose, change points, acceptance criteria, commands, and impact.
- The plan is ordered, scoped, and stoppable.
