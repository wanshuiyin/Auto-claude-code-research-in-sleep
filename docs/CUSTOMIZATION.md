# 🎛️ Customization

> [← back to README](../README.md#11--customization) · per-skill tunables (environment variables) for ARIS skills.

Skills are plain Markdown files. Fork and customize:

> 💡 **Parameter pass-through**: Parameters flow down the call chain automatically. For example, `/research-pipeline "topic" — sources: zotero, arxiv download: true` passes `sources` and `arxiv download` through `idea-discovery` all the way down to `research-lit`. This also works for optional sources such as `deepxiv` and `exa`: `/research-pipeline "topic" — sources: all, deepxiv, exa`. You can set any downstream parameter at any level — just add `— key: value` to your command.
>
> ```
> research-pipeline  ──→  idea-discovery      ──→  research-lit
>                    ──→  experiment-bridge    ──→  run-experiment
>                    ──→  auto-review-loop
>                                             ──→  idea-creator
>                                             ──→  novelty-check
>                                             ──→  research-review
> ```

### Full Research Pipeline (`research-pipeline`)

Tune end-to-end behavior: GPU target, arXiv download, code review, human checkpoints, base repo, W&B logging, compact summaries, reference paper, illustration backend, and auto-proceed.

Override inline: `/research-pipeline "topic" — auto proceed: false, illustration: mermaid`

<details>
<summary><b>Show constants, defaults, and pass-through for <code>/research-pipeline</code></b></summary>

| Constant | Default | Description | Pass-through |
|----------|---------|-------------|:---:|
| `AUTO_PROCEED` | true | Auto-continue with top-ranked option if user doesn't respond | → `idea-discovery` |
| `ARXIV_DOWNLOAD` | false | Download top arXiv PDFs after literature search | → `idea-discovery` → `research-lit` |
| `HUMAN_CHECKPOINT` | false | When `true`, pause after each review round for approval | → `auto-review-loop` |
| `WANDB` | false | Auto-add W&B logging to experiments | → `experiment-bridge` → `run-experiment` |
| `CODE_REVIEW` | true | GPT-5.6-Sol reviews experiment code before deployment | → `experiment-bridge` |
| `BASE_REPO` | false | GitHub repo URL to clone as base codebase for experiments | → `experiment-bridge` |
| `GPU` | `local` | GPU target: `local`, `remote` (SSH), or `vast` ([Vast.ai](https://vast.ai) on-demand rental) | → `experiment-bridge` → `run-experiment` |
| `COMPACT` | false | Generate compact summary files for short-context models and session recovery | → all workflows |
| `REF_PAPER` | false | Reference paper (PDF path or URL) to base ideas on. Summarized first, then used as context | → `idea-discovery` |
| `ILLUSTRATION` | `gemini` | AI illustration: `gemini` (default), `mermaid` (free), or `false` (skip) | → `paper-writing` |

</details>

### Auto Review Loop (`auto-review-loop`)

Tune stopping criteria: how many review→fix iterations, score threshold to declare submission-ready, and GPU-hour budget above which long experiments get flagged for manual follow-up.

<details>
<summary><b>Show stopping criteria for <code>/auto-review-loop</code></b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_ROUNDS` | 4 | Maximum review→fix→re-review iterations |
| `POSITIVE_THRESHOLD` | 6/10 | Score at which the loop stops (submission-ready) |
| `> 4 GPU-hour skip` | 4h | Experiments exceeding this are flagged for manual follow-up |

</details>

### Idea Discovery (`idea-discovery` / `idea-creator`)

Tune the pilot phase: max hours per pilot, hard timeout, max ideas piloted in parallel, total GPU budget, plus auto-proceed and arXiv download toggles.

Override inline: `/idea-discovery "topic" — pilot budget: 4h per idea, sources: zotero, arxiv download: true`

<details>
<summary><b>Show pilot-budget constants for <code>/idea-discovery</code> and <code>/idea-creator</code></b></summary>

| Constant | Default | Description | Pass-through |
|----------|---------|-------------|:---:|
| `PILOT_MAX_HOURS` | 2h | Skip any pilot estimated to take longer per GPU | — |
| `PILOT_TIMEOUT_HOURS` | 3h | Hard timeout — kill runaway pilots, collect partial results | — |
| `MAX_PILOT_IDEAS` | 3 | Maximum number of ideas to pilot in parallel | — |
| `MAX_TOTAL_GPU_HOURS` | 8h | Total GPU budget across all pilots | — |
| `AUTO_PROCEED` | true | Auto-continue with top-ranked option if user doesn't respond | — |
| `ARXIV_DOWNLOAD` | false | Download top arXiv PDFs after literature search | → `research-lit` |

</details>

### Experiment Bridge (`experiment-bridge`)

Tune deployment safety: GPT-5.6-Sol code review, auto-deploy after review, sanity-test smallest experiment first, parallel run cap, W&B logging, and base-repo URL.

Override inline: `/experiment-bridge — base repo: https://github.com/org/project`

<details>
<summary><b>Show deployment and safety constants for <code>/experiment-bridge</code></b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `CODE_REVIEW` | true | GPT-5.6-Sol xhigh reviews code before deployment. Catches logic bugs before wasting GPU hours |
| `AUTO_DEPLOY` | true | Automatically deploy experiments after implementation + review. Set `false` to manually inspect |
| `SANITY_FIRST` | true | Run smallest experiment first to catch setup bugs before full deployment |
| `MAX_PARALLEL_RUNS` | 4 | Maximum experiments to deploy in parallel (limited by available GPUs) |
| `WANDB` | false | Auto-add W&B logging. Requires `wandb_project` in CLAUDE.md |
| `BASE_REPO` | false | GitHub repo URL to clone as base codebase for experiments |

</details>

### Literature Search (`research-lit`)

Tune sourcing: local PDF directories, local-scan cap, which sources to search (Zotero / Obsidian / web / Semantic Scholar / DeepXiv / Exa), and arXiv PDF download settings.

Override inline: `/research-lit "topic" — sources: zotero, web`, `/research-lit "topic" — sources: all, deepxiv`, `/research-lit "topic" — sources: all, exa`, `/research-lit "topic" — arxiv download: true, max download: 10`

<details>
<summary><b>Show source-selection and arXiv download constants for <code>/research-lit</code></b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `PAPER_LIBRARY` | `papers/`, `literature/` | Local directories to scan for PDFs before searching online |
| `MAX_LOCAL_PAPERS` | 20 | Max local PDFs to scan (first 3 pages each) |
| `SOURCES` | `all` | Which sources to search: `zotero`, `obsidian`, `local`, `web`, `semantic-scholar`, `deepxiv`, `exa`, or `all`. `semantic-scholar`, `deepxiv`, and `exa` must be explicitly listed |
| `ARXIV_DOWNLOAD` | false | When `true`, download top relevant arXiv PDFs to PAPER_LIBRARY after search |
| `ARXIV_MAX_DOWNLOAD` | 5 | Maximum number of PDFs to download when `ARXIV_DOWNLOAD = true` |

</details>

### Paper Writing (`paper-write`)

Tune paper format: real BibTeX from DBLP, target venue (ICLR/NeurIPS/ICML/CVPR/ACL/AAAI/IEEE…), anonymous author block, page limit, and illustration backend.

Override inline: `/paper-write — target venue: NeurIPS, illustration: mermaid`

<details>
<summary><b>Show paper-format and illustration constants for <code>/paper-write</code></b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `DBLP_BIBTEX` | true | Fetch real BibTeX from DBLP/CrossRef instead of LLM-generated entries |
| `TARGET_VENUE` | `ICLR` | Target venue: `ICLR`, `NeurIPS`, `ICML`, `CVPR`, `ACL`, `AAAI`, `ACM`, `IEEE_JOURNAL`, `IEEE_CONF` |
| `ANONYMOUS` | true | Use anonymous author block for blind review. Note: most IEEE venues are NOT anonymous — set `false` for IEEE |
| `MAX_PAGES` | 9 | Page limit. ML conferences: main body excl. refs. IEEE: total pages incl. refs |
| `ILLUSTRATION` | `gemini` | AI illustration mode: `gemini` (default, needs `GEMINI_API_KEY`), `mermaid` (free), or `false` (skip) |

</details>

### General (all skills using Codex MCP)

Tune the reviewer model used by every Codex MCP call (default `gpt-5.6-sol`), or fork the SKILL.md to customize prompt templates and the per-skill tool allowlist.

- **Prompt templates** — tailor the review persona and evaluation criteria
- **`allowed-tools`** — restrict or expand what each skill can do

<details>
<summary><b>Show Codex MCP reviewer-model options</b></summary>

| Constant | Default | Description |
|----------|---------|-------------|
| `REVIEWER_MODEL` | `gpt-5.6-sol` | OpenAI model used via Codex MCP. Also available: `gpt-5.3-codex`, `gpt-5.2-codex`, `o3`. See [supported models](https://developers.openai.com/codex/models/) for full list. |

</details>


