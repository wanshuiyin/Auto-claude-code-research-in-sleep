---
name: "run-experiment"
description: "Deploy and run ML experiments on local or remote GPU servers. Use when user says \"run experiment\", \"deploy to server\", \"\u8dd1\u5b9e\u9a8c\", or needs to launch training jobs."
---

# Run Experiment

Deploy and run ML experiment: $ARGUMENTS

## Workflow

### Step 1: Detect Environment

Read the project's `AGENTS.md` to determine the experiment environment:

- **Local GPU**: Look for local CUDA/MPS setup info
- **Remote server**: Look for SSH alias, conda env, code directory
- **Vast.ai instance**: Look for `gpu: vast`, `vast_instance`, SSH host/port, remote path, and optional `auto_destroy`
- **Modal serverless**: Look for `gpu: modal`, app/function name, image/dependency setup, and secrets

If no server info is found in `AGENTS.md`, ask the user.

**Environment contract** (`../shared-references/compute-env-contract.md`): read
existing server notes or the provider's ledger before preparing the environment.
Reuse the user's confirmed conda/venv and working command; a missing ARIS ledger
does not require rebuilding. If no relevant validation exists, run one small,
task-relevant smoke in that environment and record the command and actual output.
Reuse prior validation when the environment and execution path have not changed.
New or rebuilt environments need the spec, import/kernel checks and a fresh
agent-follows-doc pass once setup is stable; substantive installation or invocation
changes need the affected checks. Plain prose/log edits do not trigger a rebuild
or fresh recheck. This execution evidence does not replace research acceptance.

**Preparation failures:** carry the same failure, attempted fixes and remaining
budget across child skills in the existing run notes/tracker. After two targeted
repairs to the same environment problem make no new progress, stop repeating
preparation and return the exact command/error to the main owner for takeover or
an authorized alternative. Missing permissions, authentication, network access or
a compatible driver are environment prerequisites, not reasons to rewrite the
training script. Keep the original code-sanity retry budget and reviewer gates.

### Step 2: Pre-flight Check

Check GPU availability on the target machine:

**Remote:**
```bash
ssh <server> nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
```

**Local:**
```bash
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
# or for Mac MPS:
python -c "import torch; print('MPS available:', torch.backends.mps.is_available())"
```

Free GPU = memory.used < 500 MiB.

### Step 3: Sync Code (Remote Only)

Check the project's `AGENTS.md` for a `code_sync` setting. If not specified, default to `rsync`.

#### Option A: rsync (default)

Prefer the project's existing deployment command or explicit file list. Otherwise,
allow directory traversal and include the configuration/small resources read by
the actual experiment command, alongside Python sources. For example:

```bash
rsync -avz --prune-empty-dirs \
  --exclude='.*' --exclude='__pycache__/' --exclude='/venv/' --exclude='/env/' \
  --exclude='data/' --exclude='datasets/' --exclude='weights/' \
  --exclude='checkpoints/' --exclude='outputs/' --exclude='wandb/' \
  --include='*/' --include='*.py' \
  --include='/configs/sanity.json' --include='/assets/vocab.json' \
  --exclude='*' "<local_src>/" "<server>:<remote_dst>/"
```

Replace the two explicit config/resource paths with those your command needs;
add other required small files explicitly. Keep exclusions before directory/file
includes, and add project-specific private paths there. Hidden agent/config files,
data, weights and outputs stay out of this example. Use the project source root,
not the user's home directory; do not replace these rules with an unfiltered copy.
A successful sync exit is not a launch check: run the smallest actual experiment
from the configured remote code directory and inspect its log and result file.

#### Option B: git (when `code_sync: git` is set in AGENTS.md)

Push local changes to remote repo, then pull on the server:
```bash
# 1. Push from local
git add -A && git commit -m "sync: experiment deployment" && git push

# 2. Pull on server
ssh <server> "cd <remote_dst> && git pull"
```

Benefits: version-tracked, multi-server sync with one push, no rsync include/exclude rules needed.

#### Option C: Vast.ai instance

If `gpu: vast` is configured, treat the Vast.ai machine as a remote server with an explicit lifecycle:

1. Verify the instance is running and reachable.
2. Sync code to the configured remote path.
3. Confirm data/checkpoints are already mounted or intentionally copied.
4. Record the instance id in the launch summary for later cleanup.

Do not silently ignore a requested Vast.ai route. If Vast.ai CLI credentials or instance metadata are missing, stop and ask the user to configure them.

### Step 3.5: W&B Integration (when `wandb: true` in AGENTS.md)

**Skip this step entirely if `wandb` is not set or is `false` in AGENTS.md.**

Before deploying, ensure the experiment scripts have W&B logging:

1. **Check if wandb is already in the script** — look for `import wandb` or `wandb.init`. If present, skip to Step 4.

2. **If not present, add W&B logging** to the training script:
   ```python
   import wandb
   wandb.init(project=WANDB_PROJECT, name=EXP_NAME, config={...hyperparams...})

   # Inside training loop:
   wandb.log({"train/loss": loss, "train/lr": lr, "step": step})

   # After eval:
   wandb.log({"eval/loss": eval_loss, "eval/ppl": ppl, "eval/accuracy": acc})

   # At end:
   wandb.finish()
   ```

3. **Metrics to log** (add whichever apply to the experiment):
   - `train/loss` — training loss per step
   - `train/lr` — learning rate
   - `eval/loss`, `eval/ppl`, `eval/accuracy` — eval metrics per epoch
   - `gpu/memory_used` — GPU memory (via `torch.cuda.max_memory_allocated()`)
   - `speed/samples_per_sec` — throughput
   - Any custom metrics the experiment already computes

4. **Verify wandb login on the target machine:**
   ```bash
   ssh <server> "wandb status"  # should show logged in
   # If not logged in:
   ssh <server> "wandb login <WANDB_API_KEY>"
   ```

> The W&B project name and API key come from `AGENTS.md` (see example below). The experiment name is auto-generated from the script name + timestamp.

### Step 4: Deploy

#### Remote (via SSH + screen)

For each experiment, create a dedicated screen session with GPU binding:
```bash
ssh <server> "screen -dmS <exp_name> bash -c '\
  eval \"\$(<conda_path>/conda shell.bash hook)\" && \
  conda activate <env> && \
  CUDA_VISIBLE_DEVICES=<gpu_id> python <script> <args> 2>&1 | tee <log_file>'"
```

#### Vast.ai instance

Use the same SSH + screen pattern, but include the Vast.ai instance id, public SSH endpoint, and remote working directory in the report. If `auto_destroy: true`, write a cleanup command to the run notes before launch.

Record the estimated hourly cost, expected run duration, and cleanup owner. If the command fails to start or the instance becomes unreachable, do not relaunch blindly; capture logs and ask for a rescue / second opinion before spending more GPU time.

#### Modal (serverless)

If `gpu: modal` is configured, deploy through Modal instead of SSH:

```bash
modal run <module_or_app>.py -- <args>
```

Before launch, verify required secrets, volumes, image dependencies, and output persistence. If Modal is requested but the project lacks Modal configuration, stop and ask the user to configure it rather than falling back to local execution.

Record the Modal app/function name, GPU type, timeout, mounted volumes, and where results will be stored. If Modal reports an image, secret, or volume error, preserve the exact error and run a configuration fix before retrying.

#### Local

```bash
# Linux with CUDA
CUDA_VISIBLE_DEVICES=<gpu_id> python <script> <args> 2>&1 | tee <log_file>

# Mac with MPS (PyTorch uses MPS automatically)
python <script> <args> 2>&1 | tee <log_file>
```

For local long-running jobs, use `run_in_background: true` to keep the conversation responsive.

### Step 5: Verify Launch

**Remote:**
```bash
ssh <server> "screen -ls"
```

**Local:**
Check process is running and GPU is allocated.

### Step 6: Feishu Notification (if configured)

After deployment is verified, check `~/.codex/feishu.json`:
- Send `experiment_done` notification: which experiments launched, which GPUs, estimated time
- If config absent or mode `"off"`: skip entirely (no-op)

### Step 7: Auto-Destroy Vast.ai Instance (when `gpu: vast` and `auto_destroy: true`)

Only run this after the experiment has completed and results/logs/checkpoints have been copied or otherwise persisted.

1. Verify the target process has exited.
2. Copy result files and logs to the configured durable location.
3. Ask for confirmation unless AGENTS.md explicitly says `auto_destroy: true`.
4. Destroy only the recorded instance id for this run.

If any artifact copy fails, do not destroy the instance.

## Key Rules

- ALWAYS check GPU availability first — never blindly assign GPUs
- Each experiment gets its own screen session + GPU (remote) or background process (local)
- Use `tee` to save logs for later inspection
- Run deployment commands with `run_in_background: true` to keep conversation responsive
- Report back: which GPU, which screen/process, what command, estimated time
- If multiple experiments, launch them in parallel on different GPUs

## AGENTS.md Example

Users should add their server info to their project's `AGENTS.md`:

```markdown
## Remote Server
- SSH: `ssh my-gpu-server`
- GPU: 4x A100 (80GB each)
- Conda: `eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- Code dir: `/home/user/experiments/`
- code_sync: rsync          # default. Or set to "git" for git push/pull workflow
- wandb: false              # set to "true" to auto-add W&B logging to experiment scripts
- wandb_project: my-project # W&B project name (required if wandb: true)
- wandb_entity: my-team     # W&B team/user (optional, uses default if omitted)

## Vast.ai
- gpu: vast
- vast_instance: 123456
- SSH: `ssh -p 12345 root@ssh.vast.ai`
- Code dir: `/workspace/experiments/`
- auto_destroy: false

## Modal
- gpu: modal
- modal_app: `train.py`
- modal_secrets: `wandb-secret`
- modal_volume: `experiment-results`

## Local Environment
- Mac MPS / Linux CUDA
- Conda env: `ml` (Python 3.10 + PyTorch)
```

> **W&B setup**: Run `wandb login` on your server once (or set `WANDB_API_KEY` env var). The skill reads project/entity from `AGENTS.md` and adds `wandb.init()` + `wandb.log()` to your training scripts automatically. Dashboard: `https://wandb.ai/<entity>/<project>`.
