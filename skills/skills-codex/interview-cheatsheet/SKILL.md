---
name: interview-cheatsheet
description: "Generate a long-form Chinese interview-prep cheat sheet on a specific ML/LLM topic — formulas with derivations, from-scratch PyTorch code, comparison tables, and 高频面试题 (L1 必会 / L2 进阶 / L3 顶级 lab). Use when the user says '写面试 cheat sheet', '写一份 X 教程', '帮我准备 Y 面试题', '出一份 X 速查', or wants a detailed Chinese tutorial on a specific ML topic."
argument-hint: '<topic> [--effort balanced|max] [--byline "Name (姓名), Affiliation"] [--commit false]'
allowed-tools: Bash(*), Read, Write, Edit, spawn_agent, mcp__antigravity__antigravity, mcp__antigravity__antigravity-reply, mcp__grok__grok, mcp__grok__grok-reply, mcp__claude-review__review, mcp__claude-review__review_reply, mcp__claude-review__review_start, mcp__claude-review__review_reply_start, mcp__claude-review__review_status
---

# /interview-cheatsheet — long-form Chinese ML/LLM interview prep

> **Before each reviewer slot**, follow [Selectable Reviewers](../shared-references/reviewer-backends.md):
> resolve invocation → `.aris/reviewer.json` → Codex default (fresh native reviewer)
> with `reviewer_route.py` through the canonical helper resolver, preserving this
> slot's tier, fresh contexts, source/image inputs and deterministic gates.
> Codex examples/pins below apply only to `backend=codex`; other routes use their
> own first-call/reply contract. Save the route and actual returned identity;
> unavailable selections are `REVIEW_UNAVAILABLE`. Classify acceptance from actual
> families/completion/scope. Forward invocation reviewer/model/effort overrides
> to reviewer-bearing children. Generation workers are unchanged.


Generate one comprehensive Chinese cheat sheet per invocation: formulas + derivations + from-scratch code + 分层面试题. Output receives a fresh selected math/code review before rendering; same-family positives remain provisional. **Detect-only by default: never auto-commits.**

## Inputs

- **`<topic>`** (required) — focused enough for one coherent tutorial. Good: "RLHF / DPO / PPO", "MoE", "KV Cache + Speculative Decoding". Bad (too broad): "all of LLM training", "diffusion" (split into Forward Process / Sampling / CFG separately).
- **`--effort`** (default `balanced`) — `balanced` covers the core intuition, derivations, working implementation and representative questions; `max` adds deeper proofs, engineering tradeoffs and advanced questions where they improve understanding. Neither setting imposes a line or question count.
- **`--byline`** (default `"<Your Name>, <Affiliation>"`) — passed to `/render-html --author`.
- **`--commit`** (default `false`) — if `false` (default), stop after rendering; user reviews and commits. Never push without explicit user approval.

## Style guide — STRICT (read `docs/tutorials/attention_tutorial.md` as canonical reference)

### Section skeleton (adapt to the topic)

```
## §0 TL;DR — callout intro line + a short list of key takeaways
## §1 直觉 — why this matters; analogy; one-paragraph mental model
## §2 核心公式 — main formula + derivation (variance / scaling / boundary)
## §3 实现细节 — a focused, runnable from-scratch PyTorch example
## §4-7 变体 / 工程实践 / 常见 bug — variants, comparison tables, footguns
## §8 复杂度 / 资源 — time + memory complexity
## §9 与相关方法对比 — placement in the ecosystem
## §10 高频面试题 — L1 必会 / L2 进阶 / L3 顶级 lab as relevant, with <details><summary> collapsible answers
## §A 附录 (optional) — sanity-check output, reference list
```

Use this as a coverage guide, not a required section count: combine or omit sections that do not serve the topic, and add sections for substantive gaps. Select questions that test distinct concepts; do not pad any difficulty tier.

### Conventions — bake the established lessons in

| Rule | Why | Example |
|---|---|---|
| Heading format `## §N Title` with **space after §N** | Older versions had `§0TL;DR` glued | `## §0 TL;DR Cheat Sheet` |
| Math in table cells: use `\lvert ... \rvert` not `\|...\|` | `\|` inside markdown table = cell separator → row break | `$\text{score}_{ij} - m \cdot \lvert i-j \rvert$` |
| Callouts with body list: **split** into callout intro line + separate list | Otherwise the list's first item is swallowed by the callout, then items 2..N restart numbering at 1 | `> 💡 **Sampler 选择** — 按 NFE/质量排序如下。`<br/>`- Euler …`<br/>`- Heun …` |
| Callout prefixes only: `💡` `⚠️` `✅` `❌` (others won't get class) | renderer maps these to `callout-info/warn/good/bad` | `> ⚠️ **FP16 overflow** — 即使除了 √d_k …` |
| Math: `$...$` inline, `$$...$$` display, `$$\boxed{...}$$` for key boxes | MathJax CDN; literal in source | — |
| Code: ```python fences, **real PyTorch that would run** | reviewer will check executability | — |
| Personal-info banlist: owner's institution/lab/center names, degree-program affiliations, private server aliases, job-search context, `/Users/...` paths, specific lab/company names | reviewer flags as FAIL | byline goes via `--author` at render time, not in body |
| Language: Chinese primary, English technical terms in-place | matches established cheat-sheet style | "softmax 饱和", "vector field" |

### Eyebrow / subtitle / title naming

| Field | Pattern |
|---|---|
| `--eyebrow` | `Interview Prep · <Topic>` |
| `--subtitle` | one Chinese sentence describing scope (e.g. `公式推导 + From-Scratch 代码 + 分层面试题（L1 必会 · L2 进阶 · L3 顶级 lab）`) |
| `--title` | `<Topic> 面试 Cheat Sheet` or `<Topic> Quick Reference` |
| `--lang` | `zh-CN` |

### Slug
`<topic>` → kebab/snake-case `<slug>` for filenames. e.g. "RLHF / DPO / PPO" → `rlhf_dpo_ppo`.

## Workflow

### Step 1 — Plan structure (no files written)

Internally sketch:
- Section titles covering the topic’s learning path
- List of major formulas (with derivation outline for each)
- List of code blocks (skeleton + what it demonstrates)
- Representative interview questions sorted by L1 / L2 / L3 difficulty (each with one-line expected answer)
- Comparison table topics (e.g., "RLHF vs DPO vs IPO vs SimPO")

If the topic is too broad to fit in one cheat sheet, **stop and ask the user to scope** before drafting.

### Step 2 — Draft MD

Write directly to `docs/tutorials/<slug>_tutorial.md`. Follow the style guide and requested depth. Finish when the core concepts, derivations, runnable examples and distinct interview questions are explained clearly; remove repetition rather than filling a length target.

### Step 3 — Fresh selected math/code review (Codex default xhigh; same-family stays provisional)

Invoke `spawn_agent` with `model: gpt-6-astra`, `reasoning_effort: xhigh`, and a fresh thread. Do not reuse prior reviewer context.

Reviewer prompt:

```
You are reviewing a long-form Chinese interview-prep tutorial on <TOPIC> for math/code/factual correctness and style discipline.

## Files to read (READ-ONLY)
- Draft MD: <MD_PATH>
- Style reference: docs/tutorials/attention_tutorial.md
  (Read this only for STYLE — do NOT score the draft against the reference's content topic.)

## Return JSON with these checks

1. formula_correctness — Independently re-derive each $$ display formula. Flag any error with file:line.
2. code_correctness — For each python block: would it run? Does it implement the stated math? Imports / shapes / device handling consistent?
3. interview_answer_correctness — Each L1/L2/L3 question's <details> answer. Specifically flag wrong year / wrong paper / wrong author / off-by-one indexing / inverted comparison.
4. historical_citations — Paper authors + year + venue. Flag wrong attributions (e.g., "DPO: Rafailov 2023 NeurIPS" must be checkable).
5. table_pipe_escape — Any markdown table cell containing `|x|` math (not `\lvert x \rvert`)? Cite line.
6. callout_list_collision — Any line matching the pattern `^> (?:💡|⚠️|✅|❌) \*\*[^*]+\*\* — (?:- |\d+\. )`? That swallows the list.
7. heading_consistency — All `## §N` and `### N.M` follow style guide (space after §N, no glued chars).
8. topic_coverage — Does the tutorial explain the promised scope at the requested depth? Identify specific missing concepts or unanswered learning questions; do not require fixed sections, lines or question counts.
9. personal_info_leak — None of: the owner's institution / lab / center names, degree-program affiliations, private server aliases, job-search or recruitment context, absolute `/Users/...` paths. (Keep the concrete string banlist in local untracked notes — the public SKILL defines only the CATEGORIES; listing the real values here would itself be the leak.)

Return JSON:
{
  "verdict": "PASS | WARN | FAIL",
  "checks": {<check_name>: "pass|warn|fail with one-line note + file:line if applicable"},
  "blocking_issues": ["..."],
  "warnings": ["..."]
}

Verdict: PASS = all pass, WARN = only nonblocking issues, FAIL = any math/code/factual error OR personal-info leak OR table-pipe / callout-list bug.
```

### Step 4 — Resolve concrete review findings

Fix substantiated math, code, factual and rendering defects. Run the relevant code or calculation checks, then request a focused fresh review of the fixes and any affected claims. Preserve the selected reviewer route and fresh-context contract from Step 3.

Stop when the concrete blockers are resolved; a cosmetic WARN does not require another round. Do not seek a higher verdict by repeatedly reviewing unchanged content. If an issue repeats without new evidence, or requires a scope decision, report the unresolved issue and the work needed to resolve it. Do not present the tutorial as accepted while a blocker remains.

### Step 5 — Render via /render-html

Call directly (do not invoke `/render-html` as a sub-skill; call its python script — gives clear control):

```bash
python3 skills/render-html/scripts/render_html.py docs/tutorials/<slug>_tutorial.md \
  --template academic \
  --out docs/tutorials/<slug>_tutorial.html \
  --title "<Topic> 面试 Cheat Sheet" \
  --subtitle "<one-line scope summary>" \
  --eyebrow "Interview Prep · <Topic>" \
  --author "<byline>" \
  --lang zh-CN
```

`render_html.py` renders the HTML; it does not invoke a reviewer or write a review audit. Inspect the rendered output for broken math, code, tables, callouts and navigation. Record the actual checks and results. If a defect appears, fix its source, re-render and verify the affected output. Use a fresh selected reviewer when a remaining visual question needs independent inspection; apply Step 4’s stopping rule.

### Step 6 — Combine audit trail

After concrete blockers are resolved, save the math/code review and actual render checks in one `docs/tutorials/<slug>_tutorial.review.json`:

```json
{
  "skill": "interview-cheatsheet",
  "source": "docs/tutorials/<slug>_tutorial.md",
  "source_sha256_prefix": "<16-char prefix>",
  "output": "docs/tutorials/<slug>_tutorial.html",
  "topic": "<TOPIC>",
  "effort": "balanced | max",
  "byline": "<author string>",
  "math_code_review": {
    "verdict": "<actual verdict>",
    "rounds": [
      {"run": 1, "verdict": "...", "thread_id": "...", "issue": "...", "fix": "..."},
      ...
    ]
  },
  "render_review": {
    "verdict": "<actual verdict>",
    "rounds": [...]
  },
  "summary": "<actual acceptance status, checks performed and unresolved nonblocking notes>",
  "rendered_at": "<YYYY-MM-DD>"
}
```

### Step 7 — Stop. Report to user.

Do **NOT** `git add` / `git commit` / `git push`. Report:

```
✅ /interview-cheatsheet "<TOPIC>" complete.

  Files:
    docs/tutorials/<slug>_tutorial.md          (<lines> lines, <bytes> bytes)
    docs/tutorials/<slug>_tutorial.html        (<bytes> bytes, <TOC> TOC entries)
    docs/tutorials/<slug>_tutorial.review.json

  Math/code review:  <actual verdict and acceptance status> (<thread IDs>)
  Render checks:     <checks performed and actual results>
  Depth:             <effort>; <brief scope covered>

  Issues caught + fixed during review:
    - <one line per non-trivial fix>

  Suggested commit message:
    docs(tutorials): add <Topic> cheat sheet (rendered via /render-html)

  ⚠️ Did NOT auto-commit — user reviews and pushes manually.
  Also update docs/tutorials/README.md to add the new row.
```

## Update the index

After the tutorial passes, optionally append a row to `docs/tutorials/README.md`:

```
| **<Topic> 面试 Cheat Sheet** | [`<slug>_tutorial.md`](<slug>_tutorial.md) | [`<slug>_tutorial.html`](https://wanshuiyin.github.io/Auto-claude-code-research-in-sleep/tutorials/<slug>_tutorial.html) | <one-line topic list> |
```

Suggest the row to the user but let them edit it in themselves if they want to curate.

## Key invariants (the ARIS rules baked in)

| Invariant | How it's enforced |
|---|---|
| Executor/reviewer family | Record actual executor/reviewer identities at both stages; same-family positives remain provisional |
| Fresh agent per reviewer call | Step 3 and any independent render review use fresh `spawn_agent` calls |
| Codex reasoning = xhigh | Hardcoded in Step 3 reviewer config |
| Personal info redaction | Math/code review and render inspection check; banlist in style guide |
| Lessons-learned encoded | Table-pipe + callout-list collision rules in style guide AND review checks 5+6 |
| No silent failure | Stop when concrete blockers are resolved; report unresolved repeated or scope-dependent issues rather than restarting the same review |

## When NOT to use

- Topic too broad — split into smaller scopes first
- Topic outside ML/LLM core — this style guide assumes math + code + Chinese; for general topics use a different format or write directly
- Already have a draft you want to edit — use Edit directly, this skill is for greenfield generation
- Don't want HTML output — call `/render-html` separately or skip Step 5

## Reference invocations

```
/interview-cheatsheet "RLHF / DPO / PPO"
/interview-cheatsheet "MoE (Mixture-of-Experts)" — effort: max
/interview-cheatsheet "KV Cache + Speculative Decoding"
/interview-cheatsheet "Long-context: RoPE / YaRN / NTK / MLA"
/interview-cheatsheet "Distributed Training (DDP / FSDP / ZeRO / TP / PP)"
/interview-cheatsheet "Quantization (GPTQ / AWQ / INT4 / FP8 / SmoothQuant)"
```

## Reference style files

- Style canonical: `docs/tutorials/attention_tutorial.md` + `.html`
- Style secondary: `docs/tutorials/flow_matching_tutorial.md` + `.html`
- Review audit format: `docs/tutorials/attention_tutorial.review.json`

## Provenance

Extracted from the two pilot tutorials (Attention + Flow Matching, May 2026). Both passed fresh-agent review; that review is same-family provisional in the base Codex mirror. The attention tutorial required 3 rounds and caught a table-pipe collision plus a callout-list collision.
