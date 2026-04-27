---
name: figure-description
description: "Process user-provided patent figures and generate formal drawing descriptions. Use when user says \"附图处理\", \"figure description\", \"附图说明\", \"drawings description\", or wants to describe patent figures with reference numerals."
argument-hint: [figure-directory-or-figure-list]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch
---

# Figure Description for Patents

Process patent figures and generate drawing descriptions based on: **$ARGUMENTS**

Unlike `/paper-figure` which generates data plots, this skill processes user-provided technical diagrams and assigns reference numerals.

## Constants

- `FIGURE_DIR = "patent/figures/"` — Output directory for figure descriptions
- `REFERENCE_NUMERAL_PREFIX = 100` — Starting numeral for first figure's components
- `NUMERAL_SERIES = 100` — Each figure uses a separate 100-series (Fig 1: 100-199, Fig 2: 200-299, etc.)

## Inputs

1. User-provided figures (PNG, JPG, SVG, PDF) — search for them in the project directory
2. `patent/INVENTION_DISCLOSURE.md` — for understanding what components to identify
3. `patent/CLAIMS.md` — for mapping numerals to claim elements

## Workflow

### Step 1: Discover Figures

1. Search the project directory for figure files:
   - Check `patent/figures/`, `figures/`, root directory
   - Look for PNG, JPG, SVG, PDF files
   - Check INVENTION_BRIEF.md or INVENTION_DISCLOSURE.md for figure references
2. List all discovered figures with their paths
3. If figures are missing that claims require, note them as `[MISSING: description needed]`

### Step 2: Analyze Each Figure

For each figure found:

1. **Read the image** using the Read tool (supports image files)
2. **Identify components**: What labeled or visually distinct components are shown?
3. **Identify connections**: How do components relate to each other?
4. **Identify flow**: If it's a flowchart or sequence, what is the step order?

### Step 3: Assign Reference Numerals

For each figure, assign numerals using the series convention:

| Figure | Numeral Range |
|--------|-------------|
| FIG. 1 | 100-199 |
| FIG. 2 | 200-299 |
| FIG. 3 | 300-399 |

For each identified component:
- Assign the next available numeral in the series
- Cross-reference to the claim elements it supports
- Note if a component appears in multiple figures (use same numeral across figures)

### Step 4: Generate Drawing Descriptions

Write formal drawing descriptions (附图说明):

**For CN jurisdiction (Chinese)**:
```
图1是[发明名称]的系统结构示意图；
图2是[发明名称]的方法流程图；
图3是[具体组件]的详细结构示意图；
```

**For US/EP jurisdiction (English)**:
```
FIG. 1 is a block diagram illustrating the system architecture according to one embodiment;
FIG. 2 is a flowchart illustrating the method steps according to one embodiment;
FIG. 3 is a detailed view of the processing module of FIG. 1;
```

### Step 5: Generate Reference Numeral Index

Create a complete mapping:

```markdown
## Reference Numeral Index

| Numeral | Component Name | Figure(s) | Claim Element |
|---------|---------------|-----------|---------------|
| 100 | System | FIG. 1 | Claim X preamble |
| 102 | Processor | FIG. 1 | Claim X, element 1 |
| 104 | Memory | FIG. 1 | Claim X, element 2 |
| 106 | Communication bus | FIG. 1 | Claim X, element 3 |
| 200 | Method | FIG. 2 | Claim 1 preamble |
| 202 | Receiving step | FIG. 2 | Claim 1, step 1 |
| 204 | Processing step | FIG. 2 | Claim 1, step 2 |
```

### Step 6: Cross-Reference to Claims

Verify that every claim element has at least one reference numeral:

| Claim Element | Figure | Numeral | Status |
|---------------|--------|---------|--------|
| [element] | [which fig] | [numeral] | Covered / [MISSING] |

If any claim element has no corresponding figure or numeral, flag it:
- `[MISSING FIGURE: Need a diagram showing {element description}]`
- `[MISSING NUMERAL: Component {name} in figure {X} needs a numeral]`

### Step 7: Output

Write `patent/figures/figure_descriptions.md`:
```markdown
## Figure Descriptions

### FIG. 1 — [Description]
[Formal one-paragraph description with all reference numerals]

### FIG. 2 — [Description]
[Formal one-paragraph description with all reference numerals]
...
```

Write `patent/figures/numeral_index.md`:
```markdown
## Reference Numeral Index

[Complete table of all numerals, components, figures, and claim mappings]
```

## Key Rules

- Every component in every figure must have a reference numeral.
- Every reference numeral must be explained in the specification.
- Numeral series must be consistent: 100-series for FIG. 1, 200-series for FIG. 2.
- If the same component appears in multiple figures, use the SAME numeral.
- Do NOT modify user-provided figures -- only describe them.
- Flag missing figures that the claims require but the user has not provided.
- Drawing descriptions are one sentence each, in a consistent format.
