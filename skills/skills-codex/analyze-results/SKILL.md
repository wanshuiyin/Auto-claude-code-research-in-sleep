---
name: "analyze-results"
description: "Analyze experiment outputs, compute statistics, and build comparison tables or insights. Use for descriptive result interpretation and comparisons. Do not use when the main task is to decide what claims are defensible; use `result-to-claim` then."
---

# Analyze Experiment Results

Analyze: $ARGUMENTS

## Routing Boundaries

- Use this skill for descriptive analysis, summary tables, metric comparisons, and statistical interpretation.
- Use `result-to-claim` when the real question is what the completed results justify saying in a paper.
- Use `paper-figure` when the output needed is publication-quality plots and tables rather than analysis alone.

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
3. Suggested next experiments (if any)
