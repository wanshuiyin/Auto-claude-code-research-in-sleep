---
name: meta-apply
description: "Apply meta-optimize patches that the user has reviewed and approved, with independent cross-model review and human confirmation. Use when the user says \"meta apply\", \"/meta-apply\", \"land the staged patches\", \"应用优化\", after a /meta-optimize run."
argument-hint: "[patch-number-or-all]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Task
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - `/x "args"` = load `skills/x/SKILL.md` from this pack and follow it; `$ARGUMENTS` = the user's instruction text.
> - Cross-model review uses a **Cursor Task subagent** per [reviewer-routing.md](../shared-references/reviewer-routing.md) — cross-family built-in model; `threadId` / resume = the subagent id (`Task(resume: ...)`).
> - `allowed-tools` frontmatter is advisory on Cursor.

# Meta-Apply: Apply Approved Self-Modification Patches

This skill applies optimization patches that were proposed by [`/meta-optimize`](../meta-optimize/SKILL.md) and approved by the user.

## Privilege Boundaries

- **What this skill CAN do**:
  - Read staged patch files from `.aris/meta/pending/`
  - Back up target files to `.aris/meta/backups/`
  - Apply validated patches using Write/Edit tools
  - Record provenance and audit logs

- **What this skill CANNOT do**:
  - Run automatically without explicit user invocation
  - Apply patches that failed the cross-model review check
  - Modify skill files without a valid backup and provenance stamp
  - Rely on producer-generated review verdicts without independent verification

## Independent Review at Landing

This skill independently evaluates staged diffs before applying them. It launches a fresh cross-model reviewer subagent to evaluate the patch directly, rather than trusting unverified claims.

## Core Rules (User Approval & Review Gate)

For each staged patch requested:
1. **User approval required**: Apply only patches explicitly specified by the user (`/meta-apply 1,3` or `all`).
2. **Independent cross-model review PASS**: Run a fresh reviewer subagent on the staged diff. If the reviewer returns KILL (machine token; tell user REJECT/refused), refuse to apply the patch.
3. **Cross-family enforcement**: The author and reviewer must be from different model families (`provenance.py assert_cross_family`).

## Workflow

### Step 0: Load staging + resolve the helper

```bash
PENDING=".aris/meta/pending"
[ -d "$PENDING" ] || { echo "Nothing staged. Run /meta-optimize first."; exit 0; }
echo "Staged:"; cat "$PENDING/manifest.jsonl"
```

Resolve `provenance.py` via the 4-layer chain in
[`integration-contract.md`](../shared-references/integration-contract.md) §2
(`.aris/tools/` → `tools/` → `$ARIS_REPO/tools/` → `$ARIS_REPO/tools/` via
`~/.aris/repo`).

### Step 1: Review at landing for each requested patch

For every patch the user asked to land, read its staged `.diff` and target, then run the
fresh reviewer subagent — paths-only, no producer reasoning, no prior-round context.
Record `{patch, reviewer_verdict, reviewer_thread_id, one_line_reason}`. Print a one-line result
per patch (`PASS → eligible` / `KILL → refused: <reason>`; note: when reporting to the user, present KILL as REJECT/refused).

> The producer may have written an advisory pre-screen into the manifest — only the fresh
> landing review is binding.

### Step 2: Land the survivors (Write/Edit only — never Bash)

For each patch that PASSED Step 1 **and** was named by the user:

1. **Back up** the target to `.aris/meta/backups/<date>/<target>` (use the **Write** tool
   to copy contents).
2. **Apply** the diff by **Edit/Write** on the target corpus file.
3. **Stamp provenance** on the changed file:
   ```bash
   python3 "$PROVENANCE" stamp "$TARGET" --author "$AUTHOR" \
     --reviewer "$JURY_MODEL" --verdict-id "$JURY_THREAD_ID"
   ```
   `stamp()` re-asserts cross-family and refuses on same-family — the structural backstop
   at the moment the authorization record is written. The stamp is a **process receipt**
   (who authored, who verified at landing, content hash).
4. **Log** to `.aris/meta/optimizations.jsonl`:
   `{ts, patch, target, author_model, reviewer_model, reviewer_thread_id, applied: true}`.

### Step 3: Report

Per patch: `LANDED <target>` (+ backup path + provenance sidecar) or
`REFUSED <patch>: <reason>`. Remove landed patches from `.aris/meta/pending/`. Remind the
user a landed patch is revertable from its backup, and to test the changed skill next run.

## Provenance is a process receipt, not an absolute guarantee

A stamp records that a change passed the required process (cross-model review at landing + user
confirmation), not that it is flawless.

- The stamp carries `verdict_id` (auditable review trace) + `content_hash` (invalidated if edited afterwards).
- Track follow-up verification to ensure modified skills behave correctly in production.

## Key Rules

- **Human-invoked only.** Never run as a side-effect of another skill or a hook.
- **Review at landing, reject-default, no override.** The binding verdict is produced HERE
  on the staged diff; never trust a producer-written verdict; the user picks among
  survivors, and cannot override a reviewer rejection.
- **Cross-family or refuse.** `assert_cross_family` must not raise. A
  `deterministic:<verifier>` reviewer is valid per skill-governance.md.
- **Corpus mutation goes through Write/Edit** (reviewable, attributable), not Bash. The
  `corpus_write_guard` hook (if installed) additionally denies Bash corpus writes.
- **Back up before every mutation.** Reversible by construction.
- **Only land staged patches.** Applies what producers staged in `.aris/meta/pending/`;
  invents nothing of its own.

## Review Tracing

Save each landing reviewer call's trace per
[`review-tracing.md`](../shared-references/review-tracing.md) to
`.aris/traces/meta-apply/<date>_run<NN>/` — the review trace that authorized a corpus change must
remain auditable.
