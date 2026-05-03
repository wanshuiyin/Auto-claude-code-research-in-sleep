---
name: experiment-queue
description: SSH job queue for multi-seed/multi-config ML experiments with OOM-aware retry, stale-screen cleanup, and wave-transition race prevention. Use when user says "batch experiments", "队列实验", "run grid", "multi-seed sweep", "auto-chain experiments", or when /run-experiment is insufficient for 10+ jobs that need orchestration.
argument-hint: [manifest-or-grid-spec]
allowed-tools: Bash(*), Read, Grep, Glob, Edit, Write, Agent, Skill(run-experiment), Skill(monitor-experiment)
---

# Experiment Queue

Orchestrate large batches of ML experiments on SSH remote GPU servers with proper state tracking, OOM retry, stale cleanup, and wave transitions.

## When to Use This Skill

Use when `/run-experiment` is insufficient:
- **≥10 jobs** that need batching across GPUs
- **Multi-seed sweeps** (e.g., 21 seeds × 12 cells)
- **Wave transitions** (run wave 1, wait, run wave 2, wait, run wave 3...)
- **Teacher+student chains** (train teacher then distill; auto-trigger student after teacher done)
- **OOM-prone configs** where you need to retry with different GPU or wait
- **Mixed seed grids** where failed cells need re-running

Do NOT use for:
- Single ad-hoc experiment (use `/run-experiment`)
- Modal/Vast.ai deployments (those have their own orchestration)
- Experiments that need manual inspection between runs

## Why This Exists

Based on session audit (2026-04-16), the major wall-clock sinks in multi-seed grid experiments are:

1. **Stale screens** — python finishes, wandb uploads, screen hangs, next wave blocked
2. **OOM on shared GPU** — previous job's memory not yet released
3. **Wave race** — new wave launches before previous wave fully settles
4. **Missing checkpoints** — student launches before teacher saved
5. **Parser duplication** — rewriting multi-seed analysis python every batch

All of these are pure engineering friction that can be orchestrated.

## Core Concepts

### Job Manifest

A manifest lists jobs with explicit state:

```yaml
project: my_grid_experiment
cwd: /home/user/your_project
conda: my_env
# Optional: override conda hook path if conda is not at a standard location.
# Can be a bare path (wrapped automatically) or a full `eval "$(... shell.bash hook)"` string.
# Falls back to auto-detect of ~/anaconda3, ~/miniconda3, /opt/anaconda3, etc.,
# or the ARIS_CONDA_HOOK environment variable.
# conda_hook: /custom/path/to/conda
ssh: gpu-server
default_cmd: >
  python run_distill.py --backbone softmax --lam 0.5
  --K 500 --L 96 --W 16 --n_steps 30000 --batch_size 128 --lr 1e-4

preconditions:
  - type: checkpoint_exists
    path: checkpoints/transformer/teacher_L96_K500_N{N}.pt

gpus: [0, 1, 2, 3, 4, 5, 6, 7]
max_parallel: 8
gpu_free_threshold_mib: 500  # optional, default 500; raise for shared servers, lower for tight packing
oom_retry:
  delay: 120
  max_attempts: 3

jobs:
  - id: s200_N64_n50K
    args: {seed: 200, n_hidden: 64, n_train_subset: 50000, subset_seed: 2024}
  - id: s200_N128_n50K
    args: {seed: 200, n_hidden: 128, n_train_subset: 50000, subset_seed: 2024}
  # ... 14 more
```

### Job State Machine

```
pending → running → completed
                 ↘ failed_oom → pending (after delay) [retry up to N]
                 ↘ failed_other → stuck (needs manual inspection)
stale_screen_detected → cleaned → pending
```

### Wave Orchestration

A "wave" is a batch of jobs that fit available GPUs. Next wave only starts when:
1. All current-wave python processes have exited
2. No stale screens remain for current-wave tags
3. GPU memory has dropped below threshold (≤500 MiB)
4. Precondition checks pass for next-wave jobs

## Workflow

### Step 1: Parse Manifest / Build from Grid

Input can be:
- **YAML manifest** (explicit job list, recommended for complex cases)
- **Grid spec** (Cartesian product of param values, e.g., `N=[64,128,256] × n=[50K,150K,500K,652K]`)
- **Natural language description** (Claude parses into manifest)

Bind run identifiers once so every later step refers to the same paths:

```bash
# REPLACE the placeholder path before running, or pre-export PROJECT_DIR:
PROJECT_DIR="${PROJECT_DIR:?set PROJECT_DIR to the local project root}"
RUN_TS=$(date -u +%Y%m%dT%H%M%SZ)
LOCAL_RUN_DIR="$PROJECT_DIR/experiment_queue/$RUN_TS"
mkdir -p "$LOCAL_RUN_DIR"
```

Save the built manifest to `$LOCAL_RUN_DIR/manifest.json` for reproducibility.

### Step 2: Pre-flight

- Check SSH connection works
- Check conda env exists on remote
- Check `cwd` exists on remote
- Check all preconditions (checkpoints, input files)
- Check GPU availability (at least `max_parallel` free GPUs)

If any precondition fails, show user which jobs are blocked and why.

### Step 3: Launch Scheduler

Resolve the bundled helper directory (`$PROJECT_DIR` / `$RUN_TS` / `$LOCAL_RUN_DIR` already set in Step 1):

```bash
ARIS_REPO="${ARIS_REPO:-$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null)}"
[ -n "$ARIS_REPO" ] || { echo "ERROR: ARIS_REPO not set. Use install_aris_codex.sh managed install or export ARIS_REPO=/path/to/ARIS."; exit 1; }
QUEUE_TOOLS="$ARIS_REPO/tools/experiment_queue"
[ -f "$QUEUE_TOOLS/queue_manager.py" ] || { echo "ERROR: queue_manager.py not found under $QUEUE_TOOLS"; exit 1; }
```

Compute remote paths (note: modern `scp` runs in SFTP mode and does NOT reliably expand `$HOME` in destination paths — use remote-relative for `scp`, `$HOME`-prefixed for `ssh` command strings):

```bash
REMOTE_RUN_REL=".aris_queue/runs/$RUN_TS"
REMOTE_RUN_DIR="\$HOME/$REMOTE_RUN_REL"
```

Bootstrap remote run dir + copy helpers + copy manifest. Per-invocation, idempotent:

```bash
ssh <server> "mkdir -p \"$REMOTE_RUN_DIR/logs\" \"\$HOME/.aris_queue\""
scp "$QUEUE_TOOLS/queue_manager.py" "$QUEUE_TOOLS/build_manifest.py" <server>:.aris_queue/
scp "$LOCAL_RUN_DIR/manifest.json" <server>:"$REMOTE_RUN_REL/manifest.json"
```

Launch the scheduler as a detached `nohup` process:

```bash
ssh <server> "nohup python3 \"\$HOME/.aris_queue/queue_manager.py\" \\
  --manifest \"$REMOTE_RUN_DIR/manifest.json\" \\
  --state    \"$REMOTE_RUN_DIR/queue_state.json\" \\
  --log-dir  \"$REMOTE_RUN_DIR/logs\" \\
  > \"$REMOTE_RUN_DIR/queue_mgr.log\" 2>&1 &"
```

Notes: `--log-dir` is what `queue_manager.py` actually consumes (per-job log files for OOM detection). Do NOT pass `--log <path>` — that flag is declared but unused.

Persist run identifiers for monitoring + resume (sourceable later):

```bash
{
  printf 'PROJECT_DIR=%q\n'    "$PROJECT_DIR"
  printf 'RUN_TS=%q\n'         "$RUN_TS"
  printf 'LOCAL_RUN_DIR=%q\n'  "$LOCAL_RUN_DIR"
  printf 'REMOTE_RUN_REL=%q\n' "$REMOTE_RUN_REL"
  printf 'REMOTE_RUN_DIR=%q\n' "$REMOTE_RUN_DIR"
} > "$LOCAL_RUN_DIR/run_meta.txt"
```

`%q` shell-escapes values; `REMOTE_RUN_DIR` keeps a literal `$HOME` (correct for later reuse inside `ssh "..."`).

**Resume an existing queue.** Do NOT regenerate `RUN_TS`. Reload from `run_meta.txt` and re-run only the launch command above (not the bootstrap):

```bash
LOCAL_RUN_DIR="/abs/path/to/project/experiment_queue/<existing-run-ts>"
. "$LOCAL_RUN_DIR/run_meta.txt"
# Then re-run the launch command verbatim; do NOT re-run mkdir/scp.
```

The scheduler:
- Reads manifest
- Loops: for each pending job, assign to free GPU, launch via `screen`
- Polls job status (every 60s)
- Detects stale screens (python exited but screen detached → kill)
- Detects OOM (CUDA OOM in log → mark failed_oom → retry after delay)
- Detects completion (expected output JSON/file exists) → mark completed
- Launches next wave when current wave settles
- Writes state to `queue_state.json` continuously

### Step 4: Monitoring

User can check state anytime, using `$REMOTE_RUN_DIR` from Step 3 (or reload it from `$LOCAL_RUN_DIR/run_meta.txt`):

```bash
ssh <server> "cat \"$REMOTE_RUN_DIR/queue_state.json\"" \
  | jq '.jobs | group_by(.status) | map({(.[0].status): length}) | add'
```

Note: `/monitor-experiment` is currently focused on screen sessions, result JSONs, and W&B; it does not yet read `queue_state.json` directly. For queue-state monitoring, use the literal command above.

### Step 5: Post-completion

When all jobs in `manifest.json` are `completed` or `stuck`:
- The remote scheduler (`queue_manager.py`) exits cleanly with `All jobs done` to its own stdout (captured in `$REMOTE_RUN_DIR/queue_mgr.log`). It does NOT write the local summary.
- The **local** skill agent then aggregates state into `$LOCAL_RUN_DIR/summary.md` (read `$REMOTE_RUN_DIR/queue_state.json`, group by status, optionally pull per-job logs).
- Local skill agent invokes `/analyze-results` if `analyze_on_complete: true`.

## Grid Spec Syntax

Instead of writing 24 job entries manually:

```yaml
grid:
  N: [64, 128, 256]
  n: [50000, 150000, 500000, 652000]
  seed: [42, 200, 201]
template:
  id: "s${seed}_N${N}_n${n}"
  args: {seed: ${seed}, n_hidden: ${N}, n_train_subset: ${n}}
```

Expands to 36 jobs automatically.

## Wave Chaining

For sequential phases (teacher → student):

```yaml
phases:
  - name: train_teachers
    grid:
      N: [384, 512]
    template:
      cmd: python run_train.py --direction c --backbone softmax --n_hidden ${N} ...
      output_check: checkpoints/transformer/teacher_L96_K500_N${N}.pt
  
  - name: distill_students
    depends_on: train_teachers
    grid:
      N: [384, 512]
      seed: [42, 200, 201]
    template:
      cmd: python run_distill.py --n_hidden ${N} --seed ${seed} ...
      output_check: figures/distill_sw_N${N}_*_seed${seed}.json
```

Scheduler enforces `depends_on`: `distill_students` jobs stay `pending` until all
`train_teachers` jobs are `completed`.

## OOM Handling

Detect OOM from stdout:
```regex
torch\.OutOfMemoryError: CUDA out of memory
```

On detection:
1. Mark job `failed_oom`
2. Kill screen
3. Wait `oom_retry.delay` seconds
4. Check if current GPU is free; if not, try another free GPU
5. Requeue as `pending`
6. Max `oom_retry.max_attempts` before marking `stuck`

## Stale Screen Detection

Every 60s, for each running screen:
1. Check screen exists (`screen -ls`)
2. Check python PID still running (`ps -p`)
3. If screen exists but python exited:
   - If expected output file exists → mark `completed`, kill stale screen
   - If no output file → mark `failed_other`, kill screen

## Resume-on-restart

If scheduler crashes / is killed:
1. Read `queue_state.json`
2. For each `running` job: check screen; if still alive, keep; if not, re-evaluate state
3. For each `pending`: continue normally
4. Idempotent: safe to restart scheduler without losing state

## Output: Summary Report

```markdown
# Experiment Queue Summary

**Project**: my_grid_experiment
**Started**: 2026-04-16 11:36:29
**Completed**: 2026-04-16 18:02:14
**Total wall-clock**: 6h 25m
**Jobs**: 40 completed, 2 OOM-retried then completed, 0 stuck

## Phases
| Phase | Jobs | Success | OOM retries | Duration |
| --- | --- | --- | --- | --- |
| train_teachers | 2 | 2 | 0 | 58m |
| distill_students | 24 | 24 | 2 | 4h 02m |
| multi_seed_validation | 16 | 16 | 0 | 1h 25m |

## Results Files
- 42 JSON files in `figures/distill_sw_*.json`

## Next Steps
- Run `/analyze-results` on output JSONs
- Figures auto-regen via `artifact-sync` (if configured)
```

## Comparison with `/run-experiment`

| Feature | `/run-experiment` | `experiment-queue` |
| --- | --- | --- |
| Single-shot experiment | ✅ | ✅ (overkill) |
| Multi-GPU parallel | Basic | Proper scheduling |
| Wave transitions | Manual | Automatic |
| OOM retry | Manual | Automatic |
| Stale screen cleanup | Manual | Automatic |
| Teacher→student chain | Manual | Built-in |
| State persistence | No | Yes (JSON) |
| Resume on crash | No | Yes |
| Grid expansion | Manual | Declarative |

**Rule**: Use `/run-experiment` for ≤5 jobs. Use `experiment-queue` for ≥10 jobs or anything with phases.

## Key Rules

- **Never overlap screens on the same GPU** — always wait for `memory.used < 500 MiB` before launching new job
- **Always write state to disk** — every state change flushed to `queue_state.json`
- **Idempotent scheduler** — safe to restart; picks up from state file
- **Expected-output-based completion** — don't trust screen state alone; verify output file exists
- **Bounded retry** — max N OOM retries, then mark `stuck` and alert
- **Dependencies enforced at launch** — never launch student before teacher checkpoint exists

## Known Failure Modes

- **SSH connection drop during scheduling**: scheduler keeps running on remote (nohup), just reconnect and check
- **GPU reservation by another user**: scheduler waits, does not pre-empt
- **Disk full on remote**: scheduler detects write failure, marks all pending `stuck`, alerts

## Example Session

User: "跑 T5+T6 全部实验：T5 = N∈{80,192} × n 4 values × seed {200,201}, T6 = N∈{384,512} × n 4 values × seed {42,200,201}; T6 需要先 train teacher"

Claude invokes `/experiment-queue`:
1. Parses description into 2-phase manifest
2. Phase 1: T5 (16 jobs, no teacher dependency) + T6 teacher training (2 jobs)
3. Phase 2: T6 distillation (24 jobs, depends on teachers)
4. Deploys scheduler via nohup
5. Reports: "Scheduler PID 93534, total 42 jobs, estimated 6-7h wall-clock"

Then user can check anytime or wait for summary report.

## See Also

- `/run-experiment` — single experiment deployment
- `/monitor-experiment` — check progress (now reads from queue_state.json)
- `/analyze-results` — post-hoc analysis
- `tools/experiment_queue/queue_manager.py` (bundled) — the scheduler implementation
- `tools/experiment_queue/build_manifest.py` (bundled) — build manifest from grid spec

## Rationale / Source

Identified via 2026-04-16 post-mortem analysis (Codex GPT-5.4 xhigh) of a 1.5-day
multi-seed paper experiment session:

- Wall-clock sink: stale screens, OOM, wave transitions, manual parser
- Token sink: re-writing orchestration code each session
- Cognitive sink: tracking which cells succeeded, which failed, which to retry

This skill targets the wall-clock sink specifically; see `artifact-sync` and
`paper-fix-auto-apply` for the other two.
