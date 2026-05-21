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
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_USAGE_DIR = "~/.aris/usage"
USAGE_FILE_NAME = "loop-usage.jsonl"
SIDES = ("claude", "codex")

DEFAULT_CAPS = {"claude": 15, "codex": 30}
DEFAULT_WINDOW_HOURS = {"claude": 5.0, "codex": 5.0}
DEFAULT_WARN_AT = 0.8


def usage_path() -> Path:
    base = Path(os.environ.get("ARIS_USAGE_DIR", DEFAULT_USAGE_DIR)).expanduser()
    return base / USAGE_FILE_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts: str) -> datetime:
    # Accept "...Z" and "+00:00" forms.
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _config_for(side: str) -> tuple[int, float]:
    cap_env = f"{side.upper()}_LOOP_MAX_ITERATIONS"
    win_env = f"{side.upper()}_LOOP_WINDOW_HOURS"
    cap = int(os.environ.get(cap_env, DEFAULT_CAPS[side]))
    window = float(os.environ.get(win_env, DEFAULT_WINDOW_HOURS[side]))
    return cap, window


def _warn_threshold() -> float:
    return float(os.environ.get("CLAUDE_LOOP_WARN_AT", DEFAULT_WARN_AT))


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[loop_budget] skip unparseable line: {line[:60]!r}", file=sys.stderr)
                continue
    return out


def filter_window(records: list[dict], side: str, now: datetime, window_hours: float) -> list[dict]:
    cutoff = now - timedelta(hours=window_hours)
    out: list[dict] = []
    for r in records:
        if r.get("side") != side:
            continue
        ts_raw = r.get("ts")
        if not isinstance(ts_raw, str):
            continue
        try:
            ts = _parse_ts(ts_raw)
        except ValueError:
            continue
        if ts >= cutoff:
            out.append(r)
    return out


def cmd_record(args: argparse.Namespace) -> int:
    path = usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": _utc_now_iso(), "side": args.side, "skill": args.skill}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    side = args.side
    cap, window_hours = _config_for(side)
    now = datetime.now(timezone.utc)
    in_window = filter_window(load_records(usage_path()), side, now, window_hours)
    used = len(in_window)
    if used >= cap:
        if in_window:
            oldest = min(_parse_ts(r["ts"]) for r in in_window)
            reset_local = (oldest + timedelta(hours=window_hours)).astimezone()
            reset_str = reset_local.strftime("%Y-%m-%d %H:%M %Z").strip()
        else:
            reset_str = "unknown"
        print(
            f"[budget] {side} {used}/{cap} in {window_hours}h window — STOP. "
            f"Next slot frees at {reset_str}.",
            file=sys.stderr,
        )
        return 2
    util = used / cap if cap > 0 else 1.0
    if util >= _warn_threshold():
        print(
            f"[budget warning] {side} {used}/{cap} ({int(util * 100)}%), "
            f"{cap - used} iterations until cap.",
            file=sys.stderr,
        )
    else:
        print(f"[budget] {side} {used}/{cap} in {window_hours}h window, ok", file=sys.stderr)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    records = load_records(usage_path())
    for side in SIDES:
        cap, window_hours = _config_for(side)
        in_window = filter_window(records, side, now, window_hours)
        used = len(in_window)
        pct = (used / cap * 100) if cap > 0 else 100
        if in_window:
            oldest = min(_parse_ts(r["ts"]) for r in in_window)
            reset_local = (oldest + timedelta(hours=window_hours)).astimezone()
            tail = f"next slot frees at {reset_local.strftime('%H:%M %Z').strip()}"
        else:
            tail = "plenty of headroom"
        print(f"{side:8s}: {used}/{cap} in {window_hours}h window ({pct:.0f}%) — {tail}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loop_budget")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Exit 0 if under budget, 2 if at/over.")
    p_check.add_argument("--side", required=True, choices=SIDES)
    p_check.set_defaults(func=cmd_check)

    p_record = sub.add_parser("record", help="Append one iteration record.")
    p_record.add_argument("--side", required=True, choices=SIDES)
    p_record.add_argument("--skill", required=True)
    p_record.set_defaults(func=cmd_record)

    p_status = sub.add_parser("status", help="Print current usage per side.")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
