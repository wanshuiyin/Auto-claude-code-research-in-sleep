---
name: oss-ci
description: Add or improve a minimal GitHub Actions CI pipeline for linting and tests. Use when the user says "set up CI", "add GitHub Actions", "block bad PRs", or wants a cache-enabled pull-request workflow that runs without secrets.
argument-hint: [repo-path-or-command-set]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit
---

# OSS CI

Create the smallest GitHub Actions workflow that blocks broken pull requests and keeps maintenance friction low.

## Context: $ARGUMENTS

## Input Contract

- Primary input: existing local verification commands from the repository, `OSS_TEST_STRATEGY.md`, and any lint/type-check commands added by `/oss-refactor`.
- Default: if commands are ambiguous, choose the narrowest trustworthy lint + test pair that already works locally.

## Output Contract

Produce:

1. A workflow in `.github/workflows/` (create or update, do not duplicate existing intent).
2. `OSS_CI.md` summarizing:
   - workflow triggers
   - jobs and commands
   - cache strategy
   - failure policy
   - known follow-ups

The workflow must satisfy all of the following:

- Trigger on `push` and `pull_request`
- Run lint plus test
- Use dependency caching when the ecosystem supports it
- Fail the workflow on errors
- Require no secrets or external services

## Non-goals

- Do not add deployment, release, or publish automation in this step.
- Do not build a matrix that the repository cannot maintain.
- Do not call live third-party APIs from CI.

## Workflow Design Rules

- Reuse existing scripts if they already encode the right commands.
- Prefer one job with clear steps over a sprawling workflow.
- Add caching through the setup action when available:
  - Python: `actions/setup-python` with `cache: pip`
  - Node: `actions/setup-node` with package-manager cache
  - Go: `actions/setup-go` cache support
  - Rust: lightweight cargo cache only if already justified
- If the repo has both lint and test but one is flaky, do not hide it. Either stabilize it first or document why the workflow currently omits it.

## Workflow

### Step 1: Confirm local commands

- Run or inspect the exact commands that should execute in CI.
- Prefer commands that contributors can also run locally.

### Step 2: Merge with any existing workflow

- If `.github/workflows/ci.yml` or similar already exists, extend it rather than creating a competing workflow.
- Keep the workflow readable for maintainers.

### Step 3: Enforce CI-safe execution

- Mock or bypass external services.
- Use fixture files instead of network fetches.
- Keep runtime short enough for pull requests.

### Step 4: Document the workflow

Record in `OSS_CI.md`:

- what blocks merges now
- what remains intentionally out of scope
- how to reproduce the workflow locally

## Failure Handling

- If no reliable test command exists yet, stop and hand back to `/oss-tests`.
- If the only available lint tool requires a heavy new dependency, document the recommendation and keep the workflow focused on what already works.
- If an existing workflow overlaps, consolidate instead of duplicating.

## Done Criteria

- `.github/workflows/` contains one clear minimal CI workflow for lint + test.
- The workflow triggers on push and pull requests, uses caching where appropriate, and fails on errors.
- `OSS_CI.md` explains the resulting CI design and remaining gaps.
