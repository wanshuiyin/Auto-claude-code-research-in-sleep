# Output Composition Protocol

When a skill runs **inside an orchestrating pipeline** (e.g. `/idea-discovery`,
`/research-pipeline`, `/grant-proposal`, `/kill-argument`), its intermediate
findings should fold into the pipeline's single canonical deliverable instead of
each sub-skill scattering its own overlapping `.md` files. When the same skill
runs **on its own**, it writes its files exactly as documented — unchanged.

This protocol defines the two states, the explicit signal that switches between
them, and the **enforced default**: with no signal, behave standalone.

> Past idea-discovery runs scattered `LIT_LANDSCAPE.md` + `RESEARCH_REVIEW.md` +
> `MANIFEST.md` + multiple pilot logs whose content was *also* summarized inside
> `IDEA_REPORT.md` — pure duplication. This contract is the fix, lifted out of the
> individual skills so the ~20 skills that compose these don't each carry (and
> drift) their own copy.

## The two states

- **Standalone (DEFAULT).** The skill writes its own output files exactly as its
  SKILL.md documents. This is the behavior whenever no composed-mode signal is
  present — see the fail-safe rule below.
- **Composed.** The skill is running under an orchestrator that owns one canonical
  deliverable. The skill's unique findings are folded into that deliverable (as a
  section, appendix, or linked sub-file the orchestrator manages); the skill does
  **not** emit standalone overlapping files.

## Composed-mode signal (explicit, fail-safe)

A skill is in composed mode **if and only if** an explicit signal is present:

1. **Orchestrator directive (canonical signal).** The invoking skill passed
   `— composed: <canonical-report-path>` in the arguments, e.g.
   `— composed: idea-stage/IDEA_REPORT.md`. The value names the canonical doc to
   fold into (it may not exist yet — the orchestrator creates/owns it). Orchestrators
   MUST pass this directive to every sub-skill they want folded.
2. **Escape hatch.** `— standalone` (or `— composed: false`) forces standalone even
   if an orchestrator would otherwise pass the directive. Standalone always wins a
   conflict.

### Fail-safe rule (the one regression we cannot ship)

**When no `— composed:` directive is present, the skill MUST behave standalone and
write its files as normal.** This is enforced by the contract, not left to per-skill
discretion.

In particular: **the mere existence of a canonical report file (e.g. a leftover
`idea-stage/IDEA_REPORT.md` from a previous run) does NOT trigger composed mode.**
Inferring "composed" from a file on disk would silently swallow a standalone user's
output the moment they happen to have an old report around — exactly the regression
to avoid. Composed mode is a decision the orchestrator makes and signals explicitly;
a sub-skill never guesses it.

## What "fold in" means

When in composed mode, a sub-skill:

1. Returns / hands its unique content to the orchestrator for inlining into the
   canonical deliverable, rather than writing `LIT_LANDSCAPE.md`,
   `RESEARCH_REVIEW.md`, or similar standalone summaries.
2. If it must use a scratch file mid-phase, deletes that scratch once its content is
   inlined and the phase closes.
3. Keeps **audit-trail** outputs where they belong — cross-model review traces always
   go to `.aris/traces/…` per [`review-tracing.md`](review-tracing.md); the canonical
   report cites the trace path instead of carrying a duplicate human-facing copy.
4. Keeps **reusable** artifacts (a pilot script, a small results file) but discards
   disposable scratch (launcher logs, smoke files, redundant `*_summary.json`) once
   the numbers are in the canonical report.

## Orchestrator responsibilities

An orchestrator that wants folding:

1. Owns exactly one canonical deliverable and passes its path via `— composed: <path>`
   to each sub-skill.
2. Inlines each sub-skill's returned findings into the canonical deliverable (or into
   a small set of stage-scoped files it explicitly manages — e.g. `refine-logs/` —
   which the report *links to*, not copies).
3. Does not create a `MANIFEST.md` for a handful of files — see the threshold in
   [`output-manifest.md`](output-manifest.md). A manifest is itself a duplicate index
   that has to be kept in sync.
4. On finish, the deliverable's directory top level should be roughly: the canonical
   report (+ its `.html`), any reusable script + results, and explicitly-managed
   stage sub-dirs. Nothing else unless it carries content not in the report.

## Relationship to the other output protocols

- [`output-versioning.md`](output-versioning.md) — *how* to write a file you do write
  (timestamp + fixed-name copy). Composition decides *whether* a sub-skill writes a
  standalone file at all.
- [`output-manifest.md`](output-manifest.md) — only maintain a manifest above the
  artifact threshold; below it the manifest is itself duplication.
- [`output-language.md`](output-language.md) — orthogonal; applies in both states.
