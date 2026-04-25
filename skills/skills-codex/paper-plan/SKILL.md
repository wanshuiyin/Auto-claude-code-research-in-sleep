---
name: "paper-plan"
description: "Generate a structured paper outline from results, claims, and review conclusions. Use for outlining or planning a paper before drafting. Do not use for actual LaTeX writing or compilation; use `paper-write` or `paper-compile` then."
---

# Paper Plan: From Review Conclusions to Paper Outline

Generate a structured, section-by-section paper outline from: **$ARGUMENTS**

## Routing Boundaries

- Use this skill for outline creation, section planning, and claims-to-paper structuring.
- Use `paper-write` when the user wants actual draft text or LaTeX sections.
- Use `paper-writing` only when the user explicitly wants the full paper pipeline.
- Use `result-to-claim` first when the main question is what the finished experiments support, not how to outline the paper.

## Constants

- **REVIEWER_MODEL = `gpt-5.4`** — Model used via a secondary Codex agent for outline review. Must be an OpenAI model.
- **TARGET_VENUE = `ICLR`** — Default venue. User can override (e.g., `/paper-plan "topic" — venue: NeurIPS`). Supported: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`, `IEEE_JOURNAL` (IEEE Transactions / Letters), `IEEE_CONF` (IEEE conferences).
- **MAX_PAGES** — Page limit. For ML conferences: main body to Conclusion end (excluding references, appendix). ICLR=9, NeurIPS=9, ICML=8. **For IEEE venues: references ARE included in page count.** IEEE journal Transactions ≈ 12-14 pages total, Letters ≈ 4-5 pages total; IEEE conference ≈ 5-8 pages total (including references).

## Inputs

The skill expects one or more of these in the project directory:

1. **NARRATIVE_REPORT.md** or **STORY.md** — research narrative with claims and evidence
2. **review-stage/AUTO_REVIEW.md** — auto-review loop conclusions *(fall back to `./AUTO_REVIEW.md` if not found)*
3. **Experiment results** — JSON files in `figures/`, screen logs, tables
4. **idea-stage/IDEA_REPORT.md** — from idea-discovery pipeline (if applicable) *(fall back to `./IDEA_REPORT.md` if not found)*
5. **CLAIMS_FROM_RESULTS.md** — structured claim judgment from `/result-to-claim` (preferred if available)

If none exist, ask the user to describe the paper's contribution in 3-5 sentences.

## Orchestra-Guided Writing Overlay

Keep the existing workflow and outputs, but use the shared references below to improve the quality of the story and outline:

- Read `../shared-references/writing-principles.md` when framing the Abstract, Introduction, Related Work, or hero figure
- Read `../shared-references/venue-checklists.md` before freezing the outline for a specific venue
- Load these references only when they help; they are support material, not a new workflow phase

## Workflow

### Step 1: Extract Claims and Evidence

**First check for `CLAIMS_FROM_RESULTS.md`** — if it exists, use it as the starting point for claims and merge it with any additional evidence from the narrative documents below.

Read all available narrative documents and extract:

1. **Core claims** (3-5 main contributions)
2. **Evidence** for each claim (which experiments, which metrics, which figures)
3. **Known weaknesses** (from reviewer feedback)
4. **Suggested framing** (from review conclusions)

Build a **Claims-Evidence Matrix**:

```markdown
| Claim | Evidence | Status | Section |
|-------|----------|--------|---------|
| [claim 1] | [exp A, metric B] | Supported | §3.2 |
| [claim 2] | [exp C] | Partially supported | §4.1 |
```

### Step 2: Determine Paper Type and Structure

Based on TARGET_VENUE and paper content, classify and select structure.

Before committing to a structure, apply the narrative principle from `../shared-references/writing-principles.md`:

- The paper should tell one coherent technical story
- By the end of the Introduction, the outline should make the **What**, **Why**, and **So What** explicit
- Front-load the most important material: title, abstract, introduction, and hero figure

**IMPORTANT**: The section count is FLEXIBLE (5-8 sections). Choose what fits the content best. The templates below are starting points, not rigid constraints.

**Empirical/Diagnostic paper:**
```
1. Introduction (1.5 pages)
2. Related Work (1 page)
3. Method / Setup (1.5 pages)
4. Experiments (3 pages)
5. Analysis / Discussion (1 page)
6. Conclusion (0.5 pages)
```

**Theory + Experiments paper:**
```
1. Introduction (1.5 pages)
2. Related Work (1 page)
3. Preliminaries & Modeling (1.5 pages)
4. Experiments (1.5 pages)
5. Theory Part A (1.5 pages)
6. Theory Part B (1.5 pages)
7. Conclusion (0.5 pages)
— Total: 9 pages
```
Theory papers often need 7 sections (splitting theory into estimation + optimization, or setup + analysis). The total page budget MUST sum to MAX_PAGES.

Theory papers should:
- Include **proof sketch** locations (not just theorem statements)
- Plan a **comparison table** of prior theoretical bounds vs. this paper's bounds
- Identify which proofs go in appendix vs. main body

**Method paper:**
```
1. Introduction (1.5 pages)
2. Related Work (1 page)
3. Method (2 pages)
4. Experiments (2.5 pages)
5. Ablation / Analysis (1 page)
6. Conclusion (0.5 pages)
```

### Step 3: Section-by-Section Planning

For each section, specify:

```markdown
### §0 Abstract
- **One-sentence problem**: [what gap this paper addresses]
- **Approach**: [what we do, in one sentence]
- **Key result**: [most compelling quantitative finding]
- **Implication**: [why it matters]
- **Estimated length**: 150-250 words
- **Self-contained check**: can a reader understand this without the paper?

### §1 Introduction
- **Opening hook**: [1-2 sentences that motivate the problem]
- **Gap**: [what's missing in prior work]
- **Key questions**: [the research questions this paper answers]
- **Contributions**: [numbered list, matching Claims-Evidence Matrix]
- **Hero figure**: [describe what Figure 1 should show — MUST include clear comparison if applicable]
- **Estimated length**: 1.5 pages
- **Key citations**: [3-5 papers to cite here]

### §2 Related Work
- **Subtopics**: [2-4 categories of related work]
- **Positioning**: [how this paper differs from each category]
- **Minimum length**: 1 full page (at least 3-4 paragraphs with substantive synthesis)
- **Must NOT be just a list** — synthesize, compare, and position

### §3 Method / Setup / Preliminaries
- **Notation**: [key symbols and their meanings]
- **Problem formulation**: [formal setup]
- **Method description**: [algorithm, model, or experimental design]
- **Formal statements**: [theorems, propositions if applicable]
- **Proof sketch locations**: [which key steps appear here vs. appendix]
- **Estimated length**: 1.5-2 pages

### §4 Experiments / Main Results
- **Figures planned**:
  - Fig 1: [description, type: bar/line/table/architecture, WHAT COMPARISON it shows]
  - Fig 2: [description]
  - Table 1: [what it shows, which methods/baselines compared]
- **Data source**: [which JSON files / experiment results]

### §5 Conclusion
- **Restatement**: [contributions rephrased, not copy-pasted from intro]
- **Limitations**: [honest assessment — reviewers value this]
- **Future work**: [1-2 concrete directions]
- **Estimated length**: 0.5 pages
```

### Step 4: Figure Plan

List every figure and table:

```markdown
## Figure Plan

| ID | Type | Description | Data Source | Priority |
|----|------|-------------|-------------|----------|
| Fig 1 | Hero/Architecture | System overview + comparison | manual | HIGH |
| Fig 2 | Line plot | Training curves comparison | figures/exp_A.json | HIGH |
| Fig 3 | Bar chart | Ablation results | figures/ablation.json | MEDIUM |
| Table 1 | Comparison table | Main results vs. baselines | figures/main_results.json | HIGH |
| Table 2 | Theory comparison | Prior bounds vs. ours | manual | HIGH (theory papers) |
```

**CRITICAL for Figure 1 / Hero Figure**: Describe in detail what the figure should contain, including:
- Which methods are being compared
- What the visual difference should demonstrate
- Caption draft that clearly states the comparison

### Step 5: Citation Scaffolding

For each section, list required citations:

```markdown
## Citation Plan
- §1 Intro: [paper1], [paper2], [paper3] (problem motivation)
- §2 Related: [paper4]-[paper10] (categorized by subtopic)
- §3 Method: [paper11] (baseline), [paper12] (technique we build on)
```

**Citation rules** (from claude-scholar + Imbad0202/academic-research-skills):
1. NEVER generate BibTeX from memory — always verify via search or existing .bib files
2. Every citation must be verified: correct authors, year, venue
3. Flag any citation you're unsure about with `[VERIFY]`
4. Prefer published versions over arXiv preprints when available

### Step 6: Cross-Review with REVIEWER_MODEL

Send the complete outline to GPT-5.4 xhigh for feedback:

```
spawn_agent:
  model: gpt-5.4
  reasoning_effort: xhigh
  message: |
    Review this paper outline for a [VENUE] submission.
    [full outline including Claims-Evidence Matrix]

    Score 1-10 on:
    1. Logical flow — does the story build naturally?
    2. Claim-evidence alignment — every claim backed?
    3. Missing experiments or analysis
    4. Positioning relative to prior work
    5. Page budget feasibility (MAX_PAGES = main body to Conclusion end, excluding refs/appendix)

    For each weakness, suggest the MINIMUM fix.
    Be specific and actionable — "add X" not "consider more experiments".
```

Apply feedback before finalizing.

### Step 7: Output

Save the final outline to `PAPER_PLAN.md` in the project root:

```markdown
# Paper Plan

**Title**: [working title]
**Venue**: [target venue]
**Type**: [empirical/theory/method]
**Date**: [today]
**Page budget**: [MAX_PAGES] pages (main body to Conclusion end, excluding references & appendix)
**Section count**: [N] (must match the number of section files that will be created)

## Claims-Evidence Matrix
[from Step 1]

## Structure
[from Step 2-3, section by section]

## Figure Plan
[from Step 4, with detailed hero figure description]

## Citation Plan
[from Step 5]

## Reviewer Feedback
[from Step 6, summarized]

## Next Steps
- [ ] /paper-figure to generate all figures
- [ ] /paper-write to draft LaTeX
- [ ] /paper-compile to build PDF
```

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- **Do NOT generate author information** — leave author block as placeholder or anonymous
- **Be honest about evidence gaps** — mark claims as "needs experiment" rather than overclaiming
- **Page budget is hard** — if content exceeds MAX_PAGES, suggest what to move to appendix
- **MAX_PAGES counting differs by venue** — ML conferences: main body to Conclusion end, references/appendix NOT counted. **IEEE venues: references ARE counted toward the page limit.**
- **Venue-specific norms** — ML conferences (ICLR/NeurIPS/ICML) use `natbib` (`\citep`/`\citet`); **IEEE venues use `cite` package (`\cite{}`, numeric style)**
- **Claims-Evidence Matrix is the backbone** — every claim must map to evidence, every experiment must support a claim
- **Figures need detailed descriptions** — especially the hero figure, which must clearly specify comparisons and visual expectations
- **Section count is flexible** — 5-8 sections depending on paper type. Don't force content into a rigid 5-section template.

## Acknowledgements

Outline methodology inspired by [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills) (claim-evidence mapping), [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) (citation verification), and [Imbad0202/academic-research-skills](https://github.com/Imbad0202/academic-research-skills) (claim verification protocol).

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting
