# External Cadence and Scheduling

External schedulers — such as `/loop`, `/schedule`, `CronCreate`, or periodic polling intervals — control **when** an agent executes. They manage timing and task scheduling; they do not evaluate artifact quality or render acceptance decisions.

## Core Principle

**A scheduler manages execution timing; it does not evaluate quality.**

Schedulers trigger tasks at specified intervals or in response to external events. Schedulers only evaluate objective completion criteria (e.g., process exit status, file generation). They must not bypass quality review steps, evaluate scientific validity, or render acceptance decisions.

**Rule:** Schedulers may monitor progress and resume stalled tasks, but quality and acceptance decisions always require an independent cross-model review (`acceptance-gate.md`, `reviewer-independence.md`).

## Appropriate vs. Inappropriate Uses of Cadence

External timers are effective for waiting on external processes (e.g., GPU training jobs, compilation pipelines). They should not wrap internal iterative reasoning loops.

### Risks of Wrapping Internal Loops with External Timers:

1. **Unnecessary Token Consumption:** Wrapping an iterative review skill like `/auto-review-loop` in a fixed 30-minute timer reruns reviews regardless of whether files changed, creating redundant costs without new signal.
2. **Loss of Reviewer Context:** Multi-round review workflows maintain conversational context in the reviewer thread across rounds (`codex-reply` using accumulated review memory). An external timer restarts the workflow from scratch, losing reviewer memory and the ability to verify whether previous issues were addressed.
3. **Duplicate Scheduling:** Workflows like `/experiment-queue` already run dedicated job-management loops with dependency resolution. Adding external polling loops introduces uncoordinated polling races.

**Guideline:** Schedule external wait states; do not schedule quality verdicts.

## Comparison Table

| Dimension | External-World Wait (Recommended) | Internal Semantic Loop (Do Not Wrap) |
|---|---|---|
| **Wait Target** | External system events: job completion, metric logging, file generation | Model-generated evaluation or revision |
| **Trigger Condition** | System state change (e.g., GPU idle, epoch finished, PDF compiled) | Evaluation verdict emitted |
| **Loop Management** | External: timer replaces idle session blocking | Internal: skill manages its own multi-round context and review thread |
| **Acceptance Gate** | Objective completion check (Type-A, deterministic) | Quality and correctness evaluation (Type-B, cross-model) |

## Recommended Scheduling Applications

1. **Job Completion Polling:** Checking whether background GPU or cluster jobs have exited.
2. **Training Anomaly Monitoring:** Reading metric logs periodically to detect early divergence or hardware failures.
3. **Queue Visibility:** Reporting the count of pending, running, and completed jobs.
4. **Stall Recovery:** Checking if a pipeline phase has stopped making progress and resuming dropped tasks.
5. **Periodic Literature Feeds:** Running daily scheduled sweeps for newly released papers.

These tasks evaluate objective completion criteria (exit codes, file timestamps, metric thresholds) which are safely verified by automated checks (`acceptance-gate.md`).

## Workflows Not to Wrap in External Timers

Any workflow that produces a quality or correctness evaluation should run via its own internal iteration loop and terminate with cross-model review:

- `/auto-review-loop` (maintains round-to-round reviewer context)
- `/auto-review-loop-llm`, `/auto-review-loop-minimax`
- `/auto-paper-improvement-loop`
- `/research-review`
- `/result-to-claim`
- `/experiment-audit`
- `/paper-claim-audit`
- `/citation-audit`
- `/proof-checker`
- `/kill-argument`

To schedule an audit, schedule the *external wait for upstream assets* (e.g., wait until experiments finish), then invoke the review workflow once.

## Progress Monitoring and Stall Recovery

Periodic background monitors may check whether long-running workflows are advancing and intervene if execution halts:

1. **Liveness Detection:** Background checks can detect if a process exited unexpectedly or hung on a lock, restarting the failed job.
2. **Boundary:** Stall monitors may unblock or restart stalled execution; they must never mark incomplete work as acceptable or bypass review gates. A monitor may decide to "continue execution", but never declare a draft "publication ready".

## Loop Heartbeat and Watchdog Registration

For long-running loops:

1. **Update State Files:** At the start of each iteration, update the timestamp of the workflow state file (`*_STATE.json` or `run_state.json`) before executing operations that could hang.
2. **Register with Watchdog:**
   ```bash
   python3 tools/watchdog.py --register '{"name":"<run_id>","type":"loop","state_file":"<state_file_path>","stale_after_seconds":21600}'
   # On completion:
   python3 tools/watchdog.py --unregister "<run_id>"
   ```
   Set `stale_after_seconds` based on the maximum expected duration of a single iteration. The watchdog detects stalled processes without modifying evaluation state.

## Stall Detection and Structural Reframing

When an iterative workflow fails to make progress across consecutive iterations:

1. **Track Concrete Output:** Record the count of verified findings, closed issues, or passing tests per iteration.
2. **Stall Response:**
   - **2 consecutive stagnant iterations:** Change structural assumptions (representation, hypothesis framing, or search space) rather than fine-tuning identical parameters.
   - **4 consecutive stagnant iterations:** Pause and escalate for human guidance.

## Reimplementation vs. Incremental Patching

When an implementation attempt repeatedly fails:

- **Prefer Clean Reimplementation Over Layered Patches:** If 1–2 targeted fixes fail to resolve an issue, reimplementing the component directly from specification is often faster and less error-prone than stacking consecutive workarounds.
- **Preserve Specifications and Results:** Clean reimplementations may replace temporary scripts and build artifacts, but must preserve specifications (`research_contract.md`, `EXPERIMENT_PLAN.md`, `PAPER_PLAN.md`), logs, and valid experimental data.
- **Escalate Ambiguous Specifications:** If multiple reimplementations fail identically, the underlying specification or test harness may be flawed; escalate for clarification.

## Requirements for Adding Cadence to a Skill

1. **Verify Objective Wait Condition:** Specify an observable condition (e.g., exit code present, file generated).
2. **Exclude Evaluation from Cadence Body:** The scheduled task may report status or trigger the next step; it must not render quality verdicts.
3. **Use Objective Gate Criteria:** Termination decisions must rely on deterministic checks (file existence, exit status) rather than subjective assessments.
4. **Avoid Redundant Scheduling:** Do not place external polling loops around workflows that already implement internal state polling.
5. **Preserve Review Thread Continuity:** When an external wait concludes, run the subsequent review workflow in a dedicated context to maintain state.

## Autonomous Mode Operation

When running in autonomous mode (`AUTO_PROCEED=true` or background scheduling):

- Resolve routine operational choices independently and record the rationale in execution logs.
- Respect explicit human checkpoints: stop and wait when encountering required approval points (such as submission confirmation or missing venue configuration).

## Cross-References

- `acceptance-gate.md` — Quality evaluation vs. objective completion gates.
- `fan-out-pattern.md` — Parallel execution patterns and reviewer independence.
- `reviewer-independence.md` — Maintaining context continuity in multi-round reviews.
- `experiment-integrity.md` — Decoupling code execution from evaluation.
