---
name: oss-review
description: Get a deep external review of an open-source hardening pass from Codex MCP. Use when the user wants a senior maintainer-style review of repository readiness, wants a score and minimum-fix list before publishing, or wants the oss-hardening pipeline to end with an external open-source quality gate.
argument-hint: [repo-path-or-scope]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, mcp__codex__codex, mcp__codex__codex-reply
---

# OSS Review via Codex MCP

Get a deep external review of a repository's open-source readiness from Codex MCP with maximum reasoning depth.

## Context: $ARGUMENTS

## Constants

- REVIEWER_MODEL = `gpt-5.4` — Model used via Codex MCP. Must be an OpenAI model (for example `gpt-5.4`, `gpt-5.3-codex`, `gpt-5.2-codex`)
- REVIEW_DOC = `OSS_REVIEW.md`
- READY_THRESHOLD = overall score >= 7/10 with verdict `ready` or `almost`

## Input Contract

- Primary input: the repository plus any hardening artifacts that already exist:
  - `OSS_AUDIT.md`
  - `OSS_PLAN.md`
  - `OSS_REFACTOR.md`
  - `OSS_TEST_STRATEGY.md`
  - `OSS_CI.md`
  - `OSS_DOCS.md`
  - `OSS_HARDENING_STATUS.md`
- Optional input: explicit publication target, contributor audience, support expectations, or release constraints.
- Default: if hardening artifacts are partial, review the current repository state and clearly label missing evidence.

## Output Contract

Create or update `OSS_REVIEW.md` in the repository root. The review must contain:

1. Repository scope reviewed
2. Overall verdict: `ready`, `almost`, or `not ready`
3. Overall score out of 10
4. Category scorecard:
   - onboarding and usability
   - correctness and user safety
   - maintainability and structure
   - testability and automation
   - CI and release hygiene
   - documentation and contributor clarity
   - security and responsible maintenance
5. Ranked strengths
6. Ranked weaknesses
7. Minimum fixes required before public release
8. Recommended return stage for each weakness: `audit`, `plan`, `refactor`, `tests`, `ci`, or `docs`
9. Full raw reviewer response, preserved verbatim

Also update `OSS_HARDENING_STATUS.md` with the latest review score, verdict, and suggested return stage if the review is not yet positive.

## Non-goals

- Do not treat style preferences as blocking issues unless they affect maintainability or contributor success.
- Do not claim release readiness without checking tests, docs, and automation evidence.
- Do not overwrite prior review history; append or version it.

## Workflow

### Step 1: Gather the repository briefing

Before calling Codex MCP, assemble a concise but complete review packet:

- current repo purpose and target users
- entry points and setup commands
- verification commands that currently pass
- hardening artifacts and what they claim was improved
- remaining known gaps or deferred work

Read the highest-signal files first:

- `README*`
- `CONTRIBUTING.md`
- package/build manifests
- CI workflows
- test directories
- security/changelog docs if present
- the `OSS_*.md` hardening artifacts listed above

### Step 2: Run the initial external review

Send a detailed prompt with xhigh reasoning:

```text
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    You are acting as a senior open-source maintainer and reviewer.

    Review this repository for open-source readiness.

    Repository briefing:
    [paste repo summary, commands, artifacts, and current gaps]

    Please evaluate:
    1. Onboarding and usability
    2. Correctness and user safety
    3. Maintainability and structure
    4. Testability and automation
    5. CI and release hygiene
    6. Documentation and contributor clarity
    7. Security and responsible maintenance

    For each category:
    - score it from 1-10
    - explain the most important strengths and weaknesses

    Then provide:
    - an overall score from 1-10
    - overall verdict: Ready / Almost / Not Ready
    - the minimum fixes required before public release
    - a recommended return stage for each fix: audit / plan / refactor / tests / ci / docs
    - a mock maintainer review summary suitable for a PR or launch checklist

    Be direct and practical. Focus on the smallest fixes that materially improve open-source quality.
```

### Step 3: Continue with follow-up review if needed

Use `mcp__codex__codex-reply` with the returned `threadId` when:

- you need clarification on a weakness
- you want the reviewer to reassess after targeted fixes
- you want a narrower "minimum launchable subset"

Useful follow-up prompts:

- "Which of these issues are true launch blockers versus post-launch improvements?"
- "What is the smallest fix package that would move this from not ready to almost ready?"
- "Map each weakness to the exact files or docs a maintainer should change next."
- "Re-score the repository now that these fixes were applied: [summary]."

### Step 4: Document the result

Append to `OSS_REVIEW.md` using this structure:

```markdown
## Review Round N (timestamp)

### Verdict
- Overall score: X/10
- Verdict: ready / almost / not ready

### Category Scorecard
| Category | Score | Notes |
|----------|-------|-------|
| onboarding and usability | 8/10 | ... |
| correctness and user safety | 7/10 | ... |

### Strengths
- ...

### Weaknesses
- P0 / P1 / P2 style ranking with return stage mapping

### Minimum Fixes Before Release
- ...

### Reviewer Raw Response

<details>
<summary>Full external review</summary>

[paste the complete raw response verbatim]

</details>
```

Also record in `OSS_HARDENING_STATUS.md`:

- latest review score
- latest verdict
- if not ready, the next stage to revisit first

## Stop and Return Rules

- If verdict is `ready`, finish the hardening pass.
- If verdict is `almost`, either stop with the recorded gaps or do one targeted pass and rerun `/oss-review`.
- If verdict is `not ready`, return to the highest-leverage recommended stage and only rerun review after fixes are applied.

## Key Rules

- ALWAYS use `config: {"model_reasoning_effort": "xhigh"}`
- Preserve the full raw reviewer response
- Ask for minimum fixes, not an aspirational roadmap
- Treat missing tests, broken setup, missing docs, and unsafe release posture as higher severity than polish issues
- Keep the review grounded in repo evidence, not imagined release processes

## Done Criteria

- `OSS_REVIEW.md` exists and includes verdict, scorecard, strengths, weaknesses, minimum fixes, return-stage mapping, and raw response
- `OSS_HARDENING_STATUS.md` reflects the latest external review state
- The user can decide whether to publish, patch, or loop back based on the review
