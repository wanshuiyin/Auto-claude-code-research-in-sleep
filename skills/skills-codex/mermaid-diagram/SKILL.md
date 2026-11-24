---
name: "mermaid-diagram"
description: "Generate Mermaid diagrams from user requirements. Save .mmd and .md files to figures/ with syntax verification. Supports flowcharts, sequence diagrams, class diagrams, ER diagrams, Gantt charts, and many more diagram types."
---

# Mermaid Diagram Generator

Generate high-quality Mermaid diagram code based on user requirements, with file output and verification.

## Constants

- **OUTPUT_DIR = `figures/`** — Output directory for generated files

## Workflow: MUST EXECUTE ALL STEPS

### Step 0: Pre-flight Check

# Create output directory

```bash
mkdir -p figures
```

### Step 1: Understand Requirements & Select Diagram Type

Parse the input: **$ARGUMENTS**

1. Analyze the request and choose the most suitable diagram type
2. Read the corresponding Mermaid syntax reference below
3. If the diagram involves mathematical notation, apply the math syntax rules from the **Math Formulas in Diagrams** section
4. Identify all components, connections, and data flow
5. Plan the diagram structure before writing code

### Step 2: Read Documentation

Select the appropriate diagram type. Use built-in Mermaid knowledge first; if external documentation is needed and your environment provides it, fetch the up-to-date syntax reference.

### Configuration & Themes

Choose theme, colors, and layout before writing code. For academic diagrams, prefer clean white backgrounds, restrained colors, and readable labels over decorative styling.

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
| C4 Diagram | System architecture |
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

### Step 3: Generate Mermaid Code & Save Files

Generate the Mermaid code and save **two** files:

#### File 1: `figures/<diagram-name>.mmd` — Raw Mermaid source

The `.mmd` file contains only raw Mermaid code, no markdown fences.

#### File 2: `figures/<diagram-name>.md` — Markdown with embedded Mermaid

The `.md` file wraps the same Mermaid code in a mermaid code block for preview rendering, plus a short title and description.

# Diagram Title

Use a concise title in the `.md` wrapper that matches the generated diagram name.

**Naming convention**: use a descriptive kebab-case name derived from the request, such as `auth-flow`, `system-architecture`, or `database-er`.

### Step 4: Verify Mermaid Syntax (MANDATORY)

Codex MUST verify the generated Mermaid code by running the Mermaid CLI (`mmdc`).

# Check if mermaid-cli is available

```bash
if command -v mmdc >/dev/null 2>&1; then
    mmdc -i figures/<diagram-name>.mmd -o figures/<diagram-name>.png -b transparent \
        && echo "Syntax valid — PNG rendered to figures/<diagram-name>.png"
else
    npx -y @mermaid-js/mermaid-cli@latest -i figures/<diagram-name>.mmd -o figures/<diagram-name>.png -b transparent \
        && echo "Syntax valid — PNG rendered to figures/<diagram-name>.png"
fi
```

If verification fails:

1. Read the error carefully
2. Fix the syntax issue in both `.mmd` and `.md`
3. Re-run verification
4. Continue only while a concrete error remains and the next correction addresses it; respect any user-set round or budget limit.

### Step 5: Review the Rendered Diagram (MANDATORY)

After successful rendering, Codex MUST inspect the generated PNG against the request. Check that required components and labels are present, each arrow has the intended source, target, and direction, and the layout, text, and data flow are readable at the intended viewing size. Confirm that `.mmd` contains raw Mermaid and `.md` wraps the same code in a Mermaid fence.

Fix concrete semantic or readability problems in both source files, then re-render and inspect the affected areas. Stop when the diagram meets the request and no material issue remains; do not repeat review for a numerical score or cosmetic preference. Respect any user-set round or budget limit. If rendering is unavailable or a material issue remains at that limit, report it clearly instead of claiming verification succeeded.

### Step 6: Final Output Summary

When accepted, present:

```text
Mermaid diagram generated successfully.

Files:
  figures/<diagram-name>.mmd
  figures/<diagram-name>.md
  figures/<diagram-name>.png

To re-render manually:
  mmdc -i figures/<diagram-name>.mmd -o figures/<diagram-name>.png
```

## Architecture Diagram Best Practices

When generating `architecture-beta` diagrams, apply these layout techniques for complex diagrams:

### Use Junctions for Layout Control

Think of the diagram as an invisible grid. Use `junction` nodes as virtual anchor points on that grid to precisely control placement. This is especially useful when a direct edge produces unexpected positioning.

Instead of connecting services directly:

```text
lb:R --> L:scim
lb:R --> L:webapi
```

Route through junctions:

```text
junction j_lb_r
lb:R -- L:j_lb_r
junction j_scim_l
j_lb_r:T -- B:j_scim_l
j_scim_l:R --> L:scim
junction j_webapi_l
j_lb_r:B -- T:j_webapi_l
j_webapi_l:R --> L:webapi
```

### Use Edges out of Groups for Floating Components

For services that have no real logical connection but still need stable placement, use a junction combined with `{group}` to anchor them without inventing a semantic edge.

## CVPR/ICLR/NeurIPS Style Guide (for Academic Diagrams)

When the diagram is intended for academic papers, apply these style standards:

### Visual Standards

- Clean white background
- Sans-serif fonts
- Subtle coordinated color palette
- Print-friendly grayscale readability
- Thin professional borders

### Layout Standards

- Horizontal flow for pipelines
- Clear grouping
- Consistent sizing
- Balanced whitespace

### Arrow Standards (MOST CRITICAL)

- Thick strokes
- Clear arrowheads
- Dark colors
- Labeled arrows
- No crossings
- Correct direction

### Color Palette (Academic Professional)

- **Inputs**: Green (`#10B981` / `#34D399`)
- **Encoders**: Blue (`#2563EB` / `#3B82F6`)
- **Fusion**: Purple (`#7C3AED` / `#8B5CF6`)
- **Outputs**: Orange (`#EA580C` / `#F97316`)
- **Arrows**: Dark gray (`#333333` / `#1F2937`)
- **Background**: White (`#FFFFFF`)

### What to AVOID

- Rainbow color schemes
- Thin hairline arrows
- Heavy shadows or glow effects
- 3D effects
- Decorative icons that add no meaning
- Tiny unreadable text

## Math Formulas in Diagrams (KaTeX)

Mermaid supports rendering mathematical expressions via KaTeX. When the diagram content involves formulas, equations, Greek letters, subscripts, superscripts, fractions, or matrices, use KaTeX notation instead of plain-text approximations.

### Supported Diagram Types for Math

Math rendering with `$$...$$` is supported in:

- **Flowcharts** — in node labels and edge labels
- **Sequence Diagrams** — in participant aliases, messages, and notes

### Syntax Rules

1. Wrap math expressions in `$$` inside quoted strings:

   ```text
   A["$$x^2$$"] -->|"$$\\sqrt{x+3}$$"| B("$$\\frac{1}{2}$$")
   ```

2. Node labels with math must be quoted
3. Mix text and math by placing `$$` only around the math portion
4. Use `\text{}` for non-math text inside `$$`

### Common Math Patterns for ML/Science Diagrams

| Concept | KaTeX Syntax |
| ------- | ------------ |
| Subscript | `$$W_Q$$` |
| Superscript | `$$x^2$$` |
| Fraction | `$$\\frac{QK^T}{\\sqrt{d_k}}$$` |
| Greek letters | `$$\\alpha, \\beta, \\gamma$$` |
| Square root | `$$\\sqrt{d_k}$$` |
| Summation | `$$\\sum_{i=1}^{n} x_i$$` |
| Matrix | `$$\\begin{bmatrix} a & b \\\\ c & d \\end{bmatrix}$$` |
| Softmax | `$$\\text{softmax}(z_i)$$` |
| Norm | `$$\\|\\|x\\|\\|_2$$` |
| Hat/tilde | `$$\\hat{y}, \\tilde{x}$$` |

### Example: Attention Mechanism with Math

```text
flowchart TD
    Q["$$Q \\in \\mathbb{R}^{n \\times d_k}$$"]
    K["$$K \\in \\mathbb{R}^{n \\times d_k}$$"]
    V["$$V \\in \\mathbb{R}^{n \\times d_v}$$"]
    scores["$$\\frac{QK^T}{\\sqrt{d_k}}$$"]
    softmax["$$\\text{softmax}(\\cdot)$$"]
    output["$$\\text{Attention}(Q,K,V)$$"]

    Q --> scores
    K --> scores
    scores --> softmax
    softmax --> weighted["$$\\alpha V$$"]
    V --> weighted
    weighted --> output
```

### When to Use Math vs Plain Text

- Use math when the diagram is for academic or technical audiences and precision matters
- Use plain text when the diagram is for general audiences or math would add clutter
- Default to KaTeX automatically if the request already contains math notation

### Gotchas

- `$$` delimiters must be inside quoted strings
- Very long formulas may overflow node boxes
- Always verify rendering with `mmdc`

## Code Quality Rules

Generated Mermaid code MUST:

1. Have correct syntax that renders directly
2. Have clear structure with proper indentation
3. Use semantic node naming, not `A`, `B`, `C`
4. Include styling when needed
5. Use `<br/>` for line breaks inside node labels, never `\n`
6. Avoid special characters that break Mermaid parsing unless properly quoted

## Output Structure

```text
figures/
├── <diagram-name>.mmd
├── <diagram-name>.md
└── <diagram-name>.png
```

## Key Rules (MUST FOLLOW)

1. Save `.mmd` and `.md` files to `figures/` with descriptive kebab-case names and identical Mermaid code.
2. Read the relevant syntax guidance, render with `mmdc`, and inspect the generated PNG before claiming verification.
3. Verify components, block contents, labels, and every arrow's direction against the request.
4. Fix concrete errors and report any unresolved issue or unavailable verification clearly.

---

User requirements: $ARGUMENTS
