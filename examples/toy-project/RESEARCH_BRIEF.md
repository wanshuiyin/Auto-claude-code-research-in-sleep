# Research Brief

## Problem Statement

Many sequence models are evaluated on tasks where order matters, but toy baselines often collapse the input into simple counts or pooled summaries. That can hide a basic failure mode: some tasks are impossible to solve once boundary or transition information is discarded. We want a tiny experiment that makes this failure mode explicit.

This toy project studies a binary sequence classification task where the label is `1` when the first and last bit match and `0` otherwise. The task is intentionally small enough to analyze exactly rather than through expensive training. The goal is not novelty; the goal is to provide a compact, reproducible example of the ARIS workflow.

## Background

- **Field**: toy sequence modeling
- **Sub-area**: information loss under summary features
- **Key papers I've read**: none required for the toy version
- **What I already tried**: intuitive reasoning that count-only features should be insufficient
- **What didn't work**: n/a

## Constraints

- **Compute**: local CPU only
- **Timeline**: single session
- **Target venue**: none; internal demo

## What I'm Looking For

- [x] Diagnostic study / analysis paper
- [ ] New research direction from scratch
- [ ] Improvement on existing method
- [ ] Other

## Domain Knowledge

The label depends on sequence boundaries, not just the multiset of tokens. Any summary that only preserves the number of ones should lose decisive information. A structure-aware summary that keeps the endpoints, or equivalently transition parity, should solve the task exactly.

## Non-Goals

- Large-scale training
- Deep learning frameworks
- Claims about real benchmark performance

## Existing Results (if any)

Expected result: the optimal count-only classifier should perform above chance on short sequences but degrade toward 50% as the sequence length increases. A boundary-aware classifier should remain perfect.
