# Reviewer Independence Protocol

## Core Principle

The reviewer must judge primary artifacts directly. The executor can define the review role, scope, and file list, but must not pre-digest the content into a preferred narrative.

## What Can Be Passed

- reviewer role or persona
- review objective
- absolute file paths
- structural metadata such as section count or venue
- concrete output schema

## What Must Not Be Passed

- executor summaries of file contents
- executor interpretations of results
- executor recommendations about what the reviewer should conclude
- "what changed since last round" narratives unless the skill explicitly requires diff-focused follow-up
- leading or coaching questions

## Correct Pattern

```text
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    Review the project as a senior ML reviewer.

    Files to read directly:
    - /path/to/PROPOSAL.md
    - /path/to/EXPERIMENT_LOG.md
    - /path/to/paper/main.tex
    - /path/to/src/
```

## Incorrect Pattern

```text
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    The main contribution is a new loss function that improves by 15%.
    I think the weak point is the ablation.
    Please confirm this is publishable.
```

## Multi-Round Follow-Up

When a skill uses multi-round review, reuse the same reviewer id with `send_input`, but still avoid injecting executor conclusions. Pass revised artifacts or targeted follow-up requests, not spin.

## Applies To

This protocol applies to all cross-agent review calls in `skills/skills-codex/`, including:

- `research-review`
- `auto-review-loop`
- `paper-plan`
- `paper-write`
- `paper-figure`
- `rebuttal`
- `meta-optimize`
- any skill that launches a reviewer via `spawn_agent` or continues one via `send_input`
