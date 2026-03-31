# Research Contract: Boundary-Aware Sequence Summaries

## Selected Idea

- **Description**: Compare an optimal classifier that only sees the count of ones against a structure-aware classifier that sees the sequence boundaries on a synthetic binary task.
- **Source**: IDEA_CANDIDATES.md, Candidate 1
- **Selection rationale**: It is the smallest project that still demonstrates a real workflow: hypothesis, exact experiment, findings, and a narrative report.

## Core Claims

1. Count-only summaries are insufficient for a boundary-dependent binary sequence task.
2. The best possible count-only classifier performs above chance on short sequences but trends toward chance as sequence length grows.
3. A boundary-aware summary solves the task exactly with no learning or external dependencies.

## Method Summary

The task input is a binary sequence of fixed length `n`. The label is `1` if the first and last bit are equal and `0` otherwise. We evaluate all `2^n` sequences exactly for small and medium values of `n`.

The first model family is intentionally weak: it only observes the count of ones in the sequence. For each possible count, we compute the majority label among all sequences with that count. This gives the Bayes-optimal classifier under the information restriction "count only."

The second model family is structure-aware: it uses whether the first and last bit match. That feature is sufficient for the task, so it achieves exact accuracy.

## Experiment Design

- **Datasets**: exhaustive binary sequences of lengths 4, 8, 12, 16
- **Baselines**: optimal count-only classifier
- **Metrics**: exact accuracy
- **Key hyperparameters**: sequence length only
- **Compute budget**: local CPU, under one second

## Baselines

| Method | Dataset | Metric | Score | Source |
|--------|---------|--------|-------|--------|
| Count-only optimum | length 8 | accuracy | 57.03% | exact enumeration |
| Count-only optimum | length 16 | accuracy | 53.05% | exact enumeration |

## Current Results

| Method | Dataset | Metric | Score | Notes |
|--------|---------|--------|-------|-------|
| Count-only optimum | length 4 | accuracy | 62.50% | exact enumeration |
| Count-only optimum | length 8 | accuracy | 57.03% | exact enumeration |
| Count-only optimum | length 12 | accuracy | 54.39% | exact enumeration |
| Count-only optimum | length 16 | accuracy | 53.05% | exact enumeration |
| Boundary-aware | length 4 | accuracy | 100.00% | exact |
| Boundary-aware | length 8 | accuracy | 100.00% | exact |
| Boundary-aware | length 12 | accuracy | 100.00% | exact |
| Boundary-aware | length 16 | accuracy | 100.00% | exact |

## Key Decisions

- Use exhaustive enumeration instead of sampled train/test splits so the demo stays exact and deterministic.
- Keep the baseline intentionally restricted to a count-only view because that is the information-loss question we want to surface.
- Stop at four sequence lengths; that is enough to show the trend without making the example noisy.

## Status

- [x] Idea selected
- [x] Baseline reproduced
- [x] Main method implemented
- [x] Representative dataset results
- [x] Full dataset results
- [ ] Ablation studies
- [ ] Paper draft
