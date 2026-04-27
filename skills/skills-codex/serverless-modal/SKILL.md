---
name: serverless-modal
description: "Run GPU workloads on Modal — training, fine-tuning, inference, batch processing. Zero-config serverless: no SSH, no Docker, auto scale-to-zero. Use when user says \"modal run\", \"modal training\", \"modal inference\", \"deploy to modal\", \"need a GPU\", \"run on modal\", \"serverless GPU\", or needs remote GPU compute."
argument-hint: [task-description]
allowed-tools: Bash(*), Read, Grep, Glob, Edit, Write, Agent
---

# Modal Cloud GPU — Training & Inference

Task: $ARGUMENTS

## Overview

**Modal** is a serverless GPU cloud. Key advantages over SSH-based platforms (vast.ai, remote servers):
- **Zero config**: no SSH, no Docker, no port forwarding. Write Python → `modal run` → done.
- **Auto scale-to-zero**: billing stops the instant your code finishes. No idle instances.
- **Local-first**: run `modal run` from your laptop. Code, data, and results stay local; only the GPU function runs remotely.
- **Reproducible environments**: dependencies declared in code via `modal.Image`, not system-level packages.

**Best for**: Users without a local GPU who need to debug CUDA code, run small-scale tests, or iterate quickly on experiments. The $5 free tier (no card) is enough for code debugging; $30 (with card) covers most small-scale experiment runs.

**Trade-off**: Modal costs more per GPU-hour than vast.ai or Lightning for some GPU tiers, but eliminates setup time and idle billing, often making it cheaper for short/medium workloads. For long training runs (>4 hours), consider vast.ai for lower $/hr.

## Authentication

```bash
pip install modal
modal setup          # Opens browser login, writes token to ~/.modal.toml
# Verify:
modal run -q 'print("ok")'
```

- Sign up: https://modal.com (GitHub/Google login)
- Free (no card): **$5/month** — enough for quick tests
- Free (with card): **$30/month** — bind a payment method at https://modal.com/settings for the full free tier. Set a **workspace spending limit** to prevent accidental overcharge (Settings → Usage → Spending Limit)
- Academic: apply for $10k credits | Startups: apply for $25k credits
- Secrets: `modal secret create huggingface-secret HF_TOKEN=hf_xxxxx`

> **Recommended setup**: Bind a card to unlock $30/month, then immediately set a spending limit (e.g., $30) so you never exceed the free tier. Modal will pause your workloads when the limit is hit.
>
> **SECURITY WARNING**: Always bind your card and set spending limits directly on https://modal.com/settings in your browser. NEVER enter payment information, card numbers, or billing details through Codex, Claude Code, or any CLI tool. Only the official Modal website is safe for payment operations.

## Pricing (source: modal.com/pricing, per-second billing)

| GPU | $/sec | ≈$/hr | VRAM | Bandwidth GB/s | Free budget → hours |
|---|---|---|---|---|---|
| T4 | $0.000164 | $0.59 | 16GB | 300 | ~8.5 hr ($5) / 50.8 hr ($30) |
| L4 | $0.000222 | $0.80 | 24GB | 300 | ~6.3 hr / 37.5 hr |
| A10 | $0.000306 | $1.10 | 24GB | 600 | ~4.5 hr / 27.3 hr |
| L40S | $0.000542 | $1.95 | 48GB | 864 | ~2.6 hr / 15.4 hr |
| A100-40GB | $0.000583 | $2.10 | 40GB | 1555 | ~2.4 hr / 14.3 hr |
| A100-80GB | $0.000694 | $2.50 | 80GB | 2039 | ~2.0 hr / 12.0 hr |
| H100 | $0.001097 | $3.95 | 80GB | 3352 | ~1.3 hr / 7.6 hr |
| H200 | $0.001261 | $4.54 | 141GB | 4800 | ~1.1 hr / 6.6 hr |
| B200 | $0.001736 | $6.25 | 192GB | 8000 | ~0.8 hr / 4.8 hr |

CPU: $0.047/core/hr | RAM: $0.008/GiB/hr (GPU typically 90%+ of total cost)

## !! Cost Estimation Required !!

Before EVERY run, estimate cost and show to user for confirmation.

Key insights:
- Inference bottleneck is **memory bandwidth**, not compute → high-bandwidth GPUs are often cheaper overall
- 7-8B BF16 inference needs **~22GB VRAM** (weights 15G + KV cache 1G + overhead), T4 (16GB) insufficient
- H100 is often **cheaper than L4** for benchmarks (11x faster but only 5x more expensive)

### Cost Estimation Template (required before every run)

```
Cost estimate (Modal):
  Model: [name] ([params], [precision])
  VRAM: ~[X]GB (weights + KV cache + overhead)
  GPU: [type] ([VRAM]GB, $[X]/sec = $[X]/hr, bandwidth [X] GB/s)
  Estimate: ~[N] min, ~$[X]
```

### 7-8B BF16 Benchmark Cost Comparison

| GPU | Speed tok/s | $/hr | 1000 samples x 200tok cost | Duration |
|---|---|---|---|---|
| **H100** | **224** | $3.95 | **$0.98** | **15 min** |
| A100-40GB | 104 | $2.10 | $1.12 | 32 min |
| L4 | 20 | $0.80 | $2.22 | 167 min |

## Workflow

### Step 1: Analyze Task → Estimate Cost → Choose GPU

Same analysis as any GPU skill — determine VRAM needs from model size, pick GPU, estimate hours, calculate cost. See pricing table above.

**VRAM Rules of Thumb:**
| Model Size | FP16 VRAM | Recommended GPU |
|---|---|---|
| ≤3B | ~8GB | T4, L4 |
| 7-8B | ~22GB | L4, A10, A100-40GB |
| 13B | ~30GB | L40S, A100-40GB |
| 30B | ~65GB | A100-80GB, H100 |
| 70B | ~140GB | H100:2, H200 |

### Step 2: Generate Modal Launcher

Based on the task type, generate the appropriate launcher script.

#### Pattern A: One-Shot GPU Function (training, evaluation, benchmark)

The most common pattern for `run-experiment` integration. Wraps an existing training script:

```python
import modal

app = modal.App("experiment-name")
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch", "transformers", "accelerate", "datasets", "wandb"
)

# Mount local project code into the container
local_code = modal.Mount.from_local_dir(".", remote_path="/workspace")
# Persistent volume for checkpoints and results
volume = modal.Volume.from_name("experiment-results", create_if_missing=True)

@app.function(
    image=image,
    gpu="A100-80GB",          # Chosen based on Step 1 analysis
    mounts=[local_code],
    volumes={"/results": volume},
    timeout=3600 * 6,         # 6 hours max
    secrets=[modal.Secret.from_name("wandb-secret")],  # Optional
)
def train():
    import subprocess
    subprocess.run(
        ["python", "train.py", "--output_dir", "/results/run_001"],
        cwd="/workspace",
        check=True,
    )
    volume.commit()  # Persist results to volume

@app.local_entrypoint()
def main():
    train.remote()
    print("Training complete. Results saved to Modal volume 'experiment-results'.")
```

Run: `modal run launcher.py`

#### Pattern B: Web API (persistent inference service)

```python
import modal

app = modal.App("inference-api")
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch", "transformers", "accelerate"
)

@app.cls(image=image, gpu="L40S")
@modal.concurrent(max_inputs=10)
class InferenceAPI:
    @modal.enter()
    def load_model(self):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3.2-1B")
        self.model = AutoModelForCausalLM.from_pretrained(
            "meta-llama/Llama-3.2-1B", device_map="auto"
        )

    @modal.fastapi_endpoint(method="POST")
    def generate(self, request: dict):
        inputs = self.tokenizer(request.get("prompt", ""), return_tensors="pt").to("cuda")
        outputs = self.model.generate(**inputs, max_new_tokens=256)
        return {"text": self.tokenizer.decode(outputs[0], skip_special_tokens=True)}
```

Deploy: `modal deploy app.py`

#### Pattern C: vLLM High-Performance Inference

```python
import modal, subprocess

app = modal.App("vllm-server")
image = modal.Image.debian_slim(python_version="3.11").pip_install("vllm")
VOLUME = modal.Volume.from_name("model-cache", create_if_missing=True)
MODEL = "Qwen/Qwen3-4B"

@app.function(image=image, gpu="H100", volumes={"/models": VOLUME}, timeout=3600)
@modal.concurrent(max_inputs=100)
@modal.web_server(port=8000)
def serve():
    subprocess.Popen(["python", "-m", "vllm.entrypoints.openai.api_server",
                      "--model", MODEL, "--download-dir", "/models", "--port", "8000"])
```

#### Pattern D: Batch Parallel (map over dataset)

```python
@app.function(image=image, gpu="T4", timeout=600)
def process_item(item: dict) -> dict:
    # ... process one item ...
    return {"result": "processed"}

@app.local_entrypoint()
def main():
    results = list(process_item.map([{"id": i} for i in range(1000)]))
```

#### Pattern E: LoRA Fine-Tuning

```python
@app.function(
    image=image, gpu="A100-80GB", volumes={"/output": volume},
    timeout=3600 * 6, secrets=[modal.Secret.from_name("huggingface-secret")],
)
def train():
    # ... transformers + peft + trl training code ...
    trainer.save_model("/output/final")
    volume.commit()
```

#### Pattern F: Multi-GPU Distributed Training

```python
@app.function(image=image, gpu="H100:4", volumes={"/output": volume}, timeout=3600 * 12)
def train_distributed():
    import subprocess
    subprocess.run(["accelerate", "launch", "--num_processes", "4",
                    "--mixed_precision", "bf16", "train.py"], check=True)
```

### Step 3: Run

```bash
modal run launcher.py     # One-shot execution (most common for experiments)
modal deploy app.py       # Persistent service deployment
```

### Step 4: Verify & Monitor

```bash
modal app list            # List running apps
modal app logs <app-name> # Stream logs
```

### Step 5: Collect Results

Results collection depends on the pattern used:

**Volume-based** (recommended for training):
```python
# Download results from volume after run completes
# Option A: In the launcher script, copy results to local mount before exit
# Option B: Use modal volume commands
modal volume ls experiment-results
modal volume get experiment-results /run_001/results.json ./results/
```

**Stdout/return-based** (for evaluation/benchmarks):
Results are printed to terminal or returned from the function — already local.

### Step 6: Cleanup

Modal auto-scales to zero — no manual instance destruction needed. But clean up unused resources:

```bash
modal app stop <app-name>     # Stop a deployed service
modal volume rm <volume-name> # Delete a volume when done
```

## CLI Reference

```bash
modal run app.py          # Run once
modal deploy app.py       # Deploy persistent service
modal app logs <app>      # View logs
modal app list            # List apps
modal app stop <app>      # Stop
modal volume ls           # List volumes
modal volume get <vol> <remote> <local>  # Download from volume
modal secret create NAME KEY=VALUE       # Create secret
```

## Key Tips

- GPU fallback: `gpu=["H100", "A100-80GB", "L40S"]` — Modal tries each in order
- Multi-GPU: `gpu="H100:4"` (up to 8 GPUs, cost scales linearly)
- Volume: `modal.Volume.from_name("x", create_if_missing=True)` for persistent storage
- `@modal.enter()` loads model once per container | `@modal.concurrent()` for concurrent requests
- Long training: set `timeout=3600 * N` (default is 5 min)
- Local code: `modal.Mount.from_local_dir(".", remote_path="/workspace")`
- W&B integration: `secrets=[modal.Secret.from_name("wandb-secret")]` + `wandb.init()` in your script

## Composing with Other Skills

```
/run-experiment "train model"       <- detects gpu: modal, calls /serverless-modal
  -> /serverless-modal              <- analyzes task, generates launcher, runs
  -> Results returned locally or to Modal Volume
  -> No destroy step needed (auto scale-to-zero)

/serverless-modal                   <- standalone: any Modal GPU workload
/serverless-modal "deploy vLLM"     <- inference service deployment
```

## AGENTS.md Example

```markdown
## Modal
- gpu: modal                 # tells run-experiment to use Modal serverless
- modal_gpu: A100-80GB       # optional: override GPU selection (default: auto-select)
- modal_timeout: 21600       # optional: max seconds (default: 6 hours)
- modal_volume: my-results   # optional: named volume for results persistence
```

No SSH keys, no Docker images, no instance management needed. Just `pip install modal && modal setup`.

> **Cost protection**: After `modal setup`, go to https://modal.com/settings in your browser (NEVER through CLI) → bind a payment method to unlock $30/month free tier (without card: only $5/month). Then set a **workspace spending limit** equal to your free tier amount — Modal will auto-pause workloads when the limit is reached, preventing any surprise charges.

## Documentation

- Docs: https://modal.com/docs/guide
- GPU: https://modal.com/docs/guide/gpu
- Pricing: https://modal.com/pricing
- Examples: https://modal.com/docs/examples
