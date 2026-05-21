#!/usr/bin/env python3
"""loop_budget.py — iteration-budget guard for auto-review-loop* skills.

Subcommands:
    check  --side {claude|codex}                  → exit 0 ok, 2 over budget
    record --side {claude|codex} --skill <name>   → append one record
    status                                        → print human summary

State file: $ARIS_USAGE_DIR/loop-usage.jsonl  (default: ~/.aris/usage/loop-usage.jsonl)

See docs/superpowers/specs/2026-05-21-loop-usage-monitor-design.md.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_USAGE_DIR = "~/.aris/usage"
USAGE_FILE_NAME = "loop-usage.jsonl"


def usage_path() -> Path:
    base = Path(os.environ.get("ARIS_USAGE_DIR", DEFAULT_USAGE_DIR)).expanduser()
    return base / USAGE_FILE_NAME
