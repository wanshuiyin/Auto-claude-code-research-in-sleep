# Output Manifest Protocol

Maintain a `MANIFEST.md` in the project root **only when a run produces more than
15 artifacts**. Below that threshold, do not create one: a manifest for a handful
of files is itself a duplicate index that has to be kept in sync with the files it
lists — the very duplication this protocol family exists to prevent (see
[`output-composition.md`](output-composition.md)). When the threshold is met, append
one entry per output file as below.

> Threshold rationale: the original "log *every* output to MANIFEST" rule is what
> drove the `MANIFEST.md` clutter in small idea-discovery runs. A manifest earns its
> keep only when there are enough artifacts that an index genuinely helps.

## Format

If `MANIFEST.md` does not exist, create it with this header:

```markdown
# Research Output Manifest

> Auto-maintained by ARIS skills. Tracks all generated artifacts across the research lifecycle.

| Timestamp | Skill | File | Stage | Description |
|-----------|-------|------|-------|-------------|
```

Then append one row per output file written:

```
| 2025-06-15 14:30 | /idea-creator | idea-stage/IDEA_REPORT_20250615_143022.md | idea-discovery | 12 ideas generated from "LLM reasoning" direction |
| 2025-06-15 14:30 | /idea-creator | idea-stage/IDEA_REPORT.md | idea-discovery | latest copy |
```

## Stage Values

| Stage | Skills |
|-------|--------|
| `idea-discovery` | /idea-creator, /idea-discovery, /novelty-check, /research-review |
| `implementation` | /research-refine, /research-refine-pipeline, /experiment-plan, /experiment-bridge, /run-experiment |
| `review` | /auto-review-loop |
| `paper` | /paper-writing, /paper-write, /paper-compile |

## Pre-flight Check

Before writing output, if the skill depends on a prerequisite file from a previous stage:
1. Check if the prerequisite file exists at its expected stage-scoped path (e.g., `idea-stage/IDEA_REPORT.md`, `review-stage/AUTO_REVIEW.md`)
2. If not found at the stage-scoped path, check the legacy root-level path (e.g., `./IDEA_REPORT.md`, `./AUTO_REVIEW.md`) — see [Path Fallback Rule](output-versioning.md#path-fallback-rule-backward-compatibility)
3. If not found at either path, warn: "⚠️ Expected {file} (from {skill}) but not found. Run {skill} first?"
4. Do not block — the user may have the file elsewhere or want to proceed anyway
