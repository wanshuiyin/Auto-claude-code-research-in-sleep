---
name: oss-audit
description: Audit an existing repository for open-source hardening gaps across correctness, maintainability, testability, security, performance, observability, and documentation. Use when the user says "audit this repo", "harden this project", "open source readiness", or wants a prioritized file-level report before changing code.
argument-hint: [repo-path-or-scope]
allowed-tools: Bash(*), Read, Grep, Glob, Write
---

# OSS Audit

Audit the target repository before making broad changes. Prefer evidence over guesses and produce a report that another contributor can act on without re-discovery.

## Context: $ARGUMENTS

## Input Contract

- Input: repository root or subdirectory, plus any user constraints such as "no new deps", "keep Python 3.10", or "CI only".
- Required discovery: languages, package managers, entry points, current verification commands, docs coverage, and operational surface.
- Default: if no path is provided, audit the current working directory.

## Output Contract

Create or update `OSS_AUDIT.md` in the repository root. The report must contain:

1. Repository summary: stack, entry points, package/build system, current automation, and major risks.
2. Findings grouped by:
   - Correctness
   - Maintainability
   - Testability
   - Security
   - Performance
   - Observability
   - Documentation
3. For every finding: priority (`P0`, `P1`, or `P2`), evidence, why it matters, and the smallest credible fix.
4. A required file-level change list with one row per path to add or modify.
5. A short "do first / do later" summary.

The file-level change list is mandatory. Use this shape:

```markdown
| Priority | Path | Action | Reason |
|----------|------|--------|--------|
| P0 | tests/test_cli.py | add | No automated protection for main user flow |
| P1 | .github/workflows/ci.yml | add | No blocking CI on pull requests |
| P2 | SECURITY.md | add | Missing disclosure and support policy |
```

Also return a short chat summary with the highest-priority blockers.

## Non-goals

- Do not perform broad refactors during the audit.
- Do not rewrite README or add tooling configs yet unless the user explicitly asks.
- Do not invent runtime behavior that you cannot verify from code, docs, or commands.

## Workflow

### Step 1: Map the repository

- Identify the main language(s), package manager(s), and executable entry points.
- Find existing automation: tests, linters, type checks, formatters, CI, docs, release files.
- Read the highest-signal files first: `README*`, `CONTRIBUTING.md`, package manifests, lockfiles, `Makefile`, build scripts, and top-level source entry points.

### Step 2: Probe the current verification surface

- Try to locate existing commands for install, run, lint, and test.
- If commands are documented, prefer those exact commands.
- If commands are missing or broken, record that as evidence instead of guessing silently.

### Step 3: Inspect the seven audit categories

For each category, look for concrete repo evidence:

- Correctness: missing validation, crash-prone scripts, hidden assumptions, stateful side effects.
- Maintainability: tangled structure, duplicated logic, missing boundaries, inconsistent naming/config.
- Testability: no test harness, poor seams, reliance on live services, no deterministic fixtures.
- Security: secrets risk, unsafe shelling out, unchecked input, missing dependency/update policy.
- Performance: obviously expensive hot paths, repeated I/O, unbounded loops, wasteful startup work.
- Observability: no logs, no error context, no exit codes, no troubleshooting guidance.
- Documentation: weak setup/run docs, missing contribution expectations, missing support/security info.

### Step 4: Prioritize

Use this rubric:

- `P0`: blocks safe use, safe change, or safe review right now.
- `P1`: materially improves contributor velocity or repo reliability this iteration.
- `P2`: useful hardening work that can wait until the basics are stable.

Prefer changes that improve multiple categories at once.

### Step 5: Write the report

Keep the report executable. Every recommendation should imply a concrete next file or command.

## Failure Handling

- If the repository is too large to audit fully, state the scope you audited and why.
- If a command fails, capture the failing command and observed error in `OSS_AUDIT.md`, then continue with static inspection.
- If the stack is unclear, list the ambiguity under assumptions and avoid speculative recommendations.

## Done Criteria

- `OSS_AUDIT.md` exists and covers all seven categories.
- The file-level change list is present and prioritized.
- The chat summary tells the user what to tackle first without rereading the whole report.
