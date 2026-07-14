---
name: web-debug-search
description: Search GitHub Issues and Discussions for software errors, version compatibility problems, and exact error-string matches. Use for debugging and discovery only; results are not paper-citation evidence.
allowed-tools: WebSearch, WebFetch, Grep, Read, Glob
---

# Web Debug Search

Debugging query: **$ARGUMENTS**

## Scope and boundary

Use this skill to find prior reports and compatibility clues in GitHub Issues
and Discussions. It is a **debugging/discovery** workflow, not a literature
search workflow. Never add its results to a bibliography, cite them as support
for a paper claim, or describe an issue report as peer-reviewed evidence.

The first version covers:

- GitHub Issues and Discussions, repository-scoped when a repository is known;
- exact and normalized error-string matching;
- package, runtime, OS, and version compatibility tracking;
- cautious synthesis of symptoms, environment, workaround, and status.

## Step 1: Parse the request

Extract, when available:

- `repository`: `owner/name` or a GitHub URL;
- `error`: the exact error string, exception, exit code, or log fragment;
- `package`: library, tool, plugin, runtime, or operating system;
- `versions`: installed, expected, minimum, maximum, or conflicting versions;
- `environment`: OS, Python/Node/Java version, GPU, shell, or deployment mode;
- `goal`: reproduce, find a workaround, check compatibility, or identify a
  likely regression.

If the user provides an error string, preserve the exact text before creating
variants. Remove only volatile details such as absolute paths, timestamps,
UUIDs, memory addresses, and numeric request IDs. Keep at most two variants:
the exact string and one minimally generalized substring. Do not invent a
synonym and call it an exact match.

## Step 2: Search in a controlled order

Run the narrowest useful searches first. Use `WebSearch` for discovery and
`WebFetch` to inspect the issue or discussion page before treating a result as
relevant.

1. If `repository` is known, search its Issues and Discussions separately.
2. Search GitHub globally for the exact error and the package/version pair.
3. Search official release notes, compatibility matrices, and maintainer
   documentation for the same version pair.
4. Only if the above are insufficient, search broader web pages. Label these
   results `[DISCOVERY-ONLY]` and do not imply that they are maintainer-verified.

Use query shapes such as:

```text
"EXACT ERROR" site:github.com/OWNER/REPO/issues
"EXACT ERROR" site:github.com/OWNER/REPO/discussions
"NORMALIZED ERROR" "PACKAGE" site:github.com
"PACKAGE" "INSTALLED_VERSION" "TARGET_VERSION" compatibility
"PACKAGE" "VERSION" release notes breaking change
```

Do not search only by a generic word such as `error` or `failed`. If a query
contains credentials, tokens, private URLs, or user data, redact them before
calling `WebSearch` or `WebFetch`.

## Step 3: Track versions and match quality

For every candidate, record the environment stated by the source. Use these
match labels:

- `[EXACT]`: the source contains the preserved error string;
- `[NORMALIZED]`: the source matches the minimally generalized variant;
- `[COMPATIBILITY]`: the source documents a version or environment relation;
- `[CONTEXTUAL]`: the source is related but does not establish the same failure.

Build a compact compatibility table when versions matter:

| Component | Observed version | Source version | Relation | Confidence |
|---|---|---|---|---|
| package/runtime/OS | ... | ... | compatible / conflict / unknown | high / medium / low |

Do not infer that two versions are compatible merely because they appear on the
same page. Separate `reported`, `maintainer-confirmed`, and `inferred` claims.
An old closed issue is historical context, not proof that the current release
is fixed.

## Step 4: Report actionable results

Return a table with one row per source:

| Match | Source type | URL | Version/environment | Symptom or finding | Status |
|---|---|---|---|---|---|

Then provide:

1. **Likely next checks** — commands or environment facts the user should
   verify, without claiming that a workaround is guaranteed;
2. **Compatibility summary** — only when a version relation is actually
   supported by the sources;
3. **Uncertainty and gaps** — inaccessible pages, conflicting reports, no
   exact match, or missing version information.

Every result must carry the label `[DEBUGGING]`, `[COMPATIBILITY]`, or
`[DISCOVERY-ONLY]`. Include the issue/discussion state and last-updated date
when visible. Prefer the canonical GitHub URL over a search-result URL.

## Failure handling

- If `WebSearch` is unavailable, stop with `BLOCKED: web search unavailable`;
  do not fabricate results from memory.
- If search works but `WebFetch` cannot read a candidate, report the URL as
  `unverified` and use only the search snippet as a lead.
- If there is no exact match, say so explicitly and separate normalized or
  contextual matches from exact matches.
- If a repository is private, a discussion is inaccessible, or a page is
  deleted, say `unavailable`; never fill in the missing text.
- If sources disagree about a fix or version, preserve both reports and mark
  the conclusion `unresolved` until a maintainer or release note settles it.
- Never turn a plausible workaround into a confirmed fix without a reproducible
  user-side check.

## Evidence boundary

Place this notice at the end of every report:

> **Evidence boundary:** These GitHub/web results are for debugging and
> discovery only. They are not paper-citation evidence and must not be added
> to the bibliography or used alone to support a research claim. Use the
> project's literature and citation-verification workflow for that purpose.
