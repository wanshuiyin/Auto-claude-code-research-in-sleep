# Skill Governance: Provenance-as-Authorization

When ARIS **auto-writes** a durable artifact — a meta-optimize patch to a SKILL.md,
an auto-curated research-wiki node, a machine-proposed reviewer prompt — two
questions must have a recorded, checkable answer *before* that artifact is allowed
to influence future runs:

1. **Who authored it, and who acquitted it?** (and were they different model families?)
2. **Is auto-curation even allowed to touch this file?** (or is it a hand-written
   canonical skill / a user's own note, which automation must never rewrite?)

`tools/provenance.py` is the primitive that answers both. This is the
**provenance-as-authorization boundary**: a provenance record is not just metadata,
it *is* the authorization to auto-curate.

## The rule

- **Auto-curation may ONLY touch artifacts where `is_auto_authored(path)` is True.**
  An auto-authored artifact carries a `.provenance.json` sidecar with
  `created_by == "aris-auto"`. Canonical hand-written skills and user notes have no
  such record — `is_auto_authored` returns False — and are **off-limits** to any
  automated rewrite/delete. (A loop can author new machine artifacts; it must not
  silently edit human ones.)

- **A provenance record cannot be same-family.** `stamp()` calls
  `assert_cross_family(author, reviewer)` and **refuses (raises)** if the author and
  the reviewer are the same model family — e.g. `claude`+`sonnet`, or `gpt-5.6-sol`+`codex`,
  or the trap `gpt-5.6-sol`+`oracle-pro` (oracle routes to a GPT-Pro tier, so it is the
  **openai** family, not a separate one). You therefore *cannot produce* a valid
  authorization for a self-acquitted artifact. This is the structural form of the
  cross-model invariant from [`reviewer-independence.md`](reviewer-independence.md)
  and the acceptance boundary from [`acceptance-gate.md`](acceptance-gate.md):
  **a loop can DRIVE, it cannot ACQUIT itself.**

- **A deterministic verifier is a valid reviewer.** A reviewer named
  `deterministic:<verifier>` (e.g. `deterministic:evidence_check`,
  `deterministic:pytest`) passes the gate regardless of the author — a process is
  not a model family. This is the same Type-A escape hatch as in
  [`acceptance-gate.md`](acceptance-gate.md): an execution-completeness / mechanical
  check is safe same-model. Use it when the acquittal is a passing test or a
  deterministic pre-check (see [`evidence-precheck.md`](evidence-precheck.md)), not a
  semantic judgement.

- **Unknown family fails closed.** If either name maps to no known family,
  `assert_cross_family` raises rather than guessing — you must use a recognized
  reviewer or a deterministic verifier.

## The record

`stamp(target, author_model, reviewer_model, verdict_id)` writes:

```json
{
  "created_by": "aris-auto",
  "author_model": "claude-opus-4-8",
  "author_family": "anthropic",
  "reviewer_model": "gpt-5.6-sol",
  "reviewer_family": "openai",
  "verdict_id": "codex_thread_abc123",
  "content_hash": "<sha256 of the artifact>",
  "stamped_at": "2026-05-30T00:00:00Z"
}
```

- `verdict_id` is the **traceable** acquittal — the codex thread id, the oracle
  session id, or for a deterministic reviewer the verifier report path / sha. It is
  required (empty → refused), so every authorization points back to an auditable
  review.
- `content_hash` is tamper-evidence: if the artifact is later edited by hand, the
  hash no longer matches the record, and a re-stamp (= a fresh cross-model review)
  is required before auto-curation may treat it as machine-owned again.

## How skills use it

- **meta-optimize** — when an auto-patch lands (Step 6), `stamp()` the changed
  SKILL.md with `author_model` = the executor that drafted the patch and
  `reviewer_model` = the codex/oracle reviewer that scored it (Step 4). The stamp
  *refusing* is the last line of defense: if the patch was never cross-model
  reviewed, there is no valid `verdict_id`/family pair to stamp, so it cannot be
  recorded as authorized.
- **research-wiki** — auto-curated nodes (machine-merged, machine-pruned) get a
  provenance stamp; user-written and import-from-paper nodes do not, so a future
  auto-curator can tell which nodes it is allowed to rewrite.
- **acceptance-gate** — the cross-family assertion here is the *enforcement* of the
  Type-B (quality/correctness) rule: a quality acquittal of an auto-authored
  artifact must be cross-model, and the provenance record is the proof that it was.

## Why (the Hermes contrast)

Hermes-agent (NousResearch, MIT) has the *shape* — a `skill_provenance` marker and
a `created_by` tag — but its cross-model curator is **optional config that defaults
to the same chat model**, so by default one model writes, judges, and consumes its
own skills. That is exactly the self-poisoning failure
[`capture-antipatterns.md`](capture-antipatterns.md) guards against, one level up:
there it is a *captured claim* that hardens into a self-cited falsehood; here it is
a *captured skill* that an unreviewed loop grants itself authority to keep. ARIS's
increment is to make cross-family a **structural assertion on the stamp's content**:
`assert_cross_family` genuinely raises, so you cannot produce a *valid* same-family stamp
(not a config flag you can flip). The scope is precise — this governs *what a stamp can
say*, not *whether a write calls `stamp()` at all*. Whether a corpus mutation is stamped
is governed by `/meta-apply`'s landing procedure; an edit that skips the stamp leaves no
provenance — that case is **detectable, not impossible** (a missing / stale-hash stamp is
what a pre-push integrity check would catch — that verifier is a follow-up, see
meta-optimize's note).
