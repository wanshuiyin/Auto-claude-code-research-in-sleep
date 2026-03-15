# OSS Audit

## Repository Summary

- Stack: Python script repo with one entry point (`app.py`)
- Current run command: `python app.py names.txt`
- Current automation: none
- Main risk: the only user flow has no guardrails, no tests, and no CI

## Findings

### Correctness

- `P0` Missing CLI argument validation in `app.py`
  - Evidence: `sys.argv[1]` is accessed directly
  - Why it matters: running without an argument raises `IndexError`
  - Smallest fix: add argument count validation and a clear exit message

### Maintainability

- `P1` The CLI and file-loading behavior live in one script with no tests
  - Evidence: `main()` handles argument parsing, file I/O, and output in one place
  - Why it matters: even small changes require manual retesting
  - Smallest fix: keep `greet()` and `load_names()` reusable, make `main()` a thin CLI wrapper

### Testability

- `P0` No automated tests for the main path or failure cases
  - Evidence: repository has no `tests/` directory or test command
  - Why it matters: safe refactoring is blocked
  - Smallest fix: add tests for happy path, missing file, and missing argument handling

### Security

- `P2` No security policy or disclosure path
  - Evidence: `SECURITY.md` is missing
  - Why it matters: maintainers have no documented path for vulnerability reports
  - Smallest fix: add a lightweight `SECURITY.md`

### Performance

- `P2` Full file reads are acceptable for the current size but undocumented
  - Evidence: `Path(path).read_text(...)` reads the whole file at once
  - Why it matters: future growth may turn the script into a silent memory sink
  - Smallest fix: document current assumptions; stream lines if input size grows

### Observability

- `P1` Failures do not produce friendly diagnostics
  - Evidence: Python exceptions are exposed directly to the user
  - Why it matters: users cannot easily tell whether the problem is bad input or a missing file
  - Smallest fix: catch expected user errors and return clear stderr messages plus non-zero exit codes

### Documentation

- `P1` Missing contributor and maintenance metadata
  - Evidence: no `CONTRIBUTING.md`, `CHANGELOG.md`, or setup verification docs in the example repo
  - Why it matters: contributors do not know how to validate changes
  - Smallest fix: add quick verification steps and lightweight maintenance files

## Required File-Level Changes

| Priority | Path | Action | Reason |
|----------|------|--------|--------|
| P0 | repo/app.py | modify | add CLI validation and clearer failure behavior |
| P0 | repo/tests/test_app.py | add | protect happy path, failure branch, and input validation |
| P1 | repo/.github/workflows/ci.yml | add | block regressions on pull requests |
| P1 | repo/README.md | modify | document run and verify commands |
| P2 | repo/SECURITY.md | add | document vulnerability reporting path |
| P2 | repo/CHANGELOG.md | add | create a maintenance trail |

## Do First

1. Add safe CLI handling in `app.py`
2. Add three CI-safe tests
3. Add one minimal CI workflow that runs the tests

## Do Later

1. Add maintenance metadata (`SECURITY.md`, `CHANGELOG.md`)
2. Revisit streaming input if the script grows beyond small text files
