# Review Scope Limits — what a reviewer may propose

ARIS is a research-workflow tool. Its reviewers exist to find what is **actually
wrong**, not to harden a codebase against what is not happening.

This contract is about what a reviewer may **propose**. It never limits what a
reviewer may **look for** — see *Find vs propose* below.

## The block

Every reviewer prompt that can result in a proposed change to code, prompts, or
mechanism carries this verbatim:

```
=== SCOPE LIMITS (these bound what you PROPOSE, never what you look for) ===
Report anything that is actually wrong here — including a rare-looking case, if
this repo actually produces it. Then keep the fix in scope:
1. This is a RESEARCH-WORKFLOW tool, not a security paper. Verification is
   welcome; over-defense is not. Assume a cooperating operator on their own
   machine — a malicious local user is NOT in the threat model.
2. Do NOT propose SHA / hash / content-fingerprint / digest-binding schemes.
   Reporting a real defect in hashing code that already exists is fine.
3. NO speculative machinery: do not add feature flags, migration frameworks,
   compat layers, wrappers, pins, or similar mechanisms unless evidence shows
   a current repo defect they fix or an explicit existing invariant they must
   preserve. "Load-bearing", "compatibility", and "not scaffolding" are labels,
   not evidence. Point to the failing path/artifact or invariant, and check the
   proposal's factual premises, such as whether a named package version exists.
4. NO corner-case obsession: exotic encodings, symlink races, RTL text and
   millisecond races are out of scope unless you can show the case arises here.
5. Where a rubric or checklist is genuinely needed, do not over-mechanize
   judgement. A clear sentence a human reads beats a scored table nobody
   maintains.
Exception: code that runs remote commands, starts a network service, or installs
an MCP server runs on the user's machine with their credentials — trust-boundary
findings there are in scope and the default is strict.
Say plainly when something is correct. Do not manufacture findings.
```

## Find vs propose

These limits bound the **fix**, never the **search**. A reviewer should still
report:

- a bug that only fires on an unusual input, **if that input actually occurs**
  here (a documented example that produces it counts as occurring);
- a real defect in existing hash/fingerprint code — the ban is on *proposing new*
  binding, not on reading what exists;
- a case where the code and its own documentation disagree.

Worded the wrong way, "no corner cases" would suppress real findings. The test is
not *how rare does this sound*, it is **does this happen here**.

## The one exception

Code that **executes remote commands, starts a network service, or installs an
MCP server** is different. Trust-boundary findings there are in scope and the
default is strict — that code runs on a user's GPU box with their credentials.
`/experiment-queue`, `/run-experiment`, `/vast-gpu`, `/serverless-modal`,
`mcp-servers/*` and the installers are the surfaces this covers.

## Why this exists

Not a style preference. Measured over one day of real maintenance review
(2026-08-10, ~10 rounds of gpt-5.6-sol at xhigh/ultra), every discarded proposal
fell in these categories: adding hash binding to a gate that already had four
layers, adding a lint to mechanize a rule the corpus deliberately keeps as prose,
adding a dual-spelling compatibility layer for what was a typo, and hardening a
race that closes in milliseconds. None was self-limiting; each had to be refused
by hand.

The same reviewer, in the same rounds, found five genuine defects that had shipped
— including one that killed every job in the experiment queue at 60 seconds. The
reviewer is worth its cost. This contract is how that value arrives without the
tax.

## Related

- [`acceptance-gate.md`](acceptance-gate.md) — what a reviewer verdict may and may not settle.
- [`reviewer-independence.md`](reviewer-independence.md) — what the reviewer is allowed to see.
- [`reviewer-routing.md`](reviewer-routing.md) — which backend, which effort tier.
