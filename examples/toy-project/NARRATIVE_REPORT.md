# Narrative Report: Boundary Information Beats Count-Only Summaries on a Toy Sequence Task

## Core Story

We build a tiny synthetic sequence classification problem to demonstrate a simple but important point: once boundary structure is discarded, some tasks become impossible to solve exactly. The input is a binary sequence, and the label is `1` when the first and last bit match. We compare an optimal count-only classifier against a boundary-aware classifier using exhaustive enumeration rather than stochastic training.

Our main result is that the count-only classifier performs above chance on short sequences but degrades toward chance as length increases, reaching 53.05% accuracy at length 16. In contrast, the boundary-aware classifier remains perfect because it preserves the decisive information.

## Claims

1. Count-only summaries are insufficient for a boundary-dependent task.
2. The best count-only classifier trends toward chance as sequence length grows.
3. A tiny structure-aware summary restores exact performance.

## Experiments

### Setup

- **Input space**: all binary sequences of lengths 4, 8, 12, 16
- **Label**: `1` iff first bit equals last bit
- **Baseline**: Bayes-optimal count-only classifier
- **Method**: boundary-aware classifier using endpoint equality
- **Metric**: exact accuracy

### Main Results

| Length | Count-Only | Boundary-Aware |
|--------|------------|----------------|
| 4 | 62.50% | 100.00% |
| 8 | 57.03% | 100.00% |
| 12 | 54.39% | 100.00% |
| 16 | 53.05% | 100.00% |

### Interpretation

The count-only baseline still carries a weak correlation because endpoint equality slightly changes the combinatorics within each count bucket. But that signal fades with length, which is exactly what we expect when the model is forced to compress away the relevant structure.

## Figures

1. Line plot of accuracy vs sequence length for the count-only and boundary-aware methods.
2. Bar chart for the length-16 result highlighting the gap between 53.05% and 100.00%.

## Known Weaknesses

- This is a toy problem, not a benchmark claim.
- The structure-aware method is nearly tautological for this label definition.
- The example is designed for pedagogical clarity rather than methodological novelty.

## Proposed Title

"Boundary Information Matters: An Exact Toy Study of Information Loss in Sequence Summaries"
