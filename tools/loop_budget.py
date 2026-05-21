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

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_USAGE_DIR = "~/.aris/usage"
USAGE_FILE_NAME = "loop-usage.jsonl"
SIDES = ("claude", "codex")


def usage_path() -> Path:
    base = Path(os.environ.get("ARIS_USAGE_DIR", DEFAULT_USAGE_DIR)).expanduser()
    return base / USAGE_FILE_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_record(args: argparse.Namespace) -> int:
    path = usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": _utc_now_iso(), "side": args.side, "skill": args.skill}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loop_budget")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_record = sub.add_parser("record", help="Append one iteration record.")
    p_record.add_argument("--side", required=True, choices=SIDES)
    p_record.add_argument("--skill", required=True)
    p_record.set_defaults(func=cmd_record)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
