# Adversarial Proof Audit Rubric

Use this rubric only after locating the exact proof and its dependencies.

## Issue Taxonomy

- `UNJUSTIFIED_ASSERTION`: a step lacks proof or a cited result.
- `UNPROVEN_SUBCLAIM`: a "clear" or "standard" step hides a nontrivial lemma.
- `QUANTIFIER_ERROR`: wrong order of forall/exists, missing sufficiently-small parameter scope, or hidden dependence.
- `IMPLICATION_REVERSAL`: uses one direction as an equivalence.
- `CASE_INCOMPLETE`: omits boundary, degenerate, zero, singular, or non-unique cases.
- `CIRCULAR_DEPENDENCY`: proof uses the target theorem or a downstream consequence.
- `ILLEGAL_INTERCHANGE`: swaps limit, expectation, derivative, integral, supremum, or infimum without conditions.
- `MISSING_DOMINATION`: invokes DCT, Leibniz, or differentiation under the integral without a dominating function.
- `INTEGRABILITY_GAP`: uses a moment, norm, or expectation not assumed or proved finite.
- `REGULARITY_GAP`: uses continuity, differentiability, convexity, compactness, measurability, or Lipschitzness without support.
- `STOCHASTIC_MODE_CONFUSION`: changes among almost surely, in probability, in expectation, high probability, or Lp without proof.
- `HIDDEN_ASSUMPTION`: relies on conditions not in the statement.
- `INSUFFICIENT_ASSUMPTION`: stated hypotheses are too weak for the claimed result.
- `DIMENSION_TRACKING`: constants or rates hide dependence on dimension, horizon, sample size, components, or other parameters.
- `NORMALIZATION_MISMATCH`: inconsistent scaling, coordinate convention, or notation.
- `SCOPE_OVERCLAIM`: conclusion is broader than the proof supports.
- `REFERENCE_MISMATCH`: cited result's hypotheses are not verified.

## Severity

- `FATAL`: statement is false or contradicted, and the main theorem or core dependency breaks.
- `CRITICAL`: a global proof obligation is unjustified, or a local statement is invalid.
- `MAJOR`: a local proof obligation is unjustified, or a global claim needs weakened conclusion or stronger assumptions.
- `MINOR`: notation, exposition, or bookkeeping issue that does not change the mathematics.

## Mandatory Checks

For every theorem, lemma, proposition, and proof:

1. Definitions: list symbols whose meaning, type, or domain changes.
2. Hypothesis discharge: at each application of a lemma or theorem, verify every hypothesis at that point.
3. Inequalities: check direction, absolute values, PSD or convexity assumptions, norm compatibility, and equality cases.
4. Interchanges: verify conditions for DCT, MCT, Fubini/Tonelli, Leibniz, Taylor remainder, implicit function theorem, envelope theorem, or minimax exchange.
5. Probability mode: track whether each convergence or bound is almost sure, in probability, in expectation, high probability, or Lp.
6. Uniformity and constants: make every O/o/Theta and hidden constant declare its parameter dependence and uniformity scope.
7. Edge cases: test zero weights, singular matrices, non-unique optima, boundary parameters, d=1, K=1 or K=2, small n, and extreme scaling.
8. Dependency consistency: detect circularity, forward references, and unproved prerequisites.
9. Conclusion match: confirm the last line proves exactly the stated conclusion, with the same quantifiers and constants.

## Common Side Conditions

- DCT: pointwise a.e. convergence and an integrable dominating function.
- MCT: monotone nonnegative sequence or functions.
- Fubini: product measurability and absolute integrability.
- Tonelli: product measurability and nonnegativity.
- Leibniz rule: differentiability plus domination of derivative or a suitable theorem-specific condition.
- Jensen: convexity or concavity in the correct direction and integrability.
- Cauchy-Schwarz: valid inner product or norm space and finite second moments.
- Taylor expansion: stated differentiability order and explicit remainder control.
- WLOG: reversible transformation or invariant problem class.

## Counterexample Discipline

Mark `counterexample found` only after algebraic verification. Otherwise use
`counterexample candidate` and explain what remains to check.

Useful attempts:

- collapse to one dimension;
- set matrices singular, diagonal, rank one, or identity;
- make weights zero, nearly zero, or equal;
- force overlapping parameters or non-identifiability;
- choose two-point, heavy-tailed, or boundary distributions;
- let hidden constants grow with the supposedly uniform parameter.
