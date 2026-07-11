# Capture Anti-patterns (anti-self-poisoning)

When ARIS captures *durable* knowledge — a research-wiki idea / claim / experiment
node, a `/meta-optimize` SKILL.md proposal — it must not store **operational
noise** that later hardens into a self-cited falsehood. This is the failure mode
Hermes's self-improvement loop hit and patched with a hand-written "Do NOT
capture" list: negative tool-capability claims that *"harden into refusals the
agent cites against itself for months after the actual problem was fixed."*
ARIS's research-wiki "failed ideas → anti-repeat memory" is the GOOD inverse (a
class-level *research* finding worth remembering); this is the blocklist for the
BAD kind (transient *operational* state masquerading as a durable fact).

## The four anti-patterns — do NOT capture

| class | example (do NOT store) | store INSTEAD |
|-------|------------------------|---------------|
| **env-specific failure** | "pip failed: No module named torch", "command not found" | the fix / the missing dependency / the correct config |
| **transient error** | "got a 429", "CUDA OOM", "connection refused" | nothing — it self-resolves; or the retry/backoff that worked |
| **negative tool-capability claim** | "codex can't handle long files", "gemini is broken", "don't use oracle" | the workaround, or "needs flag X" — never "tool can't do Y" |
| **single-instance narrative** | "in run 47 the loss spiked at step 300" | only the *class-level* rule it implies, if any ("LR > 3e-4 diverges on this model") |

The cardinal rule: **store *how to fix* / *what config is missing* / *the
workaround*, never *"X can't do Y"*.** A negative capability claim about your own
tooling is the most dangerous capture — it gets loaded into every future session
and the agent cites it against itself long after the real cause is gone.

## Mechanical vs judgment

- **Mechanical** (deterministic, `tools/capture_filter.py`): the unambiguous
  classes — raw error output (`No module named`, `command not found`,
  `ModuleNotFoundError`, `Permission denied`), transient errors (rate-limit / OOM
  / network), and explicitly-broken-tool phrasing anchored on ARIS infrastructure
  nouns (codex / gemini / oracle / the reviewer / the MCP / the CLI …).
- **Judgment** (this doc): the single-instance-narrative class, and any operational
  note dressed up as a finding. The agent applies this when deciding what to persist.

The mechanical filter is **deliberately conservative**: it does NOT flag
legitimate *research* findings about a model/method ("the model can't generalize
to OOD", "our method fails on long sequences") — it targets ARIS's own *tooling*
being declared broken, and raw error text. False negatives are fine (the jury
still judges); a flagged note just goes to manual review / gets rewritten.

## The asymmetry (acceptance-gate.md)

This filter may **REJECT a capture same-model** — it is a mechanical safety screen,
low risk, and same-model is always allowed to *reject*. But anything that **passes**
the filter and would become a **load-bearing** skill/claim still goes to the
**cross-model jury** before it is trusted. Same-model is fine to reject; it is
never enough to *accept* into the load-bearing set.

## Helper

```
from capture_filter import screen, reason_detail
screen(text)  # -> [reason, ...]  ([] = clean);  reason ∈ {env_failure, transient_error, negative_tool_claim}
```
```
python3 tools/capture_filter.py <file|->   # exit 1 + reasons if anti-pattern found
```

## Where ARIS uses it
- **`/research-wiki`** (and `/idea-creator` Phase-3 annotations): screen an
  idea/claim/experiment note before persisting it; if flagged, rewrite to the
  fix or drop it — don't let operational noise become a durable node.
- **`/meta-optimize`**: screen the rationale of a proposed SKILL.md change; never
  propose a change that encodes a negative tool-capability claim or a one-off
  failure as a durable rule.

## Cross-references
- `acceptance-gate.md` — the reject/accept asymmetry: same-model may reject, only
  cross-model may accept into the load-bearing set.
- `evidence-precheck.md` / `injection-hygiene.md` — sibling deterministic
  pre-gates feeding the cross-model jury.

> Anti-pattern taxonomy adapted from NousResearch/hermes-agent's background-review
> "Do NOT capture" list (MIT). ARIS's increment: Hermes patches self-poisoning with
> more self-judged prose; ARIS adds the deterministic screen + the cross-model
> acceptance gate on anything that survives it.
