---
name: "dse-loop"
description: "Autonomous design-space exploration loop for computer architecture and EDA parameter tuning. Use for iterative sweep-optimize-repeat tasks over a defined configuration space. Do not use for ordinary experiment launch or one-shot result analysis; use `run-experiment` or `analyze-results` then."
---

# DSE Loop: Autonomous Design Space Exploration

Autonomously explore a design space: run → analyze → pick next parameters → repeat, until the objective is met or timeout is reached. Designed for computer architecture and EDA problems.

## Context: $ARGUMENTS

## Routing Boundaries

- Use this skill for iterative parameter search where the system should repeatedly choose the next configuration to try.
- Use `run-experiment` for ordinary job launch without adaptive search.
- Use `analyze-results` when the runs are already finished and the task is only to interpret results.

## Safety Rules — READ FIRST

**NEVER do any of the following:**
- `sudo` anything
- `rm -rf`, `rm -r`, or any recursive deletion
- `rm` any file you did not create in this session
- Overwrite existing source files without reading them first
- `git push`, `git reset --hard`, or any destructive git operation
- Kill processes you did not start

**If a step requires any of the above, STOP and report to the user.**

## Constants (override via $ARGUMENTS)

| Constant | Default | Description |
|----------|---------|-------------|
| `TIMEOUT` | 2h | Total wall-clock budget. Stop exploring after this. |
| `MAX_ITERATIONS` | 50 | Hard cap on number of design points evaluated. |
| `PATIENCE` | 10 | Stop early if no improvement for this many consecutive iterations. |
| `OBJECTIVE` | minimize | `minimize` or `maximize` the target metric. |

Override inline: `/dse-loop "task desc — timeout: 4h, max_iterations: 100, patience: 15"`

## Typical Use Cases

| Problem | Program | Parameters | Objective |
|---------|---------|-----------|-----------|
| Microarch DSE | gem5 simulation | cache size, assoc, pipeline width, ROB size, branch predictor | maximize IPC or minimize area×delay |
| Synthesis tuning | yosys/DC script | optimization passes, target freq, effort level | minimize area at timing closure |
| RTL parameterization | verilator sim | data width, FIFO depth, pipeline stages, buffer sizes | meet throughput target at min area |
| Compiler flags | gcc/llvm build + benchmark | -O levels, unroll factor, vectorization, scheduling | minimize runtime or code size |
| Placement/routing | openroad/innovus | utilization, aspect ratio, layer config | minimize wirelength / timing |
| Formal verification | abc/sby | bound depth, engine, timeout per property | maximize coverage in time budget |
| Memory subsystem | cacti / ramulator | bank count, row buffer policy, scheduling | optimize bandwidth/energy |

## Workflow

### Phase 0: Parse Task & Setup

1. **Parse $ARGUMENTS** to extract:
   - **Program**: what to run (command, script, or Makefile target)
   - **Parameter space**: which knobs to tune and their ranges/options (may be incomplete — see step 2)
   - **Objective metric**: what to optimize (and how to extract it from output)
   - **Constraints**: hard limits that must not be violated (e.g., timing must close)
   - **Timeout**: wall-clock budget
   - **Success criteria**: when is the result "good enough" to stop early?

2. **Infer missing parameter ranges** — If the user provides parameter names but NOT ranges/options, you MUST infer them before exploring:

   a. **Read the source code** — search for the parameter names in the codebase:
      - Look for argparse/click definitions, config files, Makefile variables, module parameters, `#define`, `parameter` (SystemVerilog), `localparam`, etc.
      - Extract defaults, types, and any comments hinting at valid values

   b. **Apply domain knowledge** to set reasonable ranges:
      | Parameter type | Inference strategy |
      |---------------|-------------------|
      | Cache/memory sizes | Powers of 2, typically 1KB–16MB |
      | Associativity | Powers of 2: 1, 2, 4, 8, 16 |
      | Pipeline width / issue width | Small integers: 1, 2, 4, 8 |
      | Buffer/queue/FIFO depth | Powers of 2: 4, 8, 16, 32, 64 |
      | Clock period / frequency | Based on technology node; try ±50% from default |
      | Bound depth (BMC/formal) | Geometric: 5, 10, 20, 50, 100 |
      | Timeout values | Geometric: 10s, 30s, 60s, 120s, 300s |
      | Boolean/enum flags | Enumerate all options found in source |
      | Continuous (learning rate, threshold) | Log-scale sweep: 5 points spanning 2 orders of magnitude around default |
      | Integer counts (threads, cores) | Linear: from 1 to hardware max |

   c. **Start conservative** — begin with 3-5 values per parameter. Expand range later if the best result is at a boundary.

   d. **Log inferred ranges** — write the inferred parameter space to `dse_results/inferred_params.md` so the user can review:
      ```markdown
      # Inferred Parameter Space

      | Parameter | Source | Default | Inferred Range | Reasoning |
      |-----------|--------|---------|---------------|-----------|
      | CACHE_SIZE | config.py:42 | 32768 | [8192, 16384, 32768, 65536, 131072] | powers of 2, ±2x from default |
      | ASSOC | config.py:43 | 4 | [1, 2, 4, 8] | standard associativities |
      | BMC_DEPTH | run_bmc.py:15 | 10 | [5, 10, 20, 50] | geometric, common BMC depths |
      ```

   e. **Boundary expansion** — during the search, if the best result is at the min or max of a range, automatically extend that range by one step in that direction (but log the extension).

3. **Read the project** to understand:
   - How to run the program
   - Where results are produced (stdout, log files, reports)
   - How to parse the objective metric from output
   - Current/baseline configuration (if any)

4. **Create working directory**: `dse_results/` in project root
   - `dse_results/dse_log.csv` — one row per design point
   - `dse_results/DSE_REPORT.md` — final report
   - `dse_results/DSE_STATE.json` — state for recovery
   - `dse_results/inferred_params.md` — inferred parameter space (if ranges were not provided)
   - `dse_results/configs/` — config files for each run
   - `dse_results/outputs/` — raw output for each run

5. **Write a parameter extraction script** (`dse_results/parse_result.py` or similar) that takes a run's output and returns the objective metric as a number. Test it on a baseline run first.

6. **Run baseline** (iteration 0): run the program with default/current parameters. Record the baseline metric. This is the point to beat.

### Phase 1: Initial Exploration

**Goal**: Quickly survey the space to understand which parameters matter most.

**Strategy**: Latin Hypercube Sampling or structured sweep of key parameters.

1. Pick 5-10 diverse design points that span the parameter ranges
2. Run them (in parallel if independent, via background processes or sequential)
3. Record all results in `dse_log.csv`:
   ```
   iteration,param1,param2,...,metric,constraint_met,timestamp,notes
   0,default,default,...,baseline_val,yes,2026-03-13T10:00:00,baseline
   1,val1a,val2a,...,result1,yes,2026-03-13T10:05:00,initial sweep
   ...
   ```
4. Analyze: which parameters have the most impact on the objective?
5. Narrow the search to the most sensitive parameters

### Phase 2: Directed Search

**Goal**: Converge toward the optimum by making informed choices.

**Strategy**: Adaptive — pick the approach that fits the problem:

- **Few parameters (≤3)**: Fine-grained grid search around the best region from Phase 1
- **Many parameters (>3)**: Coordinate descent — optimize one parameter at a time, holding others at current best
- **Binary/categorical params**: Enumerate promising combinations
- **Continuous params**: Binary search or golden section between best neighbors
- **Multi-objective**: Track Pareto frontier, explore along the front

For each iteration:

1. **Select next design point** based on results so far:
   - Look at the trend: which direction improves the metric?
   - Avoid re-running configurations already evaluated
   - Balance exploration (untested regions) vs exploitation (near current best)

2. **Modify parameters**: edit config file, command-line args, or source constants

3. **Run the program**: execute and capture output

4. **Parse results**: extract the objective metric and check constraints

5. **Log to `dse_log.csv`**: append the new row

6. **Check stopping conditions**:
   - Timeout reached? → stop
   - Max iterations reached? → stop
   - Patience exhausted (no improvement in N iterations)? → stop
   - Success criteria met (metric is "good enough")? → stop
   - Constraint violation pattern detected? → adjust search bounds

7. **Update `DSE_STATE.json`**:
   ```json
   {
     "iteration": 15,
     "status": "in_progress",
     "best_metric": 1.23,
     "best_params": {"cache_size": 32768, "assoc": 4, "pipeline_width": 2},
     "total_iterations": 15,
     "start_time": "2026-03-13T10:00:00",
     "timeout": "2h",
     "patience_counter": 3
   }
   ```

8. **Decide next step** → back to step 1

### Phase 3: Refinement (if time allows)

If the search converged and there's still time budget:

1. **Local perturbation**: try ±1 step on each parameter from the best point
2. **Sensitivity analysis**: which parameters can be relaxed without hurting the metric?
3. **Constraint boundary**: if a constraint is nearly binding, explore near-feasible points

### Phase 4: Report

Write `dse_results/DSE_REPORT.md`:

```markdown
# Design Space Exploration Report

**Task**: [description]
**Date**: [start] → [end]
**Total iterations**: N
**Wall-clock time**: X hours Y minutes

## Objective
- **Metric**: [what was optimized]
- **Direction**: minimize / maximize
- **Baseline**: [value]
- **Best found**: [value] ([improvement]% better than baseline)

## Best Configuration
| Parameter | Baseline | Best |
|-----------|----------|------|
| param1    | default  | best_val |
| param2    | default  | best_val |
| ...       | ...      | ... |

## Search Trajectory
| Iteration | param1 | param2 | ... | Metric | Notes |
|-----------|--------|--------|-----|--------|-------|
| 0 (baseline) | ... | ... | ... | ... | baseline |
| 1 | ... | ... | ... | ... | initial sweep |
| ... | ... | ... | ... | ... | ... |
| N (best) | ... | ... | ... | ... | ★ best |

## Parameter Sensitivity
- **param1**: [high/medium/low impact] — [brief explanation]
- **param2**: [high/medium/low impact] — [brief explanation]

## Pareto Frontier (if multi-objective)
[Table or description of non-dominated points]

## Stopping Reason
[timeout / max_iterations / patience / success_criteria_met]

## Recommendations
- [actionable insights from the exploration]
- [which parameters matter most]
- [suggested follow-up explorations]
```

Also generate a summary plot if matplotlib is available:
- Convergence curve (metric vs iteration)
- Parameter sensitivity bar chart
- Pareto frontier scatter (if multi-objective)

## State Recovery

If the context window compacts mid-run, the loop recovers from `DSE_STATE.json` + `dse_log.csv`:

1. Read `DSE_STATE.json` for current iteration, best params, patience counter
2. Read `dse_log.csv` for full history
3. Resume from next iteration

## Key Rules

- Work AUTONOMOUSLY — do not ask the user for permission at each iteration
- **Every run must be logged** — even failed runs, constraint violations, errors. The log is the ground truth.
- **Never re-run an identical configuration** — check `dse_log.csv` before each run
- **Respect the timeout** — check elapsed time before starting a new iteration. If the next run is likely to exceed the timeout, stop and report.
- **Parse metrics programmatically** — write a parsing script, don't eyeball logs
- **Keep raw outputs** — save each run's full output in `dse_results/outputs/iter_N/`
- **Constraint violations are not improvements** — a design point that violates constraints is never "best", regardless of the metric
- If a run crashes, log the error, skip that point, and continue with the next
- If the same crash repeats 3 times with different configs, stop and report the issue

## Example Invocations

```
# Minimal — just name the parameters, let the agent figure out ranges
/dse-loop "Run gem5 mcf benchmark. Tune: L1D_SIZE, L2_SIZE, ROB_ENTRIES. Objective: maximize IPC. Timeout: 3h"

# Partial — some ranges given, some not
/dse-loop "Run make synth. Tune: CLOCK_PERIOD [5ns, 4ns, 3ns, 2ns], FLATTEN, ABC_SCRIPT. Objective: minimize area at timing closure. Timeout: 1h"

# Fully specified — explicit ranges for everything
/dse-loop "Simulate processor with FIFO_DEPTH [4,8,16,32], ISSUE_WIDTH [1,2,4], PREFETCH [on,off]. Run: make sim. Objective: max throughput/area. Timeout: 2h"

# Real-world: PDAG-SFA formal verification tuning
/dse-loop "Run python run_bmc.py. Tune: BMC_DEPTH, ENGINE, TIMEOUT_PER_PROP. Objective: maximize properties proved. Timeout: 2h"
```
