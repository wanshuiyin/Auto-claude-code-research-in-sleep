# Academic Figure Style Guide

Shared reference for all figure-generating skills (`paper-figure`, `analyze-results`, `paper-illustration`).
Skills should import or consult this guide when making visualization decisions.

---

## 1. Figure Type Decision Tree

### Level 1: What Is Your Goal?

```
What do you want to show?
├── Comparison        → §1A
├── Trend / Change    → §1B
├── Distribution      → §1C
├── Relationship      → §1D
├── Composition       → §1E
├── Spatial / Geo     → §1F
├── Flow / Network    → §1G
└── Hierarchy         → §1H
```

### §1A — Comparison

| Data Shape | Recommended Figure | Notes |
|------------|-------------------|-------|
| Few categories, 1 metric | **Bar chart** (vertical) | ≤12 categories; horizontal if labels are long |
| Few categories, 1 metric, with ordering emphasis | **Lollipop chart** | Cleaner than bar for many categories |
| Few categories, paired values (before/after) | **Dumbbell chart** | Shows change between two states |
| Many categories, 1 metric | **Dot plot** or **horizontal bar** | Easier to read than vertical bars |
| Categories × multiple metrics | **Grouped bar** | ≤4 groups; use **radar/spider** if >4 metrics with similar scales |
| Categories × multiple metrics (ranked) | **Bump chart** | Show ranking changes across conditions |
| Two methods, item-by-item | **Scatter plot** (x=method1, y=method2) with diagonal | Points above/below diagonal show which is better |

### §1B — Trend / Change Over Time

| Data Shape | Recommended Figure | Notes |
|------------|-------------------|-------|
| 1–5 series, continuous x | **Line plot** | The workhorse; use markers if <20 points |
| 1–5 series with uncertainty | **Line + shaded band** (mean ± std/CI) | Use `fill_between` |
| Many series (>5) | **Multi-panel (small multiples)** | One subplot per series; shared axes |
| Stacked contributions over time | **Stacked area** | Only if parts sum to meaningful total |
| Single metric, few time points | **Bar chart** with time on x-axis | Not line — line implies continuous interpolation |
| Step function / discrete changes | **Step plot** (`plt.step`) | For discrete state changes |

### §1C — Distribution

| Data Shape | Recommended Figure | Notes |
|------------|-------------------|-------|
| Single variable | **Histogram** or **KDE density** | Histogram for discrete-ish; KDE for smooth |
| 2–5 groups, compare distributions | **Violin plot** | Shows shape; better than box for multimodal |
| 2–5 groups, compare medians/quartiles | **Box plot** | Classic; add swarm overlay if n < 50 |
| Many groups (>5) | **Ridgeline / joy plot** | Stacked densities; compact |
| 2D distribution | **2D histogram** or **KDE contour** | Use `hexbin` for large n |
| Cumulative distribution | **CDF / ECDF plot** | Good for comparing tails |

### §1D — Relationship

| Data Shape | Recommended Figure | Notes |
|------------|-------------------|-------|
| Two continuous variables | **Scatter plot** | Add regression line if testing correlation |
| Two continuous + grouping variable | **Scatter with color/shape** | ≤5 groups; use both color AND marker shape |
| Two continuous + third continuous | **Scatter + colorbar** or **bubble** | Bubble size = third variable |
| Many pairs of variables | **Correlation matrix heatmap** | Use `sns.heatmap` with annotation |
| Two continuous, very large n | **Hexbin** or **2D density contour** | Scatter becomes unreadable at >10k points |
| Correlation between ranked items | **Parallel coordinates** | Show how items rank across dimensions |

### §1E — Composition / Part-to-Whole

| Data Shape | Recommended Figure | Notes |
|------------|-------------------|-------|
| Parts of a whole (single) | **Stacked bar** (single bar, horizontal) | **AVOID pie chart** — bar is always better |
| Parts of a whole over time | **Stacked area** or **stacked bar** | Area if continuous; bar if discrete time |
| Nested categories | **Treemap** | Good for file sizes, budget breakdown |
| Two-level hierarchy | **Sunburst** | Interactive; less common in papers |

### §1F — Spatial / Geophysical (Physics/Space Science)

| Data Shape | Recommended Figure | Notes |
|------------|-------------------|-------|
| Scalar field on 2D grid | **Contour plot** or **pcolormesh** | Use diverging colormap for signed quantities |
| Vector field on 2D grid | **Quiver plot** or **streamplot** | Streamplot for flow visualization |
| Particle trajectories | **Line plot in 2D/3D** with color=time | Color gradient shows temporal evolution |
| Spectrogram (freq vs time vs power) | **pcolormesh** with log color scale | Common in space physics |
| Keogram (lat vs time vs intensity) | **pcolormesh** | For auroral / ionospheric data |
| Polar data (MLT-MLAT) | **Polar plot** (`projection='polar'`) | For magnetospheric / ionospheric maps |
| Sky map / Hammer projection | **Mollweide** projection | For all-sky or heliospheric data |
| Profile (altitude/radial) | **Line plot** (horizontal orientation) | x=quantity, y=altitude; multiple profiles overlaid |

### §1G — Flow / Network

| Data Shape | Recommended Figure | Notes |
|------------|-------------------|-------|
| Flow between categories | **Sankey diagram** | Use `plotly` or `matplotlib-sankey` |
| Network/graph | **Node-link diagram** | Use `networkx` |
| Transition probabilities | **Chord diagram** or **alluvial** | Shows flow between states |

### §1H — Hierarchy / Structure

| Data Shape | Recommended Figure | Notes |
|------------|-------------------|-------|
| Tree structure | **Dendrogram** | For clustering results |
| Nested categories with size | **Treemap** | Area = size |
| Taxonomy | **Indented tree** or **sunburst** | For classification schemes |

### Quick-Reference: From Data to Viz Summary

Source: [data-to-viz.com](https://www.data-to-viz.com/) (Yan Holtz & Conor Healy)

```
Data Type                    → Primary Choice
────────────────────────────────────────────────
One Numeric                  → Histogram / Density
Two Numeric                  → Scatter / Hexbin
One Numeric + One Categoric  → Violin / Boxplot / Bar
Multiple Numeric             → Correlation heatmap / PCA scatter
One Categoric                → Bar / Lollipop
Time Series                  → Line / Area
Geospatial                   → Choropleth / Bubble map
Network                      → Node-link / Sankey
```

---

## 2. Venue Presets (Journal/Conference Style Specifications)

### Nature

| Property | Value |
|----------|-------|
| Font | Helvetica or Arial (sans-serif) |
| Body text | 5–7pt |
| Panel labels | 8pt bold lowercase (a, b, c) |
| Max resolution | 300 ppi |
| Format | JPEG (preferred), TIFF, EPS |
| Color mode | RGB |
| Single column | 89 mm (3.5 in) |
| Double column | 183 mm (7.2 in) |
| Max height | 247 mm (9.7 in) |
| Color | Must be colorblind-friendly |

### IEEE (Transactions / Conference)

| Property | Value |
|----------|-------|
| Font | Helvetica, Times New Roman, or Arial, 9–10pt |
| Figure label | `Fig. 1.` + sentence-case description |
| Line width | ≥ 0.5pt |
| Format | PDF, EPS, PNG, TIFF |
| Single column | 88 mm (3.46 in) |
| Double column | 181 mm (7.13 in) |
| Requirement | Use color AND shape/linestyle to distinguish data |

### AGU (JGR, GRL, Space Weather)

| Property | Value |
|----------|-------|
| Font | Helvetica or Arial, 8–12pt |
| Panel labels | lowercase bold (a), (b), (c) in top-left |
| Format | TIFF (preferred), EPS, PDF |
| Resolution | 300 dpi (halftone), 600 dpi (line art) |
| Single column | 95 mm |
| Full width | 190 mm |
| Color | Colorblind-friendly required |

### APS (Physical Review Letters, PRE, etc.)

| Property | Value |
|----------|-------|
| Font | Computer Modern / Times, 8–10pt |
| Panel labels | (a), (b), (c) — inside or outside panel |
| Format | EPS, PDF (vector preferred) |
| Single column | 86 mm (3.375 in) |
| Double column | 178 mm (7 in) |

### Generic ML Conference (NeurIPS, ICML, ICLR, CVPR)

| Property | Value |
|----------|-------|
| Font | Typically serif (Times); some allow sans-serif |
| Body text | 9–10pt |
| Panel labels | (a), (b), (c) or bold lowercase |
| Format | PDF (vector) |
| Single column | ~5.5 in (varies by template) |
| Full width | varies by template |
| Color | Colorblind-friendly strongly recommended |

---

## 3. Color Palette Guide

### Categorical Data (Discrete Groups)

| Palette | Source | N colors | Colorblind-safe? | Notes |
|---------|--------|----------|-------------------|-------|
| **Okabe-Ito** | Okabe & Ito (2008) | 8 | Yes (gold standard) | Nature recommended; DEFAULT CHOICE |
| **Tol Bright** | Paul Tol | 7 | Yes | SciencePlots `bright` cycle |
| **tab10** | matplotlib | 10 | Partial | Decent but not fully colorblind-safe |
| **Set2** | ColorBrewer | 8 | Partial | Pastel; good for fills |

**Okabe-Ito colors** (hex):
```
#E69F00  orange
#56B4E9  sky blue
#009E73  bluish green
#F0E442  yellow
#0072B2  blue
#D55E00  vermillion
#CC79A7  reddish purple
#000000  black
```

### Sequential Data (Continuous)

| Colormap | Use | Colorblind-safe? |
|----------|-----|-------------------|
| **viridis** | Default for continuous data | Yes |
| **plasma** | Alternative to viridis | Yes |
| **inferno** | High contrast; dark backgrounds | Yes |
| **cividis** | Specifically designed for CVD | Yes (optimized) |

### Diverging Data (Positive/Negative)

| Colormap | Use | Notes |
|----------|-----|-------|
| **coolwarm** | Centered at zero | Perceptually balanced |
| **RdBu** (reversed) | Temperature anomalies, correlations | Classic choice |
| **PiYG** | Alternative diverging | Colorblind-friendly |

### FORBIDDEN Colormaps

| Colormap | Why | Alternative |
|----------|-----|------------|
| **jet** | Perceptually non-uniform; creates fake features; fails in grayscale | viridis |
| **rainbow** | Same problems as jet | plasma or inferno |
| **hsv** | Circular; misleading for linear data | cividis |

### Color Rules

1. **Never rely on color alone** — always pair with shape, linestyle, or annotation
2. **Test in grayscale** — `plt.savefig('test.pdf', dpi=72); # then convert to grayscale and check`
3. **Limit to 3–5 colors** for categorical comparisons (more = confusion)
4. **Use ColorBrewer** ([colorbrewer2.org](https://colorbrewer2.org)) for custom palettes
5. **Check accessibility** — [davidmathlogic.com/colorblind](https://davidmathlogic.com/colorblind/)

---

## 4. SciencePlots Integration

[SciencePlots](https://github.com/garrettj403/SciencePlots) (8.7k stars) provides ready-made matplotlib styles.

### Installation

```bash
pip install SciencePlots
# Requires LaTeX for 'science' style; use 'no-latex' fallback if unavailable
```

### Usage

```python
import scienceplots

# Journal-specific styles
plt.style.use(['science', 'ieee'])      # IEEE Transactions
plt.style.use(['science', 'nature'])    # Nature
plt.style.use(['science', 'no-latex'])  # No LaTeX required

# Color cycles
plt.style.use(['science', 'bright'])    # Colorblind-safe (Tol Bright)
plt.style.use(['science', 'high-vis'])  # High visibility

# CJK support
plt.style.use(['science', 'cjk-sc-font'])  # Simplified Chinese
```

### Available Styles

| Style | Description |
|-------|------------|
| `science` | Base academic style (Times, serif) |
| `ieee` | IEEE Transactions format |
| `nature` | Nature journal format |
| `notebook` | Jupyter notebook friendly |
| `no-latex` | Fallback when LaTeX unavailable |
| `bright` | Tol Bright colorblind-safe cycle |
| `high-vis` | High visibility colors |
| `scatter` | Optimized for scatter plots |
| `grid` | With grid lines |

### Fallback (No SciencePlots)

If SciencePlots is not installed, use these rcParams:

```python
import matplotlib.pyplot as plt
plt.rcParams.update({
    'font.size': 9,
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
    'axes.labelsize': 9,
    'axes.titlesize': 10,
    'xtick.labelsize': 7,
    'ytick.labelsize': 7,
    'legend.fontsize': 7,
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
```

---

## 5. Ten Rules for Better Figures

Condensed from Rougier et al. (2014), "Ten Simple Rules for Better Figures," PLOS Computational Biology.

1. **Know your audience** — Tailor complexity and notation to readers (reviewers vs. general public)
2. **Identify the message** — Each figure should convey ONE key finding; if it tells two stories, split it
3. **Adapt to the medium** — Print (high DPI, grayscale-safe) vs. screen (interactive, color) vs. poster (large fonts)
4. **Captions are not optional** — Caption must be self-contained: reader should understand the figure without reading the main text
5. **Do not trust the defaults** — matplotlib/seaborn defaults are for exploration, not publication; always customize
6. **Use color effectively** — Color should encode data, not decorate; use colorblind-safe palettes
7. **Do not mislead** — Start y-axis at zero for bar charts; don't truncate axes to exaggerate differences; show error bars
8. **Avoid chartjunk** — No 3D effects, no background images, no decorative gridlines, no drop shadows
9. **Message trumps beauty** — Clarity > aesthetics; a plain but clear figure beats a pretty but confusing one
10. **Get the right tool** — matplotlib for static plots; plotly for interactive; TikZ for diagrams; choose wisely

---

## 6. Common Pitfalls Checklist

Sources: ACS Energy Letters (2021), Rougier et al. (2014), PMC reviews.

| # | Pitfall | Why It's Bad | Fix |
|---|---------|-------------|-----|
| 1 | Using **3D effects** | Distorts data perception, adds visual noise | Use 2D always |
| 2 | Using **pie charts** | Humans judge angles poorly; hard to compare | Use bar chart |
| 3 | **Default styling** unchanged | Looks unprofessional; font sizes too large for print | Apply journal preset |
| 4 | **Font too small** after scaling | Text unreadable when figure shrunk to column width | Set figsize to ACTUAL column width; check at 100% zoom |
| 5 | **Not presetting figure size** | Fonts/linewidths rescale unpredictably | Set `figsize` in inches matching journal column width |
| 6 | **Relying only on color** | Colorblind readers (~8% of males) lose information | Add markers, linestyles, annotations |
| 7 | **Using jet/rainbow colormap** | Perceptually non-uniform; creates phantom features | Use viridis, plasma, or cividis |
| 8 | **Saving as JPEG/raster** | Text becomes blurry; artifacts at edges | Save as PDF (vector) or PNG at 300+ dpi |
| 9 | **One figure, too many messages** | Reader can't extract the key finding | Split into multiple figures or panels |
| 10 | **Incomplete caption** | Reader can't understand figure independently | Caption should define all symbols, abbreviations, and explain what to look for |
| 11 | **Title inside the figure** | Wastes space; conflicts with LaTeX caption | Remove `plt.title()`; use LaTeX `\caption{}` only |
| 12 | **Legend overlapping data** | Obscures actual results | Move legend outside or use `bbox_to_anchor` |
| 13 | **Inconsistent style** across figures | Paper looks sloppy | Use shared style config (paper_plot_style.py) |
| 14 | **No error bars / uncertainty** | Results look more precise than they are | Always show std, CI, or min-max when applicable |
| 15 | **Overcrowded multi-panel** | Too many subplots with tiny text | Limit to 4–6 panels; use supplementary for extras |

---

## 7. Figure Size Quick Reference

### Preset Figure Sizes (inches)

```python
# Journal column widths in inches
FIGURE_SIZES = {
    # (single_col, double_col, max_height)
    'nature':   (3.50, 7.20, 9.72),
    'ieee':     (3.46, 7.13, 9.19),
    'agu':      (3.74, 7.48, 9.21),
    'aps':      (3.375, 7.00, 9.50),
    'neurips':  (5.50, 5.50, 9.00),   # single column only
    'icml':     (6.75, 6.75, 9.00),   # single column only
    'default':  (5.00, 7.00, 9.00),
}

def get_figsize(venue='default', width='single', aspect=0.7):
    """Get figure size for a given venue and width."""
    w_single, w_double, h_max = FIGURE_SIZES.get(venue, FIGURE_SIZES['default'])
    w = w_single if width == 'single' else w_double
    h = min(w * aspect, h_max)
    return (w, h)
```

### Typical Sizes by Figure Type

| Figure Type | Width | Aspect Ratio | figsize (default) |
|------------|-------|-------------|-------------------|
| Single line/bar plot | single column | 0.7 | (5.0, 3.5) |
| Wide comparison | double column | 0.45 | (7.0, 3.15) |
| Square (heatmap, scatter) | single column | 1.0 | (5.0, 5.0) |
| Multi-panel 2×2 | double column | 0.8 | (7.0, 5.6) |
| Multi-panel 1×3 | double column | 0.35 | (7.0, 2.45) |

---

## 8. Quality Checklist (Pre-Submission)

Every figure must pass ALL items before submission:

### Critical (Must Pass)

- [ ] **Figure size** matches journal column width (set in inches, not pixels)
- [ ] **Font size** readable at printed size (≥6pt after scaling)
- [ ] **No title inside figure** — title only in LaTeX `\caption{}`
- [ ] **Vector format** — saved as PDF or EPS (not JPEG for plots)
- [ ] **Axis labels** have units (e.g., "Energy (keV)" not "Energy")
- [ ] **Axis labels** are human-readable (not variable names like `emp_rate`)
- [ ] **Error bars / uncertainty** shown where applicable
- [ ] **Caption is self-contained** — defines symbols, explains the finding

### Style (Should Pass)

- [ ] **Colorblind-safe** — tested with Okabe-Ito or viridis; no red-green only distinction
- [ ] **Grayscale readable** — distinguishable when printed in B&W
- [ ] **Color + shape/linestyle** — data series distinguished by ≥2 visual channels
- [ ] **No chartjunk** — no 3D, no background images, no decorative gridlines
- [ ] **Consistent style** across all figures (same fonts, colors, linewidths)
- [ ] **Legend** does not overlap data
- [ ] **Spines** — remove top and right spines (unless convention requires them)
- [ ] **One message per figure** — not overcrowded

### Panel Labels (if multi-panel)

- [ ] Labels match venue format (Nature: bold lowercase `a`; IEEE: `(a)`; AGU: bold `(a)`)
- [ ] Labels positioned consistently (top-left of each panel)
- [ ] Shared axes labeled only once (not repeated per panel)

---

## 9. References

### Key Papers
- Rougier, N. P. et al. (2014). "Ten Simple Rules for Better Figures." *PLOS Computational Biology*. [DOI:10.1371/journal.pcbi.1003833](https://doi.org/10.1371/journal.pcbi.1003833)
- Crameri, F. et al. (2020). "The misuse of colour in science communication." *Nature Communications*. [DOI:10.1038/s41467-020-19160-7](https://doi.org/10.1038/s41467-020-19160-7)

### Tools & Libraries
- [SciencePlots](https://github.com/garrettj403/SciencePlots) — matplotlib journal styles (8.7k stars)
- [Scientific Visualization Book](https://github.com/rougier/scientific-visualization-book) — Rougier's matplotlib bible (11.2k stars)
- [matplotlib_for_papers](https://github.com/jbmouret/matplotlib_for_papers) — practical templates (2.2k stars)
- [UltraPlot](https://github.com/Ultraplot/UltraPlot) — advanced multi-panel layouts

### Decision Trees & Guides
- [From Data to Viz](https://www.data-to-viz.com/) — interactive chart chooser
- [ColorBrewer 2.0](https://colorbrewer2.org/) — color scheme selector
- [Colorblind checker](https://davidmathlogic.com/colorblind/) — test your palette

### Journal Guidelines
- [Nature figure guide](https://research-figure-guide.nature.com/)
- [IEEE graphics guidelines](https://conferences.ieeeauthorcenter.ieee.org/write-your-paper/improve-your-graphics/)
- [AGU figure requirements](https://www.agu.org/publish/author-resources/graphics-requirements)
