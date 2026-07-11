---
name: mermaid-diagram
description: "Generate Mermaid diagrams from user requirements. Supports flowcharts, sequence diagrams, class diagrams, ER diagrams, Gantt charts, and 18 more diagram types."
argument-hint: [diagram description or requirements]
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep
---

# Mermaid Diagram Generator

Generate high-quality Mermaid diagram code based on user requirements, with file output and verification.

## Constants

- **OUTPUT_DIR = `figures/`** — Output directory for all generated files
- **MAX_ITERATIONS = 3** — Maximum refinement rounds for syntax errors

## Workflow: MUST EXECUTE ALL STEPS

### Step 0: Pre-flight Check

```bash
# Create output directory
mkdir -p figures
```

### Step 1: Understand Requirements & Select Diagram Type

Parse the input: **$ARGUMENTS**

1. Analyze user description to determine the most suitable diagram type
2. Read the corresponding syntax reference documentation (see Diagram Type Reference below)
3. **If the diagram involves mathematical notation** (formulas, equations, Greek letters, subscripts, superscripts, fractions, matrices, etc.), apply the math syntax rules from the **Math Formulas in Diagrams** section below
4. Identify all components, connections, and data flow
5. Plan the diagram structure

### Step 2: Read Documentation

Select the appropriate diagram type based on the use case. Use your built-in knowledge of Mermaid syntax, or fetch up-to-date docs via the context7 MCP server if needed.

| Type | Use Cases |
| ---- | --------- |
| Flowchart | Processes, decisions, steps |
| Sequence Diagram | Interactions, messaging, API calls |
| Class Diagram | Class structure, inheritance, associations |
| State Diagram | State machines, state transitions |
| ER Diagram | Database design, entity relationships |
| Gantt Chart | Project planning, timelines |
| Pie Chart | Proportions, distributions |
| Mindmap | Hierarchical structures, knowledge graphs |
| Timeline | Historical events, milestones |
| Git Graph | Branches, merges, versions |
| Quadrant Chart | Four-quadrant analysis |
| Requirement Diagram | Requirements traceability |
| C4 Diagram | System architecture (C4 model) |
| Sankey Diagram | Flow, conversions |
| XY Chart | Line charts, bar charts |
| Block Diagram | System components, modules |
| Packet Diagram | Network protocols, data structures |
| Kanban | Task management, workflows |
| Architecture Diagram | System architecture |
| Radar Chart | Multi-dimensional comparison |
| Treemap | Hierarchical data visualization |
| User Journey | User experience flows |
| ZenUML | Sequence diagrams (code style) |

### Configuration & Themes

- **Theming** - Custom colors and styles
- **Directives** - Diagram-level configuration
- **Layouts** - Layout direction and spacing
- **Configuration** - Global settings
- **Math** - LaTeX math support (see Math Formulas in Diagrams section below)

### Step 3: Generate Mermaid Code & Save Files

Generate the Mermaid code following the reference specification, then save TWO files:

#### File 1: `figures/<diagram-name>.mmd` — Raw Mermaid source

The `.mmd` file contains ONLY the raw Mermaid code (no markdown fences). Example:

```
flowchart TD
    A[Start] --> B{Condition}
    B -->|Yes| C[Execute]
    B -->|No| D[End]
    C --> D
```

#### File 2: `figures/<diagram-name>.md` — Markdown with embedded Mermaid

The `.md` file wraps the same code in a mermaid code block for preview rendering, plus a title and description. Example:

```markdown
# Diagram Title

Brief description of what this diagram shows.

​```mermaid
flowchart TD
    A[Start] --> B{Condition}
    B -->|Yes| C[Execute]
    B -->|No| D[End]
    C --> D
​```
```

**Naming convention**: Use a descriptive kebab-case name derived from the user's request (e.g., `auth-flow`, `system-architecture`, `database-er`).

### Step 4: Verify Mermaid Syntax (MANDATORY)

**Claude MUST verify the generated Mermaid code by running the Mermaid CLI (`mmdc`).**

```bash
# Check if mermaid-cli is available
if command -v mmdc &> /dev/null; then
    # Render to PNG to verify syntax is correct
    mmdc -i figures/<diagram-name>.mmd -o figures/<diagram-name>.png -b transparent
    echo "✅ Syntax valid — PNG rendered to figures/<diagram-name>.png"
else
    # Try npx as fallback
    npx -y @mermaid-js/mermaid-cli@latest -i figures/<diagram-name>.mmd -o figures/<diagram-name>.png -b transparent
    echo "✅ Syntax valid — PNG rendered to figures/<diagram-name>.png"
fi
```

**If the verification fails:**
1. Read the error message carefully
2. Fix the syntax issue in both `.mmd` and `.md` files
3. Re-run verification
4. Repeat up to MAX_ITERATIONS (3) times

### Step 5: Claude STRICT Visual Review & Scoring (MANDATORY)

After successful rendering, Claude MUST read the generated PNG and perform a STRICT review:

```markdown
## Claude's STRICT Review of <diagram-name>

### What I See
[Describe the rendered diagram in DETAIL - every block, every arrow, every label]

### Files Generated
- `figures/<diagram-name>.mmd` — Raw Mermaid source
- `figures/<diagram-name>.md` — Markdown with embedded diagram
- `figures/<diagram-name>.png` — Rendered PNG (if mmdc available)

### ═══════════════════════════════════════════════════════════════
### STRICT VERIFICATION CHECKLIST (ALL must pass for score ≥ 9)
### ═══════════════════════════════════════════════════════════════

#### A. File Correctness
- [ ] `.mmd` file contains valid Mermaid syntax (no markdown fences)
- [ ] `.md` file has the mermaid code wrapped in ```mermaid``` fences
- [ ] `.mmd` and `.md` contain IDENTICAL Mermaid code
- [ ] Diagram renders without errors (via mmdc)

#### B. Arrow Correctness Verification (CRITICAL - any failure = score ≤ 6)
Check EACH arrow:
- [ ] Arrow 1: [Source] → [Target] — Does it point to the CORRECT target?
- [ ] Arrow 2: [Source] → [Target] — Does it point to the CORRECT target?
- [ ] ... (check ALL arrows)

#### C. Block Content Verification (any failure = score ≤ 7)
Check EACH block/node:
- [ ] Block 1 "[Name]": Has correct label? Content correct?
- [ ] Block 2 "[Name]": Has correct label? Content correct?
- [ ] ... (check ALL blocks)

#### D. Completeness
- [ ] All components from user requirements are present
- [ ] All connections/arrows are correct
- [ ] Node labels are meaningful and match requirements

#### E. Visual Quality
- [ ] Layout is clean and readable
- [ ] Color scheme is professional (not rainbow)
- [ ] Text is readable at normal zoom
- [ ] Proper spacing (not cramped, not sparse)
- [ ] Data flow is traceable in 5 seconds

### ═══════════════════════════════════════════════════════════════

### Issues Found (BE SPECIFIC)
1. [Issue 1]: [EXACTLY what is wrong] → [How to fix]
2. [Issue 2]: [EXACTLY what is wrong] → [How to fix]

### Score: X/10

### Score Breakdown Guide:
- **10**: Perfect. No issues. Publication-ready.
- **9**: Excellent. Minor issues that don't affect understanding.
- **8**: Good but has noticeable issues (layout, styling).
- **7**: Usable but has clear problems (wrong arrows, missing labels).
- **6**: Has arrow direction errors or missing major components.
- **1-5**: Major issues. Unacceptable.

### Verdict
[ ] ACCEPT (score ≥ 9 AND all critical checks pass)
[ ] FIX (score < 9 OR any critical check fails — list EXACT fixes needed)
```

**If FIX: apply corrections to both `.mmd` and `.md` files, re-render, and re-verify. Loop until ACCEPT or MAX_ITERATIONS reached.**

### Step 6: Final Output Summary

When accepted, present to user:

```
✅ Mermaid diagram generated successfully!

Files:
  figures/<diagram-name>.mmd  — Raw Mermaid source (use with mmdc, editors, CI)
  figures/<diagram-name>.md   — Markdown preview (renders on GitHub, VS Code, etc.)
  figures/<diagram-name>.png  — Rendered image (if mmdc was available)

To re-render manually:
  mmdc -i figures/<diagram-name>.mmd -o figures/<diagram-name>.png
```

## Architecture Diagram Best Practices

When generating `architecture-beta` diagrams, apply these layout techniques for complex diagrams:

### Use Junctions for Layout Control

Think of the diagram as an invisible grid. Use `junction` nodes as virtual anchor points on that grid to precisely control where each component is placed. This is especially useful when a direct edge between two services produces unexpected positioning.

Instead of connecting services directly:

```
lb:R --> L:scim
lb:R --> L:webapi
```

Route through junctions to control vertical/horizontal placement:

```
junction j_lb_r
lb:R -- L:j_lb_r
junction j_scim_l
j_lb_r:T -- B:j_scim_l
j_scim_l:R --> L:scim
junction j_webapi_l
j_lb_r:B -- T:j_webapi_l
j_webapi_l:R --> L:webapi
```

Place junctions on all four sides of components to anchor them logically on the grid.

### Use Edges out of Groups for Floating Components

For services that have no logical connection to other nodes (e.g. a deployment tool, a monitoring agent), use a junction combined with the `{group}` modifier to position them without adding a semantically incorrect edge:

```
junction j_acd_t
j_algolia_proc_b{group}:B -- T:j_acd_t
j_acd_t:B -- T:acd
```

This anchors `acd` below its intended neighbor without implying a real relationship.

## CVPR/ICLR/NeurIPS Style Guide (for Academic Diagrams)

When the diagram is intended for academic papers, apply these style standards:

### Visual Standards
- **Clean white background** — No decorative patterns or gradients (unless subtle)
- **Sans-serif fonts** — Arial, Helvetica, or Computer Modern; minimum 14pt
- **Subtle color palette** — Not rainbow colors; use 3-5 coordinated colors
- **Print-friendly** — Must be readable in grayscale (many reviewers print papers)
- **Professional borders** — Thin (2-3px), solid colors, not flashy

### Layout Standards
- **Horizontal flow** — Left-to-right is the standard for pipelines
- **Clear grouping** — Use subtle background boxes to group related modules
- **Consistent sizing** — Similar components should have similar sizes
- **Balanced whitespace** — Not cramped, not sparse

### Arrow Standards (MOST CRITICAL)
- **Thick strokes** — 4-6px minimum (thin arrows disappear when printed)
- **Clear arrowheads** — Large, filled triangular heads
- **Dark colors** — Black or dark gray (#333333); avoid colored arrows
- **Labeled** — Every arrow should indicate what data flows through it
- **No crossings** — Reorganize layout to avoid arrow crossings
- **CORRECT DIRECTION** — Arrows must point to the RIGHT target!

### Color Palette (Academic Professional)
- **Inputs**: Green (#10B981 / #34D399)
- **Encoders**: Blue (#2563EB / #3B82F6)
- **Fusion**: Purple (#7C3AED / #8B5CF6)
- **Outputs**: Orange (#EA580C / #F97316)
- **Arrows**: Black or dark gray (#333333 / #1F2937)
- **Background**: Pure white (#FFFFFF)

### What to AVOID
- Rainbow color schemes (too many colors)
- Thin, hairline arrows
- Heavy drop shadows or glowing effects
- 3D effects / perspective
- Excessive decorative icons
- Small text that's unreadable when printed

## Math Formulas in Diagrams (KaTeX)

Mermaid supports rendering mathematical expressions via KaTeX (v10.9.0+). **When the diagram content involves math** (formulas, equations, Greek letters, subscripts/superscripts, fractions, matrices, operators, etc.), use KaTeX notation instead of plain-text approximations.

### Supported Diagram Types for Math

Math rendering with `$$...$$` is supported in:
- **Flowcharts** (`flowchart` / `graph`) — in node labels and edge labels
- **Sequence Diagrams** — in participant aliases, messages, and notes

### Syntax Rules

1. **Wrap math expressions in `$$` delimiters** inside quoted strings:
   ```
   A["$$x^2$$"] -->|"$$\sqrt{x+3}$$"| B("$$\frac{1}{2}$$")
   ```

2. **Node labels with math MUST be quoted** — use `["$$...$$"]` or `("$$...$$")`:
   ```
   scaledDot["$$\text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$"]
   ```

3. **Mix text and math** by placing `$$` only around the math portion:
   ```
   layer1["Linear Layer $$W_1 x + b_1$$"]
   ```

4. **Use `\text{}`** for non-math text inside a `$$` block:
   ```
   node["$$\text{Attention}(Q, K, V)$$"]
   ```

### Common Math Patterns for ML/Science Diagrams

| Concept | KaTeX Syntax | Renders As |
| ------- | ------------ | ---------- |
| Subscript | `$$W_Q$$` | W_Q |
| Superscript | `$$x^2$$` | x² |
| Fraction | `$$\frac{QK^T}{\sqrt{d_k}}$$` | QK^T / sqrt(d_k) |
| Greek letters | `$$\alpha, \beta, \gamma$$` | α, β, γ |
| Square root | `$$\sqrt{d_k}$$` | √d_k |
| Summation | `$$\sum_{i=1}^{n} x_i$$` | Σx_i |
| Matrix | `$$\begin{bmatrix} a & b \\ c & d \end{bmatrix}$$` | 2x2 matrix |
| Softmax | `$$\text{softmax}(z_i)$$` | softmax(z_i) |
| Norm | `$$\|\|x\|\|_2$$` | ‖x‖₂ |
| Hat/tilde | `$$\hat{y}, \tilde{x}$$` | ŷ, x̃ |

### Example: Attention Mechanism with Math

```
flowchart TD
    Q["$$Q \in \mathbb{R}^{n \times d_k}$$"]
    K["$$K \in \mathbb{R}^{n \times d_k}$$"]
    V["$$V \in \mathbb{R}^{n \times d_v}$$"]
    scores["$$\frac{QK^T}{\sqrt{d_k}}$$"]
    softmax["$$\text{softmax}(\cdot)$$"]
    output["$$\text{Attention}(Q,K,V)$$"]

    Q --> scores
    K --> scores
    scores --> softmax
    softmax --> weighted["$$\alpha V$$"]
    V --> weighted
    weighted --> output
```

### When to Use Math vs Plain Text

- **Use math** when the diagram is for academic/technical audiences and precision matters (papers, lectures, technical docs)
- **Use plain text** (`<br/>` for line breaks) when the diagram is for general audiences or when math would add visual clutter without improving clarity
- **Default behavior**: If the user's request contains mathematical notation, equations, or Greek symbols, automatically use KaTeX math rendering. Otherwise, use plain text labels.

### Gotchas

- The `$$` delimiters must be **inside quoted strings** — unquoted `$$` will break parsing
- Backslashes in KaTeX (`\frac`, `\sqrt`, etc.) work normally in Mermaid strings
- Very long formulas may overflow node boxes — break them with `\\` (newline in KaTeX) or simplify
- **Always verify rendering** with `mmdc` — some KaTeX expressions may not render in all environments

## Code Quality Rules

Generated Mermaid code MUST:

1. Have correct syntax that renders directly
2. Have clear structure with proper line breaks and indentation
3. Use semantic node naming (not `A`, `B`, `C` — use `authServer`, `userDB`, etc.)
4. Include styling when needed to improve visual appearance
5. Use `<br/>` for line breaks inside node labels — never use `\n`, which renders as literal text
6. Avoid special characters in labels that break Mermaid parsing (wrap in quotes if needed)

## Output Structure

```
figures/
├── <diagram-name>.mmd    # Raw Mermaid source (no markdown fences)
├── <diagram-name>.md     # Markdown with embedded mermaid block
└── <diagram-name>.png    # Rendered PNG (if mmdc available)
```

## Key Rules (MUST FOLLOW)

1. **ALWAYS save files to `figures/` directory** — Never just output code in chat
2. **ALWAYS generate BOTH `.mmd` and `.md` files** — They must contain identical Mermaid code
3. **ALWAYS read the reference documentation** before generating code for a diagram type
4. **ALWAYS verify syntax** — Run mmdc or manually validate before accepting
5. **ALWAYS review the rendered PNG** — Read the image and perform STRICT scoring
6. **NEVER accept score < 9** — Keep refining until excellence
7. **VERIFY EVERY ARROW DIRECTION** — Wrong direction = automatic fail (score ≤ 6)
8. **VERIFY EVERY BLOCK CONTENT** — Wrong content = automatic fail (score ≤ 7)
9. **BE SPECIFIC in feedback** — "Arrow from A to B points wrong" not "arrow is wrong"
10. **FIX errors before accepting** — Do not deliver broken diagrams
11. **Use descriptive file names** — kebab-case derived from the diagram content

---

User requirements: $ARGUMENTS
