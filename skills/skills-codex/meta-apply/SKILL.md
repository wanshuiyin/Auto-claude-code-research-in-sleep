---
name: meta-apply
description: "Privileged applier that LANDS meta-optimize / corpus-audit patches the user approved, with a fresh landing review and human approval. Base Codex review is same-family provisional. Use when the user says \"meta apply\", \"/meta-apply\", \"land the staged patches\", \"应用优化\", after a /meta-optimize run."
argument-hint: "[patch-number-or-all]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob
---

# Meta-Apply: the privileged landing gate for self-modification patches

> **Codex assurance:** a base landing review records
> `review_independence: same-family` and `acceptance_status: provisional` via
> `stamp-provisional`; the artifact is not auto-curatable. Only an overlay or
> deterministic verifier may produce accepted authorization.

This skill exists to enforce a **privilege boundary**. Producers like
[`/meta-optimize`](../meta-optimize/SKILL.md) (and, later, `corpus-audit`) are
**read-only** — no `Write`/`Edit`, no apply step; they can only *stage* candidate patches
under `.aris/meta/pending/`. **This skill is the only place a staged patch becomes a real
change to the corpus.** Splitting "propose" from "land" across two skills with different
tool grants is what makes "a loop cannot apply its own patch" structural rather than a
sentence the producer is asked to obey.

It is **human-invoked only.** It runs when the user explicitly types `/meta-apply` after
reading the producer's REPORT. That invocation IS the landing authorization (the locked
2026-05-30 decision: the human stays at the landing gate).

## The acquittal is generated HERE, not relayed

The earlier design trusted a `jury_verdict: pass` field in the producer's manifest. That
is **forgeable** — the producer writes that field, so a buggy/misaligned producer could
stage a killed patch labelled "pass." **So this skill does not trust any producer-written
verdict.** It runs the fresh landing reviewer **itself, at landing time, on the actual staged
diff** (fresh reviewer, paths-only). The verdict is produced where it is consumed, by the
privileged human-invoked skill — nothing to forge.

## The non-negotiable rules (jury-at-landing, reject-default)

For each staged patch the user asks to land, in order — any failure ⇒ skip & report,
never silently apply:

1. **The human named THIS patch.** Apply only patches the user listed (`/meta-apply 1,3`
   or `all`); default to applying nothing.
2. **Fresh landing review PASS, obtained now.** Spawn a fresh `gpt-5.6-sol`
   reviewer via `spawn_agent` (`reasoning_effort: ultra`, read-only, paths-only per
   [`reviewer-independence.md`](../shared-references/reviewer-independence.md)) on the
   staged `.diff` + its target. Ask: *does this change improve the harness without
   regressions; PASS or KILL + one-line reason.* **KILL ⇒ refuse.** The human cannot
   override a KILL — they may only pick among reviewer-PASSED survivors.
3. **Record the review class honestly.** Base Codex review is same-family and
   lands only with `stamp-provisional`; it can complete this explicit
   human-invoked operation but does not authorize future auto-curation. A
   Claude/Gemini overlay or deterministic verifier uses strict `stamp` and may
   record accepted. See
   [`skill-governance.md`](../shared-references/skill-governance.md).

## Workflow

### Step 0: Load staging + resolve the helper

```bash
PENDING=".aris/meta/pending"
[ -d "$PENDING" ] || { echo "Nothing staged. Run /meta-optimize first."; exit 0; }
echo "Staged:"; cat "$PENDING/manifest.jsonl"
```

Resolve `provenance.py` through the Codex manifest:

```bash
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
  ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
PROVENANCE=""
[ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/tools/provenance.py" ] && PROVENANCE="$ARIS_REPO/tools/provenance.py"
[ -z "$PROVENANCE" ] && [ -f tools/provenance.py ] && PROVENANCE="tools/provenance.py"
[ -n "$PROVENANCE" ] || { echo "ERROR: provenance.py unresolved" >&2; exit 1; }
```

### Step 1: Jury-at-landing for each requested patch

For every patch the user asked to land, read its staged `.diff` and target, then spawn the
fresh reviewer jury (Rule 2) — paths-only, no producer reasoning, no prior-round context.
Record `{patch, jury_verdict, jury_review_id, one_line_reason}`. Print a one-line result
per patch (`PASS → eligible` / `KILL → refused: <reason>`).

> The producer may have written an *advisory* pre-screen into the manifest to help the
> human read the REPORT — **ignore it for the landing decision.** Only this fresh verdict
> counts.

### Step 2: Land the survivors (Write/Edit only — never Bash)

For each patch that PASSED Step 1 **and** was named by the user:

1. **Back up** the target to `.aris/meta/backups/<date>/<target>` (use the **Write** tool
   to copy contents; corpus paths are not Bash-writable when `corpus_write_guard` is
   active — and the applier should use Write/Edit for corpus mutation anyway).
2. **Apply** the diff by **Edit/Write** on the target corpus file.
3. **Stamp provenance** on the changed file. Base Codex uses:
   ```bash
   python3 "$PROVENANCE" stamp-provisional "$TARGET" --author "$AUTHOR" \
     --reviewer "$JURY_MODEL" --verdict-id "$JURY_REVIEW_ID"
   ```
   This records `review_independence: same-family` and
   `acceptance_status: provisional`; `is_auto_curatable` remains false. If the
   active overlay produced a cross-family result, use strict `stamp` instead.
4. **Log** to `.aris/meta/optimizations.jsonl`:
   `{ts, patch, target, author_model, reviewer_model, jury_review_id, applied: true}`.

### Step 3: Report

Per patch: `LANDED <target>` (+ backup path + provenance sidecar) or
`REFUSED <patch>: <reason>`. Remove landed patches from `.aris/meta/pending/`. Remind the
user a landed patch is revertable from its backup, and to test the changed skill next run.

## Provenance is a receipt, not an acquittal of correctness

A stamp records that a change passed *a process* (fresh landing review + human
landing), not that it is *correct*. To prevent "approved-but-wrong with a stamp that
vouches for it" (false-authority laundering — worse than no stamp, because a later
auto-curator reads it as evidence):

- The stamp carries `verdict_id` (auditable review) + `content_hash` (a later hand-edit
  invalidates it).
- **Recommended (not yet built):** a TTL forcing re-review of long-lived auto-authored
  artifacts, and a behavioral auditor that REVOKES a stamp when a landed skill misbehaves.
  Track as follow-up; never treat a stamp as permanent truth.

## Key Rules

- **Human-invoked only.** Never run as a side-effect of another skill or a hook.
- **Jury-at-landing, reject-default, no override.** The binding verdict is produced HERE
  on the staged diff; never trust a producer-written verdict; the human picks among
  survivors, never resurrects a KILL.
- **Never promote provisional to accepted.** Base Codex always uses
  `stamp-provisional`; only an overlay or deterministic verifier may use strict
  `stamp`.
- **Corpus mutation goes through Write/Edit** (reviewable, attributable), not Bash. The
  `corpus_write_guard` hook (if installed) additionally denies Bash corpus writes — it
  does NOT gate Write/Edit, so it does not by itself stop this skill from editing the
  corpus; the jury-at-landing + stamp discipline above is what governs Write/Edit
  mutations (that discipline is procedure, not a hook-enforced mechanism).
- **Back up before every mutation.** Reversible by construction.
- **Only land staged patches.** Applies what producers staged in `.aris/meta/pending/`;
  invents nothing of its own.

## Review Tracing

Save each landing-jury reviewer call's trace per
[`review-tracing.md`](../shared-references/review-tracing.md) to
`.aris/traces/meta-apply/<date>_run<NN>/` — the acquittal that landed a corpus change must
be forensically recoverable.
