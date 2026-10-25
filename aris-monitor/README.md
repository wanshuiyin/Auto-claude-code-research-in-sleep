# ARIS-Monitor

Supports **Claude Code and local Codex** sessions. Codex rows show recent turn
activity and outcomes; clicking a row opens the existing Codex chat.
**Codex approval prompts are not monitored** (this limitation stays visible in
the panel). The screenshot below illustrates the original Claude-only UI.

<p align="center">
  <img src="assets/screenshot.png" alt="ARIS-Monitor — a floating widget showing which Claude Code sessions need approval; calm all-clear state and the red ATTENTION state when a session is waiting on you" width="440">
</p>

<p align="center"><em>Top: all-clear. Bottom: a session hit a permission prompt → the row goes red <strong>NEEDS YOU</strong> and the header turns red.</em></p>

A tiny, native, **always-on-top floating** macOS widget that shows, at a glance,
which of your **Claude Code and local Codex** sessions are working or done.
Claude Code additionally provides **"needs approval / pending permission"**.

No browser. No Chrome extension. No Electron. Pure Python **stdlib Tkinter** —
**zero `pip install`**.

> ## 🔒 READ-ONLY monitoring + ONE opt-in focus action
> ARIS-Monitor reads Claude registry files under `~/.claude` and connects to
> local Codex status databases with SQLite `mode=ro` and `query_only=ON`.
> It never changes session records. Activity is inferred from timestamps; it
> does **not** even call `os.kill(pid, 0)`). The **one** non-read action is
> **Focus**: a Codex row opens an existing local chat via `codex://threads/<UUID>`.
> A Claude row raises its terminal window; only this path runs `ps` and the
> raise-only `focus-tty.sh` (osascript `activate` / `select`). Focus is always
> user-initiated and **never** kills, signals, writes, or modifies any session or
> process — it can only bring a window to the front. **No network calls, ever.**

## Run

```bash
./run.sh            # start the floating widget (top-right, draggable)
./ARIS-Monitor.command  # macOS double-click launcher, including Homebrew PATH
# or directly:
python3 widget.py
```

A small panel with a native title bar appears top-right, floating above normal
windows. It is accessible through Dock / Cmd-Tab. Drag the title bar or dark
header. Quit with the window close button, `×`, or `q` / `Esc`.

**Click a Claude row** to jump to (focus) its terminal tab/window — the
triage loop is: panel goes red → click the row → you're at that terminal to
approve. Focus is raise-only (Terminal.app / iTerm2 / tmux); it never touches the
session itself.

Other modes:

```bash
./run.sh --check    # read-only smoke test (prints the classified list, no GUI)
./run.sh --ticker   # headless terminal ticker (same scanner, same 2s loop)
python3 scanner.py  # same as --check
```

## What it watches (READ-ONLY)

The authoritative needs-approval signal is the **live session registry**, not a
transcript guess:

```
~/.claude/sessions/<pid>.json     ->  status == "waiting"   (the core signal)
~/.claude/projects/<slug>/<id>.jsonl  (read-only tail, only to refine working/done)
```

The Claude Code app itself sets `status == "waiting"` (with an optional
`waitingFor` string like `Bash(npm test) needs approval`) **while a permission
prompt is on screen**, and clears it the instant you answer. So:

- needs-approval is detected with **no transcript parsing** — straight from the
  live JSON, which is why it is authoritative; and
- it is inherently **transient** — the widget **polls every ~2 s** to catch it.
  On a quiescent machine you will only ever see *working* / *done*, never
  *waiting*. That is expected, not a bug.

| dot | bucket          | meaning                                                              |
|-----|-----------------|---------------------------------------------------------------------|
| 🔴 ● | **NEEDS YOU**   | `status == "waiting"` — a permission prompt is blocking this session on you |
| 🟡 ◐ | working         | actively running (`busy` & fresh, or a background task in flight)    |
| 🟡 ◐ | stalled         | stopped mid-tool while **not** waiting — may need a nudge (**not** red) |
| 🟢 ○ | done            | last turn completed (`end_turn`) — finished, awaiting your review    |
| ·   | stale (dim)     | `updatedAt` older than 30 min — rendered dim and sorted to the bottom |

Sort order: NEEDS YOU → stalled / unknown → working → done → stale.

The panel shows the **top 5** rows by that order; everything beyond folds behind
a clickable `▸ N more (click to show)`. **needs-approval rows are never folded** —
the cut stretches to include every red session. (Tune the cap with `MAX_VISIBLE`.)

### Why not the "unmatched trailing tool call" heuristic?

Because a transcript that stops at a `tool_use` block while the session is
**not** `status=="waiting"` only means the run **stalled**, not that it is
waiting on your approval. Keying needs-approval off that would false-positive on
every mid-tool pause. The live `status=="waiting"` flag is the only
authoritative pending-permission signal, so that is what the red bucket uses.

### Local Codex support

The scanner reads the newest numbered `state_<version>.sqlite` and
`thread_history_<version>.sqlite` under `$CODEX_HOME` (default `~/.codex`).
Read-only SQLite connections include live WAL data. It selects thread names,
the latest turn, and item timestamps; it does not read Codex message text or
credentials, contact the network, or send commands to Codex sessions.

| label | evidence |
|---|---|
| working | latest turn is `inProgress`, with turn/item activity within 5 minutes |
| done | latest turn is `completed` |
| failed / stopped | latest turn is `failed` / `interrupted` |
| unknown | in-progress turn quiet for 5–30 minutes, unrecognized status, or unavailable/incompatible store |
| stale | no observed activity within 30 minutes; no claim about process liveness |

Non-archived local `cli`, `vscode`, and `exec` threads updated within 24 hours
are retained, along with older unresolved turns. Subagent sources are excluded.
Quiet unresolved turns become dim stale rows rather than guessed approvals.
Clicking a Codex row uses a validated UUID deep link to open the existing chat.

**Codex pending approvals are not detected.** An absence of red rows does not
mean Codex needs no approval. This extension has not connected to the desktop
instance's App Server runtime approval flags. Remote-host sessions are outside
the local database scan. Codex's internal database schemas can change; missing
or incompatible stores appear as an amber `Codex status unavailable` row,
while Claude scanning continues.

## Empty / all-clear state

With zero recent sessions the panel stays visible with a `0 working · 0 done`
header and `no recent Claude/Codex sessions`. Failed/unknown states produce an
amber attention count. Only an authoritative Claude waiting signal turns the
header red; the Codex approval limitation remains visible in the footer.

## Files

- `widget.py`  — the Tkinter floating panel (UI; imports `scanner.scan()` for the
  read-only display and `focus.focus()` for the click-to-raise action).
- `scanner.py` — the strictly read-only classifier. Public: `scan()`,
  `summary()`. `python3 scanner.py` is a GUI-less smoke test.
- `focus.py` — user-initiated terminal focus or opening an existing Codex chat.
  Never kills/signals or changes session records.
- `focus-tty.sh` — bundled raise-only shim (Terminal.app / iTerm2 / tmux pane).
  Always the bundled script (no `~/.claude/focus-tty.sh` override is executed),
  so the focus action's command surface stays provably bounded to this reviewed
  shim — osascript `activate`/`select` + read-only `tmux list-*` discovery, never
  `kill`/`send-keys`/session mutation.
- `ticker.py`  — headless terminal fallback (same scanner, same 2 s loop), used
  automatically when Tkinter is unavailable.
- `run.sh`     — launcher: verifies Tk, starts the widget, falls back to the
  ticker. Supports `--check` and `--ticker`.
- `ARIS-Monitor.command` — double-click launcher for macOS, honoring `PYTHON`.
- `test_codex.py` — isolated temporary SQLite/WAL stores; no real sessions changed.
- `test_widget.py` — GUI startup/mapping/refresh/shutdown check; requires a display.

## Dependencies

Python standard library only, including `tkinter`, `sqlite3`, and `dataclasses`.
No pip packages or venv. The GUI requires **Tk >= 8.6**; system Tk 8.5 produced
a blank window on the tested Mac. Python 3.14 + Tk 9.1 was visually verified.
For Homebrew Python use `brew install python-tk`, or select a compatible
interpreter with `PYTHON=/path/to/python3 ./run.sh`. Missing/old Tk falls back
to `--ticker`, which needs no Tk.

> **Note on `run.sh` and venvs:** ARIS-Monitor has *no* third-party
> dependencies, so there is nothing to install and `run.sh` deliberately does
> **not** create a venv — a fresh venv often lacks the compiled `_tkinter`
> module the base interpreter has, which would break the GUI. The launcher
> simply verifies Tk against your existing `python3` and runs.

## Tunables

Top-of-file constants in `scanner.py` / `widget.py`:

- `REFRESH_MS` (widget) / `REFRESH_S` (ticker) — poll cadence (default 2 s).
- `MAX_VISIBLE` (widget) — rows shown before the rest fold behind `▸ N more` (default 5; needs-approval rows are never folded).
- `LIVE_WINDOW` — seconds before a session is styled dim/stale and sorted to the bottom (1800 = 30 min).
- `IDLE_THRESHOLD` — busy-but-fresh cutoff for "working" (300).
- `TRANSCRIPT_TAIL_BYTES` — read-only tail size (256 KiB).

## Validation

```bash
python3 test_codex.py  # status classification, live WAL, failures, safe navigation
python3 test_widget.py  # GUI session + Tk >= 8.6 required
./run.sh --check
```

The GUI startup uses one Tk root, avoiding queued `ThemeChanged` events against
a destroyed probe window. Native window close uses the same clean shutdown as
the panel close button. True fullscreen apps still use separate macOS Spaces.
