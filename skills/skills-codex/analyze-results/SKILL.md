---
name: "analyze-results"
description: "Analyze ML experiment results, compute statistics, generate comparison tables and insights. Use when user says \"analyze results\", \"compare\", or needs to interpret experimental data."
---

# Analyze Experiment Results

Analyze: $ARGUMENTS

## Workflow

### Step 1: Locate Results
Find all relevant JSON/CSV result files:
- Check `figures/`, `results/`, or project-specific output directories
- Parse JSON results into structured data

### Step 2: Read the measurements in context
Identify the metric, units and run conditions. For comparisons, align the dataset and settings and show both values. Report a difference in the metric’s units (percentage points for rates). Use relative change when the baseline and metric make the ratio meaningful.

### Step 3: Statistical Analysis
- If multiple seeds: report mean +/- std, check reproducibility
- If sweeping a parameter: identify trends (monotonic, U-shaped, plateau)
- Flag outliers or suspicious results

### Step 4: Answer the research question
Lead with the measured result and identify the file or run it came from. Use a table when comparing configurations or seeds. Distinguish a measured trend from a proposed explanation. Suggest a follow-up experiment when it would resolve a question the data leaves open.

If the finding changes a conclusion in the project notes or experiment report, propose the corresponding update.
