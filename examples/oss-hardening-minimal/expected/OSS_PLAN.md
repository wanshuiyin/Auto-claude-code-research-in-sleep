# OSS Plan

## Scope

This pass hardens the example repo enough to be safely shared and reviewed. It focuses on correctness, tests, CI, and minimum docs.

## Minimum Shippable Subset

- [ ] Add safe CLI argument handling
  Purpose: prevent immediate crashes on missing user input.
  Change points: `repo/app.py`.
  Acceptance criteria: running `python app.py` exits non-zero with a clear usage message.
  Suggested commands: `python app.py`, `python app.py names.txt`.
  Estimated impact radius: low; one script, user-visible behavior only on invalid input.

- [ ] Add minimal automated tests
  Purpose: protect the only user path before any further cleanup.
  Change points: `repo/tests/test_app.py`, `repo/app.py`.
  Acceptance criteria: happy path, missing argument, and missing file cases are covered by one repeatable test command.
  Suggested commands: `python -m unittest`.
  Estimated impact radius: low; tests plus small error-handling changes.

## Full Checklist

- [ ] Add safe CLI argument handling
  Purpose: prevent `IndexError` and replace stack traces with a helpful user message.
  Change points: `repo/app.py`.
  Acceptance criteria: the script exits with a clear message when no file path is provided.
  Suggested commands: `python app.py`, `python app.py names.txt`.
  Estimated impact radius: low.

- [ ] Add clear file-read failure handling
  Purpose: distinguish bad input from programmer bugs.
  Change points: `repo/app.py`.
  Acceptance criteria: a missing input file returns a non-zero exit code and a human-readable error.
  Suggested commands: `python app.py missing.txt`.
  Estimated impact radius: low.

- [ ] Add three CI-safe tests
  Purpose: lock in the main flow and the two most important failures.
  Change points: `repo/tests/test_app.py`, `repo/app.py`.
  Acceptance criteria: tests cover success, failure branch, and input validation without network access.
  Suggested commands: `python -m unittest`.
  Estimated impact radius: low.

- [ ] Add minimal GitHub Actions CI
  Purpose: block regressions on `push` and `pull_request`.
  Change points: `repo/.github/workflows/ci.yml`.
  Acceptance criteria: the workflow runs the chosen test command and fails on errors.
  Suggested commands: `python -m unittest`.
  Estimated impact radius: medium; affects contributor workflow.

- [ ] Tighten onboarding docs
  Purpose: make the repo runnable and reviewable by someone new.
  Change points: `repo/README.md`.
  Acceptance criteria: README includes run and verify commands plus a pointer to CI.
  Suggested commands: `python app.py names.txt`, `python -m unittest`.
  Estimated impact radius: low.

- [ ] Add maintenance metadata
  Purpose: give contributors a security reporting path and a release-change trail.
  Change points: `repo/SECURITY.md`, `repo/CHANGELOG.md`.
  Acceptance criteria: both files exist with lightweight starter content.
  Suggested commands: none.
  Estimated impact radius: low.

## Stop Points

- Stop after CLI fixes if the script behavior changes beyond error handling.
- Stop after tests if they require more refactoring than planned.
- Stop before CI if the local test command is still unstable.
