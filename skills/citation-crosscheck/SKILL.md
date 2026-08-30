---
name: citation-crosscheck
description: "Double-blind bibliographic cross-check: one agent extracts each cited entry verbatim from the local .bib, a second independently re-fetches the same paper's record from the web while blind to the .bib, and a third extractor emits a mechanical field-by-field delta to catch dropped/re-ordered authors, wrong years, wrong venues, and bad DOIs/arXiv ids. The main agent (never a shard) assigns the MATCH/MINOR/MISMATCH verdict per reference, and exports a side-by-side spreadsheet. Use when user says \"citation crosscheck\", \"double-blind citation check\", \"verify bib against scholar\", \"bib field audit\", \"引用交叉核对\", or before submission when bibliography FIELD accuracy (not just existence) must be certified."
argument-hint: "[paper-directory-or-bib-file] [--xlsx <path>] [--cited-only|--all]"
allowed-tools: Bash(*), Read, Grep, Glob, Write, Agent, WebFetch, WebSearch
---

# Citation Cross-Check (double-blind bib-vs-web field audit)

> 🔒 **Do not wrap this skill in `/loop`, `/schedule`, or `CronCreate`.** It is
> verdict-bearing — it emits a per-reference verdict that gates `.bib` edits (an evidence
> instrument, not a cross-model acquittal; see the acceptance-gate note in Step 2).
> Re-running it on a timer adds no signal (the verdict changes only when the
> *bibliography* changes).
> Schedule the external wait that precedes it: bibliography finalized → run once. See
> [`shared-references/external-cadence.md`](../shared-references/external-cadence.md).

## Why this exists (and how it differs from `citation-audit`)

`citation-audit` is a single cross-model reviewer that judges three things holistically:
existence, metadata, and **context-fit** (is the cited paper used for a claim it
actually supports?). This skill does **not** do context-fit. It does one thing that a
single reviewer cannot do reliably: an **adversarial, double-blind, field-level diff**
of the local `.bib` entry against an *independently reconstructed* record.

The failure mode it targets is the hand-entry error that survives a plausibility read:
a **dropped or re-ordered author**, a **wrong year**, a **swapped venue**, a **DOI that
404s**. A single reviewer that sees the `.bib` entry tends to anchor on it and rate it
"looks correct." Two agents that never see each other's output cannot anchor — a
discrepancy only survives if *both* independent records agree, and the verifier reports
exactly where they diverge.

In practice it catches dropped/re-ordered authors, wrong years, and bad DOIs that a
single-pass audit rated "looks clean" — while `NEEDS_WEBCHECK` stops it from
false-flagging a legitimate non-arXiv (blog / tech-report) citation as fabricated. Use it
**in addition to** `citation-audit`, not instead: `citation-audit` protects your *review
score* (context-fit); this protects
against the *integrity red flag* of a wrong or fabricated reference (existence + fields).

| | `citation-audit` | `citation-crosscheck` (this) |
|---|---|---|
| Owns | existence + metadata + **context-fit** | **existence + field accuracy**, adversarially |
| Method | one cross-model reviewer | **two blind extractors + a mechanical field-diff** |
| Reads the .tex claims? | yes | no (bibliographic only) |
| Deliverable | KEEP/FIX/REPLACE/REMOVE per entry | **side-by-side .xlsx** + MATCH/MINOR/MISMATCH |
| Best at catching | wrong-context citation | dropped/re-ordered author, wrong year/venue/DOI |

## Constants

- **BLIND = true** — the web agent (B) MUST be prompted with only each paper's title +
  first author, plus its opaque `dedup_key` (a run-local ordinal that carries no
  bibliographic content), and MUST NOT read the `.bib` or any repo file. This is the whole
  point; do not relax it.
- **SOURCES** = arXiv (`/abs/<id>`, `/bibtex/<id>`), DBLP, CrossRef, ACL Anthology,
  NeurIPS/PMLR proceedings, OpenReview. Report what the fetched page shows; never
  fabricate a field.
- **VERDICTS** (assigned by the **main agent only**, in Step 4 — never by a shard) =
  `MATCH` (bibliographically equivalent, cosmetic-only) / `MINOR`
  (formatting or a preprint-vs-published venue, no correction required) / `MISMATCH`
  (real discrepancy: wrong/missing author, wrong year, wrong venue, wrong id) /
  `NEEDS_WEBCHECK` (B could not confirm existence, but the entry is a
  `@misc`/blog/tech-report whose `url` B's index-based search structurally cannot see —
  the main agent must fetch that `url` in Step 4 before any verdict; **never** downgrade
  such an entry straight to `MISMATCH`).
- **SCOPE** = cited-only by default (entries that render in the `.bbl`); `--all` also
  covers uncited `.bib` entries.
- **OUTPUT** = `<paper-dir>/citation_crosscheck_<date>.xlsx` (+ the four intermediate JSONs —
  `cx_A_ourbib`, `cx_B_web`, `cx_C_fielddiff`, and the gate's `cx_gate.json` — kept for audit).

## Workflow

### Step 1 — Resolve the citation set (deterministic, main agent)

```bash
# Search the paper's own source tree, not the whole repo: bundled author-kit /
# template .tex carry demo \cite{...} that inflate the set. Set PAPER_DIR to the dir of
# the main .tex (\documentclass + \bibliography); recurse (cites often live in
# sections/*.tex); exclude vendored/example dirs.
PAPER_DIR="<dir of the paper's main .tex>"
cd "$PAPER_DIR"
python3 - <<'PY'
import re, pathlib
# Skip vendored/example/template trees: bundled author kits carry demo \cite{...}.
# NOTE: this is a NAME match — a dir you *want* audited must not match (rename it or
# narrow SKIP), e.g. `examples_of_results/` would be skipped.
SKIP = re.compile(r'(?i)(^|/)(.*template.*|.*upstream.*|.*example.*|.*vendor.*)(/|$)')
# Verbatim-ish blocks AND inline \verb|...| / \lstinline are code samples, not citations.
VERB = re.compile(r'\\begin\{(verbatim|lstlisting|minted|Verbatim)\}.*?\\end\{\1\}', re.S)
# The optional arg may itself contain brackets: \lstinline[language={[LaTeX]TeX}]|...|
VERBINLINE = re.compile(r'\\(?:verb|lstinline)\*?'
                        r'(?:\[(?:[^\[\]]|\[[^\]]*\])*\])?\s*'
                        r'([^\sA-Za-z])(?:(?!\1).)*\1', re.S)
# url/href/path args may contain a literal % that is NOT a comment. Neutralize them
# BEFORE comment-stripping, or a real \cite later on that line is silently lost.
URLCMD = re.compile(r'\\(?:url|href|path|nolinkurl)\s*\{[^{}]*\}')
COMMENT = re.compile(r'(?m)(?<!\\)%.*$')
# EXPLICIT ALLOWLIST of cite commands. Do NOT build this from a prefix/suffix pattern:
# a Cartesian `(no|paren|auto|...)?cite(s|p|t|...)?` both invents commands (\citecite,
# \parenciteyear -> fake keys from any brace arg) and misses real ones (\footfullcite,
# \volcite, \notecite). Longest-first so \footfullcite wins over \footcite.
# volcite-family: the FIRST brace arg is a volume/page, NOT a cite key.
VOLCITE = {'volcite', 'Volcite', 'pvolcite', 'Pvolcite', 'fvolcite', 'ftvolcite',
           'svolcite', 'tvolcite', 'avolcite',
           'volcites', 'Volcites', 'pvolcites', 'Pvolcites', 'fvolcites', 'svolcites',
           'tvolcites', 'avolcites', 'ftvolcite', 'ftvolcites'}
NAMES = sorted({
    # natbib / LaTeX core (capitalized variants are real natbib commands)
    'cite', 'citep', 'citet', 'citealp', 'citealt', 'citenum', 'citeyear', 'citeyearpar',
    'citeauthor', 'citefullauthor', 'Citep', 'Citet', 'Citealp', 'Citealt', 'Citeauthor',
    # biblatex singular + plural
    'parencite', 'Parencite', 'footcite', 'footcitetext', 'footcitetexts', 'textcite',
    'Textcite', 'smartcite', 'Smartcite', 'supercite', 'autocite', 'Autocite', 'fullcite',
    'footfullcite', 'notecite', 'Notecite', 'pnotecite', 'Pnotecite', 'fnotecite',
    'citetitle', 'citeurl', 'citedate', 'autocites', 'parencites', 'textcites',
    'smartcites', 'supercites', 'footcites', 'cites', 'Cites', 'nocite', 'nocites',
    # aliases + field/list forms + bibentry — real biblatex/natbib families
    'citetalias', 'citepalias', 'Citetalias', 'Citepalias', 'citefield', 'citelist',
    'bibentry', 'fullciter',
    *VOLCITE,
}, key=len, reverse=True)
# (?![A-Za-z]) stops \cite matching the \citeXYZ of an unknown command; the trailing run
# accepts any mix of [opt] and {grp} so \cites{k1}[note]{k2} yields BOTH keys.
CITE = re.compile(r'\\(?:' + '|'.join(map(re.escape, NAMES)) + r')\*?(?![A-Za-z])'
                  r'((?:\s*(?:\[[^\]]*\]|\{(?:[^{}]|\{[^{}]*\})*\}))+)', re.S)
# Strip [optional] args BEFORE reading brace groups, or a braced note like
# \cite[see {Smith} p.3]{k} contributes 'Smith' as a phantom key.
OPTARG = re.compile(r'\[[^\]]*\]', re.S)
GROUP = re.compile(r'\{((?:[^{}]|\{[^{}]*\})*)\}', re.S)
CMDNAME = re.compile(r'\\([A-Za-z]+)')
# \addbibresource[opts]{x.bib} takes an optional arg; \bibliography{a,b} may list several.
BIBRES = re.compile(r'\\(?:bibliography|addbibresource)\s*(?:\[[^\]]*\])?\{([^}]+)\}')
keys, bibs, nocite_all = set(), [], False
for p in sorted(pathlib.Path('.').rglob('*.tex')):
    if SKIP.search(str(p.parent)):
        continue
    src = p.read_text(errors='replace')
    src = VERB.sub(' ', src)
    src = VERBINLINE.sub(' ', src)
    src = URLCMD.sub(' ', src)
    src = COMMENT.sub('', src)
    for res in BIBRES.findall(src):
        bibs += [r.strip() for r in res.split(',') if r.strip()]
    for m in CITE.finditer(src):
        raw_cmd = CMDNAME.match(m.group(0)).group(1)
        cmd = raw_cmd.lower()
        grps = GROUP.findall(OPTARG.sub(' ', m.group(1)))
        if raw_cmd in VOLCITE and len(grps) > 1:
            # volcite takes {volume}{key}; the PLURAL volcites alternates
            # {vol}{key}{vol}{key}... — so keep the odd-indexed args, not just grps[1:],
            # or the second volume number is harvested as a phantom key.
            grps = grps[1::2]
        elif raw_cmd in ('citefield', 'Citefield', 'citelist', 'Citelist',
                          'bibentry') and len(grps) > 1:
            # These commands take a single key(s) arg. If a stray second brace group
            # follows (a defensive read of an ambiguous source), do not harvest it as a
            # phantom key ('\citelist{k}{publisher}' -> just 'k', not '{k, publisher}').
            grps = grps[:1]
        for grp in grps:
            toks = [''.join(g.split()) for g in grp.split(',')]
            # \nocite{*} AND \nocite{*,named}: the wildcard renders EVERY bib entry.
            if cmd.startswith('nocite') and '*' in toks:
                nocite_all = True      # see the NOCITE_ALL note below
            for k in toks:
                if k and k != '*':
                    keys.add(k)
print(f"BIB_RESOURCE={bibs[0] if bibs else '(none found - use the fallback below)'}")
print(f"BIB_RESOURCES_ALL={bibs}")
print(f"NOCITE_ALL={nocite_all}")
print(f"CITED_KEY_COUNT={len(keys)}")
import pathlib
# Persist the harvest so the shell can read it back deterministically (the heredoc only
# PRINTS to stdout; it cannot set a parent-shell variable).
pathlib.Path('/tmp/cx_cited_keys.txt').write_text('\n'.join(sorted(keys)))
pathlib.Path('/tmp/cx_cited_count.txt').write_text(str(len(keys)))
print('\n'.join(sorted(keys)))
PY
# Set $CITED_KEY_COUNT as a REAL shell variable (Step 3.5 passes it as --expect): the
# heredoc above only prints it, so read it back from the file the harvest just wrote.
CITED_KEY_COUNT=$(cat /tmp/cx_cited_count.txt)
```
Cross-check against a compiled `main.bbl` by **KEY SET, not count**: a count match with a
substituted key still hides a harvest miss (drop one real cite, gain one stray → same count).
Extract the rendered keys and diff the sets:
```bash
# \bibitem[label]{key} (natbib/plain) OR \entry{key}{type}{} (biblatex) — key is the first
# brace group either way. Empty diff = harvest and .bbl agree.
grep -oE '\\(bibitem|entry)\*?(\[[^]]*\])?\{[^}]+\}' main.bbl 2>/dev/null \
  | sed -E 's/.*\{([^}]+)\}$/\1/' | sort -u > /tmp/cx_bbl_keys.txt
comm -3 <(sort -u /tmp/cx_cited_keys.txt) /tmp/cx_bbl_keys.txt   # any output ⇒ investigate
```
**The `.bbl` cross-check is conditional — an uncompiled submission has none. When absent,
confirm `CITED_KEY_COUNT` is plausible for the paper's length before proceeding; the
Step-3.5 manifest is the load-bearing coverage guard either way.**

**If `NOCITE_ALL=True` the `.tex` harvest is NOT the citation set.** `\nocite{*}` renders
*every* entry in the `.bib`, so under the default cited-only SCOPE the set becomes all
entries that render: take the keys from the compiled `.bbl` when one exists, else from the
`.bib` itself (equivalent to `--all`), and say so in the report. Do not proceed on the
`\cite`-only harvest — it under-audits by exactly the uncited entries.

`BIB_RESOURCES_ALL` lists every `\bibliography`/`\addbibresource` found, in sorted-path
order; `BIB_RESOURCE` is just the first. If the list has more than one entry, pick the one
the **main** `.tex` declares rather than trusting the ordering, and audit the union only if
the paper really loads several. If `BIB_RESOURCE` comes back empty (e.g. a `\input`-flattened
submission), fall back to the largest `*.bib` under the paper dir and, when a compiled
`main.bbl` exists, read the cited keys from its `\bibitem{...}` entries instead of the `.tex`
(the `.bbl` is the ground truth for what actually rendered).

Produce the ordered list of cited keys and, for each, its **title + first author** (the
only thing agent B is allowed to see). Confirm every key exists in the `.bib`. Assign each
entry a stable opaque ordinal **`dedup_key`** (`01`, `02`, … in resolved order): this is the
canonical id that joins the shards downstream. A receives `dedup_key` + the cite key; B
receives `dedup_key` + title + first author only (**never** the cite key or `.bib` text), so
the join key never leaks the blind side. Write two artifacts for the Step-3.5 gate, in
resolved order: `/tmp/cx_dedup_keys.txt` (the ordinal set, whitespace-separated) and
`/tmp/cx_keymap.tsv` (one `dedup_key<TAB>cite_key` line per entry — the ordinal→cite-key
**pin**). Step 3.5 builds a coverage manifest (ordinal → cite key → title hash) from
`/tmp/cx_keymap.tsv` + the `.bib` and verifies A against it as a **mapping**, so a citation
dropped *or substituted* downstream fails the run — a bare count or ordinal-set check would
pass a substitution that keeps the count.

### Step 2 — Launch A and B IN PARALLEL, blind to each other

This is a read-only **extraction fan-out** in the sense of
[`shared-references/fan-out-pattern.md`](../shared-references/fan-out-pattern.md): A
and B are two shards that only *extract* records (each returns an `entries[]` set keyed by
`dedup_key` — never by list position, never a B-visible cite key, never a quality ranking),
and C emits a mechanical per-field delta, not a verdict. Each shard returns the
`{shard_id, entries:[{dedup_key, …}]}` envelope, and the executor runs the mechanical
`dedup_key` join below before C.

**Dispatch (tier-portable).** *Tier 1* — a Workflow/ultracode runtime: A and B as two
concurrent shards, then C once both return. *Tier 2* — the `Agent` tool: the same two calls
in a single message, then C. All three of these give B a fresh subagent context that never
received the `.bib`, so B is genuinely blind and attests `blind:true`. *Tier 3* — no
delegation (e.g. a bare host): A, then B, then C run sequentially; B is blind **only** if the
host can give it a context that did not inherit the `.bib` (else B attests `blind:false` and
Step 3.5 downgrades every accept to a flag — see the acceptance-gate note). The join and the
field-diff are identical at every tier; blindness is enforced by the `blind` attestation, not
assumed from the dispatch.

**Breadth.** The shard set is fixed at three by the *design*, not by a budget: two records
are the minimum for a double-blind diff (one per provenance), and the third is the differ
that must have produced neither. Breadth is not a swept parameter here, so there is no
breadth/cost trade-off to bound — but note the ceiling this buys: two independent records,
not an ensemble.

> **Acceptance gate (provenance, per
> [`shared-references/acceptance-gate.md`](../shared-references/acceptance-gate.md)).** This
> skill is **not a loop** and has no self-terminating accept gate; it runs once over a fixed
> citation set. Its gates split cleanly:
> - **Type-A (executor may self-judge):** the `dedup_key` join balanced; every entry carries a
>   label; the `.xlsx` was written. All machine-checkable coverage facts.
> - **Type-B (merit):** whether an entry is bibliographically correct. Never delegated to a
>   shard. Two sub-cases, and the difference is load-bearing: a **`MISMATCH` or a
>   `NEEDS_WEBCHECK` resolution requires the main agent to fetch the primary source** (arXiv
>   abstract / DOI page / the entry's own `url`) and read the answer off that external
>   artifact — no fetch, no finding. A **`MATCH`/`MINOR`** is assigned from the two
>   independently-produced records agreeing, *without* a third fetch; that agreement is the
>   evidence, and it is weaker than a fetch. Treat a no-flag `MATCH` as "two sources concur",
>   not as "verified against the publisher of record."
>
> **Requirement (4) is discharged by the deterministic branch, not by a jury.**
> `fan-out-pattern.md` admits "a single cross-model jury step — OR a deterministic verifier
> gate"; this skill takes the second branch: `scripts/cx_verify.py` (Step 3.5) is an external
> process that decides `MATCH`/`MINOR` by declared normalization and **fails closed** to
> `ESCALATE` on everything else. It is byte-identical across Tiers 1-3.
>
> Be explicit about what that does and does not buy. The accept path is mechanical. The reject
> path is *externally evidenced* — a `MISMATCH` requires the main agent's own primary-source
> fetch — but the executor still reads that page, so this skill does **not** deliver
> cross-model *acquittal* and is no substitute for it. That is exactly why its own guidance is
> to run it **in addition to** `citation-audit` (a single cross-model reviewer): `citation-audit`
> supplies the cross-model verdict, this skill supplies the mechanical gate plus adversarial
> field-level evidence. Never report a `MISMATCH` — least of all a fabrication finding — on
> shard text alone.

Both are `Agent` calls in a single message (they run concurrently and share nothing). Because
the `Agent` tool gives B a **fresh subagent context** that never received the `.bib`, B is
genuinely blind here and sets `blind:true` — the Step-3.5 gate requires that attestation before
it will certify any `MATCH`/`MINOR` (see the acceptance-gate note and Step 3.5).

- **Agent A (repo-only):** read the `.bib`; extract each cited entry **verbatim**
  (brace-matched, no reformatting) → `/tmp/cx_A_ourbib.json`
  `{"shard_id":"A","entries":[{"dedup_key","key","bibtex"}]}`. Explicit instruction: **do not
  search the web.**
- **Agent B (web-only):** given ONLY the title+first-author list from Step 1, re-fetch
  each paper's record from the web and emit a clean BibTeX per paper →
  `/tmp/cx_B_web.json`
  `{"shard_id":"B","blind","entries":[{"dedup_key","title_queried","found","source_url","bibtex","sources_tried","note"}]}`.
  Explicit instruction: **do not read any local file / .bib**; set `found:false` + a note
  if a paper cannot be confirmed; never fabricate a field.
  - **`blind` attestation (set once, for the whole B shard).** B sets `blind:true` **only**
    if it ran in a context that could not have seen the `.bib` — a genuinely isolated
    dispatch that did not inherit the main agent's history. If B cannot guarantee that
    (e.g. it ran in the main context), it MUST set `blind:false`. The Step-3.5 gate refuses
    to certify a `MATCH`/`MINOR` on any entry that is not blind-attested, so a false
    `blind:true` is the one thing that would defeat the whole cross-check — never assert it
    to "pass".
  - **Do not restrict the search to arXiv/DBLP.** Many legitimate references are workshop
    tech reports, company research blogs, or proceedings pages that never appear on arXiv.
    If a title is not on arXiv, B MUST also run a general web search and open the landing
    page **its own search returns** (a project / blog / proceedings URL) before concluding
    `found:false`. B works from the title+first-author query only — it must NOT be handed,
    and cannot use, the `.bib` entry's `url` field (that stays with the main agent's Step-4
    webcheck). A citation being absent from arXiv is NOT evidence it is fake.
  - **Record `sources_tried`** per entry (e.g.
    `["arxiv","crossref","semantic-scholar(429)","web"]`) so a `found:false` from a
    *degraded* search (a source was down or rate-limited) is distinguishable from a genuine
    not-found. Note any source that failed/blocked in the entry's `note`.

On return, the main agent **joins A and B on `dedup_key`** — every ordinal from Step 1 must
appear exactly once on each side. A missing or duplicated `dedup_key`, or an unbalanced count,
is a **fail-closed stop** (re-run the offending shard), never a silent drop or a positional
guess. This mechanical join replaces order-coupling and is judgment-free — it decides nothing
about any citation, only that the two extractions line up before C diffs them.

### Step 3 — Launch C, the field-diff extractor (after A+B return)

> **C extracts, it does not adjudicate.** Computing a field-by-field delta is mechanical
> extraction; deciding that an entry *is* `MATCH` (i.e. admitting it as correct) is the
> acceptance verdict, which [`shared-references/fan-out-pattern.md`](../shared-references/fan-out-pattern.md)
> reserves for the executor. So C emits **per-field evidence**, not a per-entry verdict:
> for each field it reports `same` / `differs` (with both values verbatim) / `absent`, plus
> the routing flags below. The main agent assigns every final
> `MATCH|MINOR|MISMATCH|NEEDS_WEBCHECK` in Step 4 from that evidence. A shard that returns
> a verdict label is out of contract — the same rule `proof-checker` and `research-lit`
> state for their shards.

A third `Agent` reads both JSONs (it produced neither) and, on each `dedup_key`-joined pair,
diffs the two records field by field
— title (ignore case/braces), **author set AND order**, year, venue (NeurIPS ≡ "Advances
in NIPS"; note a genuinely different event), volume/pages, arXiv id / DOI. Output
`/tmp/cx_C_fielddiff.json`:
`{"shard_id":"C","entries":[{"dedup_key","key","blind","found","sources_tried","url","fields":{"<field>":{"status":"same|differs|absent","ours","web"}},"flags":[...]}]}`
(`found`/`sources_tried`/`blind` copied verbatim from B, `url` from A, so Step 4 and the
gate can act without
re-reading the shard files)
(keyed by the joined `dedup_key`) plus a `summary`
`{entries, fields_by_status:{same,differs,absent}, flags_by_type}` — counts of mechanical
field states, **not** a verdict tally.

**Critical routing flag for C** (this prevents the most damaging false positive): if B
reports `found:false` for an entry whose A-side `.bib` type is `@misc` (or otherwise
carries a `url`/`howpublished` instead of an arXiv id / DOI), and B's `sources_tried`
shows it only queried indexers that cannot see that URL (arXiv/DBLP/etc.), C MUST attach
the flag `url_only_source_unqueried` — and MUST NOT report the entry as absent-from-web.
B's index-based method structurally cannot confirm a blog/tech-report citation; only the
main agent's direct `url` fetch in Step 4 can. C likewise attaches `degraded_search` when
`sources_tried` shows a source was down or rate-limited, and `web_record_absent` whenever B
returned `found:false` for any reason. These flags force the entry into the main agent's Step-4
queue; **none of them is a finding about the citation** — they record what B's search did, not
whether the reference is sound.

### Step 3.5 — Run the deterministic verifier gate (`cx_verify.py`, mandatory)

This is the fan-out's **requirement-(4) gate**: `fan-out-pattern.md` demands "a single
cross-model jury step — **OR a deterministic verifier gate** — that is identical across all
three tiers." This skill has no cross-model jury, so the gate is an **external process**, and
it runs identically at Tier 1, 2 and 3. **The gate recomputes the field diff from A's and B's
raw records itself** (it parses both `.bibtex` blocks) and reads B's blindness attestation from
B directly. It also **recomputes the routing flags from A's and B's own artifacts**
(`web_record_absent` from B's `found`; `degraded_search` / `url_only_source_unqueried` from B's
`sources_tried` + A's fields); C's `flags` are advisory only, unioned with that recompute, and a
C schema violation (e.g. `flags` not a list) fails closed. So C — itself a model shard — is not
in the trust path at all: a faulty or adversarial C that omits a differing field, forges
`blind:true`, or *drops a routing flag* can neither obtain a `MATCH` nor wave an entry through,
because the gate never takes C's word for the diff **or** the routing.

> **Resolver note (owner-local, per [`shared-references/integration-contract.md`](../shared-references/integration-contract.md)).**
> `cx_verify.py` is a single-skill helper born under this skill's own `scripts/` (Layer 0 +
> the owner-local `.aris/skills/citation-crosscheck/scripts/` chain below). It deliberately
> ships **no** `tools/cx_verify.py` shim: unlike the Phase-3 *moves* (`figure_renderer.py`
> etc.) that retained a `tools/` `os.execv` shim to keep a pre-existing canonical path working,
> this helper has no legacy `tools/` entry to forward from. The Policy-A registration is in
> `integration-contract.md`.

```bash
# Layer 0: self-contained (CC 1.0+ exposes $CLAUDE_SKILL_DIR).
CX_VERIFY=""
if [ -n "${CLAUDE_SKILL_DIR:-}" ] && [ -f "$CLAUDE_SKILL_DIR/scripts/cx_verify.py" ]; then
  CX_VERIFY="$CLAUDE_SKILL_DIR/scripts/cx_verify.py"
fi
# Layers 1-3: shared-runtime chain (non-CC hosts + manual installs).
if [ -z "$CX_VERIFY" ]; then
  cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
  if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
      ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
  fi
  CX_VERIFY=".aris/skills/citation-crosscheck/scripts/cx_verify.py"
  [ -f "$CX_VERIFY" ] || CX_VERIFY="skills/citation-crosscheck/scripts/cx_verify.py"
  [ -f "$CX_VERIFY" ] || { [ -n "${ARIS_REPO:-}" ] && CX_VERIFY="$ARIS_REPO/skills/citation-crosscheck/scripts/cx_verify.py"; }
  [ -f "$CX_VERIFY" ] || CX_VERIFY=""
fi
[ -z "$CX_VERIFY" ] && {
  echo "ERROR: cx_verify.py not resolved (layer 0: \$CLAUDE_SKILL_DIR/scripts/; layers 1-3: .aris/skills/citation-crosscheck/scripts/, skills/citation-crosscheck/scripts/, \$ARIS_REPO/skills/citation-crosscheck/scripts/)." >&2
  echo "       The requirement-(4) gate cannot run; do NOT hand-assign MATCH/MINOR in its place. Fix: rerun bash tools/install_aris.sh." >&2
  exit 1
}
python3 "$CX_VERIFY" --selftest || exit 1          # built-in cases; fail = do not trust the gate
# Build the coverage manifest (ordinal → cite key → title hash) from Step 1's ordinal PIN
# (/tmp/cx_keymap.tsv) + the .bib, using the gate's OWN parser. This is independent of A, so
# the gate can verify A against it as a MAPPING. ($BIB = the resolved .bib path from Step 1.)
python3 "$CX_VERIFY" --build-manifest --bib "$BIB" --keymap /tmp/cx_keymap.tsv \
        --out-manifest /tmp/cx_manifest.tsv || exit 1
# The gate RECOMPUTES the field diff AND the routing flags from A's and B's own raw records
# (`web_record_absent` from B's `found`, `degraded_search` / `url_only_source_unqueried` from
# B's `sources_tried` + A's fields), and reads B's blindness attestation from B directly. C's
# flags are ADVISORY only, unioned with the recompute, and a C schema violation fails closed —
# so a faulty/omitting/adversarial C can neither hide a discrepancy, forge a MATCH, nor wave an
# entry through by omitting a flag. Coverage is MANDATORY: `--expect-manifest` verifies the
# ordinal→key/title MAPPING against A (catching a drop-and-substitute the ordinal-set check
# cannot); `--expect` / `--expect-keys` add the count and ordinal-set checks. An empty artifact,
# a duplicate/absent/substituted key, a dropped citation, or A/B/C key-sets that disagree all
# exit non-zero rather than reading as "clean".
python3 "$CX_VERIFY" --a /tmp/cx_A_ourbib.json --b /tmp/cx_B_web.json --c /tmp/cx_C_fielddiff.json \
        --expect "$CITED_KEY_COUNT" --expect-keys /tmp/cx_dedup_keys.txt \
        --expect-manifest /tmp/cx_manifest.tsv \
        --json /tmp/cx_gate.json || exit 1
```

What the gate decides, and what it refuses to decide:

- **`MATCH`** — every compared field equal after *declared* normalization (LaTeX accent/brace
  folding, case, punctuation; an order-**preserving** surname list; a fixed venue-alias table).
- **`MINOR`** — the sole difference is preprint-vs-published venue for the same work.
- **`ESCALATE`** — everything else, **fail-closed**: any identifying field differing
  (`authors`, `year`, `title`, `doi`, `arxiv`), a secondary field differing, an identifying
  field absent on one side, a venue pair not in the declared table, any routing flag,
  `found != true`, **or an entry that is not blind-attested** (`blind != true`). A
  `MATCH`/`MINOR` that lacks the blindness attestation is downgraded to `ESCALATE`: the run
  can still *flag* a discrepancy, but it may not *certify* a match. This is what enforces the
  double-blind claim mechanically — a host that cannot dispatch B in isolation (so B might
  have seen the `.bib`) sets `blind:false` and the gate refuses to certify anything, turning
  the check into a labelled heuristic rather than a false certification.

**The gate never emits `MISMATCH`.** A discrepancy becomes a finding only when the main agent
reproduces it against the publisher of record, so the accept path is mechanical and the reject
path is externally evidenced. Author *order* is preserved by the normalizer on purpose — a
re-ordered author list is one of the defects this skill exists to catch, so it must not
normalize to equal.

### Step 4 — ASSIGN every verdict (main agent, mandatory)

No verdict arrives pre-assigned from a shard. Read `/tmp/cx_gate.json` (the gate's recomputed
verdicts and per-field evidence) — C's `cx_C_fielddiff.json` is audit-only and must not
override the gate. **The invariant of this step: every `MATCH`/`MINOR`/`MISMATCH` rests on
either (a) the gate's mechanical decision or (b) a completed main-agent primary-source fetch.
No shard signal — a `differs`, an `absent`, B's `found:false`, or a routing flag — is itself a
finding.** Two exhaustive cases:

- **Gate said `MATCH` or `MINOR`** → adopt it (case (a), mechanical). Do not re-litigate a
  mechanical equality decision from prose, and do not silently upgrade it to `MISMATCH`; if you
  believe the gate is wrong, the fix is the gate's normalization table plus a `--selftest` case,
  not a hand-edit of one row. (What a no-flag `MATCH` means: two independently-produced records
  concur — not "verified against the publisher of record".)
- **Gate said `ESCALATE`** → the main agent **MUST complete a primary-source fetch before it
  may assign any of `MATCH`/`MINOR`/`MISMATCH`/`NEEDS_WEBCHECK`.** This is a *procedure*, not a
  first-match menu: do every applicable fetch, **then** decide — so no earlier branch can
  preempt a stricter one.

  1. **Fetch.** Identify and `WebFetch` the primary source(s):
     - the entry's own `url` / `howpublished` whenever the `.bib` carries one — always for the
       `url_only_source_unqueried` / `web_record_absent` cases (this is the `.bib`'s `url`,
       which B never saw); **and**
     - the canonical index the fields point at — the arXiv abstract for an arXiv id, the DOI
       resolver for a DOI, else the venue / proceedings page.
     For an unconfirmed-existence entry, **also run the main agent's own general web search**
     (independent of B). Record every URL and query tried.

  2. **Decide from what the fetch(es) returned** — each terminal rests on a completed fetch:
     - Primary source **confirms** the `.bib` (title + author set/order + year + id agree) →
       `MATCH` (annotate the source; for a `url`-confirmed non-arXiv entry note
       "blog/tech-report, web-confirmed"). A gate `differs`/`absent` the source does **not**
       reproduce is downgraded here, with the reason recorded.
     - Same work, only preprint-vs-published differs → `MINOR`.
     - Primary source **contradicts** an identifying field (author set/order, year,
       venue-as-different-event, arXiv id / DOI, or a substantive title/subtitle/word change;
       or a moved page/volume range) → `MISMATCH`, citing the fetched value. (Field-discrepancy
       `MISMATCH` — the source reproduced it; this guards against a B/C hallucination inventing
       a *wrong* "fix.")
     - **Existence unconfirmable** → `MISMATCH` (fabrication) **only when BOTH hold**: the
       entry's `url` is absent / dead / contradicting, **and** the main agent's own general
       search also failed. A dead `url` alone, or B's `found:false` alone, is **never** enough
       — this is the one path to a fabrication finding and it rests on the main agent's own null
       result, not on B's miss.
     - Fetch **inconclusive** (source unreachable / genuinely ambiguous) → `NEEDS_WEBCHECK`,
       left for a human. Never default an inconclusive fetch to `MATCH` or `MISMATCH`.

  A one-sided **`absent`** field is *not* resolved "from the fields both sides share": the gate
  already escalated it, and the verdict comes from the fetched primary source per the ladder
  above (an absence becomes `MISMATCH` only when the `.bib` asserts a field the source
  contradicts; otherwise `MATCH`/`MINOR` per the fetch, with the absence noted in `Detail`).

**Every entry leaves Step 4 with exactly one of the four labels**, each `MATCH`/`MINOR`/
`MISMATCH` backed by the gate or a completed main-agent fetch. If an `ESCALATE`'s evidence
fits none of the outcomes above, that is a fetch not yet done, not licence for a shard to
decide. Do **not** edit the `.bib` on shard evidence alone: every applied fix traces to a
main-agent fetch.

### Step 5 — Emit the spreadsheet + apply confirmed fixes

Build the `.xlsx` (openpyxl) with one row per citation and columns:
`# | BibKey | Link | Our BibTeX | Web BibTeX | B source | Verdict | Author check | Year |
Detail | Fix`. Color the Verdict cell: green = `MATCH`, yellow = `MINOR` or a
`NEEDS_WEBCHECK` the main agent resolved to MATCH (annotate how), orange = `MISMATCH`.
Add a Summary sheet with the counts and the fixed/optional lists. Apply only the **main-agent-confirmed** `MISMATCH`
fixes to the `.bib`; if the paper is compiled, rebuild so the `.bbl` picks them up and
re-verify the page count is unchanged. Report MINOR items as optional (do not auto-apply
preprint→published upgrades; that is an author choice).

## Key rules

- **Blindness is the mechanism.** If B ever sees the `.bib`, the cross-check collapses
  into a single-source read and loses its power. Enforce it in the prompt.
- **Never fabricate a field** in A, B, or C. `found:false` + a note beats a guess.
- **A non-arXiv miss is not a fabrication.** `@misc`/blog/tech-report/proceedings-URL
  citations are legitimate and invisible to arXiv/DBLP search. B must try the general web
  from the title+first-author prompt only; C flags an unconfirmed URL-bearing entry
  (`url_only_source_unqueried`) and the main agent assigns `NEEDS_WEBCHECK` and fetches the
  entry's own `url` in Step 4. A `MISMATCH` (fabrication) requires **both** a dead or
  contradicting `url` **and** the main agent's own general web search also failing (per Step 4) —
  a dead `url` alone is never enough. This is the skill's most dangerous false-positive if skipped.
- **Shards extract; the main agent adjudicates.** A, B and C emit records and per-field
  deltas. Every `MATCH`/`MINOR`/`MISMATCH`/`NEEDS_WEBCHECK` is assigned by the main agent in
  Step 4, and every `MISMATCH` is web-confirmed by the main agent before the `.bib` is
  touched. The shards propose; the main agent's own fetch disposes.
- **Bibliographic only.** Context-fit ("is it cited for a claim the paper supports?") is
  out of scope — that is `citation-audit`'s job. Recommend running both before submission.
- **Report, do not silently upgrade.** Preprint-vs-published and cosmetic key/year-label
  mismatches are MINOR; list them, leave the choice to the author.
