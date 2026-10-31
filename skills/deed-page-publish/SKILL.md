---
name: deed-page-publish
description: "Publish an HTML file or a folder (for example a /render-html report, a paper-poster-html poster, or slides exported to HTML) to a public deed.page URL so a collaborator can open it in a browser. Opt-in only. Use when the user says \"publish this report\", \"share this HTML\", \"put the poster online\", \"给我一个公开链接\", or asks for a link instead of a file. Never run automatically inside a workflow."
argument-hint: "<file.html | folder> [--slug <name>]"
allowed-tools: Bash(curl:*), Bash(tar:*), Read
---

# /deed-page-publish: share an HTML artifact as a public link

ARIS writes Markdown for the audit trail and `/render-html` turns selected
artifacts into single-file HTML for human readers. This skill is the optional
last step: upload that HTML (or a folder of HTML + assets) to
[deed.page](https://deed.page) and return a permanent `https://<slug>.deed.page/`
URL. No account or API key is needed for the first publish.

## Safety rules (read before every publish)

- **Everything published is public.** Anyone with the URL can read it. Do not
  publish unpublished results, reviewer comments, private data, API keys, or
  anything under embargo unless the user explicitly says that is fine.
- **Only publish on an explicit user request** for this specific artifact. Do
  not chain this skill into `/research-pipeline`, `/auto-review-loop` or any
  other workflow as an automatic step.
- Show the user the exact file(s) and slug you are about to upload and wait for
  a yes.
- Prefer `/render-html --offline` output so the page does not depend on
  third-party CDNs.

## Workflow

1. **Pick the input.** A single `.html` file, or a folder whose entry point is
   `index.html`. If the user points at a Markdown artifact, run `/render-html`
   first and publish its HTML output, not the Markdown.
2. **Pick a slug.** Lowercase letters, digits and hyphens, with a random suffix
   so it is hard to guess, e.g. `idea-report-7k3q`. `hello`, `my-page`,
   `my-app` and `my-site` are reserved.
3. **Load the saved owner token, if any** (keeps all your sites under one owner):

   ```bash
   DEEDPAGE_TOKEN=${DEEDPAGE_TOKEN:-$(cat ~/.config/deed-page/token 2>/dev/null)}; export DEEDPAGE_TOKEN
   set --; if [ -n "$DEEDPAGE_TOKEN" ]; then set -- -H "Authorization: Bearer $DEEDPAGE_TOKEN"; fi
   ```

4. **Publish.**

   Single file:

   ```bash
   SLUG=idea-report-7k3q   # the slug you confirmed with the user
   RESP=$(curl -sS -T report.html "https://deed.page/v1/sites?slug=$SLUG" -H "X-Client: aris" "$@")
   ```

   Folder (entry point `index.html`): follow the folder upload steps in
   https://deed.page/docs, which also cover the size and file-count limits.

5. **Save a newly minted token and never print it.** Only a publish without a
   token returns one:

   ```bash
   TOKEN=$(printf '%s' "$RESP" | sed -n 's/.*"token": *"\(deed_tok_[^"]*\)".*/\1/p')
   if [ -n "$TOKEN" ]; then (umask 077 && mkdir -p ~/.config/deed-page && chmod 700 ~/.config/deed-page && printf '%s' "$TOKEN" > ~/.config/deed-page/token && chmod 600 ~/.config/deed-page/token); fi
   printf '%s\n' "$RESP" | sed 's/"token": *"[^"]*"/"token":"<saved>"/'
   ```

   If the machine has no private persistent storage, tell the user instead of
   writing the token somewhere shared.

6. **Report back** the `url` field from the response, and remind the user the
   page is public. To update the same page later, publish again to the same slug
   with the saved token.

## Failure handling

- Non-`ok` response: show the `error` message to the user and stop. Do not
  retry with a different slug unless the error says the slug is taken.
- No network / `curl` missing: say so and leave the local HTML path as the
  deliverable.

## Alternatives

deed.page also runs a hosted MCP server at `https://deed.page/mcp`, and an
MIT-licensed agent skill lives at https://github.com/f-o-x11/deed-page-skill.
Either can replace the `curl` steps above if the user already has them set up.
