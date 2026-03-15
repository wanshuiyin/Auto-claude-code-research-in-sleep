---
name: slurm-job
description: Submit, monitor, and collect results from SLURM jobs on HPC clusters. Use when user says "submit job", "run slurm", "check job", "squeue", "提交實驗", "跑slurm", or when /run-experiment or /monitor-experiment detects a SLURM environment. Handles the full lifecycle: pre-flight → submit → poll → collect results.
---

# SLURM Job Manager

Action: $ARGUMENTS

## Submission Permission: Defer to CLAUDE.md

Before submitting any job, **read the project's `CLAUDE.md`** to check the current HITL policy:
- If CLAUDE.md says experiments must be submitted by human operators → show the plan and ask the user to submit manually.
- If CLAUDE.md grants autonomous submission permission → proceed with `./submit_job.sh` directly.
- If CLAUDE.md is ambiguous → default to asking the user for confirmation.

**Never hardcode the permission policy.** Always re-read CLAUDE.md at submission time.

---

## Monitoring Rate Limits

To avoid excessive load on the SLURM controller (which can get you flagged by cluster admins):

| Command | Min Interval | Notes |
|---------|:------------:|-------|
| `squeue -u "$USER"` | **60 seconds** | Listing all user jobs |
| `squeue -j <ID>` | **60 seconds** | Checking a specific job |
| `sacct -j <ID>` | **60 seconds** | After job completes |
| `tail slurm-logs/*.out` | **10 seconds** | Reading local log files (no SLURM API call) |

**Rules:**
- Never use `watch` or tight polling loops on `squeue`/`sacct`.
- When waiting for a job, prefer reading `slurm-logs/<ID>.out` (local file) over `squeue` (API call).
- For long-running jobs (>1 hour), check status at most once every 5 minutes unless the user asks.
- If using `/loop` for monitoring, set interval >= 5 minutes: `/loop 5m /slurm-job monitor <ID>`.

---

## Mode Detection

Parse `$ARGUMENTS` to determine mode:

| Keyword | Mode |
|---------|------|
| `submit`, `run`, `deploy`, `提交` | **SUBMIT** |
| `monitor`, `check`, `status`, `squeue`, `查看` | **MONITOR** |
| `collect`, `results`, `結果` | **COLLECT** |
| (numeric job ID) | **MONITOR** that specific job |
| (no keyword, experiment description) | **SUBMIT** |

---

## Mode: SUBMIT

### Step 1: Check Submission Permission

```
Read CLAUDE.md → check HITL policy → decide whether to submit directly or ask user
```

### Step 2: Read Project Config

```bash
source ~/.bashrc && condaenv py312
```

Read `docs/SLURM_RUNBOOK.md` to confirm:
- Submission entry point: `./submit_job.sh`
- Job types: `pt` (pretraining), `sft` (fine-tuning), `inf` (inference)
- Suffix rules: e.g., `-bbc` → `scripts/run_pt_peft_bbc.sh`

### Step 3: Determine Job Type and Config

From the user's description, determine:
- **Job type**: `pt`, `sft`, or `inf`
- **Suffix**: e.g., `-bbc`, `-pt`, `-sft`, `-fl`, `-gen`, `-mc`
- **Config changes needed**: Which files need editing before submission

Common config locations:
- PT experiments: `scripts/run_pt_peft*.sh` (hyperparams), `run_pt_slurm.slurm` (exp_name)
- SFT experiments: `scripts/run_sft_peft*.sh`, `run_sft_slurm.slurm` (peft_file_path)
- Inference: `inference_cc2024.py` (MODEL_PATHS, BASE_CONFIG, TASK_CONFIG)
- Rank sweep: `scripts/run_pt_peft_bbc_rank_sweep.sh RANK SEED METHOD`

### Step 4: Apply Config Changes

Edit the necessary config files. Always show the diff to the user.

For inference jobs, the typical changes in `inference_cc2024.py` are:
```python
MODEL_PATHS = {"lora": "<checkpoint_path>"}
TASK_CONFIG = {"task_types": ["gsm8k", "mbpp", ...]}
BASE_CONFIG = {"use_full_model": True/False, ...}
```

### Step 5: Pre-flight Verification

Before submitting, verify:
```bash
# Check queue status (respect rate limit)
squeue -u "$USER"

# Check the script exists
ls scripts/run_<type>_peft<suffix>.sh 2>/dev/null

# For inference, verify checkpoint exists
ls <checkpoint_path>/pytorch_model*.bin 2>/dev/null || ls <checkpoint_path>/model*.safetensors 2>/dev/null
```

### Step 6: Present Submission Plan

Show the user:
```
Submission Plan:
  Command:  ./submit_job.sh <type> <suffix> [extra sbatch args]
  Script:   scripts/run_<type>_peft<suffix>.sh
  Resources: <N> nodes, <M> GPUs, ~<T> hours estimated
  Output:   save/<dataset>/<date>/<CPT|SFT>/<exp_name>/
  Config changes: [list of files edited]
```

Then, based on CLAUDE.md HITL policy:
- If autonomous submission allowed → submit directly
- If HITL required → show the command and ask the user to run it

### Step 7: Submit (if permitted)

```bash
./submit_job.sh <type> <suffix> [extra args]
```

Capture the SLURM job ID from output: `Submitted batch job <JOBID>`.

### Step 8: Record Submission

```bash
echo "$(date -Iseconds) JOBID=<id> CMD='./submit_job.sh <type> <suffix>' EXP=<exp_name>" >> slurm-logs/submission_history.log
```

### Step 9: Initial Status Check

```bash
squeue -u "$USER" -j <JOBID> --format="%.18i %.9P %.50j %.8u %.8T %.10M %.6D %R"
```

Report: job ID, status (PENDING/RUNNING), queue position.

---

## Mode: MONITOR

### Step 1: Identify Jobs

If a specific job ID is given, use it. Otherwise, list all user jobs:

```bash
squeue -u "$USER" --format="%.18i %.9P %.50j %.8u %.8T %.10M %.6D %R"
```

### Step 2: Check Job Status

For each job:

```bash
# Running or pending?
squeue -j <JOBID> --noheader 2>/dev/null
if [ $? -ne 0 ]; then
    # Job finished — check exit status
    sacct -j <JOBID> --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS --noheader
fi
```

### Step 3: Read Logs (prefer local file reads over SLURM API)

For running jobs, **read local log files** (no rate limit concern):
```bash
tail -30 slurm-logs/<JOBID>.out 2>/dev/null
tail -10 slurm-logs/<JOBID>.err 2>/dev/null
```

Look for:
- Training progress: `loss=`, `step`, `epoch`, `eval_loss`
- Errors: `CUDA out of memory`, `RuntimeError`, `Traceback`
- Completion: `Training completed`, `Saving model`

### Step 4: Estimate Remaining Time

From the log, extract:
- Current step / total steps
- Time per step
- Calculate ETA

### Step 5: Report Status

```
Job Status:
  Job ID:    <JOBID>
  State:     RUNNING / COMPLETED / FAILED
  Elapsed:   HH:MM:SS
  Progress:  step X/Y (Z%)
  ETA:       ~HH:MM remaining
  Last log:  <last meaningful line>
```

### Step 6: Repeated Monitoring

If the user wants continuous monitoring, suggest:
```
/loop 5m /slurm-job monitor <JOBID>
```

**Never poll more frequently than every 5 minutes for long-running jobs.**

---

## Mode: COLLECT

### Step 1: Find Output Directory

From job ID or experiment name, locate the output:

```bash
# From job log
grep -m1 "output_dir=" slurm-logs/<JOBID>.out | sed 's/.*output_dir=//'

# Or search by experiment name
find save/ -maxdepth 4 -name "<exp_name>" -type d 2>/dev/null
```

### Step 2: Check Training Success

```bash
cat <output_dir>/all_results.json 2>/dev/null

python3 -c "
import json
ts = json.load(open('<output_dir>/trainer_state.json'))
print(f'Best checkpoint: step {ts[\"best_model_checkpoint\"]}')
print(f'Best metric: {ts[\"best_metric\"]:.4f}')
" 2>/dev/null
```

### Step 3: Collect Inference Results

Search for `distribution_stats.json` in the output tree:

```bash
find <output_dir> -name "distribution_stats.json" | while read f; do
    task=$(basename $(dirname "$f") | sed 's/_result$//')
    echo "=== $task ==="
    python3 -c "import json; d=json.load(open('$f')); print(json.dumps(d.get('final_scores', d), indent=2))"
done
```

### Step 4: Collect Commonsense Aggregated Results

```bash
find <output_dir> -name "final_aggregated_results.json" | while read f; do
    python3 -c "
import json; d=json.load(open('$f'))
overall = d.get('overall', {})
wa = overall.get('weighted_average', {}).get('em', 'N/A')
print(f'Commonsense weighted avg EM: {wa}')
for name, info in d.get('datasets', {}).items():
    print(f'  {name}: {info[\"scores\"][\"em\"]:.1f}')
"
done
```

### Step 5: Build Comparison Table

Compare against known baselines from `docs/research_proposal.md`:

```
| Method | BBC QA | MBPP | GSM8K | CS-Avg | Status |
|--------|--------|------|-------|--------|--------|
| Base   | 5.75   | .606 | 85.22 | 46.14  | ref    |
| This   | XX.XX  | .XXX | XX.XX | XX.XX  | new    |
| Delta  | +XX    | -.XX | -XX   | -XX    |        |
```

### Step 6: Update docs/research_proposal.md

If results are for a method already in the table, update the row. If it's a new method, add a new row. Always show the diff to the user before writing.

### Step 7: Feishu Notification (if configured)

After results are collected, invoke `/feishu-notify` if `~/.claude/feishu.json` exists with mode != `"off"`.

---

## Batch Operations

### Submit Multiple Jobs

When the user wants to run a sweep (e.g., rank sweep, seed sweep):

```bash
for RANK in 64 256 512; do
    for METHOD in standard_lora gated_gamma_0.1; do
        echo "Would submit: SWEEP_RANK=$RANK SWEEP_METHOD=$METHOD ./submit_job.sh pt -bbc_rank_sweep"
    done
done
```

Show the full matrix to the user. Submission follows the CLAUDE.md HITL policy.

### Monitor All Running Jobs

```bash
squeue -u "$USER" --format="%.18i %.9P %.50j %.8u %.8T %.10M %.6D %R"
```

For each RUNNING job, read `slurm-logs/<ID>.out` for progress (local reads, no rate limit).

### Collect All Recent Results

```bash
find save/BBC_news/ -name "all_results.json" -mtime -1 2>/dev/null
```

---

## Integration with Other Skills

### Called by `/run-experiment`

When `/run-experiment` detects SLURM (`which squeue`), it delegates to `/slurm-job submit`.

### Called by `/monitor-experiment`

When `/monitor-experiment` detects SLURM, it delegates to `/slurm-job monitor` and `/slurm-job collect`.

### Calls `/analyze-results`

After collecting results, optionally invoke `/analyze-results` for deeper statistical analysis.

### Calls `/feishu-notify`

Send notifications after job completion or failure.

---

## Error Handling

| Error | Action |
|-------|--------|
| `sbatch: error: Batch job submission failed` | Check resource request, quota, partition |
| Job stuck in PENDING | `squeue -j <ID> --format=%R` to see reason (`Resources`, `Priority`) |
| Job FAILED | Read `slurm-logs/<ID>.err` for OOM, CUDA errors, missing files |
| `rm -rf ${SAVE}` warning | Scripts clear output dir on start — warn if re-running same exp_name same day |
| Missing checkpoint | Verify path in submission script matches `save/` structure |

---

## Quick Reference

```bash
# Submit
./submit_job.sh pt -bbc                    # BBC pretraining
./submit_job.sh sft -bbc                   # BBC SFT
./submit_job.sh inf -sft                   # SFT inference

# Monitor
squeue -u "$USER"                          # All my jobs
sacct -j <JOBID> --format=JobID,State,Elapsed  # Job history
tail -f slurm-logs/<JOBID>.out             # Live log (local read, no rate limit)

# Results
cat save/<path>/all_results.json           # Training summary
cat <path>/distribution_stats.json         # Inference metrics
```
