# 🖥️ GPU Setup for Auto-Experiments

> [← back to README](../README.md#gpu-server-setup) · declare your GPU server in CLAUDE.md so ARIS can run experiments for you.

When GPT-5.6-Sol says "run an ablation study" or "add a baseline comparison", Claude Code automatically writes the experiment script and deploys it to your GPU server. For this to work, Claude Code needs to know your server environment.

Three GPU modes are supported — pick one and add it to your project's `CLAUDE.md`:

#### Option A: Remote SSH Server (`gpu: remote`)

```markdown
## Remote Server
- gpu: remote
- SSH: `ssh my-gpu-server` (key-based auth, no password)
- GPU: 4x A100
- Conda env: `research` (Python 3.10 + PyTorch)
- Activate: `eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- Code directory: `/home/user/experiments/`
- Use `screen` for background jobs: `screen -dmS exp0 bash -c '...'`
```

Claude Code reads this and knows how to SSH in, activate the environment, and launch experiments. GPT-5.6-Sol (the reviewer) only decides **what** experiments to run — Claude Code figures out **how** based on your `CLAUDE.md`.

#### Option B: Local GPU (`gpu: local`)

If you are already on the GPU server, you can add the following to your `CLAUDE.md`:
```markdown
## GPU Environment
- gpu: local
- This machine has direct GPU access (no SSH needed)
- GPU: 4x A100 80GB
- Experiment environment: `YOUR_CONDA_ENV` (Python 3.x + PyTorch)
- Activate before any Python command: `The command to activate your experiment environment` (uv, conda, etc.)
- Code directory: `/home/YOUR_USERNAME/YOUR_CODE_DIRECTORY/`
```

#### Option C: Vast.ai On-Demand GPU (`gpu: vast`)

No GPU? Rent one from [Vast.ai](https://vast.ai) on demand. ARIS analyzes your training task (model size, dataset, time), finds the cheapest GPU that fits, ranks options by **total cost** (not just $/hr), then rents → runs → collects → destroys automatically.

Drop this in `CLAUDE.md`:

```markdown
## Vast.ai
- gpu: vast                  # rent on-demand GPU from vast.ai
- auto_destroy: true         # auto-destroy after experiment completes (default)
- max_budget: 5.00           # optional: warn if estimated cost exceeds this
```

**📖 Full setup guide → [integrations/VAST_GPU_GUIDE.md](integrations/VAST_GPU_GUIDE.md)** covers:
- Account + `vastai` CLI install + API key + SSH key prerequisites (5 steps)
- How ARIS picks GPUs and shows a live cost-ranked table
- Manual rental via `/vast-gpu` (list / rent / destroy)
- Typical cost expectations (~$0.30-2 for ablations on RTX 4090, ~$2-10 for A100/H100 baselines)
- When `gpu: vast` is preferable to `gpu: remote` / `gpu: local`

**No server at all?** The review and rewriting skills still work without GPU access. Only experiment-related fixes will be skipped (flagged for manual follow-up).
