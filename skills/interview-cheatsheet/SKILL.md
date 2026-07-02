---
name: interview-cheatsheet
description: "Generate a long-form Chinese interview-prep cheat sheet on a specific ML/LLM topic — formulas with derivations, from-scratch PyTorch code, comparison tables, and 25 高频面试题 (L1 必会 / L2 进阶 / L3 顶级 lab). Use when the user says '写面试 cheat sheet', '写一份 X 教程', '帮我准备 Y 面试题', '出一份 X 速查', or wants a 600-1000 line Chinese tutorial on a specific ML topic."
argument-hint: <topic> [--effort balanced|max] [--byline "Name (姓名), Affiliation"] [--commit false]
allowed-tools: Bash(*), Read, Write, Edit, mcp__codex__codex
---

# /interview-cheatsheet — long-form Chinese ML/LLM interview prep

Generate one comprehensive Chinese cheat sheet per invocation: formulas + derivations + from-scratch code + 25 高频题. Output passes cross-model math/code review before rendering. **Detect-only by default: never auto-commits.**

## Inputs

- **`<topic>`** (required) — narrow enough for one 600-1000 line tutorial. Good: "RLHF / DPO / PPO", "MoE", "KV Cache + Speculative Decoding". Bad (too broad): "all of LLM training", "diffusion" (split into Forward Process / Sampling / CFG separately).
- **`--effort`** (default `balanced`) — `balanced` ≈ 600 lines, `max` ≈ 1000 lines with deeper proofs and more L3 questions.
- **`--byline`** (default `"<Your Name>, <Affiliation>"`) — passed to `/render-html --author`.
- **`--commit`** (default `false`) — if `false` (default), stop after rendering; user reviews and commits. Never push without explicit user approval.

## Style guide — STRICT (read `docs/tutorials/attention_tutorial.md` as canonical reference)

### Section skeleton (12-14 sections)

```
## §0 TL;DR — callout intro line + numbered list of 5-7 takeaways
## §1 直觉 — why this matters; analogy; one-paragraph mental model
## §2 核心公式 — main formula + derivation (variance / scaling / boundary)
## §3 实现细节 — 50-80 line from-scratch PyTorch
## §4-7 变体 / 工程实践 / 常见 bug — variants, comparison tables, footguns
## §8 复杂度 / 资源 — time + memory complexity
## §9 与相关方法对比 — placement in the ecosystem
## §10 25 高频面试题 — L1 (10 必会) + L2 (10 进阶) + L3 (5 顶级 lab), all with <details><summary> collapsible answers
## §A 附录 (optional) — sanity-check output, reference list
```

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
| `--subtitle` | one Chinese sentence describing scope (e.g. `公式推导 + From-Scratch 代码 + 25 高频题（L1 必会 · L2 进阶 · L3 顶级 lab）`) |
| `--title` | `<Topic> 面试 Cheat Sheet` or `<Topic> Quick Reference` |
| `--lang` | `zh-CN` |

### Slug
`<topic>` → kebab/snake-case `<slug>` for filenames. e.g. "RLHF / DPO / PPO" → `rlhf_dpo_ppo`.

## Workflow

### Step 1 — Plan structure (no files written)

Internally sketch:
- 12-14 section titles
- List of major formulas (with derivation outline for each)
- List of code blocks (skeleton + what it demonstrates)
- 25 interview questions sorted by L1 / L2 / L3 difficulty (each with one-line expected answer)
- Comparison table topics (e.g., "RLHF vs DPO vs IPO vs SimPO")

If the topic is too broad to fit in one cheat sheet, **stop and ask the user to scope** before drafting.

### Step 2 — Draft MD

Write directly to `docs/tutorials/<slug>_tutorial.md`. Follow the style guide. Length target: 600 lines (balanced) or 1000 lines (max), ±20%.

### Step 3 — Cross-model math/code review (codex 5.5 xhigh, FRESH thread)

Invoke `mcp__codex__codex` with `model: gpt-5.5`, `config: {model_reasoning_effort: xhigh}`, `sandbox: read-only`, fresh thread (never `codex-reply`).

Reviewer prompt:

```
You are reviewing a long-form Chinese interview-prep tutorial on <TOPIC> for math/code/factual correctness and style discipline.

## Files to read (READ-ONLY)
- Draft MD: <MD_PATH>
- Style reference: docs/tutorials/attention_tutorial.md
  (Read this only for STYLE — do NOT score the draft against the reference's content topic.)

## Return JSON with these 10 checks

1. formula_correctness — Independently re-derive each $$ display formula. Flag any error with file:line.
2. code_correctness — For each python block: would it run? Does it implement the stated math? Imports / shapes / device handling consistent?
3. interview_answer_correctness — Each L1/L2/L3 question's <details> answer. Specifically flag wrong year / wrong paper / wrong author / off-by-one indexing / inverted comparison.
4. historical_citations — Paper authors + year + venue. Flag wrong attributions (e.g., "DPO: Rafailov 2023 NeurIPS" must be checkable).
5. table_pipe_escape — Any markdown table cell containing `|x|` math (not `\lvert x \rvert`)? Cite line.
6. callout_list_collision — Any line matching the pattern `^> (?:💡|⚠️|✅|❌) \*\*[^*]+\*\* — (?:- |\d+\. )`? That swallows the list.
7. heading_consistency — All `## §N` and `### N.M` follow style guide (space after §N, no glued chars).
8. section_completeness — Sections §0..§10 (and §A if effort=max) present and non-trivial.
9. length_target — Within ±20% of target (600 for balanced, 1000 for max).
10. personal_info_leak — None of: the owner's institution / lab / center names, degree-program affiliations, private server aliases, job-search or recruitment context, absolute `/Users/...` paths. (Keep the concrete string banlist in local untracked notes — the public SKILL defines only the CATEGORIES; listing the real values here would itself be the leak.)

Return JSON:
{
  "verdict": "PASS | WARN | FAIL",
  "checks": {<check_name>: "pass|warn|fail with one-line note + file:line if applicable"},
  "blocking_issues": ["..."],
  "warnings": ["..."]
}

Verdict: PASS = all pass, WARN = at most cosmetic issues (length slight off / cosmetic style), FAIL = any math/code/factual error OR personal-info leak OR table-pipe / callout-list bug.
```

### Step 4 — Fix and loop (no hard cap — judge by trajectory)

For each FAIL issue, edit the MD. Then re-invoke codex with a **fresh thread** (never reuse threadId). Stop when verdict = PASS or WARN with no FAIL items.

**No hard round cap.** Use these heuristics instead:

- ✅ **Keep going** if each round's FAIL items are *shrinking, concrete, enumerable* (e.g., citation year fixes, off-by-one, single-line code bugs). The reviewer is doing useful work — let it converge.
- ⛔ **Stop and report** if the same issue keeps coming back (loop detected), or if the FAIL items shift to architectural / scope concerns that need user input, or if the round count exceeds ~6 without convergence.

Most tutorials converge in 3-5 rounds. Going to 5-6 rounds is fine if substantive bugs are still being caught — the Video Generation tutorial (May 2026) went to 5 rounds and the final 2 rounds caught real citation errors and an over-attribution to Sora's patch size that would have shipped otherwise.

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

`render_html.py` runs its own 13-check codex review automatically. If that FAILs, fix the MD (often a table-pipe or callout-list issue the math/code reviewer missed) and re-render. Note that `render_html.py` itself writes `<slug>_tutorial.review.json` for the render-stage audit.

### Step 6 — Combine audit trail

After both reviews pass, merge math/code review history + render review history into one `docs/tutorials/<slug>_tutorial.review.json`:

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
    "verdict": "PASS",
    "rounds": [
      {"run": 1, "verdict": "...", "thread_id": "...", "issue": "...", "fix": "..."},
      ...
    ]
  },
  "render_review": {
    "verdict": "PASS",
    "rounds": [...]
  },
  "summary": "<one-line: N-round math/code review + M-round render review settled at PASS>",
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

  Math/code review:  PASS after <N> rounds (<thread IDs>)
  Render review:     PASS after <M> rounds
  Length:            <actual> lines (target <effort>)

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
| Executor != reviewer family | Claude drafts; gpt-5.5 reviews (math/code stage); gpt-5.5 reviews again (render stage) |
| Fresh thread per reviewer call | Step 3 + render's own gate both use `mcp__codex__codex` not `codex-reply` |
| Codex reasoning = xhigh | Hardcoded in Step 3 reviewer config |
| Personal info redaction | Both math/code reviewer and render reviewer check; banlist in style guide |
| Lessons-learned encoded | Table-pipe + callout-list collision rules in style guide AND review checks 5+6 |
| No silent failure | If review FAILs and the FAIL set is no longer shrinking (loop) or hits ~6 rounds without convergence, stop and report — don't push |

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

Extracted from the two pilot tutorials (Attention + Flow Matching, May 2026). Both passed cross-model review; the attention tutorial required 3 review rounds — catching a table-pipe collision and a callout-list collision that were not obvious from the rendered output. Those lessons are now baked into the style guide and reviewer checks 5+6 so future tutorials don't repeat them.
