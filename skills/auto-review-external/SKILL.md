---
name: auto-review-external
description: Automatically response to a external review and improve the paper accordingly
argument-hint: [topic-or-scope]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent, Skill
---

# Auto Review External: Autonomous Research Improvement Based On External Feedback

Autonomously implement fixes according to an external pasted review.

## Context: $ARGUMENTS

## Constants

- MAX_ROUNDS = 1
- POSITIVE_THRESHOLD: score >= 6/10, or verdict contains "accept", "sufficient", "ready for submission"
- REVIEW_DOC: `EXTERNAL_REVIEW.md` in project root

## Workflow

### Initialization

1. Read project context and prior reviews

### Loop (up to MAX_ROUNDS)

#### Phase A: Parse Assessment

**CRITICAL: Save the FULL raw response** verbatim. Then extract:
- **Score** (numeric 1-10)
- **Verdict** ("ready" / "almost" / "not ready")
- **Action items** (ranked list of fixes)

**STOP**: If score >= 6 AND verdict contains "ready/almost"

#### Phase B: Implement Fixes

Priority: metric additions > reframing > new experiments

#### Phase C: Wait for Results

Monitor remote experiments

#### Phase D: Document Round

Append to `EXTERNAL_REVIEW.md`:

```markdown
## Round N (timestamp)

### Assessment (Summary)
- Score: X/10
- Verdict: [ready/almost/not ready]
- Key criticisms: [bullet list]

### Reviewer Raw Response

<details>
<summary>Click to expand full reviewer response</summary>

[Paste the COMPLETE raw response here — verbatim, unedited.]

</details>

### Actions Taken
- [what was implemented/changed]

### Results
- [experiment outcomes, if any]

### Status
- [continuing to round N+1 / stopping]
```

### Termination

1. Write final summary

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- **Anti-hallucination citations**: When adding references, NEVER fabricate BibTeX. Use DBLP → CrossRef → `[VERIFY]` chain. Do NOT generate BibTeX from memory.
- Be honest about weaknesses
- Implement fixes BEFORE re-reviewing
- Document everything
