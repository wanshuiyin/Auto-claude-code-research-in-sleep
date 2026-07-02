# ARIS Framework & Design — Slide Outline (3-slide version)

> 16:9 high-density academic deck, paper-talk style.
> Total: 3 slides · target: 10–12 min spotlight / 6–8 min lightning.

## Slide 1 — ARIS Design Philosophy
- **Claim/title:** ARIS Design Philosophy: Separate Progress from Judgment
- **Main idea:** The entire framework rests on the rule that a system can drive progress but never acquit its own quality.
- **Top banner:** Cross-Model Jury: Claude executes → GPT-5.5 Codex adjudicates → deterministic scripts verify.
- **Column 1 — DRIVE vs ACQUIT:**
  - DRIVE: execute, schedule, generate, compile, mechanical checks
  - Safe for the same model
  - ACQUIT: correctness, novelty, sufficiency, completeness
  - Must be decided by a different model family
  - One rule shapes every design decision
- **Column 2 — Type-A / Type-B Gates:**
  - Type-A (mechanical): exit code, file exists, job completed
  - Executor self-judges safely
  - Type-B (judgmental): quality, correctness, novelty
  - Routed to GPT-5.5 Codex reviewer
  - Shared 6-state verdict: PASS / WARN / FAIL / BLOCKED / ERROR / NOT_APPLICABLE
- **Column 3 — Independent Axes:**
  - effort: lite → balanced → max → beast (how much work)
  - assurance: draft → polished → conference-ready → submission (how strict audits)
  - Example: effort:lite + assurance:submission = fast run, strict gate
- **Bottom relationship flow:** No self-acquittal → Gate taxonomy → Orthogonal controls → Verdict vocabulary
- **Time budget:** 3 min.
- **Transition cue:** "This philosophy is implemented by a three-role framework."
- **Speaker note seed:** Emphasize that DRIVE vs ACQUIT is the single non-negotiable rule; everything else is an engineering consequence.

## Slide 2 — ARIS Framework & Detailed Flow
- **Claim/title:** ARIS Framework & Detailed Flow: Six Workflows + Three Roles
- **Main idea:** Research flows through separated executor, reviewer, and verifier roles across six lifecycle workflows.
- **Left block — Architecture & lifecycle:**
  - Three roles: Claude Executor, GPT-5.5 Reviewer, Deterministic Verifier
  - All roles write to disk state: receipts, REVIEW_STATE.json, traces
  - W1–W6 lifecycle: Idea → Exp → Review → Summary → Paper → Rebuttal → Resubmit → Talk
  - Output files mapped under each stage
- **Left bottom — Integration Contract:**
  - 6 components per skill: predicate + helper + artifact + checklist + backfill + verifier
  - Helper resolution chain: .aris/tools → tools → $ARIS_REPO/tools → $CLAUDE_SKILL_DIR/scripts
  - Failure policies A–E: block / warn-skip / forensic / cascade / diagnostic
- **Right block — Mechanisms:**
  - Reviewer dispatch: only file paths, fresh round 1, continuation round 2+, REVIEWER_BIAS_GUARD
  - Fan-out: T1/T2/T3, shards EXTRACT, dedup before jury
  - 5-layer audit: experiment-audit → result-to-claim → paper-claim-audit → citation-audit → proof-checker/kill-argument → verify_paper_audits.sh exit 0
- **Time budget:** 4 min.
- **Transition cue:** "To run this for days or weeks, ARIS needs memory and long-cycle safeguards."
- **Speaker note seed:** Walk through one complete path: W1 generates ideas, W1.5 runs experiments with cross-model code review, W2 loops until reviewer says ready, W3 is blocked by the 5-layer audit.

## Slide 3 — ARIS Memory & Long-Cycle Operation
- **Claim/title:** ARIS Memory & Long-Cycle Operation: Survive, Resume, and Stay Honest
- **Main idea:** Disk is the source of truth; timers and heartbeats can fire-control progress but never own verdicts.
- **Top banner:** Long-cycle principle: disk is the source of truth; timers fire-control but never judge.
- **Column 1 — Memory system:**
  - research_wiki.py persistent knowledge base
  - Wiki load/upsert with provenance authorization
  - Capture antipatterns filtering
  - State files: REVIEW_STATE.json, PAPER_IMPROVEMENT_STATE.json, REFINE_STATE.json, queue_state.json, run_meta.txt
  - Receipts: .aris/runs/<run_id>.<phase>.done.json
- **Column 2 — Recovery:**
  - run_state.py: done vs accepted split
  - resume_point(): forward to first non-terminal phase
  - Re-audit done-but-unaccepted stages
  - External cadence fence: /loop and CronCreate fire-control only
  - Verdict skills never wrapped in /loop
  - Heartbeat is Type-A: touch state, log iterations, nudge stalls
  - Acceptance authority table: codex agent-id or deterministic verifier path/sha
- **Column 3 — Operation:**
  - iteration_log.py counts new findings
  - Overnight heartbeat with self-target create_heartbeat
  - stale≥2 → pivot=structural; stale≥4 → pivot=human
  - watchdog.py for 24/7 remote training health
  - Paseo orchestration: create_agent → notifyOnFinish → gate → archive_agent
  - Reviewer memory: continuation threads for loops, fresh threads for audits
  - Review tracing: save_trace.sh → 4 files + events.jsonl
- **Bottom relationship flow:** Memory layer → Recovery layer → Operation layer → Audit trail
- **Reinforcement notes:**
  - Wiki prevents repeated ideas; state files enable crash recovery
  - Cadence fence prevents timers from owning verdicts
  - Paseo receipts make every agent action auditable
  - Traces satisfy Policy C forensic requirements
- **Time budget:** 4 min.
- **Transition cue:** "Thank you — the core message is that quality is architecturally separated from progress."
- **Speaker note seed:** Close by returning to slide 1: the design philosophy is what makes the long-cycle operation honest.
