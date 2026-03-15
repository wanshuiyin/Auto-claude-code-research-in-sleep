---
name: oss-docs
description: Improve the repository's open-source documentation and metadata. Use when the user says "improve docs", "make this repo easier to adopt", "fix the README", or wants README polish plus SECURITY.md, CHANGELOG.md, FAQ, and architecture notes.
argument-hint: [repo-path-or-doc-scope]
allowed-tools: Read, Grep, Glob, Write, Edit
---

# OSS Docs

Make the repository easier to discover, adopt, and maintain without turning the README into a wall of text.

## Context: $ARGUMENTS

## Input Contract

- Primary input: current `README*`, docs folder, contribution guidance, and the final code/test/CI state.
- Optional input: target audience, supported platforms, support window, and release process.
- Default: if no doc scope is given, cover onboarding plus maintenance metadata.

## Output Contract

Produce:

1. `OSS_DOCS.md` with:
   - README improvement checklist
   - FAQ draft
   - architecture explanation recommendations
   - docs still intentionally deferred
2. Requested document changes in-place.
3. Add `SECURITY.md` if missing.
4. Add `CHANGELOG.md` if missing.

If the repository already has `SECURITY.md` or `CHANGELOG.md`, improve the existing file instead of creating duplicates.

The README checklist must cover at least:

- what the project does
- quick start
- how to verify locally
- contribution entry point
- where deeper docs live

## Non-goals

- Do not duplicate detailed docs inside the README.
- Do not invent guarantees, support policies, or architecture details that the code cannot support.
- Do not create a long doc set that the repository will not maintain.

## Workflow

### Step 1: Keep the README short and useful

- Ensure the README answers: what is this, why does it exist, how do I run it, how do I verify it, where do I learn more.
- Move depth into `docs/` instead of expanding the README endlessly.

### Step 2: Fill open-source metadata gaps

- `SECURITY.md`: reporting channel, supported versions if known, what to include in a report.
- `CHANGELOG.md`: lightweight "Keep a Changelog" style skeleton is enough if no release history exists yet.
- FAQ: installation pitfalls, common failure modes, and contributor questions.
- Architecture note: short overview of major modules and data/control flow.

### Step 3: Align docs with reality

- Verify commands against the current repo state.
- Link to real files and workflows that exist now.
- Remove stale instructions rather than preserving them for nostalgia.

## Failure Handling

- If behavior is uncertain, write an open question instead of making up documentation.
- If the repo is too early for a full architecture document, add a lightweight module map and defer the rest.
- If support or security policy is unknown, provide a maintainer-editable template and call out the placeholders.

## Done Criteria

- The README has a clean entry point and links to deeper docs.
- `SECURITY.md` and `CHANGELOG.md` exist or were improved in place.
- `OSS_DOCS.md` captures the doc plan, FAQ, and architecture recommendations.
