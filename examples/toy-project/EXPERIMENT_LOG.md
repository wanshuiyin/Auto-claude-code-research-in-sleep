# Experiment Log

## toy-001 to toy-004

- **Script**: `python3 scripts/run_toy_experiment.py`
- **Environment**: local CPU, Python 3 standard library only
- **Task**: classify binary sequences with label `1` iff the first and last bit match

### Exact Results

| Length | Count-Only Accuracy | Boundary-Aware Accuracy |
|--------|---------------------|-------------------------|
| 4 | 62.50% | 100.00% |
| 8 | 57.03% | 100.00% |
| 12 | 54.39% | 100.00% |
| 16 | 53.05% | 100.00% |

### Notes

- The count-only classifier is Bayes-optimal under the restriction that it only observes the number of ones.
- The boundary-aware classifier is exact because the label definition is itself a boundary predicate.
- The length trend makes the demo more useful than a single fixed-length sanity check.
