---
name: paper-figure
description: "Generate publication-quality figures and tables from experiment results. Use when user says \"画图\", \"作图\", \"generate figures\", \"paper figures\", or needs plots for a paper."
argument-hint: [figure-plan-or-data-path]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, mcp__codex__codex, mcp__codex__codex-reply
---

# Paper Figure: Publication-Quality Plots from Experiment Data

Generate all figures and tables for a paper based on: **$ARGUMENTS**

## Scope: What This Skill Can and Cannot Do

| Category | Can auto-generate? | Examples |
|----------|-------------------|----------|
| **Data-driven plots** | ✅ Yes | Line plots (training curves), bar charts (method comparison), scatter plots, heatmaps, box/violin plots |
| **Comparison tables** | ✅ Yes | LaTeX tables comparing prior bounds, method features, ablation results |
| **Multi-panel figures** | ✅ Yes | Subfigure grids combining multiple plots (e.g., 3×3 dataset × method) |
| **Architecture/pipeline diagrams** | ❌ No — manual | Model architecture, data flow diagrams, system overviews. At best can generate a rough TikZ skeleton, but **expect to draw these yourself** using tools like draw.io, Figma, or TikZ |
| **Generated image grids** | ❌ No — manual | Grids of generated samples (e.g., GAN/diffusion outputs). These come from running your model, not from this skill |
| **Photographs / screenshots** | ❌ No — manual | Real-world images, UI screenshots, qualitative examples |

**In practice:** For a typical ML paper, this skill handles ~60% of figures (all data plots + tables). The remaining ~40% (hero figure, architecture diagram, qualitative results) need to be created manually and placed in `figures/` before running `/paper-write`. The skill will detect these as "existing figures" and preserve them.

## Constants

- **STYLE = `publication`** — Visual style preset. Options: `publication` (default, clean for print), `poster` (larger fonts), `slide` (bold colors)
- **DPI = 300** — Output resolution
- **FORMAT = `pdf`** — Output format. Options: `pdf` (vector, best for LaTeX), `png` (raster fallback)
- **COLOR_PALETTE = `okabe-ito`** — Default color cycle. Options: `okabe-ito` (colorblind gold standard, Nature recommended), `tol-bright` (Paul Tol), `tab10`, `Set2`
- **FONT_SIZE = 10** — Base font size (matches typical conference body text)
- **FIG_DIR = `figures/`** — Output directory for generated figures
- **VENUE = `default`** — Target venue. Options: `nature`, `ieee`, `agu`, `aps`, `neurips`, `icml`, `default`. Auto-adjusts fonts, sizes, panel labels.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for figure quality review.
- **STYLE_GUIDE = `shared-references/FIGURE_STYLE_GUIDE.md`** — Comprehensive reference for figure types, color palettes, and venue specifications.

## Inputs

1. **PAPER_PLAN.md** — figure plan table (from `/paper-plan`)
2. **Experiment data** — JSON files, CSV files, or screen logs in `figures/` or project root
3. **Existing figures** — any manually created figures to preserve

If no PAPER_PLAN.md exists, scan for data files and ask the user which figures to generate.

## Workflow

### Step 1: Read Figure Plan

Parse the Figure Plan table from PAPER_PLAN.md:

```markdown
| ID | Type | Description | Data Source | Priority |
|----|------|-------------|-------------|----------|
| Fig 1 | Architecture | ... | manual | HIGH |
| Fig 2 | Line plot | ... | figures/exp.json | HIGH |
```

Identify:
- Which figures can be auto-generated from data
- Which need manual creation (architecture diagrams, etc.)
- Which are comparison tables (generate as LaTeX)

### Step 2: Set Up Plotting Environment

**Priority: Use SciencePlots if available, otherwise fall back to manual rcParams.**

Create a shared style configuration script:

```python
# paper_plot_style.py — shared across all figure scripts
import matplotlib.pyplot as plt
import matplotlib
import warnings

# ── Venue Presets ──────────────────────────────────────────────────────
# See shared-references/FIGURE_STYLE_GUIDE.md §2 for full specs
VENUE = 'default'  # Set to: 'nature', 'ieee', 'agu', 'aps', 'neurips', 'icml', 'default'

VENUE_CONFIG = {
    'nature':  {'font': 'sans-serif', 'family': ['Helvetica', 'Arial'], 'size': 7,
                'panel_fmt': 'bold_lower', 'col_w': 3.50, 'full_w': 7.20},
    'ieee':    {'font': 'serif', 'family': ['Times New Roman', 'Helvetica'], 'size': 9,
                'panel_fmt': 'paren_lower', 'col_w': 3.46, 'full_w': 7.13},
    'agu':     {'font': 'sans-serif', 'family': ['Helvetica', 'Arial'], 'size': 9,
                'panel_fmt': 'bold_paren_lower', 'col_w': 3.74, 'full_w': 7.48},
    'aps':     {'font': 'serif', 'family': ['Computer Modern', 'Times'], 'size': 9,
                'panel_fmt': 'paren_lower', 'col_w': 3.375, 'full_w': 7.00},
    'neurips': {'font': 'serif', 'family': ['Times New Roman', 'Times'], 'size': 9,
                'panel_fmt': 'paren_lower', 'col_w': 5.50, 'full_w': 5.50},
    'icml':    {'font': 'serif', 'family': ['Times New Roman', 'Times'], 'size': 9,
                'panel_fmt': 'paren_lower', 'col_w': 6.75, 'full_w': 6.75},
    'default': {'font': 'serif', 'family': ['Times New Roman', 'Times', 'DejaVu Serif'], 'size': 10,
                'panel_fmt': 'paren_lower', 'col_w': 5.00, 'full_w': 7.00},
}

cfg = VENUE_CONFIG[VENUE]

# ── Okabe-Ito colorblind-safe palette (Nature recommended) ────────────
OKABE_ITO = ['#E69F00', '#56B4E9', '#009E73', '#F0E442',
             '#0072B2', '#D55E00', '#CC79A7', '#000000']

# ── Try SciencePlots first ────────────────────────────────────────────
try:
    import scienceplots
    style_list = ['science']
    if VENUE == 'ieee':
        style_list.append('ieee')
    elif VENUE == 'nature':
        style_list.append('nature')
    style_list.append('no-latex')  # safe fallback; remove if LaTeX available
    plt.style.use(style_list)
    print(f'SciencePlots loaded: {style_list}')
except ImportError:
    warnings.warn('SciencePlots not installed. Using manual rcParams fallback.')
    matplotlib.rcParams.update({
        'font.size': cfg['size'],
        'font.family': cfg['font'],
        f"font.{cfg['font'].replace('-', '')}": cfg['family'],
        'axes.labelsize': cfg['size'],
        'axes.titlesize': cfg['size'] + 1,
        'xtick.labelsize': cfg['size'] - 2,
        'ytick.labelsize': cfg['size'] - 2,
        'legend.fontsize': cfg['size'] - 2,
        'figure.dpi': 300,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.05,
        'axes.grid': False,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.linewidth': 0.5,
        'lines.linewidth': 1.0,
        'text.usetex': False,
        'mathtext.fontset': 'stix',
    })

# ── Color palette ─────────────────────────────────────────────────────
# Default: Okabe-Ito (colorblind gold standard)
# Override: set COLOR_PALETTE to 'tab10', 'tol-bright', 'Set2'
COLORS = OKABE_ITO
FIG_DIR = 'figures'
FORMAT = 'pdf'

def get_figsize(width='single', aspect=0.7):
    """Get figure size matching venue column width."""
    w = cfg['col_w'] if width == 'single' else cfg['full_w']
    return (w, w * aspect)

def save_fig(fig, name, fmt=FORMAT):
    """Save figure to FIG_DIR with consistent naming."""
    fig.savefig(f'{FIG_DIR}/{name}.{fmt}')
    print(f'Saved: {FIG_DIR}/{name}.{fmt}')
```

### Step 3: Auto-Select Figure Type

**Consult `shared-references/FIGURE_STYLE_GUIDE.md` §1 for the full decision tree.**

First ask: **What is the goal?** Then match the data pattern:

#### Comparison

| Data Pattern | Recommended Type | Width |
|-------------|-----------------|-------|
| Few categories, 1 metric | **Bar chart** | single |
| Few categories, ordered emphasis | **Lollipop chart** | single |
| Before/after paired values | **Dumbbell chart** | single |
| Categories × multiple metrics | **Grouped bar** (≤4 groups) or **radar** | full |
| Two methods, item-by-item | **Scatter** with diagonal line | single |

#### Trend / Time Series

| Data Pattern | Recommended Type | Width |
|-------------|-----------------|-------|
| 1–5 series, continuous x | **Line plot** | single |
| Series with uncertainty (mean ± std) | **Line + shaded band** | single |
| Many series (>5) | **Small multiples** (multi-panel) | full |
| Discrete changes | **Step plot** | single |

#### Distribution

| Data Pattern | Recommended Type | Width |
|-------------|-----------------|-------|
| Single variable | **Histogram** or **KDE density** | single |
| 2–5 groups | **Violin plot** (shows shape) or **box plot** (shows quartiles) | single |
| Many groups (>5) | **Ridgeline / joy plot** | single |
| 2D distribution | **2D histogram / hexbin / contour** | single |
| Cumulative | **ECDF plot** | single |

#### Relationship

| Data Pattern | Recommended Type | Width |
|-------------|-----------------|-------|
| Two continuous variables | **Scatter plot** | single |
| Two continuous + grouping | **Scatter with color AND shape** | single |
| Many variable pairs | **Correlation matrix heatmap** | single |
| Very large n (>10k) | **Hexbin** or **2D density** | single |

#### Composition / Matrix / Table

| Data Pattern | Recommended Type | Width |
|-------------|-----------------|-------|
| Matrix / grid values | **Heatmap** | single |
| Parts of a whole | **Stacked bar** (NEVER pie chart) | single |
| Prior work comparison | **LaTeX table** | full |

#### Spatial / Physics / Geophysical

| Data Pattern | Recommended Type | Width |
|-------------|-----------------|-------|
| Scalar field on 2D grid | **Contour** or **pcolormesh** | single |
| Vector field | **Quiver** or **streamplot** | single |
| Particle trajectories | **Line plot** with color=time | single |
| Spectrogram (freq × time × power) | **pcolormesh** (log color) | full |
| Polar data (MLT-MLAT) | **Polar projection** | single |

#### Multi-Dataset / Combined

| Data Pattern | Recommended Type | Width |
|-------------|-----------------|-------|
| Same plot type across datasets | **Multi-panel (subfigures)** | full |
| Related but different plot types | **Mixed multi-panel** | full |

### Step 4: Generate Each Figure

For each figure in the plan, create a standalone Python script:

**Line plots** (training curves, scaling):
```python
# gen_fig2_training_curves.py
from paper_plot_style import *
import json

with open('figures/exp_results.json') as f:
    data = json.load(f)

fig, ax = plt.subplots(1, 1, figsize=(5, 3.5))
ax.plot(data['steps'], data['fac_loss'], label='Factorized', color=COLORS[0])
ax.plot(data['steps'], data['crf_loss'], label='CRF-LR', color=COLORS[1])
ax.set_xlabel('Training Steps')
ax.set_ylabel('Cross-Entropy Loss')
ax.legend(frameon=False)
save_fig(fig, 'fig2_training_curves')
```

**Bar charts** (comparison, ablation):
```python
fig, ax = plt.subplots(1, 1, figsize=(5, 3))
methods = ['Baseline', 'Method A', 'Method B', 'Ours']
values = [82.3, 85.1, 86.7, 89.2]
bars = ax.bar(methods, values, color=[COLORS[i] for i in range(len(methods))])
ax.set_ylabel('Accuracy (%)')
# Add value labels on bars
for bar, val in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
            f'{val:.1f}', ha='center', va='bottom', fontsize=FONT_SIZE-1)
save_fig(fig, 'fig3_comparison')
```

**Comparison tables** (LaTeX, for theory papers):
```latex
\begin{table}[t]
\centering
\caption{Comparison of estimation error bounds. $n$: sample size, $D$: ambient dim, $d$: latent dim, $K$: subspaces, $n_k$: modes.}
\label{tab:bounds}
\begin{tabular}{lccc}
\toprule
Method & Rate & Depends on $D$? & Multi-modal? \\
\midrule
\citet{MinimaxOkoAS23} & $n^{-s'/D}$ & Yes (curse) & No \\
\citet{ScoreMatchingdistributionrecovery} & $n^{-2/d}$ & No & No \\
\textbf{Ours} & $\sqrt{\sum n_k d_k / n}$ & No & Yes \\
\bottomrule
\end{tabular}
\end{table}
```

**Violin / box plots** (distribution comparison):
```python
fig, ax = plt.subplots(1, 1, figsize=get_figsize('single'))
data = [group1, group2, group3]  # lists of values
parts = ax.violinplot(data, showmeans=True, showmedians=True)
for i, pc in enumerate(parts['bodies']):
    pc.set_facecolor(COLORS[i])
    pc.set_alpha(0.7)
ax.set_xticks([1, 2, 3])
ax.set_xticklabels(['Group A', 'Group B', 'Group C'])
ax.set_ylabel('Value (units)')
save_fig(fig, 'fig4_distributions')
```

**Line + shaded uncertainty band** (mean ± std):
```python
fig, ax = plt.subplots(1, 1, figsize=get_figsize('single'))
ax.plot(x, mean, color=COLORS[0], label='Method')
ax.fill_between(x, mean - std, mean + std, color=COLORS[0], alpha=0.2)
ax.set_xlabel('Steps')
ax.set_ylabel('Loss')
ax.legend(frameon=False)
save_fig(fig, 'fig5_uncertainty')
```

**Heatmap / correlation matrix**:
```python
import seaborn as sns
fig, ax = plt.subplots(1, 1, figsize=get_figsize('single', aspect=1.0))
sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='coolwarm',
            center=0, vmin=-1, vmax=1, ax=ax, square=True,
            cbar_kws={'shrink': 0.8})
save_fig(fig, 'fig6_correlation')
```

**Multi-panel subfigures** (2×2 grid):
```python
fig, axes = plt.subplots(2, 2, figsize=get_figsize('full', aspect=0.8))
panel_labels = ['(a)', '(b)', '(c)', '(d)']
for ax, label in zip(axes.flat, panel_labels):
    ax.text(0.02, 0.95, label, transform=ax.transAxes,
            fontweight='bold', va='top')
    # ... plot data on each ax ...
fig.tight_layout()
save_fig(fig, 'fig7_multipanel')
```

**Contour / pcolormesh** (2D scalar field):
```python
fig, ax = plt.subplots(1, 1, figsize=get_figsize('single', aspect=1.0))
im = ax.pcolormesh(X, Y, Z, cmap='viridis', shading='auto')
fig.colorbar(im, ax=ax, label='Quantity (units)')
ax.set_xlabel('X (units)')
ax.set_ylabel('Y (units)')
save_fig(fig, 'fig8_field')
```

**Architecture/pipeline diagrams** (MANUAL — outside this skill's scope):
- These require manual creation using draw.io, Figma, Keynote, or TikZ
- This skill can generate a rough TikZ skeleton as a starting point, but **do not expect publication-quality results**
- If the figure already exists in `figures/`, preserve it and generate only the LaTeX `\includegraphics` snippet
- Flag as `[MANUAL]` in the figure plan and `latex_includes.tex`

### Step 5: Run All Scripts

```bash
# Run all figure generation scripts
for script in gen_fig*.py; do
    python "$script"
done
```

Verify all output files exist and are non-empty.

### Step 6: Generate LaTeX Include Snippets

For each figure, output the LaTeX code to include it:

```latex
% === Fig 2: Training Curves ===
\begin{figure}[t]
    \centering
    \includegraphics[width=0.48\textwidth]{figures/fig2_training_curves.pdf}
    \caption{Training curves comparing factorized and CRF-LR denoising.}
    \label{fig:training_curves}
\end{figure}
```

Save all snippets to `figures/latex_includes.tex` for easy copy-paste into the paper.

### Step 7: Figure Quality Review with REVIEWER_MODEL

Send figure descriptions and captions to GPT-5.4 for review:

```
mcp__codex__codex:
  model: gpt-5.4
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    Review these figure/table plans for a [VENUE] submission.

    For each figure:
    1. Is the caption informative and self-contained?
    2. Does the figure type match the data being shown?
    3. Is the comparison fair and clear?
    4. Any missing baselines or ablations?
    5. Would a different visualization be more effective?

    [list all figures with captions and descriptions]
```

### Step 8: Quality Checklist

Before finishing, verify each figure. See `shared-references/FIGURE_STYLE_GUIDE.md` §6 for common pitfalls and §8 for full checklist.

**Critical (must pass):**

- [ ] **Figure size** set to venue column width in inches (`get_figsize()`) — NOT arbitrary pixels
- [ ] **Font size** readable at printed size (≥6pt after scaling to column width)
- [ ] **No title inside figures** — titles go only in LaTeX `\caption{}` (from pedrohcgs)
- [ ] **Vector format** — saved as PDF or EPS (not JPEG for data plots)
- [ ] **Axis labels** have units (e.g., "Energy (keV)" not "Energy")
- [ ] **Axis labels** are human-readable (not variable names like `emp_rate`)
- [ ] **Error bars / uncertainty** shown where applicable (std, CI, or min-max)
- [ ] **Caption is self-contained** — defines all symbols, explains what to look for

**Style (should pass):**

- [ ] **Colorblind-safe** — using Okabe-Ito or viridis; NO red-green only distinction
- [ ] **Grayscale readable** — distinguishable when printed in B&W
- [ ] **Color + shape/linestyle** — data series distinguished by ≥2 visual channels
- [ ] **No chartjunk** — no 3D effects, no background images, no decorative gridlines, no drop shadows
- [ ] **Consistent style** across all figures (same fonts, colors, linewidths via paper_plot_style.py)
- [ ] **Legend** does not overlap data; use `bbox_to_anchor` if needed
- [ ] **Spines** — top and right spines removed (unless venue convention requires them)
- [ ] **One message per figure** — not overcrowded with information
- [ ] **No pie charts** — use bar chart instead (humans judge angles poorly)
- [ ] **No jet/rainbow colormap** — use viridis, plasma, or cividis for continuous data

**Panel labels (if multi-panel):**

- [ ] Labels match venue format (Nature: bold `a`; IEEE: `(a)`; AGU: bold `(a)`)
- [ ] Labels positioned consistently (top-left of each panel)
- [ ] Shared axes labeled only once (not repeated per panel)

## Output

```
figures/
├── paper_plot_style.py          # shared style config
├── gen_fig1_architecture.py     # per-figure scripts
├── gen_fig2_training_curves.py
├── gen_fig3_comparison.py
├── fig1_architecture.pdf        # generated figures
├── fig2_training_curves.pdf
├── fig3_comparison.pdf
├── latex_includes.tex           # LaTeX snippets for all figures
└── TABLE_*.tex                  # standalone table LaTeX files
```

## Key Rules

- **Every figure must be reproducible** — save the generation script alongside the output
- **Do NOT hardcode data** — always read from JSON/CSV files
- **Use vector format (PDF)** for all plots — PNG only as fallback
- **No decorative elements** — no background colors, no 3D effects, no chart junk
- **Consistent style across all figures** — same fonts, colors, line widths via paper_plot_style.py
- **Colorblind-safe by default** — Okabe-Ito for categorical, viridis for continuous; NEVER use jet/rainbow
- **Color is not enough** — always pair color with shape, linestyle, or annotation
- **One script per figure** — easy to re-run individual figures when data changes
- **No titles inside figures** — captions are in LaTeX only
- **No pie charts** — use bar charts instead
- **Preset figure size** — use `get_figsize()` matching venue column width; never guess
- **Comparison tables count as figures** — generate them as standalone .tex files

## Figure Type Reference

See `shared-references/FIGURE_STYLE_GUIDE.md` §1 for the full decision tree.

| Type | When to Use | Width |
|------|------------|-------|
| Line plot | Training curves, scaling trends, time series | single |
| Line + band | Trends with uncertainty (mean ± std/CI) | single |
| Bar chart | Method comparison, ablation (1 metric) | single |
| Grouped bar | Multi-metric comparison (≤4 groups) | full |
| Lollipop | Ordered comparison (many categories) | single |
| Dumbbell | Before/after paired comparison | single |
| Scatter plot | Correlation, relationship between 2 variables | single |
| Hexbin / 2D density | Scatter with large n (>10k points) | single |
| Heatmap | Correlation matrix, attention, confusion matrix | single |
| Violin plot | Distribution comparison (shows shape) | single |
| Box plot | Distribution comparison (shows quartiles) | single |
| Ridgeline | Many distributions (>5 groups) | single |
| ECDF | Cumulative distribution comparison | single |
| Contour / pcolormesh | 2D scalar field, spectrogram | single/full |
| Quiver / streamplot | Vector field visualization | single |
| Step plot | Discrete state changes | single |
| Multi-panel | Combined results (subfigures) | full |
| Comparison table | Prior bounds vs. ours (theory) | full |

## Common Pitfalls

See `shared-references/FIGURE_STYLE_GUIDE.md` §6 for the full list. Top offenders:

1. **Using jet/rainbow colormap** — creates phantom features; use viridis
2. **Pie charts** — humans judge angles poorly; use bar charts
3. **Font too small after scaling** — set figsize to actual column width
4. **Relying only on color** — ~8% of males are colorblind; add shapes/linestyles
5. **Saving as JPEG** — lossy compression ruins text; use PDF
6. **No error bars** — results look falsely precise
7. **3D bar charts** — distort comparisons; use 2D
8. **Overcrowded figures** — one message per figure; split if needed
9. **Default matplotlib styling** — always apply venue preset
10. **Incomplete captions** — caption should be self-contained

## Acknowledgements

Design pattern (type × style matrix) inspired by [baoyu-skills](https://github.com/jimliu/baoyu-skills). Publication style defaults and figure rules from [pedrohcgs/claude-code-my-workflow](https://github.com/pedrohcgs/claude-code-my-workflow). Visualization decision tree from [Imbad0202/academic-research-skills](https://github.com/Imbad0202/academic-research-skills) and [From Data to Viz](https://www.data-to-viz.com/). SciencePlots integration from [garrettj403/SciencePlots](https://github.com/garrettj403/SciencePlots). Ten rules from Rougier et al. (2014), PLOS Comp Bio. Color guidance from Crameri et al. (2020), Nature Comms. Venue specs from Nature, IEEE, AGU, and APS author guidelines.
