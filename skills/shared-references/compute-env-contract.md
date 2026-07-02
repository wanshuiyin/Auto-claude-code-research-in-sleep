# Compute Environment Contract

> One declarative spec for what an environment IS; per-provider knowledge for
> how it gets built HERE; a content-hash ledger so "did the env change?" has a
> mechanical answer; and a three-tier validation ladder whose top tier is a
> fresh agent following the skill's own doc verbatim. Adapted from Anthropic's
> Claude Science `compute-env-setup` skill (Apache-2.0); de-coupled from its
> proprietary `host.*` runtime — everything here runs on plain bash + SSH +
> subagents.

Every ARIS compute skill (`/run-experiment`, `/experiment-queue`,
`/serverless-modal`, `/vast-gpu`, `/qzcli`) needs the same three things for a
job: a software stack (exact versions, often with load-bearing install order),
possibly large weights placed where the tool looks, and a resource shape. What
varies per provider is only HOW those materialize. Without a shared contract,
each skill re-encodes provider quirks and every "environment is ready" claim is
vibes. The classic failure this prevents: agent says "env ready", the overnight
run dies at `import flash_attn`, 8 GPUs idle until morning.

## 1. Provider shapes — recognize, don't choose

You are rarely choosing a shape; you are recognizing which one this provider
already is. The shape determines what "build", "register", and "resolve" mean.

| Shape | ARIS examples | Build = | Env name resolves to |
|---|---|---|---|
| **Direct SSH host** (conda/venv) | personal GPU boxes, lab servers | YOU are the renderer: `conda create -n <name> python=<X>`, then run `pip_phases` in order | the conda env name itself (`conda run -n <name> …`) |
| **Scheduler cluster** (Slurm/PBS; Qizhi-like platforms) | `/qzcli` targets | `module load` or a container image built OFF-cluster and pulled (compute nodes often have **no internet** — pre-stage everything) | scheduler directives + container path in shared scratch (mind purge windows) |
| **Managed API** (serverless) | `/serverless-modal`, Vast.ai templates | the provider's image definition (Modal `Image`, Vast template) — render the same spec into it | the provider's opaque image ref, recorded in the ledger |

## 2. The declarative spec (write WHAT once; render per provider)

```yaml
# env-spec: one dict per environment, portable across shapes
base:        "cuda12.8 + python3.10"      # FROM-image / conda create versions
system_pkgs: [git, tmux]                  # apt in a container; conda-forge subset on no-root hosts
pip_phases:                               # ORDERED list of lists — each inner list = ONE pip call
  - [torch==2.8.0]                        #   phase 1 first, so later packages
  - [flash-attn --no-build-isolation]     #   can't drag torch to a wrong wheel
  - [transformers, peft, accelerate]
env:         {HF_ENDPOINT: "...", OMP_NUM_THREADS: "<tier.cpus>"}
run_commands: []                          # escape-hatch shell (RUN / %post / plain SSH)
weight_dirs: {chai: {path: /scratch/weights/chai, source: "tool's own loader", gated: false}}
smoke:                                    # probes that run INSIDE the env on every shape
  import_names: [torch, flash_attn]
  gpu_tests:                              # each = {cmd, expect}; expect is the witness regex
    - cmd: "python -c 'import torch;torch.manual_seed(0);x=torch.randn(8,8,device=\"cuda\");print(\"WITNESS\", (x@x).shape, torch.cuda.get_device_name())'"
      expect: "^WITNESS torch.Size"
  cli_checks:   [nvidia-smi]
```

- **`pip_phases` ordering IS the fix** for every "package A drags B to the
  wrong version" problem: each phase is its own pip invocation, and pip leaves
  an already-satisfied requirement alone unless asked to upgrade. Pin the
  fought-over package in an EARLIER phase than the fighter.
- A clean spec renders unchanged through every renderer. If you find yourself
  adding a field only one backend understands, that field belongs in the
  provider's ledger entry, not the spec.
- **Weights**: small (<~500 MB) and read by every job → bake into the env at
  build time. Large with a cache env var → persistent scratch + point the var
  there. Populate with the **tool's own loader** (hand-curled layouts miss
  marker files), then verify from the tool's perspective: run the real
  entrypoint once against the staged dir and `du -sh` every subdir — 0 B means
  a swallowed download error.

## 3. The environment ledger (content-hash = mechanical staleness)

Per provider, keep an append-friendly `.aris/compute/<provider>.md` (or the
project's existing server-notes file). One block per env, keyed by a content
hash of the spec, computed over an EXACT canonical form so two agents can
never hash the same spec differently: parse the spec file, re-serialize as
JSON with sorted keys and no whitespace, sha256, first 8 hex chars —

```bash
# spec stored as YAML (env-spec.yaml); requires PyYAML. If PyYAML is absent,
# store the spec as JSON instead and drop the yaml import — same pipeline.
python3 -c 'import sys,json,hashlib,yaml; \
s=json.dumps(yaml.safe_load(open(sys.argv[1])),sort_keys=True,separators=(",",":")); \
print(hashlib.sha256(s.encode()).hexdigest()[:8])' env-spec.yaml
```

Key order, comments, indentation, and trailing whitespace in the source file
do NOT affect the hash — only the parsed content does:

```
### env: dllm@a3f9c2e1
how: conda env "dllm" on <host>            # or: modal image ref / .sif path + partition
tier: {cpus: 8, mem_gib: 64, gpus: 1}
weights: HF_HOME=/scratch/hf (24 GB; purge-window 30d)
validated: 2026-07-02 (witness + agent-follows-doc clean)
gotcha: <any diagnosis-table row hit on THIS provider>
```

Spec changed → hash changes → **cache miss**: the ledger entry no longer
matches and the env must be rebuilt (or a new block added). Spec unchanged →
warm-reuse without rebuilding or re-validating tier 1–2. This turns "I think
the env is the same as last week" into a string comparison. Note `.aris/` is
gitignored by convention — the ledger is **project-local and uncommitted** by
default (like `.aris/traces/`). If you want committed, git-blameable history,
keep the ledger blocks in the project's tracked server-notes file instead;
the block format is the contract, not the path.

## 4. Validation — three tiers; the gap between them is where debugging lives

1. **Import works** — `python -c "import <pkg>"` exits 0. Necessary, cheap,
   catches almost nothing interesting.
2. **Kernel-dispatch witness** — a tiny SEEDED forward pass that prints a
   sentinel line (output shape + device name + non-emptiness). Catches "torch
   sees the GPU but the kernel was compiled for an older SM", "the compiled
   extension's `.so` isn't on the loader path", "inference writes to a
   read-only cache". Keep the witness command in the spec's `smoke.gpu_tests`
   with an `expect:` regex so the SAME probe runs on every backend. Cheap —
   run on every build.
3. **Agent-follows-doc** — the validation that actually matters and the one
   that's easy to skip. Spawn a FRESH subagent that gets ONLY: the compute
   skill's doc, the provider's ledger entry, and the documented invocation.
   It must run the invocation **verbatim** — no improvisation, no fixing —
   and report every point where the doc's claim and reality diverge. This is
   where you find the doc says `--ligand` but the flag is
   `--ligand_description`, or the weights path exists but lacks the completion
   marker the tool checks. The author agent cannot self-certify its own doc
   (it walks through on hidden knowledge the doc never wrote down — same
   principle as `acceptance-gate.md`: the writer never acquits its own
   artifact); the fresh agent's stuck-point IS the doc's lie. Expensive —
   reserve for the two moments doc and env can drift: **after any env rebuild
   or doc edit, and before declaring an env ready**.

## 5. Diagnosis table (symptom → layer → fix)

When a documented invocation fails, don't patch reflexively — ask which LAYER
is wrong: spec, build, weights, resolution, or doc. Grep-able rows (container
rows apply only to container shapes):

| Symptom | Layer | Fix |
|---|---|---|
| `no kernel image is available for execution` | build/spec | torch compiled for older SM than this GPU — record `sm_range` in the ledger and route jobs; rebuild only if no compatible hardware |
| `ModuleNotFoundError` for a package not in the spec | spec | a `--no-deps` install skipped a runtime dep — read the package's `pyproject.toml` and add an explicit phase |
| Wrong torch/numpy version after install | spec | a later package's pin won — add a `force-reinstall --no-deps` snap-back phase after it |
| `ImportError: libfoo.so: cannot open shared object` | build | compiled `.so` not on loader path — `find` it, add its dir to `LD_LIBRARY_PATH` |
| Tool re-downloads despite populated weights | weights | `du -sh $CACHE_VAR` first: 0 B = swallowed error; non-zero = tool checks a marker file, stage that too |
| `OSError: Read-only file system` under cache var | weights (container) | tool writes locks next to weights on an RO mount — symlink blobs into writable `/tmp` cache |
| 80-way thread storm on a 4-CPU allocation | exec | `os.cpu_count()` returns the HOST's cores — export `OMP/MKL/OPENBLAS_NUM_THREADS=<tier.cpus>` on every backend |
| First job slow, every later job equally slow | build | expensive precompute runs at job time in a non-persistent workdir — run it once at build time |
| Job COMPLETED but output dir empty | exec | the wrapper writing the completion marker never ran — often `#!/bin/bash` on a runtime that only ships `/bin/sh` |

Hit a row on a specific provider → append symptom + fix to that provider's
ledger `gotcha:` line, so the next agent doesn't rediscover it.

## How compute skills use this

- **Before building**: read the provider's ledger. The env — or a near-match
  to extend — may already exist; an unchanged hash means skip the rebuild.
- **When building**: write the spec first (§2), render it for the shape (§1),
  run tier-1/2 validation (§4), append the ledger block (§3).
- **Before declaring ready** (and after any rebuild/doc edit): run the
  agent-follows-doc pass (§4.3).
- **On failure**: diagnosis table (§5) before patching; record provider-true
  gotchas in the ledger.

Attribution: the spec/ledger/three-tier-validation design is adapted from
Anthropic's Claude Science `compute-env-setup` skill (Apache-2.0, re-hosted by
HughYau/AcademicForge); this document ports it off the proprietary `host.*`
runtime onto plain bash + SSH + ARIS subagents.
