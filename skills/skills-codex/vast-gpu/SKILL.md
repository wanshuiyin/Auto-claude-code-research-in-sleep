---
name: vast-gpu
description: "Rent, manage, and destroy GPU instances on vast.ai. Use when user says \"rent gpu\", \"vast.ai\", \"rent a server\", \"cloud gpu\", or needs on-demand GPU without owning hardware."
argument-hint: [task-description or action]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent
---

# Vast.ai GPU Management

Manage vast.ai GPU instance: $ARGUMENTS

## Overview

Rent cheap, capable GPUs from vast.ai on demand. This skill **analyzes the training task** to determine GPU requirements, searches for the best-value offers, presents options with estimated total cost, and handles the full lifecycle: rent → setup → run → destroy.

Users do NOT specify GPU models or hardware. They describe the task — the skill figures out what to rent.

**Prerequisites:** The `vastai` CLI must be installed (requires **Python ≥ 3.10**) and authenticated:
```bash
pip install vastai
vastai set api-key YOUR_API_KEY
```

> If your system Python is < 3.10, create a virtual environment with Python ≥ 3.10 (e.g., `conda create`, `pyenv`, `uv venv`, etc.) and install `vastai` there.

SSH public key **must be uploaded at https://cloud.vast.ai/manage-keys/ BEFORE creating any instance**. Keys are baked into instances at creation time — if you add a key after renting, you must destroy and re-create the instance.

## State File

All active vast.ai instances are tracked in `vast-instances.json` at the project root:
```json
[
  {
    "instance_id": 33799165,
    "offer_id": 25831376,
    "gpu_name": "RTX_3060",
    "num_gpus": 1,
    "dph": 0.0414,
    "ssh_url": "ssh://root@1.208.108.242:58955",
    "ssh_host": "1.208.108.242",
    "ssh_port": 58955,
    "created_at": "2026-03-29T21:12:00Z",
    "status": "running",
    "experiment": "exp01_baseline",
    "estimated_hours": 4.0,
    "estimated_cost": 0.17
  }
]
```

This file is the source of truth for `/run-experiment` and `/monitor-experiment` to connect to vast.ai instances.

## Workflow

### Action: Provision (default)

Analyze the task, find the best GPU, and present cost-optimized options. This is the main entry point — called directly or automatically by `/run-experiment` when `gpu: vast` is set.

**Step 1: Analyze Task Requirements**

Read available context to determine what the task needs:

1. **From the experiment plan** (`refine-logs/EXPERIMENT_PLAN.md`):
   - Compute budget (total GPU-hours)
   - Hardware hints (e.g., "4x RTX 3090")
   - Model architecture and dataset size
   - Run order and per-milestone cost estimates

2. **From experiment scripts** (if already written):
   - Model size — scan for model class, `num_parameters`, config files
   - Batch size, sequence length — estimate VRAM from these
   - Dataset — estimate training time from dataset size + epochs
   - Multi-GPU — check for `DataParallel`, `DistributedDataParallel`, `accelerate`, `deepspeed`

3. **From user description** (if no plan/scripts exist):
   - Model name/size (e.g., "fine-tune LLaMA-7B", "train ResNet-50")
   - Dataset scale (e.g., "ImageNet", "10k samples")
   - Estimated duration (e.g., "about 2 hours")

**Step 2: Determine GPU Requirements**

Based on the task analysis, determine:

| Factor | How to estimate |
|--------|----------------|
| **Min VRAM** | Model params × 4 bytes (fp32) or × 2 (fp16/bf16) + optimizer states + activations. Rules of thumb: 7B model ≈ 16 GB (fp16), 13B ≈ 28 GB, 70B ≈ 140 GB (needs multi-GPU). ResNet/ViT ≈ 4-8 GB. Add 20% headroom. |
| **Num GPUs** | 1 unless: model doesn't fit in single GPU VRAM, or scripts use DDP/FSDP/DeepSpeed, or plan specifies multi-GPU |
| **Est. hours** | From experiment plan's cost column, or: (dataset_size × epochs) / (throughput × batch_size). Default to user estimate if available. Add 30% buffer for setup + unexpected slowdowns |
| **Min disk** | 20 GB base + model checkpoint size + dataset size. Default: 50 GB |
| **CUDA version** | Match PyTorch version. PyTorch 2.x needs CUDA ≥ 11.8. Default: 12.1 |

**Step 3: Search Offers**

Search across multiple GPU tiers to find the best value. Always search broadly — do NOT limit to one GPU model:

```bash
# Tier 1: Budget GPUs (good for small models, fine-tuning, ablations)
vastai search offers "gpu_ram>=<MIN_VRAM> num_gpus>=<N> reliability>0.95 inet_down>100" -o 'dph+' --storage <DISK> --limit 10

# Tier 2: If VRAM > 24 GB, also search high-VRAM cards specifically
vastai search offers "gpu_ram>=48 num_gpus>=<N> reliability>0.95" -o 'dph+' --storage <DISK> --limit 5
```

The output is a table with columns: `ID`, `CUDA`, `N` (GPU count), `Model`, `PCIE`, `cpu_ghz`, `vCPUs`, `RAM`, `Disk`, `$/hr`, `DLP` (deep learning perf), `score`, `NV Driver`, `Net_up`, `Net_down`, `R` (reliability %), `Max_Days`, `mach_id`, `status`, `host_id`, `ports`, `country`.

The **first column (`ID`)** is the offer ID needed for `vastai create instance`.

**Step 4: Present Cost-Optimized Options**

Present **3 options** to the user, ranked by estimated total cost:

```
Task analysis:
- Model: [model name/size] → estimated VRAM: ~[X] GB
- Training: ~[Y] hours estimated
- Requirements: [N] GPU(s), ≥[X] GB VRAM, ~[Z] GB disk

Recommended options (sorted by estimated total cost):

| # | GPU          | VRAM  | $/hr   | Est. Hours | Est. Total | Reliability | Offer ID  |
|---|-------------|-------|--------|------------|------------|-------------|-----------|
| 1 | RTX 3060    | 12 GB | $0.04  | ~6h        | ~$0.25     | 99.4%       | 25831376  |  ← cheapest
| 2 | RTX 4090    | 24 GB | $0.28  | ~4h        | ~$1.12     | 99.2%       | 6995713   |  ← best value
| 3 | A100 SXM    | 80 GB | $0.95  | ~2h        | ~$1.90     | 99.5%       | 7023456   |  ← fastest

Option 1 is cheapest overall. Option 3 finishes fastest.
Pick a number (or type a different offer ID):
```

**Key presentation rules:**
- Always show **estimated total cost** ($/hr × estimated hours), not just $/hr
- Faster GPUs have shorter estimated hours (scale by relative FLOPS)
- Flag if a cheap option has reliability < 0.97 ("budget pick — 3% chance of interruption")
- If task is small (<1 hour), recommend interruptible pricing for even lower cost
- If no offers meet VRAM requirements, explain why and suggest alternatives (e.g., multi-GPU, quantization)

**Relative speed scaling (approximate, for estimating hours across GPU tiers):**

| GPU | Relative Speed (FP16) |
|-----|-----------------------:|
| RTX 3060 | 0.5× |
| RTX 3090 | 1.0× |
| RTX 4090 | 1.6× |
| A5000 | 0.9× |
| A6000 | 1.1× |
| L40S | 1.5× |
| A100 SXM | 2.0× |
| H100 SXM | 3.3× |

Use these to scale the base estimated hours across offers.

### Action: Rent

Create an instance from a user-selected offer.

**Step 1: Create Instance**

```bash
vastai create instance <OFFER_ID> \
  --image <DOCKER_IMAGE> \
  --disk <DISK_GB> \
  --ssh \
  --direct \
  --onstart-cmd "apt-get update && apt-get install -y git screen rsync"
```

Default Docker image: `pytorch/pytorch:2.1.0-cuda12.1-cudnn8-devel` (override via `AGENTS.md` `image:` field if set).

The output looks like:
```
Started. {'success': True, 'new_contract': 33799165, 'instance_api_key': '...'}
```

The **`new_contract` value is the instance ID** — save this for all subsequent commands.

**Step 2: Wait for Instance Ready**

Poll instance status every 20 seconds until it's running (typically takes 30-60 seconds, max ~5 minutes):
```bash
vastai show instances --raw | python3 -c "
import sys, json
instances = json.load(sys.stdin)
for inst in instances:
    if inst['id'] == <INSTANCE_ID>:
        print(inst['actual_status'])
"
```

Wait states: `loading` → `running`. If stuck in `loading` for >5 minutes, warn the user — the host may be slow or the image may be large.

**Step 3: Get SSH Connection Details**

```bash
vastai ssh-url <INSTANCE_ID>
```

This returns a URL in the format: `ssh://root@<HOST>:<PORT>`

Parse out host and port from this URL. Example:
- Input: `ssh://root@1.208.108.242:58955`
- Host: `1.208.108.242`, Port: `58955`

> **Important:** Always use `vastai ssh-url` to get connection details — do NOT rely on `ssh_host`/`ssh_port` from `vastai show instances`, as those may point to proxy servers that differ from the direct connection endpoint.

**Step 4: Verify SSH Connectivity**

```bash
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p <PORT> root@<HOST> "nvidia-smi && echo 'CONNECTION_OK'"
```

If SSH fails with "Permission denied (publickey)":
- The user's SSH key was not uploaded to https://cloud.vast.ai/manage-keys/ **before** the instance was created
- **Fix:** Destroy this instance, have user upload their key, then create a new instance. Keys are baked in at creation time — there is no way to add keys to a running instance.

If SSH fails with "Connection refused":
- The instance may still be initializing. Retry up to 3 times with 15-second intervals.

**Step 5: Update State File**

Write/update `vast-instances.json` with the new instance details including the `ssh_url` from Step 3, estimated hours and cost.

**Step 6: Report**

```
Vast.ai instance ready:
- Instance ID: <ID>
- GPU: <GPU_NAME> x <NUM_GPUS>
- Cost: $<DPH>/hr (estimated total: ~$<TOTAL>)
- SSH: ssh -p <PORT> root@<HOST>
- Docker: <IMAGE>

To deploy: /run-experiment (will auto-detect this instance)
To destroy when done: /vast-gpu destroy <ID>
```

### Action: Setup

Set up the rented instance for a specific experiment. Called automatically by `/run-experiment` when targeting a vast.ai instance.

**Step 1: Install Dependencies**

```bash
ssh -p <PORT> root@<HOST> "pip install -q wandb tensorboard scipy scikit-learn pandas"
```

If a `requirements.txt` exists in the project, install that instead:
```bash
scp -P <PORT> requirements.txt root@<HOST>:/workspace/
ssh -p <PORT> root@<HOST> "pip install -q -r /workspace/requirements.txt"
```

> Note: `scp` uses uppercase `-P` for port, while `ssh` uses lowercase `-p`.

**Step 2: Sync Code**

```bash
rsync -avz -e "ssh -p <PORT>" \
  --include='*.py' --include='*.yaml' --include='*.yml' --include='*.json' \
  --include='*.txt' --include='*.sh' --include='*/' \
  --exclude='*.pt' --exclude='*.pth' --exclude='*.ckpt' \
  --exclude='__pycache__' --exclude='.git' --exclude='data/' \
  --exclude='wandb/' --exclude='outputs/' \
  ./ root@<HOST>:/workspace/project/
```

**Step 3: Verify Setup**

```bash
ssh -p <PORT> root@<HOST> "cd /workspace/project && python -c 'import torch; print(f\"PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}, GPUs: {torch.cuda.device_count()}\")'"
```

Expected output: `PyTorch 2.1.0, CUDA: True, GPUs: 1` (or more GPUs if multi-GPU instance).

### Action: Destroy

Tear down a vast.ai instance to stop billing.

**Step 1: Confirm Results Collected**

Before destroying, check if there are experiment results to download:
```bash
ssh -p <PORT> root@<HOST> "ls /workspace/project/results/ 2>/dev/null || echo 'NO_RESULTS_DIR'"
```

If results exist, download them first:
```bash
rsync -avz -e "ssh -p <PORT>" root@<HOST>:/workspace/project/results/ ./results/
```

Also download logs:
```bash
scp -P <PORT> root@<HOST>:/workspace/*.log ./logs/ 2>/dev/null
```

**Step 2: Destroy Instance**

```bash
vastai destroy instance <INSTANCE_ID>
```

Output: `destroying instance <INSTANCE_ID>.`

> Destruction is **irreversible** — all data on the instance is permanently deleted.

**Step 3: Update State File**

Remove the instance from `vast-instances.json` or mark its status as `destroyed`.

**Step 4: Report Cost**

Calculate actual cost based on creation time and $/hr:
```
Instance <ID> destroyed.
- Duration: ~X.X hours
- Actual cost: ~$X.XX (estimated was $Y.YY)
- Results downloaded to: ./results/
```

### Action: List

Show all active vast.ai instances:
```bash
vastai show instances
```

Cross-reference with `vast-instances.json` for experiment associations.

### Action: Destroy All

Tear down all active instances (use after all experiments complete):

1. Download results from each instance
2. Destroy all instances
3. Clear `vast-instances.json`
4. Report total cost

## Key Rules

- **Task-driven selection** — NEVER ask users to pick GPU models. Analyze the task, estimate requirements, present cost-optimized options with total price
- **ALWAYS destroy instances when experiments are done** — vast.ai bills per second, leaving instances running wastes money
- **Download results before destroying** — data is lost permanently on destroy
- **Prefer on-demand pricing** for short experiments (<2 hours). Suggest interruptible/bid pricing for long runs (>4 hours) with checkpointing
- **Check reliability > 0.95** — unreliable hosts may crash mid-training
- **Use `--direct` SSH** when creating instances — faster than proxy SSH
- **Always use `vastai ssh-url <ID>`** to get connection details — the host/port from `show instances` may differ
- **SSH keys must be uploaded BEFORE creating instances** — keys are baked in at creation time. If SSH fails with "Permission denied", destroy and recreate after adding the key
- **Default Docker image**: `pytorch/pytorch:2.1.0-cuda12.1-cudnn8-devel` unless user specifies otherwise
- **Working directory on instance**: `/workspace/` (Docker default). Code syncs to `/workspace/project/`
- **State file `vast-instances.json` must stay up to date** — other skills depend on it
- **Show estimated total cost, not just $/hr** — a $0.90/hr GPU that finishes in 2h ($1.80) beats a $0.30/hr GPU that takes 8h ($2.40)
- **`vastai` CLI requires Python ≥ 3.10** — if system Python is older, use a conda env

## AGENTS.md Example

Users only need to set `gpu: vast` — no hardware preferences required:

```markdown
## Vast.ai
- gpu: vast                  # tells run-experiment to use vast.ai
- auto_destroy: true         # auto-destroy after experiment completes (default: true)
- max_budget: 5.00           # optional: max total $ to spend (skill warns if estimate exceeds this)
- image: pytorch/pytorch:2.1.0-cuda12.1-cudnn8-devel  # optional: override Docker image
```

The skill analyzes experiment scripts and plans to determine what GPU to rent. No need to specify GPU model, VRAM, or instance count.

## Composing with Other Skills

```
/run-experiment "train model"       ← detects gpu: vast, calls /vast-gpu provision
  ↳ /vast-gpu provision             ← analyzes task, presents options with cost
  ↳ user picks option               ← rent + setup + deploy
  ↳ /vast-gpu destroy               ← auto-destroy when done (if auto_destroy: true)

/vast-gpu provision                 ← manual: analyze task + show options
/vast-gpu rent <offer_id>           ← manual: rent a specific offer
/vast-gpu list                      ← show active instances
/vast-gpu destroy <instance_id>     ← tear down, stop billing
/vast-gpu destroy-all               ← tear down everything
```
