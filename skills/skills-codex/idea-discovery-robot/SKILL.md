---
name: "idea-discovery-robot"
description: "Robotics-specific idea-discovery pipeline for embodied AI, manipulation, locomotion, navigation, drones, humanoids, and sim2real topics. Use only when the domain is clearly robotics or embodied AI and the user wants end-to-end idea discovery. Do not use for generic idea generation outside robotics; use `idea-discovery` or `idea-creator` then."
---

# Robotics Idea Discovery Pipeline

Orchestrate a robotics-specific idea discovery workflow for: **$ARGUMENTS**

## Routing Boundaries

- Use this skill only for robotics or embodied-AI idea discovery requests.
- Use `idea-discovery` for non-robotics end-to-end idea discovery.
- Use `idea-creator` for robotics brainstorming when the user wants ideas only rather than the full robotics-aware pipeline.

## Overview

This skill chains four sub-skills into a single automated pipeline:

```
/research-lit → /idea-creator (robotics framing) → /novelty-check → /research-review
  (survey)              (filter + pilot plan)         (verify novel)    (critical feedback)
```

But every phase must be grounded in robotics-specific constraints:
- **Embodiment**: arm, mobile manipulator, drone, humanoid, quadruped, autonomous car, etc.
- **Task family**: grasping, insertion, locomotion, navigation, manipulation, rearrangement, multi-step planning
- **Observation + action interface**: RGB/RGB-D/tactile/language; torque/velocity/waypoints/end-effector actions
- **Simulator / benchmark availability**: simulation-first by default
- **Real robot constraints**: hardware availability, reset cost, safety, operator time
- **Evaluation quality**: success rate plus failure cases, safety violations, intervention count, latency, sample efficiency
- **Sim2real story**: whether the idea can stay in sim, needs offline logs, or truly requires hardware

The goal is not to produce flashy demos. The goal is to produce ideas that are:
- benchmarkable
- falsifiable
- feasible with available robotics infrastructure
- interesting even if the answer is negative

## Constants

- **MAX_PILOT_IDEAS = 3** — Validate at most 3 top ideas deeply
- **PILOT_MODE = `sim-first`** — Prefer simulation or offline-log pilots before any hardware execution
- **REAL_ROBOT_PILOTS = `explicit approval only`** — Never assume physical robot access or approval
- **AUTO_PROCEED = true** — If user does not respond at checkpoints, proceed with the best sim-first option
- **REVIEWER_MODEL = `gpt-5.4`** — External reviewer model via a secondary Codex agent
- **TARGET_VENUES = CoRL, RSS, ICRA, IROS, RA-L** — Default novelty and reviewer framing

> Override inline, e.g. `/idea-discovery-robot "bimanual manipulation" — only sim ideas, no real robot` or `/idea-discovery-robot "drone navigation" — focus on CoRL/RSS, 2 pilot ideas max`

## Execution Rule

Follow the phases in order. Do **not** stop after a checkpoint unless:
- the user explicitly says to stop, or
- the user asks to change scope and re-run an earlier phase

If `AUTO_PROCEED=true` and the user does not respond, continue immediately to the next phase using the strongest **sim-first, benchmark-grounded** option.

## Phase 0: Frame the Robotics Problem

Before generating ideas, extract or infer this **Robotics Problem Frame** from `$ARGUMENTS` and local project context:

- **Embodiment**
- **Task family**
- **Environment type**: tabletop, warehouse, home, outdoor, aerial, driving, legged terrain
- **Observation modalities**
- **Action interface / controller abstraction**
- **Learning regime**: RL, imitation, behavior cloning, world model, planning, VLA/VLM, classical robotics, hybrid
- **Available assets**: simulator, benchmark suite, teleop data, offline logs, existing codebase, real hardware
- **Compute budget**
- **Safety constraints**
- **Desired contribution type**: method, benchmark, diagnosis, systems, sim2real, data curation

If some fields are missing, make explicit assumptions and default to:
- **simulation-first**
- **public benchmark preferred**
- **no real robot execution**

Write this frame into working notes before moving on. Every later decision should reference it.

## Phase 1: Robotics Literature Survey

Invoke:

```
/research-lit "$ARGUMENTS — focus venues: CoRL, RSS, ICRA, IROS, RA-L, TRO, Science Robotics"
```

Then reorganize the findings using a robotics lens instead of a generic ML lens.

### Build a Robotics Landscape Matrix

For each relevant paper, classify:

| Axis | Examples |
|------|----------|
| Embodiment | single-arm, mobile manipulator, humanoid, drone, quadruped |
| Task | pick-place, insertion, navigation, locomotion, long-horizon rearrangement |
| Learning setup | RL, BC, IL, offline RL, world model, planning, diffusion policy |
| Observation | RGB, RGB-D, proprioception, tactile, language |
| Action abstraction | torque, joint velocity, end-effector delta pose, waypoint planner |
| Eval regime | pure sim, sim+real, real-only, offline benchmark |
| Benchmark | ManiSkill, RLBench, Isaac Lab, Habitat, Meta-World, CALVIN, LIBERO, custom |
| Metrics | success rate, collision rate, intervention count, path length, latency, energy |
| Main bottleneck | sample inefficiency, brittleness, reset cost, perception drift, sim2real gap |

### Search Priorities

When refining the survey, prioritize:
- recent work from **CoRL, RSS, ICRA, IROS, RA-L**
- recent arXiv papers from the last 6-12 months
- benchmark papers and follow-up reproductions
- negative-result or diagnosis papers if they reveal system bottlenecks

### What to Look For

Do not stop at "who got the best success rate." Explicitly identify:
- recurring failure modes papers do not fix
- benchmarks that are saturated or misleading
- places where embodiment changes invalidate prior conclusions
- methods that only work with privileged observations
- ideas whose reported gains come from reset engineering, reward shaping, or hidden infrastructure
- task families where evaluation quality is weak even if performance numbers look high

**Checkpoint:** Present the landscape to the user in robotics terms:

```
🤖 Robotics survey complete. I grouped the field by embodiment, benchmark, action interface, and sim2real setup.

Main gaps:
1. [...]
2. [...]
3. [...]

Should I generate ideas under this framing, or should I narrow to a specific robot / benchmark / modality?
```

- **User approves** (or no response + AUTO_PROCEED=true) → proceed to Phase 2 with the best robotics frame.
- **User requests changes** (e.g. narrower embodiment, different benchmark family, no sim2real, no hardware) → refine the robotics frame, re-run Phase 1, and present again.

## Phase 2: Robotics-Specific Idea Generation and Filtering

Generate ideas only after the robotics frame is explicit.

Invoke the existing idea generator, but pass the **Robotics Problem Frame** and landscape matrix into the prompt so it does not produce generic ML ideas:

```
/idea-creator "$ARGUMENTS — robotics frame: [paste Robotics Problem Frame] — focus venues: CoRL, RSS, ICRA, IROS, RA-L — benchmark-specific ideas only — sim-first pilots — no real-robot execution without explicit approval — require failure metrics and baseline clarity"
```

Then rewrite and filter the output using the robotics-specific rules below.

Each candidate idea must include:
- **One-sentence summary**
- **Target embodiment**
- **Target benchmark / simulator / dataset**
- **Core bottleneck being addressed**
- **Minimum sim-first pilot**
- **Mandatory metrics**
- **Expected failure mode if the idea does not work**
- **Whether the idea truly needs real hardware**

### Good Robotics Idea Patterns

Prefer ideas that:
- expose a real bottleneck in perception-action coupling
- improve robustness under embodiment or environment shift
- reduce operator time, reset cost, or demonstration cost
- strengthen sim2real transfer with measurable mechanisms
- improve recovery, retry behavior, or failure detection
- create a better benchmark, diagnostic, or evaluation protocol
- test an assumption the community repeats but rarely measures

### Weak Robotics Idea Patterns

Downrank ideas that are mostly:
- "apply a foundation model / VLM / diffusion model to robot X" with no new bottleneck analysis
- demo-driven but not benchmarkable
- dependent on inaccessible hardware, custom sensors, or massive private datasets
- impossible to evaluate without a months-long infrastructure build
- only interesting if everything works perfectly

### Filtering Rules

For each idea, reject or heavily downrank if:
- no concrete simulator or benchmark is available
- no credible baseline exists
- no measurable metric beyond "looks better"
- real robot execution is required but hardware access is unclear
- the setup depends on privileged observations that make the claim weak
- the expected contribution disappears if evaluation is made fair

**Checkpoint:** Present the ranked robotics ideas before novelty checking:

```
💡 Robotics ideas generated. Top candidates:

1. [Idea 1] — Embodiment: [...] — Benchmark: [...] — Pilot: sim/offline — Risk: LOW/MEDIUM/HIGH
2. [Idea 2] — Embodiment: [...] — Benchmark: [...] — Pilot: sim/offline — Risk: LOW/MEDIUM/HIGH
3. [Idea 3] — requires hardware / weak benchmark / high risk

Should I carry the top sim-first ideas into novelty checking and external review?
(If no response, I'll continue with the strongest benchmark-grounded ideas.)
```

- **User picks ideas** (or no response + AUTO_PROCEED=true) → proceed to Phase 3 with the top sim-first ideas, then continue to Phase 4 and Phase 5.
- **User wants different constraints** → update the robotics frame and re-run Phase 2.
- **User wants narrower scope** → go back to Phase 1 with a tighter embodiment / task / benchmark focus.

## Phase 3: Feasibility and Pilot Design

For the top ideas, design a **minimal validation package**.

If the repository already contains a usable simulator, benchmark harness, or offline dataset pipeline, you may validate the top 1-3 ideas there. If not, do **not** force execution. Produce a concrete pilot plan instead.

By default, pilots should be one of:
- **simulation pilot**
- **offline log / dataset pilot**
- **analysis-only pilot** using existing benchmark outputs

Only propose a real-robot pilot if the user explicitly wants that.

For each surviving idea, specify:

```markdown
- Embodiment:
- Benchmark / simulator:
- Baselines:
- Pilot type: sim / offline / real
- Compute estimate:
- Human/operator time:
- Success metrics:
- Failure metrics:
- Safety concerns:
- What result would count as positive signal:
- What negative result would still be publishable:
```

### Real Robot Rule

**Never auto-proceed to physical robot testing.** If an idea needs hardware:
- mark it as `needs physical validation`
- design the sim or offline precursor first
- ask for explicit user confirmation before any real-robot step

If no cheap sim/offline pilot exists, keep the idea in the report but label it **high execution risk**.

After Phase 3, continue to Phase 4 even if you only produced a pilot plan rather than running a pilot. Lack of immediate execution is not a reason to stop the workflow.

## Phase 4: Deep Novelty Verification

For each top idea, run:

```
/novelty-check "[idea description with embodiment + task family + benchmark + sensor stack + controller/policy class + sim2real angle + target venues: CoRL/RSS/ICRA/IROS/RA-L]"
```

Robotics novelty checks must include:
- embodiment
- task family
- benchmark / simulator
- sensor stack
- controller / policy type
- sim2real or safety angle if relevant

Be especially skeptical of ideas that are just:
- old method + new benchmark
- VLA/VLM + standard manipulation benchmark
- sim2real claim without new transfer mechanism

If the method is not novel but the **finding** or **evaluation protocol** is, say that explicitly.

## Phase 5: External Robotics Review

Invoke:

```
/research-review "[top idea with robotics framing, embodiment, benchmark, baselines, pilot plan, evaluation metrics, and sim2real/hardware risks — review as CoRL/RSS/ICRA reviewer]"
```

Frame the reviewer as a senior **CoRL / RSS / ICRA** reviewer. Ask them to focus on:
- whether the contribution is really new for robotics, not just ML
- the minimum benchmark package needed for credibility
- whether the sim2real story is justified
- missing baselines or failure analyses
- whether the idea survives realistic infrastructure constraints

Update the report with the reviewer's minimum viable evidence package.

## Phase 6: Final Report

Write or update `idea-stage/IDEA_REPORT.md` with a robotics-specific structure so it stays compatible with downstream workflows.

```markdown
# Robotics Idea Discovery Report

**Direction**: $ARGUMENTS
**Date**: [today]
**Pipeline**: research-lit → idea-creator (robotics framing) → novelty-check → research-review

## Robotics Problem Frame
- Embodiment:
- Task family:
- Observation / action interface:
- Available assets:
- Constraints:

## Landscape Matrix
[grouped by embodiment, benchmark, and bottleneck]

## Ranked Ideas

### Idea 1: [title] — RECOMMENDED
- Embodiment:
- Benchmark / simulator:
- Bottleneck addressed:
- Pilot type: sim / offline / real
- Positive signal:
- Novelty:
- Reviewer score:
- Hardware risk:
- Next step:

## Eliminated Ideas
- [idea] — killed because benchmark unclear / hardware inaccessible / novelty weak / no fair evaluation

## Evidence Package for the Top Idea
- Required baselines:
- Required metrics:
- Required failure cases:
- Whether real robot evidence is mandatory:

## Next Steps
- [ ] Implement sim-first pilot
- [ ] Run /novelty-check on the final idea wording
- [ ] Only after approval: consider hardware validation
```

## Key Rules

- **Simulation first.** Hardware is never the default.
- **Benchmark specificity is mandatory.** No benchmark, no serious idea.
- **Evaluation must include failures.** Success rate alone is not enough.
- **Embodiment matters.** Do not assume a result on one robot transfers to another.
- **Avoid foundation-model theater.** Novel terminology is not novelty.
- **Infrastructure realism matters.** Operator time, reset burden, and safety count as research constraints.
- **If the contribution is mainly diagnostic or evaluative, say so.** That can still be publishable.

## Composing with Later Work

After this workflow identifies a strong robotics idea:

```
/idea-discovery-robot "direction"   ← you are here
implement sim-first pilot
/run-experiment                     ← if infrastructure exists
/auto-review-loop "top robotics idea"
```

If no simulator or benchmark is available yet, stop at the report and ask the user to choose whether to build infrastructure or pivot to a more executable idea.

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../../shared-references/output-language.md)** — respect the project's language setting

