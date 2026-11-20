#!/usr/bin/env python3
"""ARIS-Monitor: a tiny, native, always-on-top FLOATING macOS widget.

Pure Python stdlib Tkinter -- zero pip installs. It shows Claude Code and local
Codex turn status. Claude sessions can also show
"needs approval / pending permission" -- plus a simple working / done status.

No browser. No Chrome extension. No Electron.

READ-ONLY MONITORING: Claude rows raise their terminal; Codex rows open the
existing local chat via a validated UUID deep link. Only Claude focus
runs `ps` (to read the pid's tty) and the raise-only `focus-tty.sh`
(osascript activate/select), via the tightly-scoped focus.py module. It is
user-initiated, best-effort, and NEVER kills, signals, writes, or otherwise
modifies any session or process. Reading files via scanner.scan() and closing
this app's own window are the only other effects.

Run it yourself:
    python3 widget.py

Quit: click the × in the header, or press 'q' / Esc while it is focused.

The native title bar keeps the window accessible via Dock / Cmd-Tab.
The panel stays above normal windows with -topmost and can be dragged by its
title bar or dark header. True fullscreen apps use separate macOS Spaces.
"""
from __future__ import annotations

import sys
import threading
import tkinter as tk
import tkinter.font as tkfont

import focus
import scanner

# ---------------------------------------------------------------------------
# Tunables (top-of-file constants only -- no config UI by design).
# ---------------------------------------------------------------------------
REFRESH_MS = 2000          # re-scan files every 2s (pure stat()+tail read)
WIDTH = 520
MAX_VISIBLE = 5            # show at most this many rows; fold the rest behind "+N more"
                          # (needs-approval rows are NEVER folded -- the cap stretches)

# Appearance.
BG = "#11151c"             # panel background (dark)
HEADER_BG = "#0a0d12"
HEADER_RED = "#2a0f12"     # header background when something needs you
FG = "#c9d4e0"
DIM = "#5b6675"
RED = "#ff5c5c"
AMBER = "#f5c451"
GREEN = "#56d364"

# triage bucket -> (dot color, text color, glyph, short label)
STYLE = {
    scanner.NEEDS_APPROVAL:  (RED,   "#ffd7d7", "●", "NEEDS YOU"),   # ● filled
    scanner.NEEDS_ATTENTION: (AMBER, "#f1e3bf", "◐", "stalled"),     # ◐ half
    scanner.WORKING:         (AMBER, "#f1e3bf", "◐", "working"),     # ◐ half
    scanner.IDLE_DONE:       (GREEN, "#bfe6c4", "○", "done"),        # ○ hollow
    scanner.STALE_HIDDEN:    (DIM,   DIM,       "·", "stale"),       # · dim (expanded)
    scanner.UNKNOWN:        (AMBER, FG,        "?", "unknown"),
}


class FloatWidget:
    def __init__(self, root=None):
        self.root = root if root is not None else tk.Tk()
        self.root.title("ARIS-Monitor")
        self.root.configure(bg=BG)

        # Native title bar keeps the monitor discoverable in Dock / Cmd-Tab.
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.96)
        except tk.TclError:
            pass

        # position: top-right corner by default.
        # Tk geometry must be "WxH+X+Y" or position-only "+X+Y". The earlier
        # "{WIDTH}+X+Y" form omitted the "xHEIGHT" and was rejected by Tk
        # ("bad geometry specifier"), crashing the launch. We position only and
        # let the panel auto-size to its content; minsize keeps a sensible floor.
        sw = self.root.winfo_screenwidth()
        x = max(0, sw - WIDTH - 24)
        self.root.geometry(f"+{x}+48")
        try:
            self.root.minsize(WIDTH, 1)
        except tk.TclError:
            pass

        self._mono = tkfont.Font(family="Menlo", size=11)
        self._mono_b = tkfont.Font(family="Menlo", size=11, weight="bold")
        self._small = tkfont.Font(family="Menlo", size=9)

        # Shutdown bookkeeping: track the pending after() id and a stopped flag
        # so a tick already scheduled can be cancelled on quit and never fires
        # its re-arm against a torn-down interpreter.
        self._stopped = False
        self._after_id = None
        self._scanning = False   # True while a worker-thread scan is in flight
        self._show_more = False   # toggled by clicking the "+N more" overflow line
        self._last_sessions = []  # last scan, so the toggle re-renders w/o a re-scan

        self._build_header()
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        tk.Label(self.root, text="Claude + local Codex · Codex approvals not monitored",
                 bg=BG, fg=DIM, font=self._small).pack(padx=8, pady=(0, 6))

        # keyboard quit (only inert state change in the whole app)
        self.root.bind("<q>", lambda e: self._quit())
        self.root.bind("<Escape>", lambda e: self._quit())
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        self._rows = []
        self.tick()

    def _quit(self):
        """Clean shutdown: cancel any pending tick, then destroy our window.

        The ONLY state change is closing this app's own window -- it never
        signals/kills/spawns anything else.
        """
        self._stopped = True
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        try:
            self.root.destroy()
        except Exception:
            pass

    # ----- header (drag handle + title + count + close) ----------------------
    def _build_header(self):
        self.header = tk.Frame(self.root, bg=HEADER_BG)
        self.header.pack(fill="x")

        self.title_lbl = tk.Label(self.header, text="  ARIS-Monitor", bg=HEADER_BG,
                                  fg=FG, font=self._mono_b, anchor="w")
        self.title_lbl.pack(side="left", pady=4)

        close = tk.Label(self.header, text="× ", bg=HEADER_BG, fg=DIM,
                         font=self._mono_b, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self._quit())

        self.count_lbl = tk.Label(self.header, text="", bg=HEADER_BG, fg=RED,
                                  font=self._mono_b)
        self.count_lbl.pack(side="right", padx=(0, 6))

        # The dark header is an additional drag handle.
        for w in (self.header, self.title_lbl):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, e):
        self._dx, self._dy = e.x, e.y

    def _on_drag(self, e):
        x = self.root.winfo_pointerx() - self._dx
        y = self.root.winfo_pointery() - self._dy
        self.root.geometry(f"+{x}+{y}")

    # ----- render ------------------------------------------------------------
    def _clear_body(self):
        for w in self._rows:
            try:
                w.destroy()
            except Exception:
                pass
        self._rows = []

    def tick(self):
        """The ~2s read-only poll loop, driven by Tk's own after() timer.

        The actual scan runs on a short-lived daemon WORKER thread so a slow
        disk or many sessions can never freeze the UI thread; its result is
        rendered back on the main thread via after(0, ...). A scan still in
        flight is not restarted (no pile-up). No busy-wait, no external sleep.
        """
        if self._stopped:
            return
        if not self._scanning:
            self._scanning = True
            threading.Thread(target=self._scan_worker, daemon=True).start()
        # Belt-and-suspenders: re-assert always-on-top each cycle, so even if
        # macOS still drops the panel behind on app-deactivate, it returns to the
        # front within ~2s without the user hunting for it. lift() is idempotent
        # and does not steal focus on a topmost window.
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
        except tk.TclError:
            pass
        # Re-arm the timer regardless; the worker renders when it finishes.
        if not self._stopped:
            try:
                self._after_id = self.root.after(REFRESH_MS, self.tick)
            except tk.TclError:
                pass

    def _scan_worker(self):
        """Read-only scan OFF the UI thread; hands results back via after(0)."""
        try:
            sessions = scanner.scan()      # read-only; returns [] on any failure
        except Exception:
            sessions = []
        if self._stopped:
            return
        try:
            self.root.after(0, lambda: self._apply(sessions))
        except (tk.TclError, RuntimeError):
            # window torn down mid-scan -- nothing to render
            pass

    def _apply(self, sessions):
        """Render scan results on the Tk main thread; clears the in-flight flag."""
        self._scanning = False
        if self._stopped:
            return
        try:
            self._render(sessions)
        except Exception:
            pass

    def _toggle_more(self):
        """Show/hide visible sessions beyond the top MAX_VISIBLE. Pure display."""
        self._show_more = not self._show_more
        self._render(self._last_sessions)

    def _render(self, sessions):
        self._last_sessions = sessions
        self._clear_body()

        need = sum(1 for s in sessions if s.triage == scanner.NEEDS_APPROVAL)
        counts = scanner.summary(sessions)
        issues = counts["needs_attention"] + counts["unknown"]

        # header: count + color
        if need:
            self.count_lbl.config(text=f"{need} ●")
            self.count_lbl.config(fg=RED)
            self.title_lbl.config(fg=RED, text="  ARIS-Monitor — ATTENTION")
            self.header.config(bg=HEADER_RED)
            self.title_lbl.config(bg=HEADER_RED)
            self.count_lbl.config(bg=HEADER_RED)
        else:
            text = f"{issues} attention" if issues else f"{counts['working']} working · {counts['idle_done']} done"
            self.count_lbl.config(text=text, fg=AMBER if issues else GREEN, bg=HEADER_BG)
            self.title_lbl.config(fg=FG, text="  ARIS-Monitor", bg=HEADER_BG)
            self.header.config(bg=HEADER_BG)

        # calm empty state -- stay visible, never flash red on zero sessions
        if not sessions:
            lbl = tk.Label(self.body, text="no recent Claude/Codex sessions",
                           bg=BG, fg=DIM, font=self._mono, anchor="w")
            lbl.pack(fill="x", pady=2)
            self._rows.append(lbl)
            return

        # ONE "top N, fold the rest" model. sessions is already sorted
        # (needs-approval first ... stale last), so the top MAX_VISIBLE are the
        # most relevant; everything beyond folds behind a clickable "+N more".
        # The cut stretches so a needs-approval row is NEVER folded.
        cut = max(MAX_VISIBLE, need)
        head, more = sessions[:cut], sessions[cut:]
        for s in head:
            self._row(s)
        if more:
            caret = "▾" if self._show_more else "▸"
            hint = "click to hide" if self._show_more else "click to show"
            toggle = tk.Label(self.body, text=f"{caret} {len(more)} more ({hint})",
                              bg=BG, fg=DIM, font=self._small, anchor="w", cursor="hand2")
            toggle.pack(fill="x", pady=(4, 0))
            toggle.bind("<Button-1>", lambda e: self._toggle_more())
            self._rows.append(toggle)
            if self._show_more:
                for s in more:
                    self._row(s)

    def _focus(self, session):
        """User-initiated terminal focus or navigation to an existing Codex chat.

        Runs on a daemon worker thread so the focus subprocess (10s worst-case
        timeout) never freezes the panel. Best-effort: a failure is reported to
        stderr and changes nothing -- it can only raise a window, never destroy.
        """
        def work():
            try:
                res = (focus.focus_codex(session.thread_id) if session.source == "Codex"
                       else focus.focus(session.pid))
            except Exception as e:   # never let a focus attempt crash the panel
                res = {"ok": False, "error": str(e)}
            if not res.get("ok"):
                print(f"[ARIS-Monitor] focus {session.source} failed: {res.get('error')}",
                      file=sys.stderr)
        threading.Thread(target=work, daemon=True).start()

    def _row(self, s):
        dot_c, txt_c, glyph, _ = STYLE.get(s.triage, (DIM, FG, "·", s.triage))
        label = scanner.display_label(s)
        row = tk.Frame(self.body, bg=BG, cursor="hand2")
        row.pack(fill="x", pady=1)

        dot = tk.Label(row, text=glyph, bg=BG, fg=dot_c, font=self._mono_b,
                       width=2, cursor="hand2")
        dot.pack(side="left")

        name = tk.Label(row, text=f"[{s.source}] {(s.name or '?')[:22]}", bg=BG, fg=txt_c,
                        font=self._mono, anchor="w", cursor="hand2")
        name.pack(side="left")

        widgets = [row, dot, name]

        # reason for needs_approval (and stalled) is the load-bearing detail
        if s.triage == scanner.NEEDS_APPROVAL and s.reason:
            reason = tk.Label(row, text=str(s.reason)[:26], bg=BG, fg="#ffb0b0",
                              font=self._small, anchor="w", cursor="hand2")
            reason.pack(side="left", padx=(6, 0))
            widgets.append(reason)

        meta = f"{label} · {scanner.fmt_age(s.idle_seconds)}"
        m = tk.Label(row, text=meta, bg=BG, fg=DIM, font=self._small,
                     anchor="e", cursor="hand2")
        m.pack(side="right")
        widgets.append(m)

        # Click anywhere on the row -> raise that session's terminal (focus).
        for w in widgets:
            w.bind("<Button-1>", lambda e, session=s: self._focus(session))

        self._rows.extend(widgets)

    def run(self):
        self.root.mainloop()


def main():
    # Reuse the availability-check root: destroying a probe leaves pending
    # ThemeChanged events targeting a destroyed application on macOS Tk 8.5.
    try:
        root = tk.Tk()
    except tk.TclError as ex:
        print("[ARIS-Monitor] Tkinter unavailable (%s)." % ex)
        print("[ARIS-Monitor] Falling back to the read-only terminal ticker.")
        print("[ARIS-Monitor] Run:  python3 ticker.py")
        raise SystemExit(1)
    FloatWidget(root).run()


if __name__ == "__main__":
    main()
