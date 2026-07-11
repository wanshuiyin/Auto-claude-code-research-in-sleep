#!/usr/bin/env python3
"""
watchdog.py — Server-side unified monitoring daemon for ARIS.

One process per server, monitors all registered tasks (training / download / loop).
Outputs per-task status JSON + aggregated summary.txt for low-frequency polling.

Usage:
    # Start the daemon (runs in foreground, use tmux/screen to persist)
    python3 watchdog.py [--base-dir /tmp/aris-watchdog] [--interval 60]

    # Register a training task
    python3 watchdog.py --register '{"name":"exp01","type":"training","session":"exp01","session_type":"screen","gpus":[0,1,2,3]}'

    # Register a download task
    python3 watchdog.py --register '{"name":"dl01","type":"download","session":"dl01","session_type":"tmux","target_path":"/path/to/file"}'

    # Unregister a task
    python3 watchdog.py --unregister exp01

    # Check current summary
    python3 watchdog.py --status

Directory structure:
    /tmp/aris-watchdog/
    ├── watchdog.pid
    ├── tasks.json          # [{name, type, session, session_type, ...}, ...]
    ├── alerts.log          # anomaly log (DEAD/STALLED/IDLE) for cross-session recovery
    └── status/
        ├── <task-name>.json   # per-task status
        └── summary.txt        # one-line-per-task summary for CronCreate polling
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_BASE = "/tmp/aris-watchdog"
DEFAULT_INTERVAL = 60
SLOW_SPEED_THRESHOLD = 1 * 1024 * 1024  # 1 MB/s
GPU_IDLE_THRESHOLD = 5  # percent


def get_paths(base_dir):
    base = Path(base_dir)
    return {
        "base": base,
        "pid": base / "watchdog.pid",
        "tasks": base / "tasks.json",
        "status": base / "status",
        "alerts": base / "alerts.log",
    }


# ── Task registration ────────────────────────────────────────────


def register_task(base_dir, task_json):
    paths = get_paths(base_dir)
    paths["base"].mkdir(parents=True, exist_ok=True)
    paths["status"].mkdir(parents=True, exist_ok=True)

    task = json.loads(task_json)
    missing = {"name", "type"} - set(task.keys())
    if missing:
        print(f"error: missing required fields: {missing}", file=sys.stderr)
        sys.exit(1)

    ttype = task["type"]
    if ttype not in ("training", "download", "loop"):
        print(f"error: type must be 'training', 'download', or 'loop', got '{ttype}'", file=sys.stderr)
        sys.exit(1)
    if ttype in ("training", "download") and "session" not in task:
        print(f"error: {ttype} task requires 'session'", file=sys.stderr)
        sys.exit(1)
    if ttype == "loop" and ("state_file" not in task or "stale_after_seconds" not in task):
        print("error: loop task requires 'state_file' and 'stale_after_seconds'", file=sys.stderr)
        sys.exit(1)

    if ttype == "loop":
        try:
            if int(task["stale_after_seconds"]) <= 0:
                raise ValueError
        except (ValueError, TypeError):
            print("error: loop 'stale_after_seconds' must be a positive integer (seconds)", file=sys.stderr)
            sys.exit(1)
        # Absolutize WITHOUT resolving symlinks: a loop may update its state file via
        # atomic os.replace, which swaps a symlink for a new file; we must keep watching
        # the registered path, not its resolve()-time target. (os is imported at module top.)
        task["state_file"] = os.path.abspath(os.path.expanduser(task["state_file"]))
    elif "session_type" not in task:
        # Default session_type for session-backed tasks: fallback to screen
        task["session_type"] = "screen"

    tasks = []
    if paths["tasks"].exists():
        try:
            tasks = json.loads(paths["tasks"].read_text())
        except (json.JSONDecodeError, OSError):
            tasks = []

    # Deduplicate: replace existing task with same name
    tasks = [t for t in tasks if t["name"] != task["name"]]
    task["registered_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    task["registered_epoch"] = time.time()  # tz-free grace anchor (loop PENDING→MISSING)
    tasks.append(task)

    paths["tasks"].write_text(json.dumps(tasks, indent=2))
    detail = f"stale_after={task['stale_after_seconds']}s" if ttype == "loop" else task["session_type"]
    print(f"registered: {task['name']} ({ttype}, {detail})")


def unregister_task(base_dir, name):
    paths = get_paths(base_dir)
    if not paths["tasks"].exists():
        print(f"no tasks file found")
        return
    try:
        tasks = json.loads(paths["tasks"].read_text())
    except (json.JSONDecodeError, OSError):
        return
    tasks = [t for t in tasks if t["name"] != name]
    paths["tasks"].write_text(json.dumps(tasks, indent=2))
    status_file = paths["status"] / f"{name}.json"
    if status_file.exists():
        status_file.unlink()
    print(f"unregistered: {name}")


# ── Session checks (tmux + screen) ──────────────────────────────


def session_alive(session_name, session_type="screen"):
    """Check if a tmux or screen session is alive."""
    if session_type == "tmux":
        r = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            capture_output=True,
        )
        return r.returncode == 0
    else:  # screen
        r = subprocess.run(
            ["screen", "-list"], capture_output=True, text=True,
        )
        return session_name in r.stdout


# ── GPU checks ───────────────────────────────────────────────────


def get_gpu_util():
    """Return list of GPU utilization percentages, e.g. [85, 92, 0, ...]"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return [int(x.strip()) for x in r.stdout.strip().split("\n") if x.strip()]
    except Exception:
        return []


# ── File size checks ─────────────────────────────────────────────


def get_path_size(path):
    """Get size of a file or directory in bytes."""
    try:
        r = subprocess.run(
            ["du", "-sb", path], capture_output=True, text=True, timeout=30,
        )
        return int(r.stdout.split()[0])
    except Exception:
        return 0


# ── Task checking logic ─────────────────────────────────────────


def check_download(task, status_dir, interval):
    name = task["name"]
    session = task["session"]
    session_type = task.get("session_type", "screen")
    target = task.get("target_path", "")
    status_file = status_dir / f"{name}.json"
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    if not session_alive(session, session_type):
        return write_status(status_file, {
            "status": "DEAD", "task": name, "type": "download",
            "msg": f"{session_type} session gone", "ts": now,
        })

    if not target:
        return write_status(status_file, {
            "status": "OK", "task": name, "type": "download",
            "msg": "alive, no target_path to check size", "ts": now,
        })

    current_size = get_path_size(target)

    # Read previous size for delta
    prev_size = 0
    if status_file.exists():
        try:
            prev = json.loads(status_file.read_text())
            prev_size = prev.get("size", 0)
        except Exception:
            pass

    if current_size == prev_size and current_size > 0:
        return write_status(status_file, {
            "status": "STALLED", "task": name, "type": "download",
            "size": current_size, "msg": "no size growth", "ts": now,
        })

    speed = (current_size - prev_size) / max(interval, 1)

    if 0 < speed < SLOW_SPEED_THRESHOLD:
        return write_status(status_file, {
            "status": "SLOW", "task": name, "type": "download",
            "size": current_size, "speed_mbps": round(speed / 1024 / 1024, 2),
            "ts": now,
        })

    return write_status(status_file, {
        "status": "OK", "task": name, "type": "download",
        "size": current_size, "speed_mbps": round(speed / 1024 / 1024, 2),
        "ts": now,
    })


def check_training(task, status_dir):
    name = task["name"]
    session = task["session"]
    session_type = task.get("session_type", "screen")
    status_file = status_dir / f"{name}.json"
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    if not session_alive(session, session_type):
        return write_status(status_file, {
            "status": "DEAD", "task": name, "type": "training",
            "msg": f"{session_type} session gone", "ts": now,
        })

    gpu_utils = get_gpu_util()

    # Check specified GPUs for activity
    gpus = task.get("gpus", [])
    if gpus and gpu_utils:
        used_utils = [gpu_utils[i] for i in gpus if i < len(gpu_utils)]
        if used_utils and all(u < GPU_IDLE_THRESHOLD for u in used_utils):
            return write_status(status_file, {
                "status": "IDLE", "task": name, "type": "training",
                "gpu_util": {str(i): gpu_utils[i] for i in gpus if i < len(gpu_utils)},
                "msg": f"GPUs idle (<{GPU_IDLE_THRESHOLD}%)", "ts": now,
            })

    return write_status(status_file, {
        "status": "OK", "task": name, "type": "training",
        "gpu_util": gpu_utils, "ts": now,
    })


# ── Loop-liveness check (detect-only) ───────────────────────────


LOOP_COMPLETED_STATUSES = {"completed", "done", "finished"}


def _loop_is_completed(state):
    """True if the watched JSON shows the loop finished (silence is then expected, not a stall)."""
    if not isinstance(state, dict):
        return False
    if str(state.get("status", "")).lower() in LOOP_COMPLETED_STATUSES:
        return True
    phases = state.get("phases")  # run_state.py shape: all phases terminal ⇒ done
    if isinstance(phases, list) and phases and all(
        isinstance(p, dict) and p.get("status") in ("accepted", "skipped") for p in phases
    ):
        return True
    return False


def check_loop(task, status_dir):
    """Loop-liveness via state-file mtime, DETECT-ONLY.

    Liveness = freshness of the file the loop rewrites/touches each iteration, judged against the
    loop's OWN declared `stale_after_seconds` (NOT the daemon interval). This function only reads
    files and writes a status; it NEVER restarts the loop, spawns a process, or invokes a skill —
    a STALE loop is surfaced via alerts.log + summary.txt for a human/cron, honoring
    external-cadence.md's fence on verdict-bearing loops. JSON is read best-effort only to
    recognize a COMPLETED loop; an unparseable file never causes STALE on its own.
    """
    name = task["name"]
    state_file = Path(task.get("state_file", ""))
    stale_after = int(task.get("stale_after_seconds", 21600))
    status_file = status_dir / f"{name}.json"
    now_str = time.strftime("%Y-%m-%dT%H:%M:%S")

    if not state_file.exists():
        # Fail-safe: a missing registered_epoch ⇒ epoch 0 ⇒ MISSING, never infinite grace.
        grace = time.time() - float(task.get("registered_epoch", 0.0))
        if grace <= stale_after:
            return write_status(status_file, {
                "status": "PENDING", "task": name, "type": "loop",
                "msg": "state file not present yet", "ts": now_str})
        return write_status(status_file, {
            "status": "MISSING", "task": name, "type": "loop",
            "msg": f"state file absent {int(grace)}s after register (path typo?)", "ts": now_str})

    try:
        state = json.loads(state_file.read_text())
        if _loop_is_completed(state):
            return write_status(status_file, {
                "status": "COMPLETED", "task": name, "type": "loop",
                "msg": "loop reports completion", "ts": now_str})
    except (json.JSONDecodeError, OSError):
        pass  # not a terminal state we can read → fall through to mtime liveness

    age = int(time.time() - state_file.stat().st_mtime)
    if age > stale_after:
        return write_status(status_file, {
            "status": "STALE", "task": name, "type": "loop",
            "age_s": age, "stale_after": stale_after,
            "msg": f"no state write in {age}s (> {stale_after}s)", "ts": now_str})
    return write_status(status_file, {
        "status": "OK", "task": name, "type": "loop",
        "age_s": age, "stale_after": stale_after, "ts": now_str})


# ── Status output ────────────────────────────────────────────────


def write_status(path, data):
    """Write per-task status and append to alerts.log on anomalies."""
    path.write_text(json.dumps(data))

    status = data.get("status", "OK")
    if status in ("DEAD", "STALLED", "STALE", "MISSING", "IDLE", "ERROR"):
        alert_file = path.parent.parent / "alerts.log"
        ts = data.get("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        task = data.get("task", "?")
        msg = data.get("msg", "")
        alert_line = f"[{ts}] {task}: {status} — {msg}\n"
        with open(alert_file, "a") as f:
            f.write(alert_line)

    return data


def write_summary(status_dir):
    """Aggregate all task statuses into summary.txt (one line per task)."""
    lines = []
    for f in sorted(status_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text())
            name = d.get("task", f.stem)
            status = d.get("status", "?")
            typ = d.get("type", "?")
            extra = ""
            if status == "SLOW":
                extra = f" speed={d.get('speed_mbps', '?')}MB/s"
            elif status == "IDLE":
                extra = f" gpu={d.get('gpu_util', '?')}"
            elif status == "DEAD":
                extra = f" {d.get('msg', '')}"
            elif status in ("STALE", "MISSING"):
                extra = f" {d.get('msg', '')}"
            elif status == "PENDING":
                extra = " (awaiting first state write)"
            elif status == "COMPLETED":
                extra = " ✓"
            lines.append(f"{name}({typ}): {status}{extra}")
        except Exception:
            continue

    summary = "\n".join(lines) if lines else "no tasks"
    (status_dir / "summary.txt").write_text(summary)
    return summary


# ── Main loop ────────────────────────────────────────────────────


def run_watchdog(base_dir, interval):
    paths = get_paths(base_dir)
    paths["base"].mkdir(parents=True, exist_ok=True)
    paths["status"].mkdir(parents=True, exist_ok=True)

    # Write PID for liveness checks
    paths["pid"].write_text(str(os.getpid()))

    def handle_signal(sig, frame):
        paths["pid"].unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print(f"watchdog started (pid={os.getpid()}, base={base_dir}, interval={interval}s)")

    while True:
        if not paths["tasks"].exists():
            time.sleep(interval)
            continue

        try:
            tasks = json.loads(paths["tasks"].read_text())
        except (json.JSONDecodeError, OSError):
            time.sleep(interval)
            continue

        for task in tasks:
            try:
                if task["type"] == "download":
                    check_download(task, paths["status"], interval)
                elif task["type"] == "training":
                    check_training(task, paths["status"])
                elif task["type"] == "loop":
                    check_loop(task, paths["status"])
            except Exception as e:
                write_status(
                    paths["status"] / f"{task['name']}.json",
                    {"status": "ERROR", "task": task["name"], "msg": str(e),
                     "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                )

        write_summary(paths["status"])
        time.sleep(interval)


# ── CLI ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="ARIS Watchdog — server-side task monitoring daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start daemon
  python3 watchdog.py

  # Register a training task (screen session)
  python3 watchdog.py --register '{"name":"exp01","type":"training","session":"exp01","gpus":[0,1]}'

  # Register a download task (tmux session)
  python3 watchdog.py --register '{"name":"dl01","type":"download","session":"dl01","session_type":"tmux","target_path":"/data/imagenet"}'

  # Check summary
  python3 watchdog.py --status
        """,
    )
    parser.add_argument("--base-dir", default=DEFAULT_BASE,
                        help=f"Working directory (default: {DEFAULT_BASE})")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Check interval in seconds (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--register", metavar="JSON",
                        help="Register a task (JSON with name, type, session)")
    parser.add_argument("--unregister", metavar="NAME",
                        help="Unregister a task by name")
    parser.add_argument("--status", action="store_true",
                        help="Print current summary and exit")
    args = parser.parse_args()

    if args.register:
        register_task(args.base_dir, args.register)
    elif args.unregister:
        unregister_task(args.base_dir, args.unregister)
    elif args.status:
        paths = get_paths(args.base_dir)
        summary = paths["status"] / "summary.txt"
        print(summary.read_text() if summary.exists() else "no status")
    else:
        run_watchdog(args.base_dir, args.interval)


if __name__ == "__main__":
    main()
