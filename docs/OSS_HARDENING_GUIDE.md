# OSS Hardening Guide

This repository now includes a staged `oss-hardening` skill suite for turning a loose codebase into a readable, testable, and maintainable open-source project. The default mode is one continuous workflow, not six separate manual runs.

## Repository Conventions

The existing repository conventions were inferred from `skills/**/SKILL.md`, `CONTRIBUTING.md`, and current skill usage:

- One skill lives in one directory: `skills/<skill-name>/SKILL.md`
- The command name maps to the directory name: `/oss-audit` -> `skills/oss-audit/`
- Frontmatter fields used by this repo:
  - Required: `name`, `description`, `allowed-tools`
  - Optional: `argument-hint`
- `description` should explain both what the skill does and when to use it
- `allowed-tools` should stay narrow and explicit enough to review

The validator in `tools/validate_skills.py` enforces those conventions.

## Skill Suite

The hardening pipeline is intentionally split into small stages, but it can run continuously in one invocation:

1. `/oss-audit`
2. `/oss-plan`
3. `/oss-refactor`
4. `/oss-tests`
5. `/oss-ci`
6. `/oss-docs`
7. `/oss-review`
8. `/oss-review-loop`
9. `/oss-hardening` orchestrates the sequence and stage gates

Each stage produces a hand-off artifact so the next stage does not need to rediscover everything. In normal use, `/oss-hardening` should carry those artifacts forward automatically and only pause on blockers.

## Artifacts

These are the default output files expected from the suite:

| Skill | Primary artifact | Purpose |
|-------|------------------|---------|
| `/oss-audit` | `OSS_AUDIT.md` | prioritized hardening report |
| `/oss-plan` | `OSS_PLAN.md` | issue/PR-ready checklist |
| `/oss-refactor` | `OSS_REFACTOR.md` | scope, tooling, touched files, rollback notes |
| `/oss-tests` | `OSS_TEST_STRATEGY.md` | test strategy and CI-safe coverage plan |
| `/oss-ci` | `OSS_CI.md` | CI workflow summary and follow-ups |
| `/oss-docs` | `OSS_DOCS.md` | docs checklist, FAQ, architecture guidance |
| `/oss-review` | `OSS_REVIEW.md` | external Codex maintainer-style readiness review |
| `/oss-review-loop` | `OSS_REVIEW_LOOP.md` | four-round external review -> fix -> re-review loop |
| `/oss-hardening` | `OSS_HARDENING_STATUS.md` | stage-by-stage status and next step |

## Recommended Flow

### Fast path: one command

Run:

```text
/oss-hardening "path/to/repo"
```

Default behavior:

- audit the repository
- turn findings into a plan
- apply only the necessary refactor
- add CI-safe tests
- wire up minimal GitHub Actions CI
- finish with docs and open-source metadata
- end with an external Codex review loop adapted for open-source quality

The workflow should continue automatically unless it hits a blocker, rollback condition, or user-requested stop point.

### Manual path: stage by stage when you want tighter control

### 1. Audit first

Run:

```text
/oss-audit "path/to/repo"
```

Stop here if:

- there is no reproducible local run command
- the repository scope is still unclear
- the audit reveals foundational safety issues that make changes risky

### 2. Turn findings into a plan

Run:

```text
/oss-plan "path/to/repo"
```

Use this stage to split work into reviewable checklist items with acceptance criteria. In the default workflow, this stage should hand off directly into refactor once the plan is actionable.

### 3. Refactor only what is needed

Run:

```text
/oss-refactor "P0 and P1 maintainability items"
```

This stage should unlock tests and CI, not trigger a repo-wide rewrite.

Rollback or pause if:

- behavior changes unexpectedly
- the refactor grows beyond the planned file set
- new tooling adds more maintenance cost than value

### 4. Add the smallest useful test loop

Run:

```text
/oss-tests "main CLI and input validation"
```

Every test added here should be CI-safe: no secrets, no live services, no local-machine assumptions.

### 5. Add CI after local commands are stable

Run:

```text
/oss-ci "use the current lint and test commands"
```

The expected workflow is minimal: `push` + `pull_request`, lint, test, cache dependencies, fail on error.

### 6. Finish with docs and metadata

Run:

```text
/oss-docs "README, FAQ, architecture, SECURITY, CHANGELOG"
```

Keep the README short. Put depth in `docs/`.

### 7. Run an external open-source review

Run:

```text
/oss-review "path/to/repo"
```

This stage uses Codex MCP as an external reviewer. It scores the repository as a maintainer would, then returns the minimum fixes needed before public release.

### 8. Run the autonomous open-source review loop

Run:

```text
/oss-review-loop "path/to/repo"
```

This is the open-source counterpart to the paper review loop. It runs up to four rounds of:

- external Codex review
- minimum hardening fixes
- local verification
- re-review

Use `/oss-hardening` when you want this loop to happen automatically at the end of the pipeline.

## Minimal Example Flow

Use the sample repo in [`examples/oss-hardening-minimal/`](../examples/oss-hardening-minimal/):

```text
/oss-hardening "examples/oss-hardening-minimal/repo"
```

Compare the outputs with:

- [`examples/oss-hardening-minimal/expected/OSS_AUDIT.md`](../examples/oss-hardening-minimal/expected/OSS_AUDIT.md)
- [`examples/oss-hardening-minimal/expected/OSS_PLAN.md`](../examples/oss-hardening-minimal/expected/OSS_PLAN.md)

## Local Validation

Validate the repo's skill metadata:

```bash
python tools/validate_skills.py
```

Run validator tests:

```bash
python -m unittest discover -s tests
```

## Notes for Contributors

- Keep new skills independent and copy-paste friendly.
- Prefer standard library implementations for maintenance helpers.
- If a new skill needs wider permissions, justify them in the skill body and keep the `allowed-tools` entry specific.
- If a stage discovers new foundational problems, move back to `/oss-audit` or `/oss-plan` instead of pushing forward blindly.
