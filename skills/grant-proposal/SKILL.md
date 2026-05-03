---
name: grant-proposal
description: "Draft a structured grant proposal from research ideas and literature. Supports KAKENHI (Japan), NSF (US), NSFC (China, including 面上/青年/优青/杰青/海外优青/重点), ERC (EU), DFG (Germany), SNSF (Switzerland), ARC (Australia), NWO (Netherlands), and generic formats. Use when user says \"write grant\", \"grant proposal\", \"申請書\", \"write KAKENHI\", \"科研費\", \"基金申请\", \"写基金\", \"NSF proposal\", or wants to turn research ideas into a funding application."
argument-hint: "[research-direction — grant-type] [— style-ref: <source>]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Grant Proposal: From Research Ideas to Fundable Application

Draft a grant proposal based on: **$ARGUMENTS**

## Overview

This skill turns validated research ideas into a structured, reviewer-ready grant proposal. It chains sub-skills into a grant-specific pipeline:

```
/research-lit → /novelty-check → [structure design] → [draft] → /research-review → [revise] → GRANT_PROPOSAL.md
  (survey)      (verify gap)     (aims + matrix)     (prose)    (panel review)     (fix)      (done!)
```

**This is a parallel branch, not part of the linear Workflow 1→1.5→2→3 pipeline.** After `/idea-discovery` produces validated ideas, the user can either:
- Go to `/experiment-bridge` → `/auto-review-loop` → `/paper-writing` (implement & publish)
- Go to `/grant-proposal` (write funding application first, then implement after funding)

```
                    ┌→ /experiment-bridge → /auto-review-loop → /paper-writing  (publish track)
/idea-discovery ────┤
                    └→ /grant-proposal → [get funded] → /experiment-bridge → ...  (funding track)
```

Grant proposals argue for **future work** (feasibility + potential), not completed work (results + claims). This skill handles the unique requirements of grant writing: narrative arc design, reviewer-facing structure, budget justification, timeline planning, and agency-specific formatting.

## Constants

- **GRANT_TYPE = `KAKENHI`** — Default grant type. Supported: `KAKENHI`, `NSF`, `NSFC`, `ERC`, `DFG`, `SNSF`, `ARC`, `NWO`, `GENERIC`. Override via argument (e.g., `/grant-proposal "topic — NSF"`).
- **GRANT_SUBTYPE = `auto`** — Sub-type within the grant agency. Examples: KAKENHI `Start-up`/`Wakate`/`Kiban-B`; NSFC `Youth`/`Excellent-Youth`/`Distinguished`/`Overseas`/`Key`; NSF `CAREER`/`CRII`/`Standard`. Auto-detected from argument or defaults to the most common sub-type.
- **REVIEWER_MODEL = `gpt-5.4`** — Model used via Codex MCP for proposal review. Must be an OpenAI model (e.g., `gpt-5.4`, `o3`, `gpt-4o`).
- **OUTPUT_FORMAT = `markdown`** — Output format. Supported: `markdown`, `latex`. LaTeX uses grant-specific templates when available.
- **MAX_REVIEW_ROUNDS = 2** — Maximum external review-revise cycles before finalizing.
- **OUTPUT_DIR = `grant-proposal/`** — Directory for generated proposal files.
- **LANGUAGE = `auto`** — Output language. Auto-detected from grant type: KAKENHI→Japanese, NSF→English, NSFC→Chinese, ERC→English, DFG→English (or German), SNSF→English, ARC→English, NWO→English. Override explicitly if needed.
- **AUTO_PROCEED = false** — At each checkpoint, **always wait for explicit user confirmation** before proceeding. Grant proposals require PI-specific judgment at every stage. Set `true` only if user explicitly requests fully autonomous mode.

> 💡 These are defaults. Override by telling the skill, e.g., `/grant-proposal "topic — NSF CAREER, latex output"` or `/grant-proposal "topic — NSFC Youth, language: English"`.

## Optional: Style reference (`— style-ref: <source>`, opt-in)

Lets the PI steer the proposal's **structural** layout (section order tendency, paragraph length, figure density, citation style) toward a successful past proposal or paper they'd like to mirror. **Default OFF — when the user does not pass `— style-ref`, do nothing differently from before.**

Only when `— style-ref: <source>` appears in `$ARGUMENTS`, run the helper FIRST, before drafting:

```bash
if [ ! -f tools/extract_paper_style.py ]; then
  echo "error: tools/extract_paper_style.py not found — re-run 'bash tools/install_aris.sh' to refresh the '.aris/tools' symlink (added in #174), or copy the helper manually from the ARIS repo" >&2
  exit 1
fi
CACHE=$(python3 tools/extract_paper_style.py --source "<source>")
case $? in
  0) ;;                                       # use $CACHE/style_profile.md as structural guidance
  2) echo "warning: style-ref skipped (missing optional dep)" >&2 ;;
  3) echo "error: --style-ref source failed; aborting proposal" >&2 ; exit 1 ;;
  *) echo "error: helper failed unexpectedly; aborting proposal" >&2 ; exit 1 ;;
esac
```

Sources accepted: local TeX dir / file, local PDF, arXiv id, http(s) URL. Overleaf URLs/IDs are rejected — clone the project locally first and pass the local path.

**Strict rules** (full contract in `tools/extract_paper_style.py` docstring):

- Use `style_profile.md` to align paragraph length tendency, figure budget, and citation density. Grant-type-mandated section order (KAKENHI 研究目的 → 研究計画・方法 → 準備状況, NSF Intellectual Merit → Broader Impacts, etc.) **always takes precedence** — the agency template wins, the style ref only refines secondary structure.
- **Never copy proposal prose, claims, vision statements, or budget items** from anything reachable through the cache. The reference might be someone else's funded proposal; reproducing language risks plagiarism.
- **Never pass `— style-ref` (or the cache contents) to the GPT-5.4 reviewer sub-agent** when it scores the draft — the proposal must be judged on its own merits.

## Grant Type Specifications

### KAKENHI (Japan — JSPS)

| Field | Detail |
|-------|--------|
| **Sections** | 研究目的 (Research Objective), 研究計画・方法 (Plan & Methods), 準備状況 (Preparation Status), 人権の保護 (Ethics, if applicable) |
| **Sub-types** | 基盤研究 A/B/C (Kiban), 若手研究 (Wakate), 研究活動スタート支援 (Start-up), 国際共同研究 (International), 学術変革領域 (Transformative), 挑戦的研究 (Challenging), DC1/DC2 (doctoral) |
| **Language** | Japanese (English technical terms acceptable) |
| **Review criteria** | 学術的重要性 (academic significance), 独創性 (originality), 研究計画の妥当性 (plan feasibility), 研究遂行能力 (PI capability) |
| **Cultural norms** | Explicit yearly milestones (Year 1 / Year 2), budget justification integrated into plan, emphasize 社会的意義 (societal significance), concrete expected outputs (papers, datasets), reference KAKEN database for related funded projects |

### NSF (US)

| Field | Detail |
|-------|--------|
| **Sections** | Project Summary (1p), Project Description (15p max), References Cited, Biographical Sketch, Budget Justification, Data Management Plan |
| **Sub-types** | Standard Grant, CAREER (early career), CRII (research initiation), RAPID, EAGER |
| **Language** | English |
| **Review criteria** | Intellectual Merit, Broader Impacts |
| **Cultural norms** | Aim-based structure (Aim 1/2/3), preliminary data strongly expected, broader impacts must be concrete and specific (not generic "benefit society"), Results from Prior Support section |

### NSFC (China — 国家自然科学基金)

| Field | Detail |
|-------|--------|
| **Sections** | 立项依据 (Rationale & Significance), 研究内容 (Content), 研究目标 (Objectives), 研究方案 (Plan & Methods), 可行性分析 (Feasibility), 创新性 (Innovation Points), 预期成果 (Expected Outcomes), 研究基础 (PI Foundation & Track Record) |
| **Sub-types** | 面上项目 (General Program) — emphasis on scientific problem and research accumulation; 青年基金 (Young Scientists Fund) — age ≤35, emphasis on independence and growth potential; 优秀青年基金/优青 (Excellent Young Scientists) — age ≤38, emphasis on outstanding achievements; 杰出青年基金/杰青 (Distinguished Young Scientists) — age ≤45, emphasis on international-leading level; 海外优青 (Overseas Excellent Young Scientists) — emphasis on overseas experience and return contribution plan; 重点项目 (Key Program) — emphasis on systematic in-depth research |
| **Language** | Chinese |
| **Review criteria** | 科学意义 (scientific significance), 创新性 (innovation), 可行性 (feasibility), 研究队伍 (team qualification) |
| **Cultural norms** | Heavy emphasis on 国际前沿 (international frontier) positioning, detailed feasibility analysis, explicit citation of applicant's prior publications, 研究基础 section is critical for demonstrating PI capability |

### ERC (EU — European Research Council)

| Field | Detail |
|-------|--------|
| **Sections** | Extended Synopsis (5p), Scientific Proposal Part B2 (15p) |
| **Sub-types** | Starting Grant (2-7 years post-PhD), Consolidator Grant (7-12 years), Advanced Grant (established leaders) |
| **Language** | English |
| **Review criteria** | Ground-breaking nature, Methodology, PI track record |
| **Cultural norms** | Emphasis on "high-risk/high-gain", methodology table with WP/deliverables/milestones, Gantt chart expected, strong PI narrative |

### DFG (Germany — Deutsche Forschungsgemeinschaft)

| Field | Detail |
|-------|--------|
| **Sections** | State of the Art, Objectives, Work Programme, Bibliography, CV |
| **Language** | English or German |
| **Review criteria** | Scientific quality, Originality, Feasibility, PI qualification |

### SNSF (Switzerland — Swiss National Science Foundation)

| Field | Detail |
|-------|--------|
| **Sections** | Summary, Research Plan, Timetable, Budget |
| **Language** | English |
| **Review criteria** | Scientific relevance, Originality, Feasibility, Track record |

### ARC (Australia — Australian Research Council)

| Field | Detail |
|-------|--------|
| **Sections** | Project Description, Feasibility, Benefit, Budget |
| **Language** | English |
| **Review criteria** | Research quality, Feasibility, Benefit to Australia |

### NWO (Netherlands — Dutch Research Council)

| Field | Detail |
|-------|--------|
| **Sections** | Summary, Proposed Research, Knowledge Utilisation |
| **Language** | English |
| **Review criteria** | Scientific quality, Innovative character, Knowledge utilisation |

### GENERIC

For any grant not listed above. User provides section names, page limits, and review criteria via argument:

```
/grant-proposal "topic — GENERIC, sections: Background|Methods|Impact, language: English"
```

## State Persistence (Compact Recovery)

Grant proposal drafting is a long task that may trigger context compaction. Persist state to `grant-proposal/GRANT_STATE.json` after each phase:

```json
{
  "phase": 2,
  "grant_type": "KAKENHI",
  "grant_subtype": "Start-up",
  "language": "Japanese",
  "codex_thread_id": "019cfcf4-...",
  "gap_statement": "...",
  "aims_count": 3,
  "status": "in_progress",
  "timestamp": "2026-03-18T15:00:00"
}
```

**Write this file at the end of every phase.** On invocation, check for this file:
- If absent or `status: "completed"` → fresh start
- If `status: "in_progress"` and within 24h → **resume** from saved phase (read `GRANT_PROPOSAL.md` and `GRANT_REVIEW.md` to restore context)
- If older than 24h → fresh start (stale state)

On completion, set `"status": "completed"`.

## Workflow

### Phase 0: Input Parsing & Context Gathering

Parse `$ARGUMENTS` to extract:

1. **Research direction/idea** — may reference existing files or be a freeform description
2. **Grant type** — detect from keywords (e.g., "科研費"→KAKENHI, "NSF"→NSF, "国自然"→NSFC, "基金"→NSFC)
3. **Grant sub-type** — detect from keywords (e.g., "Start-up", "若手", "青年", "CAREER", "优青", "海外优青")
4. **Overrides** — output format, language, review rounds

Then gather context from the project directory:

1. Read `idea-stage/IDEA_REPORT.md` if it exists (from `/idea-discovery`); fall back to `./IDEA_REPORT.md` if not found
2. Read `refine-logs/FINAL_PROPOSAL.md` if it exists (from `/research-refine`)
3. Read `refine-logs/EXPERIMENT_PLAN.md` if it exists (from `/experiment-plan`)
4. Read `review-stage/AUTO_REVIEW.md` if it exists (from `/auto-review-loop` — prior review feedback is gold for grants); fall back to `./AUTO_REVIEW.md` if not found
5. Read `NARRATIVE_REPORT.md` or `STORY.md` if they exist
6. Read any existing literature notes or survey documents
7. Scan for the user's publication list (e.g., `publications.md`, `cv.md`, `bio.md`, `CV.pdf`)
8. Check for `grant-proposal/GRANT_STATE.json` (resume from prior interrupted run)

If insufficient context exists:
- No research idea at all → suggest running `/idea-discovery` first
- No literature survey → will invoke `/research-lit` inline in Phase 1
- No publication list → leave PI qualification section with `[TODO: Add publications]` placeholders
- Has review-stage/AUTO_REVIEW.md → extract reviewer feedback and use it to strengthen the feasibility narrative

### Phase 1: Literature & Landscape Positioning

Invoke `/research-lit` to ground the proposal in real literature, then search for competing funded projects:

```
/research-lit "$ARGUMENTS"
```

**What this does:**
- Reuse existing surveys if `/research-lit` was already run and notes exist
- Otherwise invoke `/research-lit` for multi-source literature search (arXiv, Scholar, Zotero, local PDFs)
- Search for **funded projects** in the same area via WebSearch:
  - KAKENHI → KAKEN database (https://kaken.nii.ac.jp/)
  - NSF → NSF Award Search (https://www.nsf.gov/awardsearch/)
  - NSFC → NSFC funded projects
  - Other agencies → general web search
- Identify competing groups and their recent publications
- Run `/novelty-check` on the proposed research direction to verify the gap is real:
  ```
  /novelty-check "[proposed gap statement]"
  ```
- Build the **gap statement** — the single most important sentence in the proposal:
  ```
  "Despite progress in [X], [specific gap] remains unaddressed because [reason].
  This proposal addresses this by [approach], which will [expected impact]."
  ```

**🚦 Checkpoint:** Present the landscape summary and gap statement to the user:

```
📚 Literature & landscape analysis complete:
- [key findings from literature]
- [competing funded projects found]
- Gap statement: "[the gap statement]"

Does this accurately capture the positioning? Should I adjust before designing the proposal structure?
```

**⛔ STOP HERE and wait for user response.** Do NOT auto-proceed unless AUTO_PROCEED=true was explicitly set by the user.

Options for the user:
- Reply **"go"** or **"ok"** → proceed to Phase 2 with current positioning
- Reply with **adjustments** (e.g., "focus more on X", "the gap should emphasize Y") → refine and re-present
- Reply **"stop"** → end the skill, save current progress to `grant-proposal/DRAFT_NOTES.md`

**State**: Write `GRANT_STATE.json` with `phase: 1` and the gap statement.

### Phase 2: Narrative Structure & Aims Design

Design the proposal's logical architecture before writing any prose.

#### 2.1 Define Specific Aims (2-4)

Each aim must satisfy:
- **Independently valuable** — if one aim fails, others still produce publishable results
- **Logically connected** — Aim 1 enables Aim 2, Aim 2 informs Aim 3
- **Concrete deliverables** — each aim maps to specific outputs (papers, datasets, tools, benchmarks)
- **Feasible within budget and timeline**

#### 2.2 Build Claims-Aims-Evidence Matrix

```markdown
| Aim | Key Claim | Preliminary Evidence | Proposed Validation | Risk Level | Deliverable |
|-----|-----------|---------------------|--------------------|-----------:|-------------|
| Aim 1 | [claim] | [pilot data, prior work] | [experiments] | LOW | [paper, dataset] |
| Aim 2 | [claim] | [theoretical basis] | [experiments] | MEDIUM | [paper, tool] |
```

#### 2.3 Design the Narrative Arc

Grant proposals follow a fundamentally different arc from papers:

```
Problem → Why Now → What We Propose → Why It Will Work → What We Will Deliver
         (not: Problem → Method → Results → Implications)
```

- **Problem**: What gap exists and why it matters (scientific + societal)
- **Why Now**: What recent developments make this the right time (new data, new methods, new need)
- **What We Propose**: The specific aims and approach
- **Why It Will Work**: Preliminary data, PI track record, team expertise, feasibility arguments
- **What We Will Deliver**: Concrete outputs, timeline, expected publications

#### 2.4 Timeline & Milestones

Design year-by-year (or quarter-by-quarter) plan:

```markdown
### Year 1
- Q1-Q2: [Aim 1 tasks]
- Q3-Q4: [Aim 1 completion + Aim 2 start]
- Expected outputs: [papers, datasets]

### Year 2
- Q1-Q2: [Aim 2 completion + Aim 3]
- Q3-Q4: [Aim 3 completion + synthesis]
- Expected outputs: [papers, tools, final report]
```

#### 2.5 Structural Review

Invoke `/research-review` to get critical feedback on the proposal structure before drafting:

```
/research-review "[GRANT_TYPE] [GRANT_SUBTYPE] proposal structure:
Gap: [gap statement]
Aims: [aims list with claims-evidence matrix]
Timeline: [timeline]
— reviewer persona: [GRANT_TYPE] review panelist"
```

**What this does:**
- GPT-5.4 xhigh acts as a grant review panelist (not a paper reviewer)
- Evaluates aims independence, narrative arc, risk identification, timeline realism
- Identifies the single biggest reviewer concern
- Provides actionable fixes ranked by severity

Apply structural feedback before proceeding to drafting.

**🚦 Checkpoint:** Present the proposal structure to the user:

```
🏗️ Proposal structure designed:
- Gap: [gap statement]
- Aim 1: [title] — Risk: LOW
- Aim 2: [title] — Risk: MEDIUM
- Aim 3: [title] — Risk: LOW
- Timeline: [summary]
- Reviewer feedback: [key points from GPT-5.4]

Proceed to section drafting? Or adjust the structure?
```

**⛔ STOP HERE. This is the most critical checkpoint — the proposal structure determines everything downstream.**

Options for the user:
- Reply **"go"** or **"ok"** → proceed to Phase 3 (section drafting)
- Reply with **structural changes** (e.g., "merge Aim 2 and 3", "add an aim about X", "reduce to 2 aims") → redesign and re-present
- Reply **"back"** → return to Phase 1 to adjust the gap/positioning
- Reply **"stop"** → save current structure to `grant-proposal/DRAFT_NOTES.md`

**State**: Write `GRANT_STATE.json` with `phase: 2`, aims summary, and Codex threadId.

### Phase 3: Section Drafting

Draft each section according to the grant type template. Write **complete prose**, not outlines or placeholders.

**What this does:**
- Writes all required sections in the agency-specific language and tone
- Pulls content from idea-stage/IDEA_REPORT.md, FINAL_PROPOSAL.md, and literature notes
- Uses `/paper-illustration` for figure generation (if user requests)
- Leaves `[TODO]` only for PI-specific information, `[AMOUNT]` for budget figures
- Outputs `grant-proposal/GRANT_PROPOSAL.md`

#### Drafting Order (optimized for narrative coherence)

1. **Specific Aims / Research Objective** — the "abstract" of the grant. Write first, refine last.
2. **Background / Significance / State of the Art** — establish the problem and gap.
3. **Research Plan / Methods** — per aim, with feasibility arguments.
4. **Figures** — generate key diagrams (see below).
5. **Timeline & Milestones** — year-by-year deliverables.
6. **PI Qualification / Preparation Status** — track record, team, infrastructure.
7. **Budget Justification** — narrative only (leave dollar/yen amounts as `[AMOUNT]` placeholders).
8. **Broader Impacts / Societal Significance** — if required by the grant type.

#### Figure Generation

Grant proposals benefit greatly from clear diagrams. Generate the following figures using SVG or matplotlib (save to `grant-proposal/figures/`):

1. **全体構成図 / Overview Diagram** — Show the relationship between aims (Aim 1 → Aim 2 → Aim 3), shared resources (participants, stimuli, pipeline), and outputs. This is the single most important figure.
2. **実験パラダイム図 / Experimental Paradigm** — Visual schematic of each paradigm (stimulus timing, conditions, EEG recording).
3. **年次計画 / Timeline Gantt Chart** — Year-by-year (or H1/H2) milestones with deliverables.

For AI-generated publication-quality figures, invoke `/paper-illustration`:

```
/paper-illustration "Overview diagram showing [aims relationship + shared resources] for grant proposal"
```

For simpler diagrams (flowcharts, Gantt charts), generate clean SVG or matplotlib directly via code.

**🚦 Figure Checkpoint:** Before generating, ask which figures the user wants:

```
🎨 The following figures would strengthen this proposal:
1. 全体構成図 / Overview — aims relationship + shared resources
2. 実験パラダイム図 / Paradigm — stimulus timing + conditions
3. 年次計画 / Gantt — timeline with milestones

Which should I generate? (e.g., "1 and 3", "all", "skip")
```

**⛔ Wait for user response.** Generate only the requested figures.

#### Grant-Specific Drafting Guidelines

**KAKENHI:**
- Write in formal Japanese academic style (である調, not です/ます調)
- Use 「」for Japanese quotations, bold for emphasis
- Structure: 研究の学術的背景 → 研究期間内に何をどこまで明らかにするか → 本研究の学術的な特色・独創性
- Include explicit 年次計画 (yearly plan) with concrete milestones
- Emphasize 社会的意義 (societal significance)
- Reference related KAKEN-funded projects to show awareness of the field

**NSF:**
- Write in clear, direct English
- Use Aim-based structure with bold headings
- Preliminary data paragraphs for each Aim (with figure references)
- Broader Impacts must be concrete: specific outreach activities, broadening participation plans
- Include Results from Prior Support (if PI has prior NSF funding)

**NSFC:**
- Write in formal Chinese academic style
- 立项依据 must position work at 国际前沿 (international frontier)
- 创新性 section must list numbered innovation points (创新点)
- 研究基础 must cite PI's own publications (with IF and citations if possible)
- 可行性分析 must address: technical feasibility, team capability, time feasibility, equipment/conditions

**ERC:**
- Write a compelling "high-risk/high-gain" narrative
- Extended Synopsis must be self-contained and compelling
- Include Work Package table with deliverables and milestones
- Gantt chart (describe in text, or generate as figure)

#### For Each Section

1. **Pull relevant content** from idea-stage/IDEA_REPORT.md, FINAL_PROPOSAL.md, literature notes
2. **Write complete prose** — no `[TODO]` except for PI-specific information
3. **Include figure/table placeholders** where appropriate (e.g., `[Figure 1: System architecture]`)
4. **Cite references properly** — use citation keys, will build bibliography later
5. **Match the agency's tone and style** — formal Japanese for KAKENHI, direct English for NSF, etc.

### Phase 4: External Review

Invoke `/research-review` on the complete draft for grant-type-specific evaluation:

```
/research-review "Complete [GRANT_TYPE] [GRANT_SUBTYPE] proposal draft. Evaluate as a [GRANT_TYPE] review panelist using official criteria. [PASTE FULL PROPOSAL TEXT]"
```

**What this does:**
- GPT-5.4 xhigh acts as a grant review panelist
- Scores each section 1-5 using agency-specific criteria
- Identifies fatal flaws and recommends funding/revisions/rejection
- Provides ranked action items for improvement
- All feedback saved to `grant-proposal/GRANT_REVIEW.md`

> ⚠️ **Codex MCP fallback**: If `mcp__codex__codex` is not available (no OpenAI API key), skip external review. Note "External review skipped — no Codex MCP available. Consider running `/auto-review-loop-llm` separately." in GRANT_REVIEW.md. The proposal is still usable without external review.

If `/research-review` is invoked (preferred), it handles the Codex call internally. If calling Codex directly (e.g., to maintain thread context from Phase 2):

#### Round 1 (full draft review):

```
mcp__codex__codex-reply:
  threadId: [from Phase 2]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    Review this complete [GRANT_TYPE] [GRANT_SUBTYPE] proposal draft.

    Act as a [GRANT_TYPE] review panelist. Evaluate using the official criteria:

    [INSERT GRANT-TYPE-SPECIFIC CRITERIA — see Grant Type Specifications above]

    For each section:
    1. Score 1-5 (5 = excellent)
    2. Strongest aspect
    3. Most critical weakness
    4. Specific fix suggestion (actionable, not vague)

    Overall assessment:
    - Would you recommend funding? (Yes / Yes with revisions / No)
    - Single most impactful change to improve funding chances?
    - Any fatal flaws?

    [PASTE FULL PROPOSAL TEXT]
```

#### Round 2+ (after revisions):

If MAX_REVIEW_ROUNDS > 1 and revisions were applied:

```
mcp__codex__codex-reply:
  threadId: [saved from Round 1]
  config: {"model_reasoning_effort": "xhigh"}
  prompt: |
    [Round N review of revised [GRANT_TYPE] [GRANT_SUBTYPE] proposal]

    Since your last review, I have applied the following changes:
    1. [Change 1]: [what was done]
    2. [Change 2]: [what was done]
    3. [Change 3]: [what was done]

    Please re-evaluate. Same format: section scores, overall assessment, remaining weaknesses.
    Focus on whether the CRITICAL and MAJOR issues from Round 1 have been adequately addressed.

    [PASTE REVISED PROPOSAL TEXT]
```

### Phase 5: Revision & Output

#### 5.1 Apply Reviewer Feedback

Parse reviewer feedback into severity levels:
- **CRITICAL** — fatal flaws that would lead to rejection. Fix immediately.
- **MAJOR** — significant weaknesses. Fix before submission.
- **MINOR** — suggestions for improvement. Fix if time allows.

Implement CRITICAL and MAJOR fixes. If MAX_REVIEW_ROUNDS > 1, re-submit for another round via `mcp__codex__codex-reply`.

#### 5.2 Generate Output

**Markdown output** (default):

```
grant-proposal/
├── GRANT_PROPOSAL.md          # Complete proposal, all sections
├── GRANT_REVIEW.md            # Review history and reviewer feedback
├── GRANT_STATE.json           # State persistence file
├── figures/                   # Generated diagrams (if any)
└── references.bib             # Bibliography (if citations were used)
```

**LaTeX output** (when OUTPUT_FORMAT = latex):

```
grant-proposal/
├── main.tex                   # Master file
├── sections/
│   ├── aims.tex               # Specific Aims / Research Objective
│   ├── background.tex         # Background / Significance
│   ├── research_plan.tex      # Research Plan / Methods
│   ├── timeline.tex           # Timeline & Milestones
│   ├── pi_qualification.tex   # PI Qualification / Track Record
│   └── budget.tex             # Budget Justification (if applicable)
├── references.bib
└── figures/                   # Any generated diagrams
```

#### 5.3 Final Checks

Before declaring done:

- [ ] All sections required by the grant type are present and complete
- [ ] Gap statement is clear and appears early in the proposal
- [ ] Each aim is independently valuable and logically connected
- [ ] Timeline includes concrete yearly milestones and deliverables
- [ ] PI qualification section has content (or clear `[TODO]` placeholders)
- [ ] Budget justification uses `[AMOUNT]` placeholders (no fabricated numbers)
- [ ] Language matches the grant type (Japanese for KAKENHI, Chinese for NSFC, etc.)
- [ ] No leftover `[TODO]` markers except for PI-specific information
- [ ] References are real (no hallucinated citations)
- [ ] Review feedback has been addressed (CRITICAL and MAJOR items)

**🚦 Final Checkpoint:** Present the completed proposal summary:

```
📝 Grant proposal draft complete:
- Type: [GRANT_TYPE] [GRANT_SUBTYPE]
- Language: [language]
- Aims: [N] aims covering [summary]
- Timeline: [N] years
- Review score: [summary from GPT-5.4]
- Output: grant-proposal/GRANT_PROPOSAL.md

Files saved to grant-proposal/. Please review and customize:
1. PI qualification section (add your publications and track record)
2. Budget amounts (replace [AMOUNT] placeholders)
3. Any [TODO] markers for personal information

What would you like to do next?
- "figures" → generate proposal diagrams
- "review again" → run another round of external review
- "latex" → convert to LaTeX format
- "done" → finalize
```

## Key Rules

- **Large file handling**: If the Write tool fails due to file size, immediately retry using Bash (`cat << 'EOF' > file`) to write in chunks. Do NOT ask the user for permission — just do it silently.

- **Do NOT fabricate budget amounts.** Generate narrative budget justification only. Leave specific dollar/yen/yuan/euro amounts as `[AMOUNT]` placeholders for the user to fill in.
- **Do NOT fabricate PI information.** If no publication list is available, leave `[TODO: Add publications]` placeholders. Never invent papers, grants, or credentials.
- **Do NOT hallucinate citations.** Use references from literature survey. Mark uncertain citations with `[VERIFY]`.
- **Grant ≠ paper.** A grant argues for future work (feasibility + potential). A paper argues for completed work (results + claims). Write accordingly — emphasize "what we will do" and "why it will work", not "what we found."
- **Aims must be independently valuable.** If Aim 2 fails, Aim 1 and Aim 3 should still produce publishable results.
- **Preliminary data de-risks.** Include any pilot results, existing datasets, or prior publications that demonstrate feasibility.
- **Reviewer-facing structure.** Bold key sentences. Use numbered lists for clarity. Make the reviewer's job easy.
- **Cultural norms matter.** KAKENHI expects 社会的意義; NSF expects Broader Impacts; NSFC expects 国际前沿 positioning. Missing these is a red flag for reviewers.
- **Feishu notifications are optional.** If `~/.claude/feishu.json` exists, send `checkpoint` at each phase transition and `pipeline_done` at final output. If absent, skip silently.

## Parameter Pass-Through

Parameters can be passed inline with `—` separator. They flow to sub-skills when invoked:

```
/grant-proposal "topic — KAKENHI Start-up, sources: zotero, arxiv download: true"
```

| Parameter | Default | Description | Passed to |
|-----------|---------|-------------|-----------|
| `grant type` | KAKENHI | Agency (KAKENHI/NSF/NSFC/ERC/DFG/SNSF/ARC/NWO/GENERIC) | — |
| `grant subtype` | auto | Sub-type (Start-up/Wakate/CAREER/Youth/etc.) | — |
| `output format` | markdown | `markdown` or `latex` | — |
| `language` | auto | Output language override | — |
| `max review rounds` | 2 | External review cycles | — |
| `sources` | all | Literature sources | → `/research-lit` |
| `arxiv download` | false | Download arXiv PDFs | → `/research-lit` |
| `reviewer model` | gpt-5.4 | Codex review model | → Codex MCP |
| `auto proceed` | false | Skip checkpoints | — |

## Composing with Other Skills

### Sub-skills used by this skill

| Sub-skill | Phase | Purpose |
|-----------|:-----:|---------|
| `/research-lit` | 1 | Literature survey (if not already done) |
| `/novelty-check` | 1 | Verify the gap is real |
| `/research-review` | 2, 4 | Structural review + full draft review |
| `/paper-illustration` | 3 | Generate proposal figures (optional) |

### Funding Track (this skill's primary use case)

```
/idea-discovery "direction"              ← Workflow 1: find validated ideas
/research-refine "idea"                  ← sharpen the method
/grant-proposal "idea — KAKENHI"         ← this skill: write the grant proposal
                                          ← [submit & get funded]
/experiment-bridge                       ← implement experiments with funding
/auto-review-loop "results"              ← Workflow 2: iterate until submission-ready
/paper-writing                           ← Workflow 3: write the paper
```

### Publish Track (skip this skill)

```
/idea-discovery → /experiment-bridge → /auto-review-loop → /paper-writing → submit
```

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)** — write timestamped file first, then copy to fixed name
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)** — log every output to MANIFEST.md
> - **[Output Language Protocol](../shared-references/output-language.md)** — respect the project's language setting
