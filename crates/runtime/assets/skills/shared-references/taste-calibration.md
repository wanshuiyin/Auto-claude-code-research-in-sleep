# Taste Calibration Protocol

> Subjective quality is gradable **if you write the taste down and anchor the
> scale**. The model will not invent taste; it will only converge toward the
> taste you described — so the whole game is (1) a weighted rubric worth
> converging to, and (2) reference anchors that pin what "good" and "slop"
> actually look like. (After Karpathy's LOOPS.md VI, "score the subjective".)

Use this protocol whenever a skill grades an artifact on axes that are matters
of judgment — visual design, writing elegance, proposal quality — rather than
machine-checkable facts. It layers ON TOP of any deterministic gates the skill
already has (hard caps, measurement gates); it never replaces them.

## 1. Named axes with explicit numeric weights

Define 2–7 named axes and give each an explicit weight; weights sum to 1.0.
Model the table on `research-refine`'s working precedent (its Phase 2 uses
15/25/25/15/10/5/5% across seven axes):

```markdown
| Axis          | Weight | What it measures                                  |
|---------------|:------:|---------------------------------------------------|
| Design        |  0.35  | hierarchy, spacing, restraint, gestalt            |
| Originality   |  0.15  | distinct voice vs template sameness               |
| Craft         |  0.30  | detail quality: typography, alignment, math, figs |
| Functionality |  0.20  | does it do its job (readable at distance, ...)    |
```

Score each axis 0–1 (or 1–10 rescaled). Composite = Σ weightᵢ · axisᵢ. A single
holistic number without named weighted axes is not this protocol.

## 2. Calibrate on reference anchors BEFORE scoring the target

The grader first scores **3 known-good and 3 known-bad reference exemplars** on
the same axes, so the scale is anchored to concrete artifacts instead of the
grader's free-floating prior.

- References are **pre-existing, human-curated files** — the executor never
  selects, generates, or searches for anchors itself (an executor-picked anchor
  set just smuggles the free-floating prior back in). The invoking skill
  supplies the paths — convention: `<skill-dir>/references/good/` and
  `<skill-dir>/references/bad/` (images, PDFs, or text artifacts of the same
  kind as the target). Project-local references may override the skill-local
  set.
- The grader is TOLD which set is which ("these three are good, these three are
  slop") — calibration is about anchoring the scale, not blind classification.
- Sanity check: if the calibrated scores don't separate the sets (a "bad"
  exemplar scores at or above a "good" one on the composite), the rubric is
  broken — fix the rubric before trusting any target score.

**Graceful degradation:** if no reference sets exist, proceed with the weighted
rubric alone, but the output MUST carry `calibration: none` so a downstream
reader never mistakes an unanchored score for an anchored one. Do not fabricate
or hallucinate reference scores.

## 3. Output contract

```
COMPOSITE: 0.xx            (weighted; also give per-axis scores)
CALIBRATION: anchored | none
GAP: <one mandatory paragraph naming WHICH reference exemplar(s) the target
     falls short of or exceeds, on WHICH axes, and why — "0.71 because the
     figure hierarchy matches good/poster_B but the typography is closer to
     bad/poster_A's crowding" — never just a number>
```

The GAP paragraph is what makes the score actionable: converging toward the
described taste requires knowing where the artifact sits relative to the
anchors, not just its scalar.

## 4. Interaction with existing gates and the jury

- **Deterministic caps stay hard floors.** A calibrated composite never
  overrides a measurement gate or critical cap (e.g. paper-poster-html's
  "< 2 real figures → ≤ 3"). Compute caps first; the composite lives under
  them.
- **Calibration ≠ acquittal.** A taste score produced by the executor's own
  model family may DRIVE the fix loop (rank issues, decide what to patch next)
  but can never acquit: wherever a skill's acceptance requires a cross-model
  verdict, that requirement is unchanged. (Per `acceptance-gate.md`'s taxonomy
  a model-assigned score is a semantic judgment — calibration narrows its
  variance; it does not make it machine-checkable.)
- **Rubric drift is meta-optimize's job.** If users repeatedly override
  calibrated scores, the rubric or the anchors are wrong — that's an event-log
  signal for `/meta-optimize`, not a reason to hand-tweak scores per run.
