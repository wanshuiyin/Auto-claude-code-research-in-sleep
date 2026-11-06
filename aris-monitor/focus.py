#!/usr/bin/env python3
"""ARIS-Monitor: user-initiated focus of a terminal or existing local Codex chat.

Everything else in ARIS-Monitor is strictly read-only. This module is the single
exception, and it is deliberately tiny and tightly scoped:

  * Claude focus runs exactly two external commands:
      1. `ps -o tty= -p <pid>`  -- READ a pid's controlling tty (no mutation)
      2. `focus-tty.sh <tty>`   -- RAISE the owning Terminal.app / iTerm2 / tmux
                                   tab via osascript (activate / select only)
  * Codex focus runs `open codex://threads/<validated UUID>`.
  * It NEVER kills, signals, or writes session data. It cannot end,
    pause, resume, or modify a session -- it can only bring a window to the front.
  * focus-tty.sh is the bundled hardened raise-only shim. ARIS-Monitor ALWAYS
    runs the bundled script -- it does NOT honor a ~/.claude/focus-tty.sh
    override -- so the action's command surface stays provably bounded to this
    reviewed shim. That surface is entirely non-destructive: osascript
    (activate / select / set index), read-only tmux discovery (list-panes /
    list-clients / display-message), standard text utils (awk / sort / cut /
    grep), and a private mktemp errfile for its own stderr (removed on exit).
    It contains NO kill / signal / send-keys / session mutation.

A focus attempt is ALWAYS user-initiated (a click) and best-effort: any failure
(no tty, no matching tab, Automation permission denied, timeout) returns a
structured result and changes nothing.
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Optional

# ALWAYS the bundled script -- ARIS-Monitor deliberately does NOT honor a
# ~/.claude/focus-tty.sh override, so the focus action's command surface is
# provably bounded to this reviewed, raise-only shim.
_FOCUS_SCRIPT = Path(__file__).resolve().parent / "focus-tty.sh"


def focus_codex(thread_id: str) -> dict:
    """User-initiated navigation to an existing local Codex chat."""
    try:
        thread_id = str(uuid.UUID(thread_id))
        proc = subprocess.run(["open", "codex://threads/" + thread_id],
                              capture_output=True, text=True, timeout=5)
        return {"ok": proc.returncode == 0, "code": proc.returncode,
                "error": proc.stderr.strip()}
    except (ValueError, TypeError, AttributeError, OSError, subprocess.TimeoutExpired) as ex:
        return {"ok": False, "code": None, "error": str(ex)}


def _pid_tty(pid: int) -> Optional[str]:
    """READ-ONLY: the controlling tty of <pid> via `ps`. None if unknown.

    `ps -o tty=` only reads the process table; it never mutates anything.
    """
    if not pid or pid <= 0:
        return None
    try:
        out = subprocess.check_output(
            ["ps", "-o", "tty=", "-p", str(pid)],
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
    except Exception:
        return None
    if not out or out == "??":
        return None
    return out if out.startswith("/dev/") else f"/dev/{out}"


def focus(pid: int) -> dict:
    """Raise the terminal tab that owns <pid>. Best-effort; never destructive.

    Returns {"ok": bool, "code": int|None, "error": str}. The ONLY effect is
    raising a window -- it never kills / signals / writes anything.
    """
    tty = _pid_tty(pid)
    if not tty:
        return {"ok": False, "code": None,
                "error": "no tty for pid (session may have no terminal)"}
    script = _FOCUS_SCRIPT
    try:
        if not script.exists():
            return {"ok": False, "code": None,
                    "error": f"bundled focus-tty.sh missing at {script}"}
    except Exception:
        return {"ok": False, "code": None, "error": "focus-tty.sh not accessible"}
    # Direct exec respects the script's own shebang; fall back to bash only if the
    # +x bit was lost on an odd checkout. A blocking macOS Automation prompt is
    # bounded by the timeout; nothing here can hang the caller indefinitely.
    try:
        try:
            proc = subprocess.run([str(script), tty],
                                  capture_output=True, text=True, timeout=10)
        except PermissionError:
            proc = subprocess.run(["bash", str(script), tty],
                                  capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": None, "error": "focus timed out after 10s"}
    except Exception as e:  # noqa: BLE001 -- best-effort, never raise to the UI
        return {"ok": False, "code": None, "error": str(e)}
    return {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "error": (proc.stderr or "").strip(),
    }
