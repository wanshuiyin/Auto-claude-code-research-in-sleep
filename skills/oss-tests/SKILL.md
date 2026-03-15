---
name: oss-tests
description: Build the smallest effective automated test loop for a repository. Use when the user says "add tests", "make this CI-safe", "cover the important paths", or wants a minimal but meaningful test strategy with mocks instead of secrets or live services.
argument-hint: [scope-or-critical-path]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit
---

# OSS Tests

Create the minimum automated test loop that materially protects the repository. Bias toward deterministic tests that run in CI without secrets.

## Context: $ARGUMENTS

## Input Contract

- Primary input: current codebase plus `OSS_AUDIT.md` or `OSS_PLAN.md` if available.
- Optional input: critical workflows, known failure modes, or target command such as `python app.py`.
- Default: focus on the main user-facing path and the top audit risks.

## Output Contract

Produce:

1. Actual test files or test scaffolding where feasible.
2. `OSS_TEST_STRATEGY.md` containing:
   - chosen test framework and why
   - test command(s)
   - mock/fake strategy for external dependencies
   - known gaps
3. At least three classes of test coverage:
   - critical path
   - failure branch
   - input validation

The strategy file must include a table like:

```markdown
| Test class | Target | Why it matters | CI notes |
|------------|--------|----------------|----------|
| Critical path | `src/cli.py` happy path | protects the main user workflow | no network, fixture input |
| Failure branch | missing file / bad config | proves clear failure behavior | assert exit code and stderr |
| Input validation | invalid arguments | blocks unsafe or confusing inputs | pure unit test |
```

## Non-goals

- Do not chase high line coverage for its own sake.
- Do not add tests that require secrets, paid APIs, or live infrastructure.
- Do not lock the repo into a heavyweight test stack unless the repo already uses it.

## Strategy Rules

- Prefer built-in or already-present frameworks first.
- Add fixtures, fakes, or dependency injection seams before adding slow integration tests.
- If external services exist, replace them with mocks, temporary files, or recorded responses.
- If the code is too entangled to test directly, do the smallest seam extraction necessary and document it.

## Workflow

### Step 1: Pick the smallest reliable test command

Examples:

- Python: `python -m unittest` or existing `pytest` command
- Node: existing `npm test` or `node --test`
- Go: `go test ./...`
- Rust: `cargo test`

### Step 2: Choose three high-value cases

Start with:

1. Critical path success case
2. Failure branch with a clear user-visible error
3. Input validation or boundary handling

Only add more once those are stable.

### Step 3: Make tests CI-safe

- No network calls
- No secrets
- No reliance on local machine state
- No long-running jobs

### Step 4: Run and record

- Run the chosen test command locally.
- Record the command and outcome in `OSS_TEST_STRATEGY.md`.

## Failure Handling

- If the repo has no testable seam yet, document the blocker and add the smallest seam extraction task.
- If a test is flaky, either stabilize it immediately or leave it out and note the reason.
- If the best available test is only a smoke test, say so explicitly and list the missing deeper tests.

## Done Criteria

- There is a reproducible local test command.
- Three distinct test classes are covered or clearly specified with blockers.
- The resulting tests can run in CI without secrets or live services.
