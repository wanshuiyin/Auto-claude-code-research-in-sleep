# Research Contract: [Idea Name]

> **A focused working document for the currently selected idea.** Created when an idea is chosen from `IDEA_REPORT.md`, updated throughout implementation and training. This is what the LLM reads on session recovery — not the full IDEA_REPORT with all 8-12 candidates.
>
> **Why this file exists:** After brainstorming, `IDEA_REPORT.md` contains many candidate ideas. Keeping all of them in context pollutes the LLM's working memory and degrades output quality. This contract extracts *only the active idea* into a standalone document, so new sessions and post-compaction recovery load focused context instead of the entire idea pool.

## Selected Idea

- **Description**: [One-paragraph summary of the idea]
- **Source**: IDEA_REPORT.md, Idea #N
- **Selection rationale**: [Why this idea over others — pilot results, novelty score, feasibility]

## Core Claims

1. [Main claim — what your method achieves]
2. [Supporting claim — why it works / when it works best]
3. [Optional: scope/limitation claim]

## Method Summary

[2-3 paragraphs: How the method works. Enough detail that a new session can understand the approach without reading the full codebase.]

## Experiment Design

- **Datasets**: [Which datasets, which splits]
- **Baselines**: [What you compare against]
- **Metrics**: [Primary and secondary metrics]
- **Key hyperparameters**: [The ones that matter most]
- **Compute budget**: [GPU hours, hardware]

## Baselines

| Method | Dataset | Metric | Score | Source |
|--------|---------|--------|-------|--------|
| [Baseline A] | [Dataset] | [Metric] | [Number] | [Paper / reproduced] |
| [Baseline B] | [Dataset] | [Metric] | [Number] | [Paper / reproduced] |

## Current Results

> Updated as experiments complete. Start empty, fill in as you go.

| Method | Dataset | Metric | Score | Notes |
|--------|---------|--------|-------|-------|
| [Your method] | [Dataset] | [Metric] | [Number] | [e.g., "3 seeds, mean±std"] |

## Key Decisions

- [Decision 1: Why approach X over Y — with reasoning]
- [Decision 2: Why this hyperparameter / architecture choice]
- [Known limitations / risks and how you plan to handle them]

## Status

- [ ] Idea selected
- [ ] Baseline reproduced
- [ ] Main method implemented
- [ ] Representative dataset results
- [ ] Full dataset results
- [ ] Ablation studies
- [ ] Paper draft
