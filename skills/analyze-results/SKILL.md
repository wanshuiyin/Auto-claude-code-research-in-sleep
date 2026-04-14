---
name: analyze-results
description: Analyze ML experiment results, compute statistics, generate comparison tables and insights. Use when user says "analyze results", "compare", or needs to interpret experimental data.
argument-hint: [results-path-or-description]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, Agent
---

# Analyze Experiment Results

Analyze: $ARGUMENTS

## Workflow

### Step 1: Locate Results
Find all relevant JSON/CSV result files:
- Check `figures/`, `results/`, or project-specific output directories
- Parse JSON results into structured data

### Step 2: Build Comparison Table
Organize results by:
- **Independent variables**: model type, hyperparameters, data config
- **Dependent variables**: primary metric (e.g., perplexity, accuracy, loss), secondary metrics
- **Delta vs baseline**: always compute relative improvement

### Step 3: Statistical Analysis
- If multiple seeds: report mean +/- std, check reproducibility
- If sweeping a parameter: identify trends (monotonic, U-shaped, plateau)
- Flag outliers or suspicious results

### Step 3.5: Recommend Visualizations

Based on the data structure discovered in Steps 1–3, recommend figure types using the decision tree from `shared-references/FIGURE_STYLE_GUIDE.md` §1:

| Analysis Result | Recommended Figure | Rationale |
|----------------|-------------------|-----------|
| Single metric across methods | Bar chart or lollipop | Direct comparison |
| Metric across methods + multiple datasets | Grouped bar or multi-panel | Shows interaction |
| Training curves (metric vs steps) | Line plot (+ shaded band if multiple seeds) | Shows trend + uncertainty |
| Hyperparameter sweep (1 param) | Line plot with param on x-axis | Shows sensitivity |
| Hyperparameter sweep (2 params) | Heatmap | Shows interaction surface |
| Distribution of metrics across seeds | Violin or box plot | Shows spread + shape |
| Pairwise method comparison | Scatter with diagonal | Shows per-item winner |
| Correlation between metrics | Correlation matrix heatmap | Shows metric relationships |
| Ablation results (component on/off) | Stacked bar or grouped bar | Shows contribution |

**Output**: For each recommended figure, provide:
1. Figure type and suggested filename
2. Data columns / keys to use
3. Suggested caption draft
4. Whether it belongs in main paper or supplementary

This output can be passed directly to `/paper-figure` for generation.

### Step 4: Generate Insights
For each finding, structure as:
1. **Observation**: what the data shows (with numbers)
2. **Interpretation**: why this might be happening
3. **Implication**: what this means for the research question
4. **Next step**: what experiment would test the interpretation

### Step 5: Update Documentation
If findings are significant:
- Propose updates to project notes or experiment reports
- Draft a concise finding statement (1-2 sentences)

## Output Format
Always include:
1. Raw data table
2. Key findings (numbered, concise)
3. **Recommended visualizations** (figure type, data mapping, caption draft) — ready for `/paper-figure`
4. Suggested next experiments (if any)
