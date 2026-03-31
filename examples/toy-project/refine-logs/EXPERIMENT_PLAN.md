# Experiment Plan

## Objective

Demonstrate, with exact enumeration, that count-only sequence summaries discard boundary information needed for a simple binary classification task.

## Claim Map

### Claim A

Count-only summaries cannot solve the task exactly.

- **Evidence needed**: optimal count-only accuracy below 100% for multiple sequence lengths
- **Experiment**: enumerate all sequences, group by number of ones, assign majority label per group

### Claim B

The count-only classifier degrades toward chance as sequence length grows.

- **Evidence needed**: monotonic decline from short to longer lengths
- **Experiment**: evaluate lengths 4, 8, 12, 16

### Claim C

A boundary-aware summary is sufficient.

- **Evidence needed**: perfect accuracy for all evaluated lengths
- **Experiment**: predict label directly from whether the first and last bit match

## Run Order

1. Sanity check length 4 by exhaustive enumeration.
2. Evaluate lengths 8, 12, and 16.
3. Store exact results in `EXPERIMENT_LOG.md`.
4. Record concise takeaways in `findings.md`.

## Risks

- Risk: the count-only baseline might be closer to chance than expected for all lengths, making the trend less interesting.
- Mitigation: still useful because it cleanly demonstrates information loss.

## Deliverables

- Runnable script in `scripts/run_toy_experiment.py`
- Test coverage in `tests/test_run_toy_experiment.py`
- Updated `EXPERIMENT_LOG.md` and `findings.md`
