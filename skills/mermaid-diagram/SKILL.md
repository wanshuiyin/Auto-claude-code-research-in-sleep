---
name: mermaid-diagram
description: "Generate Mermaid diagrams from user requirements. Supports flowcharts, sequence diagrams, class diagrams, ER diagrams, Gantt charts, and 18 more diagram types."
argument-hint: "[diagram description or requirements]"
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep
---

# Mermaid Diagram Generator

Generate high-quality Mermaid diagram code based on user requirements, with file output and verification.

## Constants

- **OUTPUT_DIR = `figures/`** — Output directory for all generated files

## Workflow: MUST EXECUTE ALL STEPS

### Step 0: Pre-flight Check

```bash
# Create output directory
mkdir -p figures
```

### Step 1: Understand Requirements & Select Diagram Type

Parse the input: **$ARGUMENTS**

1. Analyze user description to determine the most suitable diagram type
2. Read the corresponding syntax reference documentation (see Step 2 below)
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
    mmdc -i figures/<diagram-name>.mmd -o figures/<diagram-name>.png -b transparent \
        && echo "✅ Syntax valid — PNG rendered to figures/<diagram-name>.png"
else
    # Try npx as fallback
    npx -y @mermaid-js/mermaid-cli@latest -i figures/<diagram-name>.mmd -o figures/<diagram-name>.png -b transparent \
        && echo "✅ Syntax valid — PNG rendered to figures/<diagram-name>.png"
fi
```

**If the verification fails:**
1. Read the error message carefully
2. Fix the syntax issue in both `.mmd` and `.md` files
3. Re-run verification
4. Continue only while a concrete error remains and the next correction addresses it; respect any user-set round or budget limit.

### Step 5: Review the Rendered Diagram (MANDATORY)

After successful rendering, Claude MUST inspect the generated PNG against the request. Check that required components and labels are present, each arrow has the intended source, target, and direction, and the layout, text, and data flow are readable at the intended viewing size. Confirm that `.mmd` contains raw Mermaid and `.md` wraps the same code in a Mermaid fence.

Fix concrete semantic or readability problems in both source files, then re-render and inspect the affected areas. Stop when the diagram meets the request and no material issue remains; do not repeat review for a numerical score or cosmetic preference. Respect any user-set round or budget limit. If rendering is unavailable or a material issue remains at that limit, report it clearly instead of claiming verification succeeded.

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

1. Save `.mmd` and `.md` files to `figures/` with descriptive kebab-case names and identical Mermaid code.
2. Read the relevant syntax guidance, render with `mmdc`, and inspect the generated PNG before claiming verification.
3. Verify components, block contents, labels, and every arrow's direction against the request.
4. Fix concrete errors and report any unresolved issue or unavailable verification clearly.

---

User requirements: $ARGUMENTS
