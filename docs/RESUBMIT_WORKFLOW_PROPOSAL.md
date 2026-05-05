# Resubmit Workflow Proposal — Theory Paper, Text-Only Microedit Mode

**Status**: draft, awaiting ARIS reviewer-agent feedback
**Drafted by**: a Claude session (Opus 4.7) working on a real resubmit task; Codex GPT-5.5 xhigh has already done one critique pass on this draft and the changes are folded in
**Purpose**: ask whether ARIS already has a canonical resubmit-orchestration recipe; if not, decide whether this composition deserves to become a skill (`/resubmit-pipeline` or similar) or stays as a one-off composition
**Not in scope**: any actual ARIS skill / SKILL.md / shared-references edit. This file is a discussion artifact in `docs/`.

---

## Concrete situation behind this proposal

A theory paper was rejected at one top venue (three reviews available, decision = reject) and the user wants to resubmit to a different top venue with the following hard constraints:

- **No new experiments** (compute / time budget closed)
- **No bibliography edits** (LLM hallucination paranoia — adding/removing/retitling citations is forbidden)
- **No framework changes** unless the user explicitly approves a specific change
- **Never overwrite any prior submission directory** — must compose into a new sibling directory
- **Reviewer for everything = Codex GPT-5.5 xhigh, multi-round**
- Page-limit shrink between source venue and target venue (workshop-camera-ready → 9-page main)

This is a scope where most of the existing W3 (paper-writing) pipeline is **inappropriate** because the input is not a narrative report — it is an already-written, polished paper that must only be *micro-edited* to absorb prior reviewer concerns without re-deriving anything.

---

## Open question to the ARIS reviewer agent

> Does ARIS already have a documented orchestration for "resubmit a polished paper across venues with text-only microedits, gated by prior reviewer feedback"? If yes, point me at it. If no, is the composition below worth promoting into a real skill (`/resubmit-pipeline`), or is it inherently one-off because every resubmit has different constraints?

I did not find an obvious existing skill that exactly matches. `/rebuttal` is the closest neighbor but it is scoped to the rebuttal-response artifact (the OpenReview-style separate document), not in-paper microedits. `/auto-paper-improvement-loop` is the natural per-round engine, but it presupposes someone has already (a) chosen the base manuscript, (b) migrated venue format, (c) set the edit whitelist, (d) queued the reviewer feedback, (e) decided what to NOT change. Those five pre-conditions are exactly the orchestration gap a `/resubmit-pipeline` skill would fill.

---

## Proposed workflow (after Codex critique)

Five phases. Phase numbering is loose; some phases may be re-entered.

### Phase 0 — Physical isolation setup (zero edits to existing files)

Create `<NewVenue>/` as a sibling of every prior submission folder. Inside it:

- New `main.tex` written for the target venue's `.sty`
- **Copy** (not symlink, not `\input{../...}`) the section pool used by the base version into `<NewVenue>/sections/`. Symlinks break Overleaf zip export; cross-directory `\input` would mutate the shared pool and pollute prior submissions.
- Copy `math_commands.tex` from the base venue (the macros existing sections depend on)
- Copy or symlink `Figure/` such that `\includegraphics{Figure/...}` paths inside copied sections still resolve. **Path trap**: if existing sections write `\includegraphics{Figure/foo.pdf}`, then `\graphicspath{{../Figure/}}` from a child directory will resolve `../Figure/Figure/foo.pdf` — wrong. Either copy `Figure/` in or use `\graphicspath{{../}}`.
- Bibliography: `\bibliographystyle{...}` + `\bibliography{../ref}` in the new main; **never** `\input` an existing `ref.tex` that already contains its own `\bibliography{}` command (path resolution will silently break).

Output: `BASELINE.md` recording initial page count + warning list, before any edits.

### Phase 0.5 — Health check (still zero text edits)

- Compile passes
- Page count vs venue limit (**measure first**, do not assume room or assume overflow)
- Anonymity scan if target venue is double-blind (grep author surnames, affiliations, prior funding tags)
- Residual coloring / margin-note scan (`\revise`, `\fix`, `\new`, todonotes leftovers from camera-ready cycles)
- Overfull/underfull box scan, hyperref color sanity, figure-overlap visual review

### Phase 1 — Audit (zero edits)

| Skill | Purpose | Artifact |
|---|---|---|
| `/proof-checker <new>/main.tex --restatement-check` | gap-find on the specific theorems prior reviewers attacked | `PROOF_AUDIT.md` |
| `/paper-claim-audit <new>/` | numerical fidelity (every number in body matches what proofs establish) | `CLAIM_AUDIT.md` |
| `/citation-audit <new>/` (no `--uncited`, detect-only) | wrong-context citations + misattributions; **no removals allowed under user constraint** | `CITATION_AUDIT.md` |

Important nuance for `/citation-audit` under "no bib edits": even if it finds a wrong-context citation, the fix is to **soften the surrounding sentence**, not change the cite. The audit still has value because the prior reviewers may attack overclaiming-by-citation, but the fix vector is text, not bib.

### Phase 2 — Targeted text microedits via Codex multi-round

Inputs into `/auto-paper-improvement-loop`:

1. The Phase 1 audit reports
2. A `KNOWN_WEAKNESSES.md` extracted from prior reviews — atomized concern list with severity, type (assumption / novelty / scope / rigor / experiment-coverage) and addressability (text-fixable / partial / unaddressable)
3. An **edit whitelist** baked into the loop's system instruction. This is the load-bearing guardrail. Forbidden:
   - Touching `.bib` files
   - Touching prior submission directories
   - Touching `.sty` / `.bst`
   - Adding new `\cite{...}` or new `\bibitem`
   - Adding new theorem/lemma/proposition environments
   - Restructuring proof flow (only text-level wording, scope qualification, sentence reordering allowed)
   - Adding numerical claims not already established in proofs
   - Inventing new experiments / numbers
4. Loop config: `effort: max`, `reviewer: codex`, `rounds: 3`. Each round is a fresh-thread Codex review (`REVIEWER_BIAS_GUARD=true`). Each proposed edit must be mapped to a specific reviewer concern OR an audit finding; un-mapped edits get rejected.

Each round ends with `/proof-checker` + `/paper-claim-audit` re-run to catch regressions.

### Phase 3 — Adversarial gate

`/kill-argument <new>/ — difficulty: hard` (deliberately not `nightmare` — see "Risks" section).

Treat the hostile reviewer's 200-word rejection memo as **residual-risk reporting**, not as auto-rewrite directives. Critical: a hard reviewer may demand framework changes the user banned; the adjudication step exists to triage which findings are text-fixable vs which need user escalation.

If text-fixable findings remain: one extra `/auto-paper-improvement-loop` round.
Else: stop and surface to user with a written escalation note ("here is what cannot be fixed under your constraints; please decide").

### Phase 4 — Final compile and integrity gate

- `/paper-compile <new>/main.tex — venue: <target>` (page limit, font, bib resolve, figure overflow)
- Final `/paper-claim-audit` zero-context pass
- `DIFF_REPORT.md`: per-section diff between base venue's body and resubmit body, ready for user to skim before any export
- If user requests Overleaf push: explicit token request, push to a **new** Overleaf project, never overwriting any existing one

---

## Things this composition reveals about gaps in current ARIS

These are honest gaps I noticed while writing this, presented as questions for the reviewer agent:

1. **Edit-whitelist concept**: `/auto-paper-improvement-loop` (as I read its SKILL.md) does not have a first-class "this is forbidden to touch" parameter. Under text-only microedit mode, the whitelist is the most important piece of safety. Should this become an opt-in flag?
2. **`/citation-audit --soft-only` mode**: when bib edits are forbidden, audit findings need to be re-routed to "soften the citing sentence" rather than "change the cite". Currently the skill returns KEEP/FIX/REPLACE/REMOVE verdicts. A `--soft-only` mode that only emits sentence-rewrite suggestions would be useful.
3. **Cross-venue format migration**: there is no canonical helper for "take a paper at venue A's `.sty`, port to venue B's `.sty` without touching content". This feels like a small reusable tool (`tools/venue_migrate.py`?) rather than a full skill — or it could ride along in `/paper-compile`.
4. **`KNOWN_WEAKNESSES.md` format**: should this be a shared-reference schema? `/rebuttal` already builds an `ISSUE_BOARD.md`; the resubmit case wants something similar but scoped to "concerns that survive into the new submission" not "issues to answer in this round's response". A shared schema would let `/rebuttal`-style tooling and `/auto-paper-improvement-loop` consume the same artifact.
5. **`difficulty: hard` vs `nightmare` semantics in `/kill-argument`**: the docstring mentions both as adversarial settings. For resubmit-mode, `nightmare` may demand framework changes and waste a round. Either the skill needs a "constraints-aware" mode that honors a user-supplied "framework is fixed" flag, or callers need to be told that `nightmare` is unsafe under text-only constraints. Either way the SKILL.md should make this explicit.

---

## Top-3 risks the user will hear regardless of skill polish

(These are user-facing realities, not skill issues — listing here so the reviewer agent doesn't try to "solve" them with workflow tweaks.)

1. **Text-only edits cannot fully answer "no large-scale experiments" or "diversity claim needs a metric"**. These objections survive into the next venue. The mitigation is scope-narrowing in the manuscript, not pretending the issue is gone.
2. **Novelty-overclaiming relative to a closely-cited prior work** is the main rejection driver. Must be *narrowed* in writing, not rhetorically inflated. This is the single highest-risk text edit.
3. **Tightening an intuitive argument into "support-preservation" language risks accidentally creating a fake theorem**. The microedit must be explicitly labeled as interpretation/observation unless an existing proof actually establishes it. Reviewer agent should flag any Phase 2 diff that adds a theorem-shaped statement.

---

## What I'd like the reviewer agent to decide

In rough order of importance:

1. Does an existing skill / pipeline already cover this? (If yes, kill this draft.)
2. Are the five gaps in "Things this composition reveals" worth filing as separate skill-modification issues, or would a single new `/resubmit-pipeline` skill subsume them?
3. Is "edit whitelist" worth promoting to a `shared-references/` contract that any text-editing skill can honor, similar to how `reviewer-independence.md` is honored across review skills?
4. Verdict on whether this draft should become a skill, an `AGENT_GUIDE.md` section, or stay as a one-off discussion artifact and get archived.

---

## How to read the cross-model review trail behind this proposal

The Codex GPT-5.5 xhigh review pass already caught:

- Section-pool sharing risk (sections were proposed to be `\input`-ed across directories — would have polluted prior submissions; fixed by physical copy)
- `\graphicspath` doubling bug (described above; fixed)
- `ref.tex` carrying its own bibliography command (would have caused silent path failure; fixed by writing bibliography directly in new main)
- Phase 0.5 being missing (anonymity / residual color / overfull boxes)
- `nightmare` difficulty being inappropriate under text-only constraints (downgraded to `hard`)
- The "diversity rewrite as fake theorem" risk (now item #3 in Top-3 risks)

If the reviewer agent flags more, I'll re-iterate before any execution. Nothing has been executed yet — this is purely a planning artifact.
