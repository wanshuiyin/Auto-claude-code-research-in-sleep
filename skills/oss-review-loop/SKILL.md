---
name: oss-review-loop
description: Autonomous multi-round open-source review loop. Repeatedly reviews a repository via Codex MCP, applies the minimum hardening fixes, and re-reviews until the repository is release-ready or max rounds are reached. Use when the user says "review until it passes", "open source review loop", "maintainer review loop", or wants the oss-hardening pipeline to end with an external quality gate and iterative fixes.
argument-hint: [repo-path-or-scope]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# OSS Review Loop

Autonomously iterate: review -> implement the minimum hardening fixes -> re-review, until the external reviewer gives a positive release-readiness assessment or `MAX_ROUNDS` is reached.

## Context: $ARGUMENTS

## Constants

- MAX_ROUNDS = 4
- POSITIVE_THRESHOLD: score >= 7/10, or verdict contains `ready` or `almost`
- REVIEW_DOC = `OSS_REVIEW_LOOP.md` in the project root
- REVIEWER_MODEL = `gpt-5.4` — Model used via Codex MCP. Must be an OpenAI model (for example `gpt-5.4`, `gpt-5.3-codex`, `gpt-5.2-codex`)

## Input Contract

- Primary input: the repository plus any hardening artifacts that already exist:
  - `OSS_AUDIT.md`
  - `OSS_PLAN.md`
  - `OSS_REFACTOR.md`
  - `OSS_TEST_STRATEGY.md`
  - `OSS_CI.md`
  - `OSS_DOCS.md`
  - `OSS_HARDENING_STATUS.md`
  - `OSS_REVIEW.md` if a one-shot review already happened
- Optional input: explicit release target, contributor audience, support expectations, or constraints like "no new deps".
- Default: if artifacts are partial, review the current repo state and fix the highest-leverage open-source gaps first.

## Output Contract

Create or update `OSS_REVIEW_LOOP.md` as a cumulative log. Each round must include:

1. Overall score
2. Verdict: `ready`, `almost`, or `not ready`
3. Ranked weaknesses
4. Minimum fixes requested by the reviewer
5. Actions taken this round
6. Verification commands and outcomes
7. Full raw reviewer response, preserved verbatim

Also update `OSS_HARDENING_STATUS.md` after every round with:

- current review-loop round
- latest score
- latest verdict
- next recommended stage or command

## Non-goals

- Do not chase cosmetic perfection if the repository is already releasable.
- Do not hide failing checks, weak docs, or missing automation to get a better score.
- Do not broaden the scope beyond the minimum fixes that materially improve release readiness.

## Workflow

### Initialization

1. Read `README*`, `CONTRIBUTING.md`, package/build manifests, CI workflows, tests, and the `OSS_*.md` hardening artifacts.
2. Identify current strengths, known gaps, and available local verification commands.
3. Initialize round counter = 1.
4. Create or update `OSS_REVIEW_LOOP.md` with a header and timestamp.

### Loop (repeat up to MAX_ROUNDS)

#### Phase A: Review

Send comprehensive repository context to the external reviewer:

```text
mcp__codex__codex:
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N/MAX_ROUNDS of open-source review loop]

    Repository briefing:
    [purpose, setup commands, verification commands, hardening artifacts, known gaps]

    Please act as a senior open-source maintainer reviewing this repository for public release readiness.

    Evaluate:
    1. Onboarding and usability
    2. Correctness and user safety
    3. Maintainability and structure
    4. Testability and automation
    5. CI and release hygiene
    6. Documentation and contributor clarity
    7. Security and responsible maintenance

    Then provide:
    1. Overall score 1-10
    2. Overall verdict: Ready / Almost / Not Ready
    3. Remaining critical weaknesses ranked by severity
    4. For each weakness, specify the MINIMUM fix
    5. For each fix, specify the best return stage: audit / plan / refactor / tests / ci / docs

    Be direct and practical. Focus on the smallest fix package that materially improves open-source quality.
```

If this is round 2+, use `mcp__codex__codex-reply` with the saved `threadId` to maintain conversation context.

#### Phase B: Parse Assessment

Save the full raw response verbatim for the round log. Then extract:

- overall score
- verdict
- ranked weaknesses
- minimum fixes
- return stage for each fix

Stop condition:

- If score >= 7 and verdict contains `ready` or `almost`, stop the loop and document final state.

#### Phase C: Implement Fixes

Apply the minimum fixes in priority order. Use the recommended return stage to guide how you respond:

- `audit`: revisit the repo assumptions and update `OSS_AUDIT.md` and `OSS_PLAN.md` only as needed
- `plan`: tighten scope, ordering, or acceptance criteria in `OSS_PLAN.md`
- `refactor`: apply the smallest structural or tooling change that unlocks maintainability
- `tests`: add or repair CI-safe tests, fixtures, and local verification commands
- `ci`: update or add the minimal workflow needed to enforce checks
- `docs`: tighten README, FAQ, architecture notes, `SECURITY.md`, or `CHANGELOG.md`

Rules for implementation:

- Prefer the smallest change set that addresses the reviewer concern
- Reuse the existing `oss-*` stage artifacts instead of inventing a parallel process
- If a fix clearly belongs to another stage skill, follow that stage's contract and update its artifact

#### Phase D: Verify

After implementing fixes:

- run the narrowest relevant local verification commands
- record success or failure
- if a command fails, fix the highest-leverage issue before asking for re-review

Typical verification sources:

- commands documented in `README*`
- commands recorded in `OSS_TEST_STRATEGY.md`
- commands recorded in `OSS_CI.md`
- repository-native scripts such as `npm test`, `python -m unittest`, `pytest`, `cargo test`, `go test ./...`

#### Phase E: Document Round

Append to `OSS_REVIEW_LOOP.md`:

```markdown
## Round N (timestamp)

### Assessment
- Score: X/10
- Verdict: ready / almost / not ready
- Key weaknesses: [bullet list]

### Minimum Fixes Requested
- [fix 1] -> return stage: tests
- [fix 2] -> return stage: docs

### Actions Taken
- [what was changed]

### Verification
- [command] -> [pass/fail]

### Reviewer Raw Response

<details>
<summary>Click to expand full reviewer response</summary>

[paste the complete raw response verbatim]

</details>

### Status
- [continuing to round N+1 / stopping]
```

Update `OSS_HARDENING_STATUS.md` with:

- current round
- latest score
- latest verdict
- current loop status

Increment round counter -> back to Phase A.

### Termination

When the loop ends:

1. Write a final summary to `OSS_REVIEW_LOOP.md`
2. Update `OSS_HARDENING_STATUS.md`
3. If stopped at max rounds without a positive assessment:
   - list the remaining blockers
   - estimate which stage should be revisited next
   - say whether the repo is close to release or still materially blocked

## Key Rules

- ALWAYS use `config: {"model_reasoning_effort": "xhigh"}`
- Save `threadId` from the first call and use `mcp__codex__codex-reply` for subsequent rounds
- Preserve the full raw reviewer response
- Ask for minimum fixes, not an aspirational rewrite
- Fix issues before re-reviewing; do not just promise changes
- Treat broken setup, missing tests, missing CI, weak docs, and unsafe release posture as higher severity than polish
- Keep the log self-contained

## Prompt Template for Round 2+

```text
mcp__codex__codex-reply:
  threadId: [saved from round 1]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N update]

    Since your last review, we have:
    1. [Action 1]: [result]
    2. [Action 2]: [result]
    3. [Action 3]: [result]

    Updated verification status:
    [commands and outcomes]

    Please re-score and re-assess.
    Same format: Score, Verdict, Remaining Weaknesses, Minimum Fixes, Return Stage for each fix.
```

## Done Criteria

- `OSS_REVIEW_LOOP.md` documents up to four rounds of review, fixes, and re-review
- `OSS_HARDENING_STATUS.md` reflects the latest loop state
- The repository either reaches a positive readiness assessment or ends with a clear, ranked blocker list
