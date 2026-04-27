---
name: writing-systems-papers
description: "Paragraph-level structural blueprint for 10-12 page systems papers targeting OSDI, SOSP, ASPLOS, NSDI, and EuroSys. Provides page allocation, paragraph templates, and writing patterns. Use when user says \"写系统论文\", \"systems paper structure\", \"OSDI paper\", \"SOSP paper\", or wants fine-grained structural guidance for a systems conference submission."
argument-hint: [venue-or-section]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch
---

# Writing Systems Papers: Paragraph-Level Blueprint

Structural guidance for **$ARGUMENTS**

## Relationship to Other ARIS Skills

- **paper-write**: General paper generation workflow with citation verification. This skill complements it with systems-specific structural blueprints.
- **paper-slides**: Conference presentation generation (Beamer+PPTX). Already covers talks — no overlap.
- **paper-plan**: Research outline creation. Use paper-plan first, then this skill for paragraph-level structure.

**Boundary**: paper-write handles the generation workflow (LaTeX output, DBLP verification, section-by-section drafting). This skill provides the **structural skeleton** — page budgets, paragraph roles, and writing patterns specific to systems venues.

---

## Page Allocation: 12-Page Systems Paper

| Section | Pages | Key Content |
|---------|-------|-------------|
| Abstract | ~0.25 | 150–250 words, 5 sentences |
| S1 Introduction | 1.5–2 | Problem → Gap → Insight → Contributions |
| S2 Background & Motivation | 1–1.5 | Terms + Production observations |
| S3 Design | 3–4 | Architecture + Modules + Alternatives |
| S4 Implementation | 0.5–1 | Prototype, LOC, engineering |
| S5 Evaluation | 3–4 | Setup + E2E + Ablation + Scalability |
| S6 Related Work | 1 | By methodology, explicit comparison |
| S7 Conclusion | 0.5 | 3-sentence summary |

---

## Section Blueprints

### Abstract (5 sentences)

```text
S1: Problem context and importance
S2: Gap in existing approaches
S3: Thesis — "X is better for Y in environment Z" (Irene Zhang formula)
S4: Approach summary + headline results
S5: Impact or availability
```

Sources: Levin & Redell — "Can you state the new idea concisely?"; Irene Zhang — "abstract cannot use terms introduced in the paper."

### S1 Introduction (1.5–2 pages)

1. **Problem** (~0.5p) — Domain + concrete numbers + why it matters
2. **Gap analysis** (~0.5p) — G1–Gn: specific shortcomings with evidence
3. **Key insight** (1 para) — Thesis: "X is better for Y in Z"
4. **Contributions** (~0.5p) — 3–5 numbered, testable claims with §N references

Pattern: hzwer Move 1 (territory) → Move 2 (niche) → Move 3 (occupy).

### S2 Background & Motivation (1–1.5 pages)

1. **Technical background** (~0.5p) — Define-before-use (Gernot Heiser)
2. **Observations** (~0.5–1p) — O1, O2, O3 from production data → design insights

### S3 Design (3–4 pages)

1. **Architecture overview** (~0.5p) — Diagram first (Yi Ding: "draw a picture first")
2. **Module details** (~2–2.5p) — Per module: choice, alternatives, why
3. **Trade-offs** (~0.5–1p) — Summary of design decisions

Rule: "Every design choice must discuss alternatives" (Irene Zhang).

### S4 Implementation (0.5–1 page)

Language, LOC, framework, key engineering decisions. Keep concise.

### S5 Evaluation (3–4 pages)

1. **Setup** (~0.5p) — Hardware, baselines, workloads, metrics
2. **End-to-end** (~1–1.5p) — X vs baselines for Y on Z
3. **Ablation** (~1–1.5p) — Remove each component, measure impact
4. **Scalability** (~0.5p) — Behavior at increasing scale

**Three-statement rule** (Irene Zhang): Every conclusion stated as:
- Hypothesis (section opening)
- Conclusion (section closing)
- Caption (figure caption)

### S6 Related Work (1 page)

Group by methodology. For each group: what they do, limitation, how we differ.

### S7 Conclusion (0.5 page)

Three sentences: problem, solution, result. No new information.

---

## Writing Patterns

### Pattern 1: Gap Analysis
Enumerate G1–Gn in intro → A1–An in design → verify in evaluation.
*Example*: Lucid (ASPLOS'23) — 5 gaps mapped to 5 answers.

### Pattern 2: Observation-Driven
O1–O3 from production data → insights → design components.
*Example*: GFS (arXiv 2025) — 3 observations drive 3 components.

### Pattern 3: Contribution List
Numbered contributions in intro, each with §N cross-reference.
*Example*: Blox (EuroSys'24) — 7 contributions; Sia (SOSP'23) — 5 contributions.

### Pattern 4: Thesis Formula
"X is better for Y in Z" structures the entire paper.
Combine with other patterns for maximum impact.

---

## Conference Differences

> Always verify against current CFP — rules change yearly.

| Venue | Format | Pages | Camera-Ready |
|-------|--------|-------|-------------|
| OSDI | USENIX | 12 | 14 |
| NSDI | USENIX | 12 | 14 |
| SOSP | ACM SIGOPS | 12 | — |
| ASPLOS | ACM SIGPLAN | 11 | 13 |
| EuroSys | ACM | 12 | — |

Based on 2025/2026 CFPs.

---

## Workflow

```text
1. Determine venue and page limit
2. Choose writing pattern (Gap/Observation/Contribution/Thesis)
3. Allocate pages per section using the table above
4. Draft Abstract following 5-sentence template
5. Draft Introduction: Problem → Gap → Insight → Contributions
6. Draft Motivation with production observations (if available)
7. Draw architecture figure, then write Design
8. Draft Implementation (concise)
9. Draft Evaluation: setup → E2E → ablation → scalability
10. Draft Related Work by methodology groups
11. Draft Conclusion: 3 sentences
12. Run pre-submission checklist
13. Hand off to /paper-write for LaTeX generation and citation verification
```

---

## Quick Self-Check

- [ ] Thesis follows "X is better for Y in Z"
- [ ] 3–5 numbered contributions with §N references
- [ ] Design discusses alternatives for every major choice
- [ ] Eval conclusions stated 3 times (hypothesis, result, caption)
- [ ] Related work grouped by methodology
- [ ] Page budget within venue limits
- [ ] No fabricated observations, traces, or results
- [ ] All citations verified (delegate to /paper-write)

---

## Academic Integrity

- Never fabricate observations, traces, or experimental results
- Never generate citations from memory — use /paper-write citation workflow
- Disclose LLM use per venue policy
- This blueprint provides structural guidance, not copy-paste text

---

## Authoritative Sources

1. Levin & Redell — "How (and How Not) to Write a Good Systems Paper" (USENIX)
2. Irene Zhang — "Hints on how to write an SOSP paper"
3. Gernot Heiser — Style Guide + Paper Writing Talk
4. Timothy Roscoe — "Writing reviews for systems conferences"
5. Yi Ding — "How to write good systems papers?"
6. hzwer & DingXiaoH — WritingAIPaper (GitHub)
