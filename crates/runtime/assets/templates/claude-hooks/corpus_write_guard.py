#!/usr/bin/env python3
"""PreToolUse guard: deny Bash writes to the ARIS skill corpus.

Why: a read-only PRODUCER skill (meta-optimize, corpus-audit) is given no `Write`/
`Edit` tool so it cannot mutate the corpus with the frictionless mutators. But a skill
that retains *any* `Bash` access can still write a corpus file via shell redirection
(`cat > skills/x`, `sed -i ... skills/x`, `tee skills/x`, `cp/mv ... skills/x`) — which
no `allowed-tools` allowlist can block, because redirection is appended after the matched
command prefix. The only place to enforce "Bash may not write the corpus" is the harness:
this PreToolUse hook inspects the actual command and DENIES corpus-write shell ops.

Invariant this establishes (with the producer holding Bash-but-no-Write/Edit):
    corpus mutation MUST go through the Write/Edit tools (reviewable, attributable) —
    never an opaque Bash redirection. So a producer with no Write/Edit + this hook
    active is STRUCTURALLY unable to mutate the corpus by any path.

Scope: this guard is GLOBAL (not skill-scoped — hooks have no reliable skill context).
It blocks Bash *corpus writes* for every skill; legitimate corpus edits (yours, and
/meta-apply's landing) use the Write/Edit tools and are unaffected. Blocking opaque
shell writes to the corpus is good hygiene regardless of who runs.

Threat model: closes the ACCIDENTAL/casual self-acquittal path (an honest producer
slipping into `cat > skills/...`). A determined adversary can still obfuscate a write
(`p=skills/x; printf ... >"$p"`); defense-in-depth against that is the provenance
integrity check (an un-stamped / stale-hash corpus change is detectable before push),
not this regex. This hook is the cheap, harness-level prevention layer, not a sandbox.

Install: add to .claude/settings.json hooks.PreToolUse (matcher "Bash"); see
templates/claude-hooks/corpus_write_guard.json. Exit 2 = block + reason to the model.
"""

from __future__ import annotations

import json
import re
import sys

# Corpus = the parts of the repo a self-modification producer must never write via Bash.
_CORPUS = r"(?:\./)?(?:skills|shared-references|tools|templates|plugins)/"

# Shell ops that WRITE a path. Each pattern is "write-operator ... targeting a corpus path".
_WRITE_OPS = [
    re.compile(r">>?\s*\"?'?" + _CORPUS),                      # > corpus / >> corpus
    re.compile(r"\btee\s+(?:-a\s+)?\"?'?" + _CORPUS),           # tee [-a] corpus
    re.compile(r"\bsed\s+(?:-[a-zA-Z]*\s+)*-i\b[^|;&]*" + _CORPUS),  # sed -i ... corpus
    re.compile(r"\bdd\b[^|;&]*\bof=\"?'?" + _CORPUS),           # dd of=corpus
    re.compile(r"\b(?:cp|mv|install|rsync|ln)\b[^|;&]*\s\"?'?" + _CORPUS),  # cp/mv/... corpus (as dest)
    re.compile(r"\btruncate\b[^|;&]*" + _CORPUS),
    re.compile(r"\btouch\s+[^|;&]*" + _CORPUS),                  # touch corpus (create)
    re.compile(r"\.write_(?:text|bytes)\b[^|;&]*" + _CORPUS),    # Path(...).write_text into corpus
    re.compile(_CORPUS + r"[^'\"]*['\"]\s*\)\s*\.write_(?:text|bytes)"),  # Path('corpus..').write_text
    re.compile(r"\b(?:python3?|perl|ruby|node)\b[^|;&]*open\([^)]*" + _CORPUS),  # open('skills/..','w')
]


def violates(command: str) -> str | None:
    for rx in _WRITE_OPS:
        m = rx.search(command)
        if m:
            return command[m.start():m.start() + 80]
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # malformed input → don't block (fail open on parse, not on match)
    if data.get("tool_name") != "Bash":
        return 0
    command = (data.get("tool_input") or {}).get("command", "") or ""
    hit = violates(command)
    if hit:
        sys.stderr.write(
            "BLOCKED by corpus_write_guard: Bash may not WRITE the skill corpus "
            f"(matched: {hit!r}). Corpus mutation must go through the Write/Edit tools "
            "(reviewable, attributable). A read-only producer (meta-optimize / corpus-"
            "audit) stages patches to .aris/meta/ and hands off to /meta-apply, which "
            "lands them with the Write/Edit tools after the cross-model jury + human gate.\n")
        return 2  # PreToolUse: block the call, show stderr to the model
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
