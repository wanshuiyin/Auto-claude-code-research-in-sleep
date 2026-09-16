# External Review Stress Tests

User-operated manual browser handoff is the default for proof-orchestrator
stress tests; the executor never operates a browser.
First complete the local attempt and isolate the exact obligation being tested.

For every test:

1. Create a fresh local run directory.
2. Keep only the required source snapshots under `sources/` and record them in
   `source-manifest.md`.
3. Prepare `browser-prompt.md` as exact copy-ready text and `handoff.md` as the
   user-facing upload/paste instructions.
4. Use a fresh ChatGPT Project for an unrelated test. A direct continuation may
   reuse a Project only when the source set still matches, and must use a new
   conversation.
5. Save the returned text as `gpt-pro-output.md`, then run correctness and
   exposition passes separately.

If a test names PDFs or other primary documents, mark them as required separate
uploads in `source-manifest.md`. Do not silently replace them with extracted
text, memory, or a bundle.

Only when the user explicitly asks executor to perform the dispatch should executor
load `call-gpt-pro` and follow its selected-route instructions. A failed browser
route is not authorization to spend API credit.
## DeepSeek Route Tests

- With no explicit DeepSeek request, complete the local pipeline without a
  remote reviewer and without creating `deepseek-review.md`.
- With an explicit DeepSeek second-opinion request and an available llm-chat
  route, save raw output, validate issue locations and counterexamples, and
  integrate only checked findings into `audit.md`.
- With an explicit request but no available route, mark
  `DEEPSEEK_REVIEW_BLOCKED`; label any local audit as a fallback and do not
  claim independent acceptance.
- Never redirect existing paper workflows from `/proof-checker` to this optional
  branch.
