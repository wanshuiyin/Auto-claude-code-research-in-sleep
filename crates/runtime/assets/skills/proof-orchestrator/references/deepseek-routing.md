# DeepSeek Reviewer Routing

Use DeepSeek only after the user explicitly requests the optional adversarial
review branch in `proof-orchestrator`. The executor remains the controller:
gather context, write the brief, call DeepSeek, validate the response, then
produce the final audit.

## Preferred Route: DeepSeek MCP

Prefer an installed MCP bridge that can call DeepSeek directly, such as
`mcp__llm_chat__chat`.

The bridge is generic: `llm-chat`'s default model AND its 504-timeout fallback
are both `gpt-4o` unless the environment overrides them, so "the configured
default" may not be DeepSeek at all. Before labeling any output
`llm-chat-deepseek`, VERIFY the actual provider/model: the bridge response
reports the model it used — require it to be a DeepSeek model. If the response
comes back from a non-DeepSeek model (wrong default, or the bridge's timeout
fallback), mark the run `DEEPSEEK_REVIEW_BLOCKED` and record what actually
answered; never record a non-DeepSeek or unknown-model response as DeepSeek
evidence or as cross-family review. `unknown` fails closed.

Use the verified DeepSeek model unless the user names another DeepSeek model.
Do not expose or write API keys. If the MCP bridge is missing, unavailable, or
misconfigured, do not create credentials inside the repository; report setup as
blocked or use the fallback route.

## Fallback Route: Local Audit

If the DeepSeek MCP route is unavailable, do not improvise credentials, install
unrequested software, or run an undeclared wrapper. Report the external route
as blocked. A local audit may still identify issues, but it must be labeled
`local-executor-fallback` (or `local-codex-fallback` in the Codex mirror)
and cannot satisfy a cross-family acceptance gate.

## Reviewer Prompt Template

```text
ROLE:
You are an adversarial mathematical proof reviewer. Find false statements,
hidden assumptions, missing side conditions, illegal interchanges, quantifier
errors, and counterexamples. Prefer an honest blocker over a plausible repair.

TASK:
Audit the target proof below. Do not edit source files. Return a structured
proof audit.

OUTPUT FORMAT:
- Verdict: PASS | WARN | FAIL | BLOCKED | NOT_APPLICABLE
- Claim status: PROVABLE AS STATED | PROVABLE AFTER WEAKENING / EXTRA ASSUMPTION | NOT CURRENTLY JUSTIFIED
- Claim restatement
- Obligation ledger
- Issues, each with severity, category, location, claimed step, problem,
  counterexample status, downstream effect, and minimal repair
- Counterexample pass
- Remaining risks

MANDATORY CHECKS:
Use the taxonomy and side-condition checklist from
references/proof-audit-rubric.md.

TARGET PROOF:
<insert exact proof content and source locations>
```

## Response Validation

After DeepSeek returns:

1. Confirm the output follows the requested issue schema.
2. Check that every fatal or critical issue cites an exact source location or a clearly identifiable proof step.
3. Verify any claimed counterexample algebraically before calling it found; otherwise relabel it as a candidate.
4. Preserve DeepSeek's substantive critique, but correct output-format errors and add local source line numbers when available.
5. If the response is empty, truncated, or mostly generic, retry once in a fresh DeepSeek session; if still unusable, mark the audit `ERROR` or `BLOCKED`.
