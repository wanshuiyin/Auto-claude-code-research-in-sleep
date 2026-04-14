---
name: qzcli
description: Manage GPU compute jobs on the Qizhi (启智) platform using qzcli — a kubectl-style CLI tool. Use when user says "qzcli", "启智平台", "submit job", "stop job", "查计算组", "avail", "list jobs", "batch submit", or needs to manage distributed training jobs on a Qizhi instance.
argument-hint: [login|avail|list|create|stop <job-id>|batch|status|watch]
allowed-tools: Bash(*), Read, Write
---

# qzcli — 启智平台任务管理

A kubectl/docker-style CLI for managing GPU compute jobs on the Qizhi (启智) platform.

**GitHub:** [tianyilt/qzcli_tool](https://github.com/tianyilt/qzcli_tool)

## Installation

```bash
pip install rich requests prompt_toolkit mcp
git clone https://github.com/tianyilt/qzcli_tool
cd qzcli_tool && pip install -e .
```

### MCP Integration (optional)

To use qzcli as an MCP tool directly from Claude Code or Codex:

```bash
# Claude Code
claude mcp add qzcli -- qzcli-mcp

# Codex
codex mcp add qzcli -- qzcli-mcp
```

---

## Configuration

Credentials are read in this priority order:
`CLI args > --password-stdin > env vars > QZCLI_ENV_FILE (.env) > ~/.qzcli/config.json > interactive input`

```bash
# Option A: env file (recommended)
mkdir -p ~/.qzcli
cat > ~/.qzcli/.env <<'EOF'
QZCLI_USERNAME="your_username"
QZCLI_PASSWORD="your_password"
EOF

# Option B: environment variables
export QZCLI_USERNAME="your_username"
export QZCLI_PASSWORD="your_password"
export QZCLI_API_URL="https://qz.yourorg.edu.cn"
```

Config files are stored in `~/.qzcli/`: `config.json`, `.cookie`, `resources.json`, `jobs.json`.

---

## Quick Start

```bash
# 1. Login
qzcli login

# 2. Discover and cache workspaces/compute groups (run once, re-run after joining new workspaces)
qzcli res -u

# 3. Check available nodes
qzcli avail

# 4. List running jobs
qzcli ls -c -r
```

---

## Authentication

```bash
# Interactive login
qzcli login

# With credentials
qzcli login -u YOUR_USERNAME -p 'YOUR_PASSWORD'

# Read password from stdin (for scripts)
echo 'YOUR_PASSWORD' | qzcli login -u YOUR_USERNAME --password-stdin

# Check current cookie
qzcli cookie --show

# Clear cookie
qzcli cookie --clear
```

**Note:** `qzcli avail` auto-refreshes the cookie if it expires and credentials are configured.

---

## Resource Discovery

```bash
# List cached workspaces
qzcli res --list

# Refresh all workspace resource cache (run this first!)
qzcli res -u

# Refresh a specific workspace
qzcli res -w MY_WORKSPACE -u

# Set a human-readable alias for a workspace
qzcli res -w ws-xxxxxxxx --name "My Workspace"
```

---

## Check Available Nodes

```bash
# All workspaces
qzcli avail

# Including low-priority task nodes (slower but more accurate)
qzcli avail --lp

# Specific workspace
qzcli avail -w MY_WORKSPACE

# Find compute groups with N free nodes
qzcli avail -n 4

# Export IDs for scripting
qzcli avail -n 4 -e

# Show idle node names
qzcli avail -w MY_WORKSPACE -v
```

---

## Job Submission

### Interactive (recommended for first-time use)

```bash
# Full interactive selection: workspace → project → compute group → spec
qzcli create -i

# Interactive for a specific workspace only
qzcli create -i -w "My Workspace"
```

The TUI shows GPU type, availability, and spec status at each level. Press `Enter/→` to go deeper, `←` to go back.

### Non-interactive

```bash
# Using names (resolved from qzcli res cache)
qzcli create \
  --name "my-training-job" \
  --command "bash /path/to/train.sh" \
  --workspace "My Workspace" \
  --compute-group "My Compute Group" \
  --image YOUR_REGISTRY/team/image:tag \
  --instances 4 \
  --priority 10

# Using IDs directly
qzcli create \
  --name "my-job" \
  --command "bash /path/to/train.sh" \
  --workspace ws-YOUR_WORKSPACE_ID \
  --compute-group lcg-YOUR_LCG_ID \
  --spec YOUR_SPEC_ID \
  --image YOUR_REGISTRY/team/image:tag \
  --instances 4
```

**Key parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--name` / `-n` | required | Job name |
| `--command` / `-c` | required | Command to run |
| `--workspace` / `-w` | | Workspace name or ID (`ws-...`) |
| `--compute-group` / `-g` | auto | Compute group name or ID (`lcg-...`) |
| `--spec` / `-s` | auto | Resource spec ID |
| `--image` / `-m` | | Docker image |
| `--instances` | 1 | Number of instances |
| `--shm` | 1200 | Shared memory (GiB) |
| `--priority` | 10 | Priority (1–10) |
| `--dry-run` | | Preview only, don't submit |
| `--json` | | JSON output for scripting |

```bash
# Preview before submitting
qzcli create --name test --command "echo hi" --workspace "My Workspace" \
  --image YOUR_IMAGE --dry-run
```

### Env-var passthrough (for existing submission scripts)

```bash
# Pass vars directly — do NOT use "export VAR; bash script.sh"
WORKSPACE_ID="ws-YOUR_WORKSPACE_ID" \
LCG_ID="lcg-YOUR_LCG_ID" \
SPEC_ID="YOUR_SPEC_ID" \
CHECKPOINT_DIR="/path/to/checkpoint" \
bash YOUR_SUBMIT_SCRIPT.sh
```

### HPC / CPU jobs (Slurm)

```bash
qzcli hpc \
  --name "my-cpu-job" \
  --workspace ws-YOUR_WORKSPACE_ID \
  --compute-group lcg-YOUR_LCG_ID \
  --predef-quota-id YOUR_QUOTA_ID \
  --cpu 55 --mem-gi 300 --instances 30 \
  --image YOUR_REGISTRY/team/cpu-image:tag \
  --entrypoint "cd /path/to/dir && bash run.sh"
```

---

## Batch Submission

```bash
# Submit from config file
qzcli batch batch_config.json --delay 3

# Preview all jobs
qzcli batch batch_config.json --dry-run

# Continue on error
qzcli batch batch_config.json --continue-on-error
```

**Config format** (`batch_config.json`):

```json
{
  "defaults": {
    "workspace": "ws-YOUR_WORKSPACE_ID",
    "compute_group": "lcg-YOUR_LCG_ID",
    "spec": "YOUR_SPEC_ID",
    "image": "YOUR_REGISTRY/team/image:tag",
    "instances": 4,
    "priority": 10
  },
  "matrix": {
    "checkpoint": ["/path/to/ckpt1", "/path/to/ckpt2"],
    "step": [50000, 100000]
  },
  "name_template": "eval-{checkpoint_basename}-step{step}",
  "command_template": "bash eval.sh --checkpoint {checkpoint} --step {step}"
}
```

Matrix keys are Cartesian-producted (2×2 = 4 jobs above). Use `{key_basename}` for path basenames.

### Shell loop (alternative)

```bash
for step in 040000 050000 060000; do
  qzcli create \
    --name "eval-step${step}" \
    --command "bash eval.sh --step $step" \
    --workspace "My Workspace" \
    --compute-group "My Compute Group" \
    --instances 4
  sleep 3
done
```

---

## Job Management

```bash
# List jobs
qzcli ls -c -w MY_WORKSPACE          # specific workspace
qzcli ls -c --all-ws                 # all workspaces
qzcli ls -c -w MY_WORKSPACE -r       # running only
qzcli ls -c -w MY_WORKSPACE -n 50    # show 50

# Stop a job
qzcli stop JOB_ID

# Job status / details
qzcli status JOB_ID

# Watch all running jobs (refresh every 10s)
qzcli watch -i 10

# Workspace view with GPU utilization
qzcli ws
qzcli ws -a           # all projects
qzcli ws -p "My Project"
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Cookie expired | Session gap | Re-run `qzcli login` |
| `未找到名称为 'xxx' 的工作空间` | Stale cache | Run `qzcli res -u` |
| No resources in `create -i` | Cache empty | Run `qzcli login && qzcli res -u` |
| `qzcli-mcp` not found | Not installed | `cd qzcli_tool && pip install -e .` |
| Spec not in workspace | ID mismatch | Match spec ID to the correct workspace |
| Silent job failure | Script `sys.exit(0)` | Check job logs directly |
| zsh glob errors | Remote shell is zsh | Wrap commands in `bash -c` or use Python |
