# Watchdog Monitoring Guide

[中文版](WATCHDOG_GUIDE_CN.md) | English

> Persistent server-side monitoring for ARIS experiments — catch dead sessions, stalled downloads, and idle GPUs without manual polling.

## The Problem

ARIS experiments run remotely in screen/tmux sessions. Current monitoring (`/monitor-experiment`) is **on-demand** — you have to actively ask "how are my experiments doing?". Between checks:

- A training session can crash silently (screen dies, OOM kill)
- A download can stall (network timeout, auth failure)
- GPUs can go idle (training finished or crashed but session stays open)

These go undetected until the next manual check, wasting hours of potential GPU time.

## The Solution: watchdog.py

A lightweight Python daemon that runs on each GPU server, continuously monitoring all registered tasks. Zero dependencies beyond Python 3 standard library + `nvidia-smi`.

**What it monitors:**

| Task Type | Checks | Anomalies |
|-----------|--------|-----------|
| `training` | Session alive + GPU utilization | `DEAD` (session gone), `IDLE` (GPU <5%) |
| `download` | Session alive + file size growth + speed | `DEAD`, `STALLED` (no growth), `SLOW` (<1MB/s) |
| `loop` | State-file mtime vs `stale_after_seconds` (detect-only) | `STALE` (no update in window), `MISSING` (file absent past grace), `PENDING` (awaiting first write), `COMPLETED` |

**What it outputs:**

```
/tmp/aris-watchdog/
├── watchdog.pid              # daemon PID (for liveness checks)
├── tasks.json                # registered tasks
├── alerts.log                # anomaly log (for cross-session recovery)
└── status/
    ├── exp01.json            # per-task status
    ├── dl01.json
    └── summary.txt           # one-line-per-task summary
```

## Setup

### 1. Copy to your server

```bash
# From your local machine (adjust paths)
scp tools/watchdog.py your-server:/path/to/project/tools/
```

Or if using rsync for code sync (as in `/run-experiment`), just include `tools/` in the sync.

### 2. Start the daemon

```bash
# In a screen/tmux session on the server (so it persists)
screen -dmS watchdog python3 tools/watchdog.py
# or
tmux new-session -d -s watchdog "python3 tools/watchdog.py"
```

Optional flags:
```bash
python3 tools/watchdog.py --base-dir /tmp/my-monitor --interval 30
```

### 3. Register tasks

After launching an experiment:

```bash
# Training task (screen session, specific GPUs)
python3 tools/watchdog.py --register '{
  "name": "exp01",
  "type": "training",
  "session": "exp01",
  "session_type": "screen",
  "gpus": [0, 1, 2, 3]
}'

# Download task (tmux session, with file to track)
python3 tools/watchdog.py --register '{
  "name": "dl-imagenet",
  "type": "download",
  "session": "dl01",
  "session_type": "tmux",
  "target_path": "/data/imagenet"
}'
```

**Required fields:**
- `name` — unique task identifier
- `type` — `"training"`, `"download"`, or `"loop"`
- `session` — screen/tmux session name (training/download only)
- `state_file` — path to the loop's heartbeat/state file (loop only)
- `stale_after_seconds` — staleness window in seconds; set ≥ the loop's longest single iteration (loop only)

**Optional fields:**
- `session_type` — `"screen"` (default) or `"tmux"` (training/download)
- `gpus` — list of GPU indices to monitor (training only)
- `target_path` — file/directory to track size growth (download only)

### 4. Monitor from your local machine

**One-shot check:**
```bash
ssh your-server "python3 /path/to/tools/watchdog.py --status"
# or
ssh your-server "cat /tmp/aris-watchdog/status/summary.txt"
```

**Example output:**
```
exp01(training): OK
exp02(training): IDLE gpu={'0': 0, '1': 0, '2': 0, '3': 2}
dl01(download): SLOW speed=0.45MB/s
```

**Automated polling with CronCreate (Claude Code):**
```
CronCreate: every 15 minutes
  ssh your-server "cat /tmp/aris-watchdog/status/summary.txt"
  → all OK → do nothing
  → any DEAD/STALLED/SLOW/IDLE → investigate and fix
```

> **One cron job per server**, not per task — summary.txt aggregates everything.

### 5. Unregister completed tasks

```bash
python3 tools/watchdog.py --unregister exp01
```

## Status Codes

| Status | Meaning | Suggested Action |
|--------|---------|-----------------|
| `OK` | Task running normally | Nothing |
| `DEAD` | Session no longer exists | Check if training finished or crashed; restart if needed |
| `IDLE` | GPU utilization <5% | Training may have finished, crashed, or is stuck in data loading |
| `STALLED` | Download file size not growing | Check network, disk space, auth tokens |
| `SLOW` | Download speed <1 MB/s | May be throttled; check network or source |
| `STALE` | Loop's state file not updated within `stale_after_seconds` | Loop may have died silently (compaction/session close); restart/nudge it (detect-only — watchdog never auto-restarts) |
| `MISSING` | Loop registered but state file absent past grace | Likely a path typo in `state_file`, or the loop never started |
| `PENDING` | Loop registered, awaiting first state write | Normal at startup; no action |
| `COMPLETED` | Loop reported completion | Unregister it (`--unregister`) |
| `ERROR` | Watchdog encountered an error checking this task | Check watchdog logs |

## Integration with ARIS Workflows

### With `/run-experiment`

After deploying an experiment with `/run-experiment`, register it with watchdog:

```bash
# /run-experiment launches screen session "exp01"
# Then register it:
python3 tools/watchdog.py --register '{"name":"exp01","type":"training","session":"exp01","gpus":[0,1]}'
```

### With `/monitor-experiment`

`/monitor-experiment` does deep inspection (log parsing, W&B metrics, result collection). Watchdog does continuous surface-level health checks. They complement each other:

- **Watchdog** — "is it alive and using GPU?" (runs 24/7, low overhead)
- **`/monitor-experiment`** — "what are the actual results?" (on-demand, detailed)

### With Session Recovery

When starting a new session, check `alerts.log` for anomalies that happened while you were away:

```bash
ssh your-server "tail -20 /tmp/aris-watchdog/alerts.log"
```

This pairs well with the [Session Recovery Guide](SESSION_RECOVERY_GUIDE.md) — add watchdog alert checking to your recovery flow.

## Customization

| Parameter | Default | How to change |
|-----------|---------|---------------|
| Base directory | `/tmp/aris-watchdog` | `--base-dir /your/path` |
| Check interval | 60 seconds | `--interval 30` |
| GPU idle threshold | 5% | Edit `GPU_IDLE_THRESHOLD` in script |
| Slow download threshold | 1 MB/s | Edit `SLOW_SPEED_THRESHOLD` in script |

## FAQ

**Q: Does it need root / sudo?**
A: No. Just Python 3 and `nvidia-smi` (for training tasks).

**Q: Can I run multiple watchdog instances on one server?**
A: Yes, use different `--base-dir` for each. But normally one instance per server is sufficient — it handles multiple tasks.

**Q: What if the watchdog itself crashes?**
A: Check `watchdog.pid` — if the PID is stale, restart it. The daemon handles SIGTERM/SIGINT gracefully.

**Q: Does it work without nvidia-smi?**
A: Yes for download tasks. Training tasks will report OK (no GPU data) but won't detect IDLE GPUs.
