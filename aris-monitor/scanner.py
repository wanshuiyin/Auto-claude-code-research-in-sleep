#!/usr/bin/env python3
"""ARIS-Monitor: STRICTLY READ-ONLY session scanner / triage classifier.

This module READS files under ~/.claude and Codex's local SQLite stores. It NEVER writes, kills, signals,
spawns, runs subprocess/tmux/ps, polls processes, or touches the network.

Authoritative needs-approval signal
------------------------------------
The core MVP signal -- "this session is blocked waiting for you to approve
something" -- comes STRAIGHT FROM the live registry file:

    ~/.claude/sessions/<pid>.json   ->   status == "waiting"

The Claude Code app itself sets status=="waiting" (with an optional
`waitingFor` string like "Bash(npm test) needs approval") while a permission
prompt is on screen, and rewrites the file the instant the user answers. So:
  * needs_approval is detected with NO transcript parsing at all, and
  * it is inherently TRANSIENT -- you must poll (every ~1-2s) to catch it;
    on a quiescent machine you will only ever see busy/idle.

We deliberately do NOT use the "unmatched trailing tool_use" transcript
heuristic for needs_approval: a bare tool_use stop while status != "waiting"
means STALLED, not pending-approval, and keying off it false-positives on
every mid-tool pause.

Liveness
--------
Liveness is inferred purely from `updatedAt` freshness. We deliberately do NOT
call os.kill(pid, 0), ps, or anything that interacts with live OS state. A
registry file untouched within LIVE_WINDOW is treated as stale and hidden.

Codex
-----
Codex's state/history SQLite stores provide thread names and turn outcomes.
An inProgress turn with recent activity is working; a quiet one is UNKNOWN,
never an inferred permission prompt. Codex approval detection is unavailable.

Public API
----------
    scan() -> list[Session]      # classified, sorted, stale folded to a count
    summary(sessions) -> dict    # header counts for the widget

Run as a script for a GUI-less smoke test:
    python3 scanner.py           # prints the classified session list to stdout
                                 # (names + triage only; no transcript content)
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Tunables (top-of-file constants only -- no config UI by design).
# ---------------------------------------------------------------------------
IDLE_THRESHOLD = 300            # seconds; "busy & fresh" => working
LIVE_WINDOW = 1800            # seconds (30 min); updatedAt older than this => stale,
                              # folded into the dim "+N stale" line (click to expand)
TRANSCRIPT_TAIL_BYTES = 262144  # 256 KiB read-only tail of the transcript
TAIL_LINES = 40               # how many trailing JSONL lines we inspect
CODEX_WINDOW = 86400          # completed threads retained for the last 24 hours

# ---------------------------------------------------------------------------
# Paths. CLAUDE_FLOAT_HOME lets tests/demos point at a fixture tree; defaults
# to the real ~. We ONLY ever read from here.
# ---------------------------------------------------------------------------
def _home_base() -> Path:
    env = os.environ.get("CLAUDE_FLOAT_HOME")
    return Path(env).expanduser() if env else Path.home()


HOME_BASE = _home_base()
CLAUDE_HOME = HOME_BASE / ".claude"
SESSIONS_DIR = CLAUDE_HOME / "sessions"
PROJECTS_DIR = CLAUDE_HOME / "projects"

# ---------------------------------------------------------------------------
# Triage buckets. The 5 fleet buckets collapse into the 3 visible MVP buckets
# (+ a low-priority amber for stalled and a hidden stale bucket).
# The ONLY bucket the MVP must get exactly right is needs_approval, and it
# comes straight from status == "waiting" -- no transcript parse required.
# ---------------------------------------------------------------------------
NEEDS_APPROVAL = "needs_approval"    # RED   -- blocked on the user to approve
NEEDS_ATTENTION = "needs_attention"  # amber -- stalled mid-tool, may need a nudge
WORKING = "working"                  # amber -- actively running
IDLE_DONE = "idle_done"              # green -- finished / awaiting your review
STALE_HIDDEN = "stale_hidden"        # folded into a dim "+N stale" count
UNKNOWN = "unknown"                 # no reliable current status

# Sort priority (lower = more urgent / higher in the list).
SORT_PRIORITY = {
    NEEDS_APPROVAL: 0,
    NEEDS_ATTENTION: 1,
    UNKNOWN: 1,
    WORKING: 2,
    IDLE_DONE: 3,
    STALE_HIDDEN: 9,
}


@dataclass
class Info:
    stop_reason: Optional[str] = None
    last_tool: str = ""
    has_pending_background: bool = False


@dataclass
class Session:
    pid: int
    name: str
    cwd: str
    status: str            # raw status from the source registry or turn store
    triage: str            # one of the bucket constants above
    reason: str            # human-readable detail
    idle_seconds: int
    updated_at: int        # last observed activity, ms epoch
    source: str = "Claude"
    thread_id: str = ""


def display_label(session: Session) -> str:
    if session.source == "Codex":
        return {"failed": "failed", "interrupted": "stopped"}.get(
            session.status, {WORKING: "working", IDLE_DONE: "done",
                             UNKNOWN: "unknown", STALE_HIDDEN: "stale"}.get(session.triage, "unknown"))
    return {NEEDS_APPROVAL: "NEEDS YOU", NEEDS_ATTENTION: "stalled",
            WORKING: "working", IDLE_DONE: "done", STALE_HIDDEN: "stale"}.get(session.triage, "unknown")


def _codex_store(home: Path, prefix: str) -> Path:
    stores = [p for p in home.glob(prefix + "_*.sqlite")
              if p.stem[len(prefix) + 1:].isdigit()]
    if not stores:
        raise FileNotFoundError(prefix)
    return max(stores, key=lambda p: int(p.stem[len(prefix) + 1:]))


def _scan_codex() -> List[Session]:
    home = Path(os.environ.get("CODEX_HOME", str(HOME_BASE / ".codex"))).expanduser().resolve()
    if not home.exists():
        return []
    now = time.time()
    out = []
    try:
        # Read-only URI connections include live WAL data; immutable=1 would miss it.
        with closing(sqlite3.connect(_codex_store(home, "state").as_uri() + "?mode=ro", uri=True, timeout=0.2)) as state, \
             closing(sqlite3.connect(_codex_store(home, "thread_history").as_uri() + "?mode=ro", uri=True, timeout=0.2)) as history:
            state.execute("PRAGMA query_only=ON")
            history.execute("PRAGMA query_only=ON")
            # Keep unresolved turns even when their metadata is old, so a long
            # silent run is shown as unknown rather than disappearing.
            unfinished = {row[0] for row in history.execute("""
                SELECT t.thread_id FROM thread_turns t WHERE t.status='inProgress'
                AND NOT EXISTS (SELECT 1 FROM thread_turns newer
                    WHERE newer.thread_id=t.thread_id AND newer.rollout_ordinal>t.rollout_ordinal)
            """)}
            for tid, name, title, cwd, updated, source in state.execute("""
                SELECT id, name, title, cwd, updated_at, source FROM threads
                WHERE archived=0 AND source IN ('cli', 'vscode', 'exec')
            """):
                if updated < now - CODEX_WINDOW and tid not in unfinished:
                    continue
                turn = history.execute("""SELECT turn_id, status, started_at, completed_at
                    FROM thread_turns WHERE thread_id=? ORDER BY rollout_ordinal DESC LIMIT 1""", (tid,)).fetchone()
                status = turn[1] if turn else "unknown"
                activity = (turn[3] or turn[2] or updated) if turn else updated
                if turn and status == "inProgress":
                    last_item = history.execute("""SELECT MAX(COALESCE(completed_at_ms, started_at_ms, created_at_ms))
                        FROM thread_items WHERE thread_id=? AND turn_id=?""", (tid, turn[0])).fetchone()[0]
                    activity = max(activity, (last_item or 0) / 1000)
                age = max(0, int(now - activity))
                if status == "inProgress":
                    triage = (WORKING if age < IDLE_THRESHOLD else
                              UNKNOWN if age <= LIVE_WINDOW else STALE_HIDDEN)
                    reason = "turn in progress" if triage == WORKING else "in-progress turn; no recent activity"
                elif status == "completed":
                    triage, reason = (IDLE_DONE if age <= LIVE_WINDOW else STALE_HIDDEN), "turn completed"
                elif status in ("failed", "interrupted"):
                    triage, reason = (NEEDS_ATTENTION if age <= LIVE_WINDOW else STALE_HIDDEN), status
                else:
                    triage, reason = UNKNOWN, "no recognized turn status"
                out.append(Session(0, str(name or title or tid), str(cwd), status, triage,
                                   reason, age, int(activity * 1000), "Codex", str(tid)))
    except (sqlite3.Error, OSError, TypeError, ValueError):
        out.append(Session(0, "Codex status unavailable", "", "unknown", UNKNOWN,
                           "local status store unavailable or incompatible", 0, int(now * 1000), "Codex"))
    return out


# ---------------------------------------------------------------------------
# Read-only helpers.
# ---------------------------------------------------------------------------
def _as_int(value, default: int = 0) -> int:
    """Coerce a possibly-malformed registry value to int -- never raises.

    Concurrent partial writes can leave a field like updatedAt=="12.5" or
    pid=="abc" mid-flush. int() would raise ValueError on those; we swallow it
    so ONE half-written field can never blank the whole scan.
    """
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def _cwd_to_project_slug(cwd: str) -> str:
    """Mirror Claude Code's project-dir naming: / _ . all become -."""
    return cwd.replace("/", "-").replace("_", "-").replace(".", "-")


def _load_session_file(path: Path) -> Optional[dict]:
    """Read one <pid>.json. Returns None on any failure -- never raises.

    ~/.claude/sessions is mode 0700; we run as the user so reads succeed, but
    we still wrap every open() for robustness against truncated/partial writes.
    """
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    # Only require a dict. We deliberately do NOT require "pid": a half-written
    # file can have status=="waiting" before pid is flushed, and dropping it
    # here would be a costly miss of the one thing we exist to surface. pid is
    # recovered from the <pid>.json filename in scan() when absent.
    if not isinstance(data, dict):
        return None
    return data


def _transcript_path(session_id: str, cwd: str) -> Optional[Path]:
    """Derive the transcript path from the sessionId + cwd slug.

    The slug derivation can collide for two distinct cwds, so we guard with
    exists() before returning a usable path.
    """
    if not session_id or not cwd:
        return None
    slug = _cwd_to_project_slug(cwd)
    p = PROJECTS_DIR / slug / f"{session_id}.jsonl"
    try:
        if p.exists():
            return p
    except Exception:
        return None
    return None


def _last_assistant_info(path: Optional[Path]) -> Optional[Info]:
    """Read-only tail of the transcript -> stop_reason / last_tool / bg flag.

    Returns None if the transcript is missing, empty, or unparseable. Reads at
    most the last TRANSCRIPT_TAIL_BYTES so even a 35k-line transcript is cheap.
    Every json.loads is wrapped: the final line may be a half-written record.
    """
    if path is None:
        return None
    try:
        if not path.exists():
            return None
        size = path.stat().st_size
        seeked = size > TRANSCRIPT_TAIL_BYTES
        with path.open("rb") as fh:
            if seeked:
                fh.seek(size - TRANSCRIPT_TAIL_BYTES)
            tail = fh.read().decode("utf-8", "replace")
    except Exception:
        return None

    lines = [ln for ln in tail.splitlines() if ln.strip()]
    if not lines:
        return None
    # Only when we actually seeked into the middle of the file is the leading
    # line possibly a half record. On a complete (un-seeked) read every line is
    # whole -- dropping the first there would discard real data and could
    # misreport a short transcript as empty.
    if seeked and len(lines) > 1:
        lines = lines[1:]

    window = lines[-TAIL_LINES:]

    # Background-task heuristic: a queue-operation line AFTER the most recent
    # assistant end_turn means there is still unresolved background work.
    has_pending_bg = False
    last_end_turn_idx = -1
    for i, raw in enumerate(window):
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        t = d.get("type", "")
        if t == "assistant" and (d.get("message") or {}).get("stop_reason") == "end_turn":
            last_end_turn_idx = i
            has_pending_bg = False
        elif t == "queue-operation" and i > last_end_turn_idx:
            has_pending_bg = True

    # Find the last assistant message for stop_reason / last tool name.
    last_asst = None
    for raw in reversed(window):
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if isinstance(d, dict) and d.get("type") == "assistant":
            last_asst = d
            break
    if last_asst is None:
        return None

    msg = last_asst.get("message", {})
    if not isinstance(msg, dict):
        msg = {}
    content = msg.get("content", []) or []
    last_tool = ""
    if isinstance(content, list) and content:
        last_block = content[-1]
        if isinstance(last_block, dict) and last_block.get("type") == "tool_use":
            last_tool = last_block.get("name", "") or ""

    return Info(
        stop_reason=msg.get("stop_reason"),
        last_tool=last_tool,
        has_pending_background=has_pending_bg,
    )


# ---------------------------------------------------------------------------
# Status decision function. Mirrors claude-fleet patrol.classify() but is
# strictly file-only (no os.kill / no ps / no subprocess) and collapses the
# fleet buckets into the MVP's three visible ones.
# ---------------------------------------------------------------------------
def _status_for(data: dict, transcript: Optional[Path], now: float) -> Tuple[str, str]:
    """Return (triage, reason) for one session dict."""
    s = data.get("status", "unknown")
    updated_at = _as_int(data.get("updatedAt", 0))
    idle = max(0, int(now - updated_at / 1000)) if updated_at else 10 ** 9

    # 1) NEEDS-APPROVAL -- highest priority, straight from the live JSON.
    #    THIS is the core MVP signal; no transcript parse needed. It MUST be
    #    checked BEFORE the stale-liveness gate: a session genuinely waiting on
    #    a permission prompt while the user stepped away may not have its
    #    updatedAt refreshed, yet it is precisely the one that must stay RED. A
    #    waiting session is therefore never folded into the hidden stale count,
    #    regardless of updatedAt age.
    if s == "waiting":
        # str(): waitingFor is external/untrusted -- a half-written value could
        # be a dict/list, which would later crash the widget's reason[:26].
        return (NEEDS_APPROVAL, str(data.get("waitingFor") or "needs approval / 等待授权"))

    # 2) File-only liveness. No os.kill. A registry file not touched within
    #    LIVE_WINDOW is treated as stale and hidden (waiting already handled).
    if idle > LIVE_WINDOW:
        return (STALE_HIDDEN, "")

    # 3) Actively working -- trust a fresh live JSON.
    if s == "busy" and idle < IDLE_THRESHOLD:
        return (WORKING, "working")
    if s == "shell":
        # A shell process is actively running -- mirror claude-fleet's
        # patrol.classify() which maps status=='shell' to working.
        return (WORKING, "shell process running")

    # 4) Refine the rest with a read-only transcript tail.
    info = _last_assistant_info(transcript)
    if info is None:
        return (IDLE_DONE, "no/empty transcript")
    if info.has_pending_background:
        return (WORKING, "background task running")
    if info.stop_reason in ("end_turn", "stop_sequence"):
        return (IDLE_DONE, "completed")
    if info.stop_reason == "tool_use":
        # Stopped mid-tool but NOT status==waiting => stalled, NOT pending
        # approval. Never flag this red. A genuinely busy & fresh session was
        # already returned WORKING in step 3; reaching here means it is not
        # fresh, so a mid-tool stop is stalled per the documented spec.
        nudge = f"stalled at {info.last_tool}" if info.last_tool else "stalled mid-tool"
        return (NEEDS_ATTENTION, nudge)
    return (IDLE_DONE if idle >= IDLE_THRESHOLD else WORKING, "")


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------
def _scan_claude() -> List[Session]:
    """Read ~/.claude/sessions/*.json, classify each, sort.

    Returns [] on ANY failure (also the natural value when there are zero
    sessions) -- the two are indistinguishable and both safe. Never raises.
    Stale registry files are kept as STALE_HIDDEN entries so the widget can
    show a "+N stale (hidden)" count, but they sort to the bottom.
    """
    try:
        if not SESSIONS_DIR.exists():
            return []
        now = time.time()
        out: List[Session] = []

        for f in sorted(glob.glob(str(SESSIONS_DIR / "*.json"))):
            base = os.path.basename(f)
            # Legacy session-<ts>.json files carry no pid/status -- skip them.
            if base.startswith("session-"):
                continue
            data = _load_session_file(Path(f))
            if not data:
                continue

            # Per-file guard: one malformed/half-written registry file (e.g. a
            # truncated value that slips past _load_session_file but trips a
            # later coercion) must be SKIPPED, not allowed to blank the whole
            # fleet -- otherwise a real needs_approval could vanish.
            try:
                # str(): cwd/sessionId are external; a non-string from a half
                # write would make slug derivation raise and skip the ENTIRE
                # session -- including one that is genuinely waiting.
                session_id = str(data.get("sessionId") or "")
                cwd = str(data.get("cwd") or "")
                transcript = _transcript_path(session_id, cwd)
                triage, reason = _status_for(data, transcript, now)

                updated_at = _as_int(data.get("updatedAt", 0))
                idle_seconds = max(0, int(now - updated_at / 1000)) if updated_at else 0

                # Recover pid from the "<pid>.json" filename when the field is
                # absent/half-written (see _load_session_file).
                fname_pid = _as_int(base[:-5]) if base.endswith(".json") else 0

                out.append(
                    Session(
                        pid=_as_int(data.get("pid"), fname_pid),
                        name=str(data.get("name") or os.path.basename(cwd) or "?"),
                        cwd=cwd,
                        status=data.get("status", "unknown"),
                        triage=triage,
                        reason=reason,
                        idle_seconds=idle_seconds,
                        updated_at=updated_at,
                    )
                )
            except Exception:
                # Skip just this file; keep scanning siblings.
                continue

        out.sort(key=lambda x: (SORT_PRIORITY.get(x.triage, 5), -x.updated_at, x.pid))
        return out
    except Exception:
        # A read-only scan must never raise; degrade to empty.
        return []


def scan() -> List[Session]:
    sessions = _scan_claude() + _scan_codex()
    sessions.sort(key=lambda s: (SORT_PRIORITY.get(s.triage, 5), -s.updated_at, s.thread_id, s.pid))
    return sessions


def summary(sessions: Optional[List[Session]] = None) -> dict:
    """Header counts for the widget. needs_approval is the headline number."""
    if sessions is None:
        sessions = scan()
    visible = [s for s in sessions if s.triage != STALE_HIDDEN]
    stale = [s for s in sessions if s.triage == STALE_HIDDEN]
    return {
        "needs_approval": sum(1 for s in visible if s.triage == NEEDS_APPROVAL),
        "needs_attention": sum(1 for s in visible if s.triage == NEEDS_ATTENTION),
        "working": sum(1 for s in visible if s.triage == WORKING),
        "idle_done": sum(1 for s in visible if s.triage == IDLE_DONE),
        "visible": len(visible),
        "stale": len(stale),
        "unknown": sum(1 for s in visible if s.triage == UNKNOWN),
    }


def fmt_age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h{m}m" if m else f"{h}h"


def _main() -> None:
    """GUI-less smoke test: print the classified session list to stdout.

    Read-only. Prints session NAMEs and triage/reason only -- it does not echo
    transcript content.
    """
    sessions = scan()
    s = summary(sessions)
    print(
        "ARIS-Monitor scanner -- "
        f"needs_approval={s['needs_approval']} "
        f"working={s['working']} idle_done={s['idle_done']} "
        f"attention={s['needs_attention']} unknown={s['unknown']} stale={s['stale']}"
    )
    visible = [x for x in sessions if x.triage != STALE_HIDDEN]
    if not visible:
        print("  (no recent Claude/Codex sessions)")
    for x in visible:
        dot = {
            NEEDS_APPROVAL: "[!]",
            NEEDS_ATTENTION: "[~]",
            WORKING: "[*]",
            IDLE_DONE: "[ ]",
        }.get(x.triage, "[?]")
        print(f"  {dot} [{x.source}] {x.name:<28} {display_label(x):<15} {x.reason}  ({fmt_age(x.idle_seconds)})")
    if s["stale"]:
        print(f"  +{s['stale']} stale (hidden)")
    print("  Codex approval status is not monitored.")


if __name__ == "__main__":
    _main()
