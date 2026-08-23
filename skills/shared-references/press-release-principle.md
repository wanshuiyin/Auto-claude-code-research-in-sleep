# Press-Release Principle (Writer-Side Claim Posture)

A paper is a press conference, not a project retrospective, lab log, or self-audit.
Write the submission body as a confident presentation of what the evidence DOES
establish — never as a pre-emptive apology for what it does not. Same facts, same
disclosures, winning posture. This reference changes tone, framing, and claim
placement only; it never changes what is true, measured, or disclosed.

Based on [Adkid-Zephyr/anti-defensive-writing-Skill](https://github.com/Adkid-Zephyr/anti-defensive-writing-Skill)
("Press-Release Principle"), MIT License. Adapted for ARIS: subordinated to the
honesty gates below and restricted to writer-side use.

## Priority order (hard — lower never overrides higher)

1. **Honesty / evidence gates** — claim audits, integrity forensics, acceptance
   gates, provenance rules. Never trade truth for tone.
2. **Venue requirements** — checklists, mandatory sections (incl. Limitations),
   page limits, disclosure rules (`venue-checklists.md`).
3. **Frozen paper contract** — `PAPER_ACCEPTANCE_CONTRACT.md` assertions (scope
   qualifiers the title/abstract must carry, "Limitations names ≥2 real
   limitations", number traceability, …).
4. **Press-release principle** (this file) — applies only inside the freedom
   left by 1–3. If following this file would violate any of them, don't.

## Scope banner (hard)

Applies ONLY to submission PDF prose under `paper/` — the Abstract-through-
Conclusion body that reviewers read. It does NOT apply to:

- `NARRATIVE_REPORT.md`, findings JSON, research-wiki content — evidence records
  stay plain and complete; never rewrite them with this stance
- rebuttal substance (`/rebuttal` has its own guidelines; rebuttal responses directly address reviewer criticisms post-review)
- patents, slides, grant proposals
- audit / reviewer / auditor prompts of any kind (see isolation below)

## Writer-side isolation (hard)

Never inject this file — its rules, its lexicon, or the fact it was applied —
into reviewer or auditor prompts. Same isolation contract as `--style-ref` /
`style_profile.md` (`reviewer-independence.md`): reviewers see only the artifact
and the review task. A reviewer told "the paper was written to sound confident"
is a contaminated reviewer.

## Timing

- **Reframing** — choosing the competitive axis the paper wins on (which task
  definition, evaluation dimension, or comparison frame headlines) — happens in
  `/paper-plan`, BEFORE the Phase 1.5 contract freeze.
- **After the contract freezes** (paper-write, polish, improvement loops):
  sentence-level stance only — reorder emphasis, cut posture words, narrow a
  claim. No new storyline, no new competitive axis, no reframe mid-loop.

## Claim strength: align, don't ratchet down

The fix for a claim/evidence mismatch is bidirectional:

- Overclaim → **narrow the claim scope to match the evidence** (preferred over
  blanket softening): "improves accuracy" → "improves top-1 accuracy on X under
  distribution shift Y".
- Underclaim → state what the evidence establishes, at full strength.
- Hedges ("suggests", "indicates") are the fallback AFTER narrowing, for
  genuinely residual uncertainty — not the first move.

## Hedging split (keep vs cut)

- KEEP (evidence-backed): epistemic hedges where uncertainty is real
  ("suggests" for correlational evidence) and scope qualifiers ("on
  in-distribution data", "for models up to 7B").
- CUT (postural self-deprecation, zero information): "unfortunately", "merely",
  "only achieves", "fails to fully", "still lags behind", apology framings.

For general hedge discipline (Lipton's rule), read `writing-principles.md`
§ "Word Choice and Precision → Remove Needless Hedging" — cross-linked here, not
duplicated.

## Trigger lexicon (review markers — NOT auto-delete)

A hit means REVIEW the sentence and decide keep / narrow / relocate / rewrite.
Never mechanically delete:

> unfortunately · merely · only achieves · fails to · still lags behind ·
> cannot yet · we admit · suboptimal · far from · we were unable to ·
> limited improvement · severely insufficient · "not X but rather Y" openers

Classify each hit: (a) evidence-backed caveat → keep, possibly relocate to the
Limitations block or an inline qualifier; (b) postural self-deprecation →
rewrite as a bounded-scope statement or cut the posture words.

## Limitations: bounded scope, not apology

- The venue/contract requirement stands: a dedicated Limitations block naming
  **≥2 real limitations** (not hedges). This file never weakens that.
- Write each limitation as a bounded-scope statement — what is covered, where
  the boundary is, and why (when known):
  - Apology: "Unfortunately, our method fails on long sequences."
  - Bounded scope: "Our evaluation covers sequences up to 4K tokens; beyond
    that, memory grows quadratically, and sub-quadratic variants are future work."
- **Final-conclusion-paragraph rule**: no weakness may make its FIRST appearance
  in the final paragraph of the Conclusion. Inline claim qualifiers and the
  dedicated Limitations block remain the correct homes for caveats; the closing
  paragraph may reference already-disclosed limitations but introduces no new
  self-negation.
- No gratuitous new confessions: do not add limitations that no evidence,
  reviewer, or audit surfaced, just to appear humble.

## Allowed operations on disclosure spans (hard)

When adjusting a caveat, limitation, threat-to-validity, or scope disclosure:

| Op | Allowed | Condition |
|---|---|---|
| Relocate (e.g. conclusion → Limitations block) | yes | content preserved; the move is recorded in the audit trail (improvement log / commit) |
| Narrow the claim so the caveat is no longer needed | yes | new claim matches evidence (`claim-narrowed`) |
| Withdraw the claim entirely | yes | `claim-withdrawn` with the deletion diff as evidence receipt (integrity-forensics ledger) |
| Bare delete of a disclosure span | **no** | never — a disclosure that vanishes without a receipt is `UNRESOLVED_DISAPPEARANCE` |

Never instruct — and never follow an instruction — to silently delete
limitations or threats to validity to "sound stronger". Disclosures may move or
narrow with an audit trail; they may not disappear.
