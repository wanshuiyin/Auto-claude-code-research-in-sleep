#!/usr/bin/env python3
"""build_manifest.py — Convert grid specs into queue_manager manifest.json.

Usage:
    python3 build_manifest.py \\
        --config grid_spec.yaml \\
        --output manifest.json

Grid spec YAML format:

project: my_grid_experiment
cwd: /home/user/your_project
conda: my_env
gpus: [0, 1, 2, 3, 4, 5, 6, 7]
max_parallel: 8
oom_retry:
  delay: 120
  max_attempts: 3

phases:
  - name: train_teachers
    grid:
      N: [384, 512]
    template:
      id: "teacher_N${N}"
      cmd: "python run_train.py --direction c --backbone softmax --n_hidden ${N} --L 96 --K 500 --window_size 16 --n_steps 30000 --batch_size 128 --seed 42"
      expected_output: "checkpoints/transformer/teacher_L96_K500_N${N}.pt"

  - name: distill
    depends_on: [train_teachers]
    grid:
      N: [384, 512]
      seed: [42, 200, 201]
      n_train_subset: [50000, 150000, 500000, 652000]
    template:
      id: "s${seed}_N${N}_n${n_train_subset}"
      cmd: >
        python run_distill.py --backbone softmax --lam 0.5 --t_max_distill 0
        --K 500 --L 96 --W 16 --n_steps 30000 --batch_size 128 --lr 1e-4
        --seed ${seed} --subset_seed 2024 --n_hidden ${N}
        --n_train_subset ${n_train_subset}
      expected_output: "figures/distill_sw_N${N}_n*_lam0.5_W16_L96_K500_seed${seed}.json"
"""

import argparse
import itertools
import json
import re
from pathlib import Path


def substitute(template, values):
    """Substitute ${var} placeholders in a string or nested dict."""
    if isinstance(template, str):
        def replace(match):
            key = match.group(1)
            return str(values[key]) if key in values else match.group(0)
        return re.sub(r'\$\{([^}]+)\}', replace, template)
    elif isinstance(template, dict):
        return {k: substitute(v, values) for k, v in template.items()}
    elif isinstance(template, list):
        return [substitute(v, values) for v in template]
    return template


def expand_grid(grid):
    """Cartesian product over grid dict values."""
    keys = list(grid.keys())
    vals = [grid[k] for k in keys]
    for combo in itertools.product(*vals):
        yield dict(zip(keys, combo))


def build(config):
    out = {
        "project": config.get("project", "unknown"),
        "cwd": config.get("cwd", "."),
        "conda": config.get("conda", "base"),
        "gpus": config.get("gpus", list(range(8))),
        "max_parallel": config.get("max_parallel", 8),
        "oom_retry": config.get("oom_retry", {"delay": 120, "max_attempts": 3}),
        "phases": [],
    }
    for phase in config.get("phases", []):
        phase_out = {
            "name": phase["name"],
            "depends_on": phase.get("depends_on", []),
            "jobs": [],
        }
        grid = phase.get("grid", {})
        template = phase.get("template", {})
        if not grid:
            # Single job in this phase
            phase_out["jobs"].append({
                "id": template.get("id", phase["name"]),
                "cmd": template["cmd"],
                "expected_output": template.get("expected_output"),
            })
        else:
            for values in expand_grid(grid):
                job = {
                    "id": substitute(template["id"], values),
                    "cmd": substitute(template["cmd"], values),
                }
                if "expected_output" in template:
                    job["expected_output"] = substitute(
                        template["expected_output"], values)
                phase_out["jobs"].append(job)
        out["phases"].append(phase_out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True,
                    help="Grid-spec YAML or JSON file")
    ap.add_argument("--output", required=True,
                    help="Output manifest.json path")
    args = ap.parse_args()

    p = Path(args.config)
    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            print("PyYAML not available; install with: pip install pyyaml")
            raise SystemExit(1)
        config = yaml.safe_load(p.read_text())
    else:
        config = json.loads(p.read_text())

    manifest = build(config)
    Path(args.output).write_text(json.dumps(manifest, indent=2))

    total_jobs = sum(len(ph["jobs"]) for ph in manifest["phases"])
    print(f"Built manifest with {len(manifest['phases'])} phases, "
          f"{total_jobs} total jobs")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
