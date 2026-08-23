---
name: embodiment-description
description: "Write detailed embodiment descriptions for patent specifications. Use when user says \"撰写实施例\", \"write embodiment\", \"实施例描述\", \"detailed description\", or wants to describe how to practice an invention."
argument-hint: "[claims-path-or-embodiment-details]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob
---
> **ARIS-Cursor port** — runs on Cursor built-in models, zero API keys / zero CLI.
> - `/x "args"` = load `skills/x/SKILL.md` from this pack and follow it; `$ARGUMENTS` = the user's instruction text.
> - Runs locally on Cursor built-in models with standard workspace tools.
> - `allowed-tools` frontmatter is advisory on Cursor.

# Embodiment Description

Write detailed embodiments for: **$ARGUMENTS**

Embodiments describe HOW to make and use the invention -- they are the patent equivalent of experiment sections, but describe the invention rather than evaluating it empirically.

## Constants

- `MIN_EMBODIMENTS = 1` — At least one complete embodiment required
- `MAX_EMBODIMENTS = 3` — Practical limit; more embodiments strengthen enablement
- `EMBODIMENT_STYLE = detailed` — `detailed` (full working example) or `outline` (sketch)
- `REFERENCE_NUMERAL_PREFIX = 100` — Starting reference numeral for first figure's components

## Inputs

1. `patent/INVENTION_DISCLOSURE.md` — invention decomposition (core/supporting/optional features)
2. `patent/CLAIMS.md` — drafted claims that the embodiments must support
3. User-provided figures (if any) in any directory
4. `patent/figures/numeral_index.md` if it exists (from `/figure-description`)

## Workflow

### Step 1: Plan Embodiments

For each claim category (method, system, etc.), plan at least one embodiment:

| Embodiment | Covers Claims | Type | Key Variations |
|-----------|--------------|------|----------------|
| 1 | Claims 1, X | Best mode / preferred | [primary implementation] |
| 2 | Claims 2, 3 | Alternative | [different parameters/materials] |
| 3 | Claims 4, 5 | Additional alternative | [different configuration] |

### Step 2: Write Each Embodiment

For each embodiment, write a detailed description following this structure:

**Opening paragraph**:
"In one embodiment, [invention summary with reference to what is being described]."

**Component/step-by-step description**:

For method embodiments:
- Describe each step in order
- Reference figure numerals: "As shown in FIG. 1, at step 202, the processor 102 receives the input data 104..."
- Include specific parameters, ranges, and conditions
- Describe what happens at each decision point

For system/apparatus embodiments:
- Describe each component
- Reference figure numerals: "Referring to FIG. 1, the system 100 comprises a processor 102, a memory 104, and a communication interface 106..."
- Describe interconnections between components
- Describe operation of the system step-by-step

**Variations and alternatives**:
- "In some embodiments, the processor 102 may be a GPU, an FPGA, or an ASIC."
- "In another embodiment, the memory 104 may be replaced with a distributed storage system."
- "The parameters described above are exemplary; other values within the range [X, Y] are also contemplated."

These variations are critical -- they support broader claim interpretation.

### Step 3: Reference Numeral Integration

Ensure consistent reference numeral usage:

1. Every component mentioned must have a numeral
2. Numeral must appear first in parentheses after the component name: "the processor (102)"
3. Subsequent references: "the processor 102" (no parentheses)
4. Numbering follows figure series: 100-series for FIG. 1, 200-series for FIG. 2

**Format**:
- First mention: "the processor (102)"
- Later in same embodiment: "the processor 102"
- Cross-figure: "the processor 102 (shown in both FIG. 1 and FIG. 2)"

### Step 4: Claim Support Verification

For each claim element, verify it appears in at least one embodiment:

| Claim Element | Embodiment | Reference Numeral | Description Paragraph |
|---------------|-----------|-------------------|----------------------|
| [element] | [which] | [numeral] | [paragraph reference] |

If any claim element lacks embodiment support, add the necessary description.

### Step 5: Software/Algorithm Embodiments (if applicable)

For method/software inventions, include:
- Pseudocode or algorithmic description (NOT actual code)
- Flowchart description tied to figures
- Data structure descriptions
- Interface specifications

Example:
```
In one embodiment, the method comprises the following steps:
At step 202, the processor 102 receives input data from the input device 108.
At step 204, the processor 102 extracts feature vectors from the input data using a convolutional neural network.
At step 206, the processor 102 applies the attention mechanism 110 to the feature vectors...
```

### Step 6: Output

Embodiment sections are written to `patent/specification/detailed_description.md` (or appended to the specification structure).

Each embodiment section should be self-contained but cross-reference other embodiments when describing alternatives.

## Key Rules

- Embodiments must teach a POSITA to make and use the invention without undue experimentation.
- Include at least one "best mode" embodiment (US requirement).
- Multiple embodiments strengthen the specification against enablement challenges.
- Describe the invention, do NOT evaluate it empirically ("The embodiment achieves 95% accuracy" is wrong; "The processor classifies the input data" is correct).
- **Guidelines on Embodiment vs. Experimental Data:**
  - Embodiments teach *how to make and practice* the invention (structural recipe and operational flow), not *how well it scores in laboratory benchmarks*.
  - Avoid framing embodiments as empirical evaluations (e.g., do not include accuracy percentages, detection rates, benchmark tables, or comparative performance metrics against prior art).
  - Describe physical mechanisms and qualitative technical interactions (e.g., instead of "achieved 98% detection rate at 150μm", describe "when metallic particles traverse the gap sensing region, the resonant frequency shifts inversely with particle dimension").
  - Do not copy paper experiment sections directly; convert research apparatus into manufacturing/structural embodiment descriptions.
- Include specific parameters where possible, but frame them as exemplary, not limiting.
- Reference numerals must be consistent with the figures.
- Do NOT use subjective language ("excellent", "surprising", "superior").
