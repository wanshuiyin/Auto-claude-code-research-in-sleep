---
name: render-html
description: "Render an ARIS Markdown / JSON artifact (IDEA_REPORT, AUTO_REVIEW, KILL_ARGUMENT, PAPER_PLAN, research-wiki state, etc.) into a single-file HTML view designed for human reading. Academic template outputs are gated by a fresh cross-model Codex review for render fidelity + safety (the ARIS invariant). Use when the user says \"渲染 HTML\", \"出一份 HTML 报告\", \"render html\", \"make this readable\", \"export to html\", or wants a polished web-rendered view of a Markdown artifact. Markdown/JSON stays the canonical source; HTML is a generated, reviewed view."
argument-hint: <input.md> [--template academic|dashboard] [--out <path>] [--title ...] [--state <state.json>] [--json <sidecar.json>] [--offline] [--review|--no-review]
allowed-tools: Bash(*), Read, Write, spawn_agent
---

# /render-html: Markdown → single-file HTML for human reading

> **Markdown is for writers. HTML is for readers.** ARIS workflow nodes write Markdown (canonical, audit-trail-friendly, machine-parseable). `/render-html` turns *selected* artifacts into a polished single-file HTML view for the human who actually has to read them. The Markdown stays the source of truth.

## When to use this skill

**Use `/render-html` for** ARIS artifacts that have a real human reader:

| Artifact | Why HTML helps | Template |
|----------|----------------|----------|
| `idea-stage/IDEA_REPORT.md` | Ranked ideas + pilot signal + scores feel like a decision dashboard, not a flat list | `academic` |
| `review-stage/AUTO_REVIEW.md` (+ `REVIEW_STATE.json`) | Round-by-round score progression + weakness status; pass `--state` to embed the JSON | `academic` |
| `paper/KILL_ARGUMENT.md` (+ `KILL_ARGUMENT.json`) | Per-point attack/defense with `<details>` Q&A cards + red/yellow/green callouts | `academic` |
| `research-wiki/SUMMARY.md` (or `research-wiki/index.md`) | Cross-entity cockpit: papers / ideas / experiments / claims at a glance | `dashboard` |
| `PAPER_PLAN.md` (optional) | Claims-evidence matrix renders better as a polished table than raw MD | `academic` |
| `RESUBMIT_REPORT.{md,json}` (optional) | 7-state failure-mode ledger | `academic` or `dashboard` |

**Do NOT use** for:
- LaTeX paper output — the final reader-facing artifact is PDF, not HTML.
- `SKILL.md` files — those are internal LLM-facing protocol.
- `.aris/traces/*` review traces — forensic debug, not human display.
- Every Markdown file in your project — only artifacts that benefit from sticky TOC, callouts, math, or score progressions.

## Core invariants

- **MD / JSON is canonical, HTML is generated view.** Edit the source, then re-render. Do not hand-edit the HTML.
- **Cross-model review at the artifact boundary** (ARIS invariant). Academic-template HTML — used for the artifacts humans actually read (IDEA_REPORT, AUTO_REVIEW, KILL_ARGUMENT, PAPER_PLAN) — is reviewed by a fresh cross-family Codex thread before being claimed as a finished view. Dashboard-template HTML (cockpit / debug views) skips review by default but accepts `--review` to force it. See § *HTML Review Gate* below.
- **Drift detection.** Every rendered HTML embeds the source path, SHA256, and generation timestamp in `<meta>` tags AND in the visible page header. If the HTML and source diverge, the meta tells you which version of the source produced it.
- **Single-file output.** No build system, no separate CSS, no `node_modules`. Just one `.html`.
- **CDN-friendly default, `--offline` fallback.** MathJax 3 and highlight.js load from `cdn.jsdelivr.net` by default. Pass `--offline` to skip both — math will appear as raw `$x$`, code blocks won't get syntax highlighting, but everything stays readable.
- **Pure stdlib helper.** `render_html.py` uses only `re`, `html`, `hashlib`, `json`, `datetime`, `pathlib`, `argparse`, `sys`. No pip install required.
- **Defense-in-depth XSS sanitization.** The helper strips `<script>`/`<style>`/`<iframe>`/`<object>`/`<embed>`/`<form>`/`<input>`/`<button>`/`<link>`/`<meta>`/`<base>` tags, all `on*` event-handler attributes (`onclick`, `onload`, …), and rewrites `javascript:`/`vbscript:`/`data:` href/src/action schemes to `#blocked-unsafe-url:`. ARIS workflow artifacts should not contain these in the first place, but the sanitizer is the safety net in case an LLM hallucinates one. Markdown text content is HTML-escaped separately and never reaches the sanitizer.

## Tool Location

Arch C self-contained: the canonical implementation lives at `skills/render-html/scripts/render_html.py` (this SKILL's own `scripts/` subdirectory), together with its templates at `skills/render-html/scripts/templates/{academic,dashboard}.html`. The helper is new — no legacy `tools/` shim exists.

Resolve `$RENDER_HTML` with the Codex hybrid chain (managed project install, in-repo checkout, ARIS repo fallback, then copied global Codex skill install). This is **Policy A — skill-local gate**:

```bash
RENDER_HTML=""
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills-codex.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills-codex.txt 2>/dev/null) || true
fi
[ -f ".agents/skills/render-html/scripts/render_html.py" ] && RENDER_HTML=".agents/skills/render-html/scripts/render_html.py"
[ -z "$RENDER_HTML" ] && [ -f "skills/render-html/scripts/render_html.py" ] && RENDER_HTML="skills/render-html/scripts/render_html.py"
[ -z "$RENDER_HTML" ] && [ -n "${ARIS_REPO:-}" ] && [ -f "$ARIS_REPO/skills/render-html/scripts/render_html.py" ] && RENDER_HTML="$ARIS_REPO/skills/render-html/scripts/render_html.py"
[ -z "$RENDER_HTML" ] && [ -f ~/.codex/skills/render-html/scripts/render_html.py ] && RENDER_HTML="$HOME/.codex/skills/render-html/scripts/render_html.py"
[ -z "$RENDER_HTML" ] && {
  echo "ERROR: render_html.py not resolved at .agents/skills/render-html/scripts/, skills/render-html/scripts/, \$ARIS_REPO/skills/render-html/scripts/, or ~/.codex/skills/render-html/scripts/." >&2
  echo "       /render-html cannot produce HTML output. Fix: rerun install_aris_codex.sh, export ARIS_REPO, or copy the render-html skill into ~/.codex/skills/." >&2
  exit 1
}
```

## Invocation

```bash
# Default: academic template, output to <input>.html alongside source
python3 "$RENDER_HTML" idea-stage/IDEA_REPORT.md

# Dashboard template for cockpit-style views
python3 "$RENDER_HTML" research-wiki/SUMMARY.md --template dashboard

# Custom output path + title + eyebrow
python3 "$RENDER_HTML" review-stage/AUTO_REVIEW.md \
  --out review-stage/AUTO_REVIEW.html \
  --title "Auto Review — overnight run" \
  --eyebrow "Workflow 2"

# Embed sidecar state JSON (rendered as a folded <details> JSON block at end)
python3 "$RENDER_HTML" review-stage/AUTO_REVIEW.md \
  --state review-stage/REVIEW_STATE.json

# Embed sidecar JSON (e.g., for KILL_ARGUMENT.md + KILL_ARGUMENT.json)
python3 "$RENDER_HTML" paper/KILL_ARGUMENT.md \
  --json paper/KILL_ARGUMENT.json \
  --title "Kill Argument — adversarial review"

# Offline (no CDN; math + code render as plain text)
python3 "$RENDER_HTML" idea-stage/IDEA_REPORT.md --offline

# JSON-only input (wrapped in a <pre><code class="language-json"> block)
python3 "$RENDER_HTML" review-stage/REVIEW_STATE.json --template dashboard

# Language attr (default zh-CN; set for English-primary artifacts)
python3 "$RENDER_HTML" docs/SKILLS_CATALOG.md --lang en

# Skip review (academic template otherwise reviews by default)
python3 "$RENDER_HTML" idea-stage/IDEA_REPORT.md
# … then the skill skips the spawn_agent review step if --no-review
# was on the command line. Pass --review to a dashboard render to force it.
```

The `--review` / `--no-review` flags are parsed by the SKILL orchestrator
(Claude Code), not by `render_html.py`. The helper itself stays pure
stdlib and never calls MCP. See § *HTML Review Gate* below for the
exact resolution and prompt.

## Workflow

### Step 1: Identify the artifact

From `$ARGUMENTS`, determine what to render. Common patterns:

- "render IDEA_REPORT" → `idea-stage/IDEA_REPORT.md`, academic template
- "make AUTO_REVIEW readable" → `review-stage/AUTO_REVIEW.md` + `--state review-stage/REVIEW_STATE.json`
- "show the kill argument as HTML" → `paper/KILL_ARGUMENT.md` + `--json paper/KILL_ARGUMENT.json`
- "research-wiki dashboard" → look for `research-wiki/SUMMARY.md` or generate from raw entity counts (Phase 2 work; for Phase 1 just render `SUMMARY.md` if present, else fall back to listing top-level wiki structure)

### Step 2: Pick template

- `academic` (default): linear long-form. Sticky TOC sidebar + serif body + callouts + tables + math + Q&A `<details>`. Use for IDEA_REPORT, AUTO_REVIEW, KILL_ARGUMENT, PAPER_PLAN.
- `dashboard`: grid layout, smaller font, denser metrics cards, no TOC sidebar. Use for research-wiki cockpit, RESUBMIT_REPORT, multi-project overviews.

### Step 3: Run the helper

Use the resolver above to get `$RENDER_HTML`, then invoke. The script writes the HTML alongside the source by default (or wherever `--out` says) and prints a one-line confirmation including the source SHA256 prefix.

### Step 4: HTML Review Gate (cross-model)

**Decide whether to run review.** Per ARIS invariant "executor must not judge its own output", the academic-template HTML is reviewed by a fresh cross-family Codex thread before being claimed as a delivered view. Resolution:

```
should_review = explicit --review present
             or (template == "academic" and --no-review NOT present)
```

So:

- `--template academic` (default) → **review by default**. Skip with `--no-review`.
- `--template dashboard` → no review by default. Force with `--review`.
- Phase 2 workflow auto-emit (planned) follows the same rule.

**If `should_review` is true**, fire a fresh `spawn_agent` call (NEVER `send_input`) with the prompt below. The reviewer reads the source MD + generated HTML directly; it does **not** see this skill's intermediate state.

**Scope of review (narrow on purpose).** The HTML reviewer audits **render fidelity / safety / structure only** — not claim truthfulness. Claim audit belongs upstream (`/paper-claim-audit`, `/research-review`, `/result-to-claim`). Specifically the reviewer checks:

1. **Information fidelity** — every section, claim, table, code block, list, math snippet, sidecar payload is present in the HTML (no silent drop)
2. **Structural integrity** — heading hierarchy / nested lists / table cells / code fences / `<details>` blocks / math delimiters survive parsing
3. **Callout routing** — `> 🚨 …` got `.callout-bad`, `> 💡 …` got `.callout-info`, etc.
4. **Safety / escaping** — no raw `<script>` / `onclick=` / `javascript:` / unreplaced placeholders / template-leak survives
5. **Expected-difference allowance** — frontmatter strip, generated header/footer/meta, TOC insert, sanitized unsafe HTML are all expected, not flagged

**Codex prompt (mandatory shape).** Send this as a fresh reviewer call (`spawn_agent`, NOT `send_input`):

```
You are an independent ARIS HTML render auditor. This is a fresh review thread.

Read these files directly:
- Source artifact: <ABS path to source.md or source.json>
- Generated HTML:  <ABS path to out.html>
- Optional sidecars: <state.json>, <kill_argument.json> (if any)

Task: Audit whether the generated HTML is a faithful, safe, structurally
usable view of the source artifact. Do NOT judge whether the research
claims are true. Judge only rendering fidelity.

Checks:
1. Information fidelity — sections / claims / tables / code blocks /
   lists / math / sidecars not silently dropped or materially altered.
2. Structural integrity — heading hierarchy, tables, nested lists,
   code fences, details/summary, math delimiters preserved.
3. Callout routing — warning/critical/good/info blockquotes map to
   appropriate CSS classes when present.
4. Safety/escaping — no unexpected raw script/style/iframe/form/
   event-handler/javascript/data URL survives from source.
5. Placeholder/template leakage — no unreplaced {{PLACEHOLDER}} or
   parser private placeholder character appears.
6. Expected differences — frontmatter strip, generated header/footer/
   meta, TOC insertion, sanitized unsafe HTML are EXPECTED and not a
   defect.

Return STRICT JSON first, then a short prose note:

{
  "verdict": "PASS|WARN|FAIL|ERROR",
  "checks": {
    "source_hash_match": "pass|warn|fail|unknown",
    "information_fidelity": "pass|warn|fail",
    "structure": "pass|warn|fail",
    "math_code_tables": "pass|warn|fail",
    "callouts": "pass|warn|fail|not_applicable",
    "safety_escaping": "pass|warn|fail",
    "placeholder_leak": "pass|warn|fail"
  },
  "blocking_issues": [
    {"severity": "fail",
     "source_location": "L<n>...",
     "html_location": "<selector or near-text>",
     "issue": "...",
     "suggested_fix": "..."}
  ],
  "warnings": [
    {"severity": "warn", "issue": "...", "suggested_fix": "..."}
  ],
  "summary": "one paragraph"
}

Verdict rules:
- PASS: no material fidelity/safety issue.
- WARN: readable output with minor unsupported-Markdown or cosmetic
  degradation only.
- FAIL: missing/altered meaningful content, broken tables/math/code/
  callouts that change interpretation, unsafe executable HTML, source
  hash mismatch, or placeholder leakage.
- ERROR: files could not be read or audit could not complete.
```

**Save outputs**:

1. Write the JSON verdict to `<out_path>.review.json` (sibling to the HTML).
2. Save the raw codex trace to `.aris/traces/render-html/<YYYY-MM-DD>_run<NN>/review.{txt,json}` per `shared-references/review-tracing.md`.
3. Print a one-line summary to the user: `verdict, N blocking, N warnings, trace: <path>`.

**If `verdict == FAIL`**: the HTML is **NOT** a delivered review-passed view. Tell the user the blocking issues, point them at the source (fix MD or template, not the HTML), and re-render. Do not silently overwrite or mark as complete.

**If `verdict == WARN`**: deliver the HTML but surface the warning list. User decides whether to fix or accept.

**If `spawn_agent` is not available** (e.g., user runs `/render-html` on a Codex-CLI-only setup where Codex MCP isn't wired): emit `verdict: REVIEW_UNAVAILABLE` to the sidecar, do not fabricate `PASS`, and tell the user the HTML was generated but **not** independently reviewed. The user can manually invoke `/research-review` on the source MD or re-run with Codex MCP available.

### Step 5: (Optional) Verify in browser

`open <out.html>` on macOS, `xdg-open` on Linux, `start` on Windows. Math + code highlighting need internet (CDN); offline mode degrades gracefully to readable text.

## What the helper supports

**Markdown subset** (chosen to match what ARIS workflows actually emit):

- Headings `#`/`##`/`###`/`####` with auto-generated IDs for TOC
- Paragraphs, bold `**x**`, italic `*x*` / `_x_`, inline code `` `x` ``, strikethrough `~~x~~`, links `[t](url)`, images `![a](url)`
- Unordered/ordered lists with 2-space nested indentation
- Code blocks with optional language (` ```python `) — gets `<pre><code class="language-python">` for highlight.js
- ASCII-art code blocks (heuristic: many box-drawing chars) → `<pre class="diagram">` with a distinct cream-yellow background
- Tables with `:---` / `:---:` / `---:` alignment
- Blockquotes `> ...` — emoji-prefix detection routes to callout variants:
  - `⚠️` → `.callout-warn` (Warning)
  - `💡` / `📝` → `.callout-info` (Tip / Note)
  - `✅` / `🔒` → `.callout-good` (OK / Guarantee)
  - `❌` / `🚨` → `.callout-bad` (Blocked / Critical)
- HTML passthrough for `<details>`, `<summary>`, `<div>`, `<figure>`, `<table>`, `<section>`, etc. (block-level) — used for the existing Round-1/2/3 fix details in `KILL_ARGUMENT.md`
- LaTeX math: inline `$x$` and display `$$x$$` pass through verbatim to MathJax

**What the helper does NOT support** (intentional simplifications):

- Footnotes (`[^1]`)
- Definition lists
- Reference-style links `[label][ref]`
- Setext-style headings (`===` / `---` underline form — ARIS doesn't emit these)

**Frontmatter (`--- ... ---`) at the very top of the file is stripped before rendering** (SKILL.md frontmatter style); the body that follows is what gets converted.

## Two-phase integration plan (Phase 1 is this skill; Phase 2 is workflow hooks)

**Phase 1 (this skill, currently shipped):** Opt-in only. Users explicitly call `/render-html <artifact.md>` after a workflow completes. No existing skill changes. Lets us validate which HTML views are actually useful before automating.

**Phase 2 (later, planned):** Selectively auto-emit HTML at workflow termination:

- `/idea-discovery` completes → also writes `idea-stage/IDEA_REPORT.html` (academic)
- `/auto-review-loop` terminates → also writes `review-stage/AUTO_REVIEW.html` (academic, with `--state`)
- `/kill-argument` already writes `.md + .json` → naturally extends to `+ .html`
- `/research-pipeline` final report links to the HTML files above (doesn't re-render)
- `/research-wiki render` subcommand generates `research-wiki/index.html` dashboard
- `/paper-writing` **does not** auto-emit HTML (the final reader artifact is PDF)

Phase 2 will be guarded by a `— html: true` flag in each affected skill, defaulting to `false` until we have empirical evidence the HTML views are read.

## Customizing the templates

The two templates live at `skills/render-html/scripts/templates/{academic,dashboard}.html`. Each is a single self-contained HTML file with inline CSS using `{{PLACEHOLDER}}` substitution. To customize:

1. Copy one of the templates to a new name, e.g., `my_brand.html`.
2. Edit the CSS variables in `:root { ... }` to change colors, the font stack, or layout dimensions.
3. Add the template name to the `--template` choices in `render_html.py` `argparse`.
4. Re-run `/render-html <input> --template my_brand`.

The default templates are derived from the user's own academic-newspaper tutorial style (Source Serif Pro + Songti SC, 3-color palette, sticky TOC, low-flash). Stay close to that idiom for ARIS artifacts unless you have a specific reason to break the visual language.

## External alternatives (for richer surfaces)

For deck / poster / Xiaohongshu card / tweet card / data report style outputs, point users to **[html-anything](https://github.com/nexu-io/html-anything)** (Apache-2.0, 3000⭐ at time of writing). It ships 75 SKILL.md templates across 9 surfaces and detects 8 coding-agent CLIs (including Claude Code, Codex, Copilot). ARIS does *not* depend on it — `/render-html` covers ARIS-native artifacts; html-anything is the recommended path for richer publishing surfaces.

## Key rules

- **Do not auto-render every Markdown file.** Only artifacts on the whitelist above. File proliferation is the main anti-pattern.
- **Do not hand-edit the generated HTML.** Edit the source, then re-render. The embedded SHA256 in the HTML meta tells you if the source has changed since render.
- **academic-template HTML is a reviewed artifact**, not raw output. Cross-model Codex review (fresh thread) gates the academic deliverables — the same way `/proof-checker`, `/paper-claim-audit`, `/citation-audit`, `/kill-argument` gate their respective products. `--no-review` exists for fast iteration but should not be the way you ship.
- **The reviewer audits rendering, not research.** Claim truthfulness is owned upstream by `/paper-claim-audit`, `/result-to-claim`, `/research-review`. The HTML reviewer asks: "did the renderer faithfully + safely convert this source?" — nothing more.
- **CDN dependency is opt-out, not opt-in.** Most users have internet; `--offline` is for air-gapped runs / archival.
- **The default style is academic-newspaper, not marketing-flashy.** Match the existing ARIS tonal voice. If you want decks/posters/social cards, point users to html-anything.
- **Pure stdlib only.** Adding a `pip install` dependency to `render_html.py` requires an explicit decision — the helper currently has none. MCP calls live in the skill orchestrator, never in the helper script.
