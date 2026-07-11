#!/usr/bin/env python3
"""Deterministic prompt-injection / promptware / exfiltration scanner for ARIS.

ARIS injects model- and web-authored content back into agent context: MEMORY.md,
research-wiki nodes/edges, the query_pack that feeds /idea-creator, fetched paper
abstracts, and community-PR-authored SKILL.md. None of that was scanned before.
This module is the cheap, deterministic FIRST layer of ARIS's two-layer defense:

  layer 1 (this file) — regex, fail-closed, no model. A poisoned model cannot
                        talk its way past a regex. Blocks overt injection.
  layer 2 (the jury)  — cross-model review (codex/gemini) catches semantic
                        poisoning a regex can't (see injection-hygiene.md).

A clean scan is NOT a safety acquittal — only the absence of known-bad strings.
"Drive, not acquit": this scanner may GATE a write/inject; correctness of the
content still belongs to the cross-model jury (acceptance-gate.md).

Pattern set adapted from NousResearch/hermes-agent `tools/threat_patterns.py`
(MIT License, Copyright (c) 2025 Nous Research), with ARIS-runtime adaptations
(Claude/Codex/Gemini env vars, ARIS config paths) and an added entry-level
`quarantine()` + CLI. See shared-references/injection-hygiene.md.

Scope (nested: all ⊂ context ⊂ strict):
  all      — classic injection + exfil; minimal false positives, any text.
  context  — + promptware / C2 / role-hijack; web/tool content, warn-by-default.
  strict   — + persistence / ssh-backdoor / exfil-URL / config-mod / secrets;
             user-mediated writes (memory, wiki, skill install) — block here,
             because false positives are resolvable interactively.

Pattern anchoring: anchor on attack-specific vocabulary, NOT bossy English
("you must" alone is too common in legitimate CLAUDE.md / AGENTS.md to flag).
The (?:\\w+\\s+)* filler-gap between key tokens defeats "ignore all PRIOR
instructions"-style evasion.
"""

from __future__ import annotations

import re
import sys
from typing import List, Optional, Tuple

# Each entry: (regex, pattern_id, scope), scope ∈ {"all", "context", "strict"}
_PATTERNS: List[Tuple[str, str, str]] = [
    # ── Classic prompt injection (everywhere) ────────────────────────
    (r'ignore\s+(?:\w+\s+)*(previous|all|above|prior)\s+(?:\w+\s+)*instructions', "prompt_injection", "all"),
    (r'system\s+prompt\s+override', "sys_prompt_override", "all"),
    (r'disregard\s+(?:\w+\s+)*(your|all|any)\s+(?:\w+\s+)*(instructions|rules|guidelines)', "disregard_rules", "all"),
    (r'act\s+as\s+(if|though)\s+(?:\w+\s+)*you\s+(?:\w+\s+)*(have\s+no|don\'t\s+have)\s+(?:\w+\s+)*(restrictions|limits|rules)', "bypass_restrictions", "all"),
    (r'<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->', "html_comment_injection", "all"),
    (r'<\s*div\s+style\s*=\s*["\'][\s\S]*?display\s*:\s*none', "hidden_div", "all"),
    (r'translate\s+[^\n]{0,80}\s+into\s+[^\n]{0,40}\s+and\s+(execute|run|eval)\b', "translate_execute", "all"),
    (r'do\s+not\s+(?:\w+\s+)*tell\s+(?:\w+\s+)*the\s+user', "deception_hide", "all"),

    # ── Role-play / identity hijack (context) ────────────────────────
    (r'you\s+are\s+(?:\w+\s+)*now\s+(?:a|an|the)\s+', "role_hijack", "context"),
    (r'pretend\s+(?:\w+\s+)*(you\s+are|to\s+be)\s+', "role_pretend", "context"),
    (r'output\s+(?:\w+\s+)*(system|initial)\s+prompt', "leak_system_prompt", "context"),
    (r'(respond|answer|reply)\s+without\s+(?:\w+\s+)*(restrictions|limitations|filters|safety)', "remove_filters", "context"),
    (r'you\s+have\s+been\s+(?:\w+\s+)*(updated|upgraded|patched)\s+to', "fake_update", "context"),
    (r'\bname\s+yourself\s+\w+', "identity_override", "context"),

    # ── C2 / promptware (context; warn-by-default) ───────────────────
    # Narrowed to require an explicit C2 target — bare "register a node" / "pull
    # tasks" are legitimate distributed-ML / task-queue terms in research content.
    (r'register\s+(?:yourself\s+)?as\s+a\s+node\s+(?:with|to)\s+(?:the\s+)?(?:c2|controller|server|botnet)\b', "c2_node_registration", "context"),
    (r'(heartbeat|beacon|check[\s\-]?in)\s+(to|with)\s+', "c2_heartbeat", "context"),
    (r'pull\s+(?:down\s+)?(?:new\s+)?tasking(?:s)?\b', "c2_task_pull", "context"),  # "tasking" is C2 vocab; "tasks" is not
    (r'connect\s+to\s+the\s+network\b', "c2_network_connect", "context"),
    # Verbs that are near-zero-FP (dropped "register/connect/report" — too common
    # in legitimate "you must report results" / "connect to the database").
    (r'you\s+must\s+(?:\w+\s+){0,3}(beacon|exfiltrate|phone\s+home)\b', "forced_action", "context"),
    (r'only\s+use\s+one[\s\-]?liners?\b', "anti_forensic_oneliner", "context"),
    (r'never\s+(?:\w+\s+)*(?:create|write)\s+(?:\w+\s+)*(?:script|file)\s+(?:\w+\s+)*disk', "anti_forensic_disk", "context"),
    # ARIS runtime: unsetting known agent/provider env vars is pure attack behavior.
    (r'unset\s+\w*(?:CLAUDE|CODEX|GEMINI|AGENT|OPENAI|ANTHROPIC)\w*', "env_var_unset_agent", "context"),
    (r'\b(?:praxis|cobalt\s*strike|sliver|havoc|mythic|metasploit|brainworm)\b', "known_c2_framework", "context"),
    (r'\bc2\s+(?:server|channel|infrastructure|beacon)\b', "c2_explicit", "context"),
    (r'\bcommand\s+and\s+control\b', "c2_explicit_long", "context"),

    # ── Exfiltration (everywhere / strict) ───────────────────────────
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl", "all"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget", "all"),
    # [^\n>] stops the match at a redirect, so "cat > ~/.qzcli/.env" (a WRITE,
    # legitimate) is not mistaken for reading a secret.
    (r'cat\s+[^\n>]*(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)', "read_secrets", "all"),
    # Require explicit exfil intent — "upload your SSH key at https://..." (legit
    # setup) must NOT trip; "exfiltrate the data to https://..." must.
    (r'(?:exfiltrate|smuggle|leak)\s+[^\n]{0,60}\s+(?:to|at)\s+https?://', "exfil_to_url", "strict"),
    (r'(include|output|print|share)\s+(?:\w+\s+)*(conversation|chat\s+history|previous\s+messages|full\s+context|entire\s+context)', "context_exfil", "strict"),

    # ── Persistence / backdoor / config-mod (strict) ─────────────────
    (r'authorized_keys', "ssh_backdoor", "strict"),
    (r'\$HOME/\.ssh|\~/\.ssh', "ssh_access", "strict"),
    # ARIS config surface: tampering with the agent's instructions / install state.
    # Bounded gap + fixed-width negative lookbehind so "REVIEWER_MEMORY.md" does
    # NOT match via the "MEMORY.md" substring. NOTE: legit ARIS skill docs do say
    # "update CLAUDE.md", so this is tuned for wiki/web content; scanning SKILL.md
    # itself needs an ARIS-content allowlist first (see injection-hygiene.md).
    (r'(?:update|modify|edit|append\s+to|overwrite)\s+[^\n]{0,40}(?:AGENTS\.md|CLAUDE\.md|(?<![A-Za-z_])MEMORY\.md|\.cursorrules|\.clinerules)', "agent_config_mod", "strict"),
    (r'(update|modify|edit|write|change|append|add\s+to)\s+.*\.aris/(installed-skills\.txt|skill-source\.txt)', "aris_config_mod", "strict"),

    # ── Hardcoded secrets (strict) ───────────────────────────────────
    (r'(?:api[_-]?key|token|secret|password)\s*[=:]\s*["\'][A-Za-z0-9+/=_-]{20,}', "hardcoded_secret", "strict"),
]

# Invisible / bidirectional unicode used in injection attacks.
INVISIBLE_CHARS = frozenset({
    '​', '‌', '‍', '⁠', '⁢', '⁣', '⁤',
    '﻿', '‪', '‫', '‬', '‭', '‮',
    '⁦', '⁧', '⁨', '⁩',
})

_COMPILED: dict[str, List[Tuple[re.Pattern, str]]] = {}


def _compile() -> None:
    global _COMPILED
    if _COMPILED:
        return
    all_p: List[Tuple[re.Pattern, str]] = []
    context_p: List[Tuple[re.Pattern, str]] = []
    strict_p: List[Tuple[re.Pattern, str]] = []
    for pattern, pid, scope in _PATTERNS:
        entry = (re.compile(pattern, re.IGNORECASE), pid)
        if scope == "all":
            all_p.append(entry); context_p.append(entry); strict_p.append(entry)
        elif scope == "context":
            context_p.append(entry); strict_p.append(entry)
        elif scope == "strict":
            strict_p.append(entry)
        else:
            raise ValueError(f"threat_scan: unknown scope {scope!r} for {pid!r}")
    _COMPILED = {"all": all_p, "context": context_p, "strict": strict_p}


_compile()


def scan_for_threats(content: str, scope: str = "context") -> List[str]:
    """Return matched pattern IDs in ``content`` at ``scope`` (empty = clean).

    Invisible-unicode hits are returned as ``invisible_unicode_U+XXXX``.
    """
    if not content:
        return []
    findings: List[str] = []
    for ch in (set(content) & INVISIBLE_CHARS):
        findings.append(f"invisible_unicode_U+{ord(ch):04X}")
    patterns = _COMPILED.get(scope)
    if patterns is None:
        raise ValueError(f"scan_for_threats: unknown scope {scope!r}")
    for compiled, pid in patterns:
        if compiled.search(content):
            findings.append(pid)
    return findings


def first_threat_message(content: str, scope: str = "strict") -> Optional[str]:
    """Human-readable error for the first threat found at ``scope``, else None.

    Use on block-on-first-hit write paths (wiki write, memory write, skill install).
    """
    findings = scan_for_threats(content, scope=scope)
    if not findings:
        return None
    pid = findings[0]
    if pid.startswith("invisible_unicode_"):
        return f"Blocked: invisible unicode character {pid.replace('invisible_unicode_', '')} (possible injection)."
    return (
        f"Blocked: content matches threat pattern '{pid}'. This content is "
        f"re-injected into agent context and must not carry an injection or "
        f"exfiltration payload."
    )


def quarantine(content: str, scope: str = "strict", label: str = "entry") -> Tuple[str, List[str]]:
    """Load-time / inject-time quarantine (entry-level, fail-closed-with-visibility).

    If ``content`` trips a pattern, return a visible ``[BLOCKED: ...]`` placeholder
    (so the poison is NOT injected into the prompt) plus the findings. The caller
    keeps the RAW text on disk so a human can read and remove it — silently
    dropping it would hide the attack. If clean, returns ``(content, [])``.

    This is the Hermes load-time-quarantine pattern: keep the prompt safe without
    losing the evidence.
    """
    findings = scan_for_threats(content, scope=scope)
    if not findings:
        return content, []
    placeholder = (
        f"[BLOCKED: {label} matched threat pattern(s): {', '.join(findings)} "
        f"— raw text preserved on disk; review and remove. Not injected into context.]"
    )
    return placeholder, findings


__all__ = ["INVISIBLE_CHARS", "scan_for_threats", "first_threat_message", "quarantine"]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="ARIS injection / exfiltration scanner.")
    ap.add_argument("path", help="file to scan, or - for stdin")
    ap.add_argument("--scope", choices=["all", "context", "strict"], default="strict")
    ap.add_argument("--quarantine", action="store_true",
                    help="print the quarantined text instead of the findings")
    args = ap.parse_args()
    text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    if args.quarantine:
        out, findings = quarantine(text, scope=args.scope, label=args.path)
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
        return 1 if findings else 0
    findings = scan_for_threats(text, scope=args.scope)
    if findings:
        print(f"THREAT ({args.scope}): {', '.join(findings)}", file=sys.stderr)
        return 1
    print(f"clean ({args.scope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
