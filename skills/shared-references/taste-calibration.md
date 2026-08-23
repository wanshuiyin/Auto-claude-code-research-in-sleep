# Taste Calibration Protocol

Subjective quality can be evaluated consistently when evaluation criteria are explicitly documented with anchored scales. Models converge toward specified criteria when provided with:
1. A weighted rubric with explicit evaluation axes.
2. Reference anchor examples illustrating high-quality vs. low-quality implementations.

Use this protocol when evaluating artifacts on subjective axes — such as visual design, writing style, or proposal structure — rather than deterministic rules. This protocol complements deterministic checks (e.g., hard layout constraints, size caps) without replacing them.

## 1. Named Axes with Explicit Numeric Weights

Define 2–7 named axes with assigned weights summing to 1.0. For example:

```markdown
| Axis          | Weight | Description                                       |
|---------------|:------:|---------------------------------------------------|
| Design        |  0.35  | Visual hierarchy, whitespace, balance, structure  |
| Originality   |  0.15  | Distinctive framing vs. generic boilerplate       |
| Craft         |  0.30  | Detail execution: typography, math, figure layout |
| Functionality |  0.20  | Core effectiveness (readability, clarity)         |
```

Score each axis from 0.0 to 1.0 (or 1 to 10 rescaled).
Composite Score = $\sum (\text{weight}_i \times \text{axis}_i)$.

## 2. Calibrate on Reference Anchors Before Scoring

The evaluator first scores curated reference examples (e.g., 3 high-quality and 3 low-quality exemplars) on the same axes to anchor the scoring scale:

- **Curated Reference Files:** Anchors are pre-existing, human-curated files provided at `<skill-dir>/references/good/` and `<skill-dir>/references/bad/`. Evaluators do not generate or select their own anchors.
- **Labeled Sets:** The evaluator is informed of exemplar classifications to establish baseline reference points across the rubric.
- **Validation Check:** If calibrated scores fail to separate known good from known poor exemplars (e.g., a poor exemplar scores equal to or higher than a good exemplar on the composite score), the rubric requires adjustment before evaluating target artifacts.

**Fallback:** If no curated reference files exist, proceed with the weighted rubric directly and set `CALIBRATION: none` in the output. Do not fabricate anchor scores.

## 3. Output Contract

```markdown
COMPOSITE: 0.xx            (Weighted score; include individual axis breakdown)
CALIBRATION: anchored | none
GAP: <A concrete paragraph identifying specific axes where the target deviates from reference anchors, citing concrete examples: e.g., "The section structure matches the clarity of good/paper_A, but paragraph transitions in Section 3 are verbose and resemble bad/paper_B's repetitive phrasing. Action: tighten topic sentences in Section 3.2.">
```

The `GAP` paragraph must provide concrete, actionable critique referencing specific weaknesses and corresponding anchor comparisons rather than generic ratings.

## 4. Interaction with Deterministic Gates and Independent Review

- **Deterministic Hard Caps Apply First:** Subjective composite scores never override hard constraints or measurement failures (e.g., missing required figures, font size violations). Hard caps are evaluated first.
- **Calibration Does Not Replace Cross-Model Review:** Calibrated scores generated during drafting help prioritize revisions, but they do not replace required independent cross-model reviews (`acceptance-gate.md`).
- **Rubric Maintenance:** If evaluation scores consistently diverge from expert human judgment, the rubric definitions or anchor exemplars should be updated via `/meta-optimize`.
