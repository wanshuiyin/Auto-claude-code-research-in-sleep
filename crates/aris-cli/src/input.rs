use std::collections::VecDeque;
use std::io::{self, IsTerminal, Write};
use std::time::Duration;

use crossterm::{
    cursor,
    event::{
        self, DisableBracketedPaste, EnableBracketedPaste, Event, KeyCode, KeyEvent, KeyEventKind,
        KeyModifiers,
    },
    style::{Color, Print, ResetColor, SetForegroundColor},
    terminal::{self, ClearType},
    QueueableCommand,
};

const MAX_DROPDOWN: usize = 10;

/// Per-read renderer state: tracks the logical row index of the last drawn
/// cursor so we can move back to the start of the input area before clearing.
/// Row-based (not width-based) so that wide CJK chars at the right edge,
/// which terminals pre-wrap before drawing, are accounted for correctly.
#[derive(Debug, Default)]
struct RenderState {
    cursor_row: u16,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ReadOutcome {
    Submit(String),
    Cancel,
    Exit,
}

/// Outcome of the Ctrl+R reverse-search submode (v0.4.16 Track A).
/// `Accept` carries the chosen history entry as chars (loaded into the buffer;
/// the user then presses Enter to submit). `Cancel` restores the prior buffer.
#[derive(Debug, Clone, PartialEq, Eq)]
enum ReverseSearchResult {
    Accept(Vec<char>),
    Cancel,
}

/// Find the index of the newest history entry at or before `from_idx` whose
/// text contains `query` (case-insensitive, substring). History is oldest-first
/// so we scan downward (newest → oldest) starting at `from_idx`.
///
/// An empty `query` matches the entry at `from_idx` itself (bash behaviour:
/// the most recent candidate). Returns `None` if no entry matches.
///
/// Pure + char-based (CJK safe). Extracted as a free function so the match
/// selection logic is unit-testable without a TTY.
fn reverse_search_match(history: &[String], query: &[char], from_idx: usize) -> Option<usize> {
    if history.is_empty() {
        return None;
    }
    let query_lower: Vec<char> = query
        .iter()
        .flat_map(|c| c.to_lowercase())
        .collect();
    let start = from_idx.min(history.len().saturating_sub(1));
    for idx in (0..=start).rev() {
        if entry_contains(&history[idx], &query_lower) {
            return Some(idx);
        }
    }
    None
}

/// Case-insensitive substring test where `needle_lower` is already lowercased
/// chars. An empty needle matches everything. Char-based (CJK safe).
fn entry_contains(haystack: &str, needle_lower: &[char]) -> bool {
    if needle_lower.is_empty() {
        return true;
    }
    let hay: Vec<char> = haystack.chars().flat_map(|c| c.to_lowercase()).collect();
    if needle_lower.len() > hay.len() {
        return false;
    }
    hay.windows(needle_lower.len())
        .any(|w| w == needle_lower)
}

/// Erase the reverse-search prompt line and park the cursor at column 0 so the
/// caller's next `redraw` (which starts from a fresh draw) is valid.
fn clear_reverse_search(stdout: &mut io::Stdout) -> io::Result<()> {
    stdout.queue(cursor::MoveToColumn(0))?;
    stdout.queue(terminal::Clear(ClearType::FromCursorDown))?;
    stdout.flush()
}

pub struct LineEditor {
    prompt: String,
    completions: Vec<(String, String)>,
    history: Vec<String>,
    /// v0.4.25 (#430): console events already pulled off the OS queue while
    /// collecting a Windows paste burst but not part of it (a control key, an
    /// arrow…). Every editor read consumes these before asking the OS again,
    /// so nothing typed or pasted is lost or reordered.
    pending: VecDeque<Event>,
}

/// v0.4.25 (#430): idle window used on Windows to decide that a burst of
/// console records (a multi-line paste) has finished arriving. `poll(0)` is
/// not enough: a modifier-only record or the first half of a UTF-16 surrogate
/// pair yields no event, so crossterm's poll returns `false` while records are
/// still queued behind it.
const PASTE_BURST_IDLE_MS: u64 = 20;

/// v0.4.25 (#430): the merge of one paste burst — what becomes input text and
/// the events that must be replayed unchanged afterwards.
#[derive(Debug, Default, PartialEq)]
pub(crate) struct BurstMerge {
    pub inserted: Vec<char>,
    pub leftover: Vec<Event>,
}

/// v0.4.25 (#430): fold a burst of key events into single-line input text.
/// Printable characters (plain or shifted) are kept, Enter and Tab become a
/// space (exactly what `normalize_paste_text` does for a bracketed paste),
/// key releases / resize / focus events are skipped. Anything else — a
/// control chord, an arrow, Backspace, Esc, a real `Event::Paste` — ends the
/// burst; it and everything after it are handed back as `leftover`, in order.
pub(crate) fn merge_paste_burst(events: &[Event]) -> BurstMerge {
    let mut merged = BurstMerge::default();
    for (index, event) in events.iter().enumerate() {
        match event {
            Event::Key(KeyEvent {
                kind: KeyEventKind::Release,
                ..
            })
            | Event::Resize(..)
            | Event::FocusGained
            | Event::FocusLost => {}
            Event::Key(KeyEvent {
                code: KeyCode::Char(c),
                modifiers,
                ..
            }) if *modifiers == KeyModifiers::NONE || *modifiers == KeyModifiers::SHIFT => {
                merged.inserted.push(*c);
            }
            Event::Key(
                KeyEvent {
                    code: KeyCode::Enter,
                    modifiers: KeyModifiers::NONE,
                    ..
                }
                | KeyEvent {
                    code: KeyCode::Tab, ..
                },
            ) => merged.inserted.push(' '),
            _ => {
                merged.leftover = events[index..].to_vec();
                break;
            }
        }
    }
    merged
}

/// What an Enter keypress means once the events queued behind it are known.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum EnterDecision {
    /// Plain Enter: submit the line.
    Submit,
    /// Text and/or edit keys followed the Enter (or the Enter itself was
    /// replayed from a burst): it is a pasted newline — insert, stay in the
    /// editor, replay the leftover events afterwards.
    InsertAsNewline,
    /// A Ctrl+C was queued right behind the Enter: cancel the input now.
    CancelInput,
    /// A Ctrl+D was queued right behind the Enter: leave the editor now.
    ExitEditor,
}

/// Pure decision for the Enter arm (v0.4.25 #430). Cancellation queued behind
/// the Enter wins over everything so it can never be deferred until after a
/// submitted turn; anything else left over keeps the editor active.
pub(crate) fn enter_decision(from_pending: bool, merged: &BurstMerge) -> EnterDecision {
    match merged.leftover.first() {
        Some(Event::Key(KeyEvent {
            code: KeyCode::Char('c'),
            modifiers: KeyModifiers::CONTROL,
            ..
        })) => EnterDecision::CancelInput,
        Some(Event::Key(KeyEvent {
            code: KeyCode::Char('d'),
            modifiers: KeyModifiers::CONTROL,
            ..
        })) => EnterDecision::ExitEditor,
        Some(_) => EnterDecision::InsertAsNewline,
        None if from_pending || !merged.inserted.is_empty() => EnterDecision::InsertAsNewline,
        None => EnterDecision::Submit,
    }
}

/// Kill switch for the paste-burst heuristic: only an exact `0` disables it
/// (`ARIS_PASTE_BURST=0` restores the pre-v0.4.25 behaviour).
fn paste_burst_enabled_from(value: Option<&str>) -> bool {
    value.is_none_or(|v| v.trim() != "0")
}

/// Whether this build/host collects paste bursts at all: Windows only (its
/// console never delivers `Event::Paste`, so a paste is a run of key records;
/// on Unix bracketed paste already arrives as one event).
fn paste_burst_collection_active(windows: bool, env_value: Option<&str>) -> bool {
    windows && paste_burst_enabled_from(env_value)
}

/// Pull every console event that is already queued (Windows only), waiting a
/// short idle window between records. Used after an Enter (is this Enter the
/// end of a pasted line?) and to clear typed-ahead lines after Ctrl+C.
fn collect_queued_console_events() -> io::Result<Vec<Event>> {
    let mut out = Vec::new();
    if !paste_burst_collection_active(cfg!(windows), std::env::var("ARIS_PASTE_BURST").ok().as_deref()) {
        return Ok(out);
    }
    while event::poll(Duration::from_millis(PASTE_BURST_IDLE_MS))? {
        out.push(event::read()?);
    }
    Ok(out)
}

/// v0.4.25 (#430): discard console input that arrived while a turn was
/// running (the rest of a pasted block after Ctrl+C). Windows only; a no-op
/// elsewhere. Best effort.
pub fn drain_console_input() {
    let _ = collect_queued_console_events();
}

impl LineEditor {
    #[must_use]
    pub fn new(prompt: impl Into<String>, completions: Vec<(String, String)>) -> Self {
        Self {
            prompt: prompt.into(),
            completions,
            history: Vec::new(),
            pending: VecDeque::new(),
        }
    }

    /// Forget events held back from an earlier paste burst (after Ctrl+C).
    pub fn clear_pending(&mut self) {
        self.pending.clear();
    }

    /// The next editor event: a held-back event first, else the OS. The flag
    /// says which, so an Enter that was part of a paste burst never submits.
    fn next_event(&mut self) -> io::Result<(Event, bool)> {
        match self.pending.pop_front() {
            Some(event) => Ok((event, true)),
            None => Ok((event::read()?, false)),
        }
    }

    pub fn push_history(&mut self, entry: impl Into<String>) {
        let entry = entry.into();
        if !entry.trim().is_empty() {
            self.history.push(entry);
        }
    }

    /// v0.4.16 Track A (additive): seed the in-memory history Vec from a
    /// persisted history file before the first `read_line`. Uses the *same*
    /// blank filter as `push_history` (`!entry.trim().is_empty()`); the loaded
    /// entries are appended oldest-first so Up/Down indexing reproduces exactly.
    ///
    /// Best-effort: a missing/corrupt file (or the `ARIS_NO_HISTORY`
    /// kill-switch) yields a silent empty start — no error surfaces. Pre-existing
    /// in-memory entries are preserved (loaded entries are appended after them).
    pub fn load_history_from(&mut self, path: &std::path::PathBuf) {
        for entry in crate::history::load_history(path) {
            // `load_history` already applied the blank filter, but re-check so
            // this method is independently correct regardless of caller.
            if !entry.trim().is_empty() {
                self.history.push(entry);
            }
        }
    }

    pub fn read_line(&mut self) -> io::Result<ReadOutcome> {
        if !io::stdin().is_terminal() || !io::stdout().is_terminal() {
            return self.read_line_fallback();
        }

        terminal::enable_raw_mode()?;
        let mut stdout = io::stdout();

        // Enable bracketed paste so multi-line paste arrives as a single
        // Event::Paste(String) instead of being mis-parsed as a sequence of
        // KeyCode::Enter submits. Terminals that don't support the sequence
        // simply return Unsupported and we keep the legacy behavior.
        let bracketed_paste_enabled =
            match stdout.queue(EnableBracketedPaste).and_then(|s| s.flush()) {
                Ok(()) => true,
                Err(err) if err.kind() == io::ErrorKind::Unsupported => false,
                Err(err) => {
                    let _ = terminal::disable_raw_mode();
                    return Err(err);
                }
            };

        let result = self.read_line_raw();

        let paste_disable_result = if bracketed_paste_enabled {
            stdout.queue(DisableBracketedPaste).and_then(|s| s.flush())
        } else {
            Ok(())
        };
        let raw_disable_result = terminal::disable_raw_mode();
        let newline_result = writeln!(stdout).and_then(|()| stdout.flush());

        paste_disable_result?;
        raw_disable_result?;
        newline_result?;
        result
    }

    fn read_line_raw(&mut self) -> io::Result<ReadOutcome> {
        let mut stdout = io::stdout();
        let mut buf: Vec<char> = Vec::new();
        let mut cursor_pos: usize = 0;
        let mut sel: usize = 0; // dropdown selection index
        let mut history_idx: Option<usize> = None;
        let mut saved_buf: Option<Vec<char>> = None;
        // v0.4.20 (#8): after Esc dismisses the completion dropdown, suppress it
        // while the buffer is unchanged. Snapshotting `buf` means any edit (which
        // changes `buf`) auto-clears the suppression and the dropdown returns —
        // no need to reset a flag in every edit branch.
        let mut suppressed_for: Option<Vec<char>> = None;
        let mut render = RenderState::default();

        self.redraw(
            &mut stdout,
            &mut render,
            &buf,
            cursor_pos,
            sel,
            suppressed_for.as_deref() == Some(buf.as_slice()),
        )?;

        loop {
            let (ev, from_pending) = self.next_event()?;

            // Handle terminal resize
            if let Event::Resize(..) = ev {
                self.redraw(
            &mut stdout,
            &mut render,
            &buf,
            cursor_pos,
            sel,
            suppressed_for.as_deref() == Some(buf.as_slice()),
        )?;
                continue;
            }

            // Bracketed-paste payload: insert the whole pasted block at
            // cursor_pos as a single edit. Newlines/tabs are flattened to
            // spaces because this is a single-line editor.
            if let Event::Paste(text) = ev {
                let pasted = normalize_paste_text(&text);
                if !pasted.is_empty() {
                    let inserted_len = pasted.len();
                    buf.splice(cursor_pos..cursor_pos, pasted);
                    cursor_pos += inserted_len;
                    sel = 0;
                    history_idx = None;
                    saved_buf = None;
                    self.redraw(
            &mut stdout,
            &mut render,
            &buf,
            cursor_pos,
            sel,
            suppressed_for.as_deref() == Some(buf.as_slice()),
        )?;
                }
                continue;
            }

            let Event::Key(KeyEvent {
                code,
                modifiers,
                kind,
                ..
            }) = ev
            else {
                continue;
            };
            if kind == KeyEventKind::Release {
                continue;
            }

            let line: String = buf.iter().collect();
            // v0.4.20 (#8): honor an Esc-suppression only while the buffer is
            // exactly what it was when Esc was pressed; any edit changes `buf`
            // and brings completions back.
            let matches = if suppressed_for.as_deref() == Some(buf.as_slice()) {
                Vec::new()
            } else {
                suppressed_for = None;
                self.compute_matches(&line)
            };

            match (code, modifiers) {
                // ── Exit / Cancel ──────────────────────────────────────────
                (KeyCode::Char('c'), KeyModifiers::CONTROL) => {
                    // v0.4.25 (#430): whatever else was pasted or typed behind
                    // this Ctrl+C is abandoned with the line, not fed to the
                    // next prompt one line at a time.
                    let _ = collect_queued_console_events();
                    self.pending.clear();
                    self.clear_and_restore(&mut stdout, &mut render, &buf, cursor_pos)?;
                    if buf.is_empty() {
                        return Ok(ReadOutcome::Exit);
                    } else {
                        return Ok(ReadOutcome::Cancel);
                    }
                }
                (KeyCode::Char('d'), KeyModifiers::CONTROL) => {
                    self.clear_and_restore(&mut stdout, &mut render, &buf, cursor_pos)?;
                    return Ok(ReadOutcome::Exit);
                }

                // ── Submit ─────────────────────────────────────────────────
                (KeyCode::Enter, KeyModifiers::NONE) => {
                    // v0.4.25 (#430): on Windows a multi-line paste arrives as
                    // key records with an Enter between lines. If more input
                    // is already queued behind this Enter, it is a pasted
                    // newline: merge the burst into the buffer as text (a
                    // burst is never auto-submitted — the user presses Enter
                    // again). An Enter replayed from `pending` is likewise a
                    // newline, never a submit.
                    let burst = if from_pending {
                        Vec::new()
                    } else {
                        collect_queued_console_events()?
                    };
                    let merged = merge_paste_burst(&burst);
                    match enter_decision(from_pending, &merged) {
                        decision @ (EnterDecision::CancelInput | EnterDecision::ExitEditor) => {
                            // Cancellation queued right behind the Enter: the
                            // user is cancelling, not submitting — and the rest
                            // of the queue goes with it.
                            let exit = decision == EnterDecision::ExitEditor || buf.is_empty();
                            self.pending.clear();
                            self.clear_and_restore(&mut stdout, &mut render, &buf, cursor_pos)?;
                            return Ok(if exit {
                                ReadOutcome::Exit
                            } else {
                                ReadOutcome::Cancel
                            });
                        }
                        EnterDecision::InsertAsNewline => {
                            let mut inserted = vec![' '];
                            inserted.extend(merged.inserted);
                            let inserted_len = inserted.len();
                            buf.splice(cursor_pos..cursor_pos, inserted);
                            cursor_pos += inserted_len;
                            sel = 0;
                            history_idx = None;
                            saved_buf = None;
                            self.pending.extend(merged.leftover);
                        }
                        EnterDecision::Submit => {
                            if !matches.is_empty() {
                                let (name, _) = &self.completions[matches[sel]];
                                let result = name.clone();
                                self.accept_and_clear(&mut stdout, &mut render, &result)?;
                                return Ok(ReadOutcome::Submit(result));
                            }
                            self.accept_and_clear(&mut stdout, &mut render, &line)?;
                            return Ok(ReadOutcome::Submit(line));
                        }
                    }
                }

                // ── Tab: accept first/selected match ───────────────────────
                (KeyCode::Tab, _) => {
                    if !matches.is_empty() {
                        let (name, _) = &self.completions[matches[sel]];
                        buf = name.chars().collect();
                        cursor_pos = buf.len();
                        sel = 0;
                    }
                }

                // ── ESC: close dropdown ─────────────────────────────────────
                (KeyCode::Esc, _) => {
                    sel = 0;
                    // v0.4.20 (#8): actually dismiss the dropdown. Snapshot the
                    // current buffer; `matches` stays empty until the buffer
                    // changes (previously Esc was a no-op — `matches` was
                    // recomputed from the unchanged buffer, so it reappeared).
                    suppressed_for = Some(buf.clone());
                }

                // ── Down: next dropdown item or history forward ─────────────
                (KeyCode::Down, KeyModifiers::NONE) => {
                    if !matches.is_empty() {
                        sel = (sel + 1).min(matches.len().saturating_sub(1));
                    } else if let Some(idx) = history_idx {
                        if idx + 1 < self.history.len() {
                            history_idx = Some(idx + 1);
                            buf = self.history[idx + 1].chars().collect();
                        } else {
                            history_idx = None;
                            buf = saved_buf.take().unwrap_or_default();
                        }
                        cursor_pos = buf.len();
                        sel = 0;
                    }
                }

                // ── Up: prev dropdown item or history back ──────────────────
                (KeyCode::Up, KeyModifiers::NONE) => {
                    if !matches.is_empty() {
                        if sel > 0 {
                            sel -= 1;
                        }
                    } else if !self.history.is_empty() {
                        match history_idx {
                            None => {
                                saved_buf = Some(buf.clone());
                                let new_idx = self.history.len() - 1;
                                history_idx = Some(new_idx);
                                buf = self.history[new_idx].chars().collect();
                            }
                            Some(idx) if idx > 0 => {
                                history_idx = Some(idx - 1);
                                buf = self.history[idx - 1].chars().collect();
                            }
                            _ => {}
                        }
                        cursor_pos = buf.len();
                        sel = 0;
                    }
                }

                // ── Backspace ────────────────────────────────────────────────
                (KeyCode::Backspace, _) => {
                    if cursor_pos > 0 {
                        buf.remove(cursor_pos - 1);
                        cursor_pos -= 1;
                        sel = 0;
                    }
                }

                // ── Delete ───────────────────────────────────────────────────
                (KeyCode::Delete, _) => {
                    if cursor_pos < buf.len() {
                        buf.remove(cursor_pos);
                        sel = 0;
                    }
                }

                // ── Cursor movement ──────────────────────────────────────────
                (KeyCode::Left, KeyModifiers::NONE) => {
                    if cursor_pos > 0 {
                        cursor_pos -= 1;
                    }
                }
                (KeyCode::Right, KeyModifiers::NONE) => {
                    if cursor_pos < buf.len() {
                        cursor_pos += 1;
                    }
                }
                (KeyCode::Home, _) | (KeyCode::Char('a'), KeyModifiers::CONTROL) => {
                    cursor_pos = 0;
                }
                (KeyCode::End, _) | (KeyCode::Char('e'), KeyModifiers::CONTROL) => {
                    cursor_pos = buf.len();
                }

                // ── Kill commands ────────────────────────────────────────────
                (KeyCode::Char('k'), KeyModifiers::CONTROL) => {
                    buf.truncate(cursor_pos);
                    sel = 0;
                }
                (KeyCode::Char('u'), KeyModifiers::CONTROL) => {
                    buf.drain(..cursor_pos);
                    cursor_pos = 0;
                    sel = 0;
                }
                (KeyCode::Char('w'), KeyModifiers::CONTROL) => {
                    // Delete word backwards
                    while cursor_pos > 0 && buf[cursor_pos - 1] == ' ' {
                        buf.remove(cursor_pos - 1);
                        cursor_pos -= 1;
                    }
                    while cursor_pos > 0 && buf[cursor_pos - 1] != ' ' {
                        buf.remove(cursor_pos - 1);
                        cursor_pos -= 1;
                    }
                    sel = 0;
                }

                // ── Ctrl+R: reverse incremental history search (additive) ─────
                // v0.4.16 Track A. Today this lands in `_ => continue` and is
                // swallowed; the regular-char arm below requires NONE|SHIFT so
                // Char('r')+CONTROL can never reach it. Adding this arm does not
                // change the reachability of any existing arm. The submode owns
                // its own event loop + redraw and never toggles raw mode or
                // bracketed paste (it runs inside read_line's lifecycle).
                (KeyCode::Char('r'), KeyModifiers::CONTROL) => {
                    // Snapshot the FULL pre-search state so Cancel is a true
                    // no-op (buffer + cursor + dropdown selection + history-nav).
                    let initial_buf = buf.clone();
                    let initial_cursor = cursor_pos;
                    let initial_sel = sel;
                    let initial_history_idx = history_idx;
                    let initial_saved_buf = saved_buf.clone();
                    // The current input may have wrapped across several physical
                    // rows; move the cursor back to the input start row first so
                    // the submode draws over (and clears) the whole input area,
                    // not just the current row. After this the cursor is at the
                    // input start and the submode's single-line prompt sits on
                    // exactly one row.
                    move_to_input_start(&mut stdout, &render, terminal_width())?;
                    match self.reverse_search(&mut stdout)? {
                        ReverseSearchResult::Accept(entry) => {
                            buf = entry;
                            cursor_pos = buf.len();
                            sel = 0;
                            history_idx = None;
                            saved_buf = None;
                        }
                        ReverseSearchResult::Cancel => {
                            buf = initial_buf;
                            cursor_pos = initial_cursor.min(buf.len());
                            sel = initial_sel;
                            history_idx = initial_history_idx;
                            saved_buf = initial_saved_buf;
                        }
                    }
                    // The submode erased its single-line prompt and parked the
                    // cursor at column 0 of the input start row. Reset the row
                    // anchor so the next `redraw`'s `move_to_input_start` does
                    // not `MoveToPreviousLine` past the (now single-line) area.
                    render.cursor_row = 0;
                    // Fall through to the existing redraw at the end of the loop.
                }

                // ── Regular character ────────────────────────────────────────
                (KeyCode::Char(c), mods)
                    if mods == KeyModifiers::NONE || mods == KeyModifiers::SHIFT =>
                {
                    buf.insert(cursor_pos, c);
                    cursor_pos += 1;
                    sel = 0;
                    history_idx = None;
                }

                _ => continue,
            }

            self.redraw(
            &mut stdout,
            &mut render,
            &buf,
            cursor_pos,
            sel,
            suppressed_for.as_deref() == Some(buf.as_slice()),
        )?;
        }
    }

    /// Ctrl+R reverse incremental history search submode (v0.4.16 Track A).
    ///
    /// Self-contained: owns its own event loop + a single search-prompt line
    /// that it draws and then erases on exit. It does **not** toggle raw mode or
    /// bracketed paste (it runs inside `read_line`'s lifecycle) and never emits
    /// `Exit`/`Cancel` out of `read_line_raw`.
    ///
    /// On exit it clears its own prompt line and parks the cursor at column 0 of
    /// the (now empty) input line, so the caller's subsequent `redraw` —
    /// starting from `render.cursor_row == 0` after a fresh draw — stays valid.
    ///
    /// Keys: printable char → extend query (re-scan newest→oldest); Backspace →
    /// shrink query; Ctrl+R again → step to the next older match; Enter → Accept
    /// the matched entry into the buffer; Esc / Ctrl+C / Ctrl+G → Cancel; other
    /// keys ignored. Non-TTY callers never reach here (fallback skips raw loop).
    fn reverse_search(&mut self, stdout: &mut io::Stdout) -> io::Result<ReverseSearchResult> {
        let mut query: Vec<char> = Vec::new();
        // The scan anchor is always the newest entry on a query change; Ctrl+R
        // steps from the current match minus one. We don't keep it as a
        // persistent local because every branch recomputes the anchor it needs.
        // history does not change inside the submode; a plain value avoids
        // holding a borrow of `self` across `next_event`.
        let newest = self.history.len().saturating_sub(1);
        let mut matched: Option<usize> = if self.history.is_empty() {
            None
        } else {
            reverse_search_match(&self.history, &query, newest)
        };

        self.draw_reverse_search(stdout, &query, matched)?;

        loop {
            let (ev, _) = self.next_event()?;

            // Ignore resize/paste inside the submode (keep the prompt as-is);
            // a resize just redraws the single prompt line.
            match ev {
                Event::Resize(..) => {
                    self.draw_reverse_search(stdout, &query, matched)?;
                    continue;
                }
                Event::Paste(_) => continue,
                _ => {}
            }

            let Event::Key(KeyEvent {
                code,
                modifiers,
                kind,
                ..
            }) = ev
            else {
                continue;
            };
            if kind == KeyEventKind::Release {
                continue;
            }

            match (code, modifiers) {
                // Cancel: restore the prior buffer.
                (KeyCode::Esc, _)
                | (KeyCode::Char('c' | 'g'), KeyModifiers::CONTROL) => {
                    // Buffer restore is handled by the caller (read_line_raw).
                    clear_reverse_search(stdout)?;
                    return Ok(ReverseSearchResult::Cancel);
                }

                // Accept the current match (or, if none, cancel without change).
                (KeyCode::Enter, _) => {
                    clear_reverse_search(stdout)?;
                    return match matched {
                        Some(idx) => {
                            Ok(ReverseSearchResult::Accept(self.history[idx].chars().collect()))
                        }
                        None => Ok(ReverseSearchResult::Cancel),
                    };
                }

                // Step to the next older match.
                (KeyCode::Char('r'), KeyModifiers::CONTROL) => {
                    if let Some(cur) = matched {
                        if cur > 0 {
                            if let Some(next) =
                                reverse_search_match(&self.history, &query, cur - 1)
                            {
                                matched = Some(next);
                            }
                        }
                    }
                    self.draw_reverse_search(stdout, &query, matched)?;
                }

                // Shrink the query.
                (KeyCode::Backspace, _) => {
                    query.pop();
                    matched = reverse_search_match(&self.history, &query, newest);
                    self.draw_reverse_search(stdout, &query, matched)?;
                }

                // Extend the query with a printable char (re-scan newest→oldest).
                (KeyCode::Char(c), mods)
                    if mods == KeyModifiers::NONE || mods == KeyModifiers::SHIFT =>
                {
                    query.push(c);
                    matched = reverse_search_match(&self.history, &query, newest);
                    self.draw_reverse_search(stdout, &query, matched)?;
                }

                // Ignore everything else (don't leak it to the outer loop).
                _ => continue,
            }
        }
    }

    /// Draw the single reverse-search prompt line in place: clear from column 0
    /// downward, print the `reverse-i-search` prompt + current match, then park
    /// the cursor at column 0 of that same line (we never leave the search line
    /// during the submode, so a one-line render is self-consistent).
    fn draw_reverse_search(
        &self,
        stdout: &mut io::Stdout,
        query: &[char],
        matched: Option<usize>,
    ) -> io::Result<()> {
        let query_str: String = query.iter().collect();
        let match_str = matched.map_or("", |idx| self.history[idx].as_str());
        let prefix = format!("(reverse-i-search)`{query_str}': ");
        // Keep the whole search line to a SINGLE terminal row. A long history
        // match (or a long query) would otherwise wrap, after which the
        // submode's "park cursor at one row" bookkeeping — and the caller's
        // `render.cursor_row = 0` — would misanchor the next redraw. Clip by
        // DISPLAY CELLS (CJK/wide-char aware), budget `width-1` so a wide char
        // landing exactly at the right edge can't push to the next row.
        let width = terminal_width().saturating_sub(1);
        let prefix_w = visible_len(&prefix);
        let (prefix_out, match_out) = if prefix_w >= width {
            (clip_cells(&prefix, width), String::new())
        } else {
            (prefix, clip_cells(match_str, width - prefix_w))
        };
        stdout.queue(cursor::MoveToColumn(0))?;
        stdout.queue(terminal::Clear(ClearType::FromCursorDown))?;
        stdout.queue(SetForegroundColor(Color::DarkGrey))?;
        stdout.queue(Print(prefix_out))?;
        stdout.queue(ResetColor)?;
        stdout.queue(Print(match_out))?;
        stdout.queue(cursor::MoveToColumn(0))?;
        stdout.flush()
    }

    fn compute_matches(&self, line: &str) -> Vec<usize> {
        if !line.starts_with('/') {
            return Vec::new();
        }
        self.completions
            .iter()
            .enumerate()
            .filter(|(_, (name, _))| name.starts_with(line))
            .map(|(i, _)| i)
            .take(MAX_DROPDOWN)
            .collect()
    }

    /// Full redraw: clears from current line down, draws prompt+buffer+dropdown,
    /// then moves cursor back to input line at the right column.
    fn redraw(
        &self,
        stdout: &mut io::Stdout,
        render: &mut RenderState,
        buf: &[char],
        cursor_pos: usize,
        sel: usize,
        suppressed: bool,
    ) -> io::Result<()> {
        let line: String = buf.iter().collect();
        // v0.4.20 (#8): honor Esc-suppression here too — previously `redraw`
        // unconditionally recomputed matches, so it painted the dismissed
        // dropdown right back after Esc.
        let matches = if suppressed {
            Vec::new()
        } else {
            self.compute_matches(&line)
        };
        let prompt_len = visible_len(&self.prompt);
        let term_w = terminal_width();
        let input_rows = layout_rows(prompt_len, buf, term_w);
        let (cursor_row, cursor_col) = layout_position(prompt_len, buf, cursor_pos, term_w);

        // Jump back to the start of the previously drawn input area (handles
        // multi-row wrap) and clear everything that was drawn last time.
        move_to_input_start(stdout, render, term_w)?;
        stdout.queue(terminal::Clear(ClearType::FromCursorDown))?;

        // Draw prompt + input buffer
        stdout.queue(Print(&self.prompt))?;
        stdout.queue(Print(&line))?;

        // Draw dropdown if there are matches
        let dropdown_rows: u16 = if !matches.is_empty() {
            let max_name = matches
                .iter()
                .map(|&i| self.completions[i].0.len())
                .max()
                .unwrap_or(0);
            let name_col = max_name.max(15).min(36) + 2;
            let desc_max = term_w.saturating_sub(name_col + 2).min(80);

            // Separator line
            stdout.queue(Print("\r\n"))?;
            stdout.queue(SetForegroundColor(Color::DarkGrey))?;
            stdout.queue(Print(" ".repeat(term_w.min(120))))?;
            stdout.queue(ResetColor)?;

            let mut rows: u16 = 1;

            for (row_idx, &comp_idx) in matches.iter().enumerate() {
                let (name, desc) = &self.completions[comp_idx];
                let is_sel = row_idx == sel;

                stdout.queue(Print("\r\n"))?;
                rows += 1;

                if is_sel {
                    // Selected: bold blue name + bright yellow desc
                    stdout.queue(Print(format!(
                        "\x1b[1;34m{name:<width$}\x1b[0m",
                        width = name_col
                    )))?;
                    if !desc.is_empty() {
                        let d = clip(desc, desc_max);
                        stdout.queue(Print(format!("  \x1b[1;33m{d}\x1b[0m")))?;
                    }
                } else {
                    // Normal: plain blue name + dim yellow desc
                    stdout.queue(SetForegroundColor(Color::Blue))?;
                    stdout.queue(Print(format!("{name:<width$}", width = name_col)))?;
                    stdout.queue(ResetColor)?;
                    if !desc.is_empty() {
                        let d = clip(desc, desc_max);
                        stdout.queue(SetForegroundColor(Color::DarkYellow))?;
                        stdout.queue(Print(format!("  {d}")))?;
                        stdout.queue(ResetColor)?;
                    }
                }
            }

            rows
        } else {
            0
        };

        // Move cursor back to the logical cursor position inside the input
        // area, accounting for both input wrap rows and dropdown rows below.
        move_to_input_cursor(stdout, input_rows, dropdown_rows, cursor_row, cursor_col)?;
        render.cursor_row = cursor_row;
        stdout.flush()
    }

    /// Clear from start of input line downward (erases dropdown too).
    fn clear_and_restore(
        &self,
        stdout: &mut io::Stdout,
        render: &mut RenderState,
        buf: &[char],
        cursor_pos: usize,
    ) -> io::Result<()> {
        let line: String = buf.iter().collect();
        let prompt_len = visible_len(&self.prompt);
        let term_w = terminal_width();
        let input_rows = layout_rows(prompt_len, buf, term_w);
        let (cursor_row, cursor_col) = layout_position(prompt_len, buf, cursor_pos, term_w);

        move_to_input_start(stdout, render, term_w)?;
        stdout.queue(terminal::Clear(ClearType::FromCursorDown))?;
        stdout.queue(Print(&self.prompt))?;
        stdout.queue(Print(&line))?;
        move_to_input_cursor(stdout, input_rows, 0, cursor_row, cursor_col)?;
        render.cursor_row = cursor_row;
        stdout.flush()
    }

    /// Print accepted text and clear dropdown before returning.
    fn accept_and_clear(
        &self,
        stdout: &mut io::Stdout,
        render: &mut RenderState,
        accepted: &str,
    ) -> io::Result<()> {
        let term_w = terminal_width();
        move_to_input_start(stdout, render, term_w)?;
        stdout.queue(terminal::Clear(ClearType::FromCursorDown))?;
        stdout.queue(Print(&self.prompt))?;
        stdout.queue(Print(accepted))?;
        let accepted_chars: Vec<char> = accepted.chars().collect();
        let (cursor_row, _) = layout_position(
            visible_len(&self.prompt),
            &accepted_chars,
            accepted_chars.len(),
            term_w,
        );
        render.cursor_row = cursor_row;
        stdout.flush()
    }

    fn read_line_fallback(&self) -> io::Result<ReadOutcome> {
        let mut stdout = io::stdout();
        write!(stdout, "{}", self.prompt)?;
        stdout.flush()?;

        let mut buffer = String::new();
        let bytes_read = io::stdin().read_line(&mut buffer)?;
        if bytes_read == 0 {
            return Ok(ReadOutcome::Exit);
        }
        while matches!(buffer.chars().last(), Some('\n' | '\r')) {
            buffer.pop();
        }
        Ok(ReadOutcome::Submit(buffer))
    }
}

/// Flatten a pasted block for a single-line editor.
///
/// `\r\n` / `\r` / `\n` / `\t` and other control characters all become a
/// single space so paste doesn't accidentally submit (newline) or break the
/// single-row redraw model.
fn normalize_paste_text(text: &str) -> Vec<char> {
    let mut out = Vec::with_capacity(text.chars().count());
    let mut chars = text.chars().peekable();
    while let Some(ch) = chars.next() {
        match ch {
            '\r' => {
                if matches!(chars.peek(), Some('\n')) {
                    chars.next();
                }
                out.push(' ');
            }
            '\n' | '\t' => out.push(' '),
            ch if ch.is_control() => out.push(' '),
            ch => out.push(ch),
        }
    }
    out
}

// ── Multi-line redraw helpers ────────────────────────────────────────────────

fn terminal_width() -> usize {
    terminal::size()
        .map(|(w, _)| usize::from(w.max(1)))
        .unwrap_or(120)
}

/// Move the cursor to the physical row/column where the input area starts,
/// based on where the cursor was last drawn. Required to correctly clear a
/// buffer that wrapped across multiple rows on the previous redraw.
fn move_to_input_start(
    stdout: &mut io::Stdout,
    render: &RenderState,
    _term_w: usize,
) -> io::Result<()> {
    if render.cursor_row > 0 {
        stdout.queue(cursor::MoveToPreviousLine(render.cursor_row))?;
    }
    stdout.queue(cursor::MoveToColumn(0))?;
    Ok(())
}

/// After drawing the prompt+buffer (cursor naturally at the end of input,
/// followed by `dropdown_rows` extra rows below), move the cursor back to the
/// logical (row, col) position within the input area.
fn move_to_input_cursor(
    stdout: &mut io::Stdout,
    input_rows: u16,
    dropdown_rows: u16,
    cursor_row: u16,
    cursor_col: u16,
) -> io::Result<()> {
    let lines_after_cursor = input_rows
        .saturating_sub(1)
        .saturating_sub(cursor_row)
        .saturating_add(dropdown_rows);
    if lines_after_cursor > 0 {
        stdout.queue(cursor::MoveToPreviousLine(lines_after_cursor))?;
    }
    stdout.queue(cursor::MoveToColumn(cursor_col))?;
    Ok(())
}

/// Total physical rows occupied by prompt + buffer at the given terminal
/// width, simulating actual terminal cell layout (handles wide CJK chars
/// that pre-wrap at the right edge).
fn layout_rows(prompt_width: usize, buf: &[char], term_w: usize) -> u16 {
    let (row, _) = layout_position(prompt_width, buf, buf.len(), term_w);
    row.saturating_add(1)
}

/// Compute (row, col) for the cursor positioned after the first `pos`
/// chars of `buf`, when prompt of width `prompt_width` precedes the buffer.
///
/// Models terminal behavior precisely:
/// - ASCII chars take 1 cell; CJK / wide chars take 2 cells (per `char_width`).
/// - If a wide char would land partially past the right edge, the terminal
///   pre-wraps to the next row before drawing it (so cursor never lands
///   inside a wide-char cell).
/// - After filling the last cell of a row, the cursor stays at (row, term_w-1)
///   with a pending-wrap flag — terminals don't physically advance to the
///   next row until the next char is drawn.
fn layout_position(prompt_width: usize, buf: &[char], pos: usize, term_w: usize) -> (u16, u16) {
    let term_w = term_w.max(1);
    let mut row = 0usize;
    let mut col = 0usize;
    let mut pending_wrap = false;

    for _ in 0..prompt_width {
        advance_layout(&mut row, &mut col, &mut pending_wrap, 1, term_w);
    }
    for &ch in &buf[..pos.min(buf.len())] {
        advance_layout(
            &mut row,
            &mut col,
            &mut pending_wrap,
            char_width(ch),
            term_w,
        );
    }

    (
        row.min(u16::MAX as usize) as u16,
        col.min(u16::MAX as usize) as u16,
    )
}

/// Advance a (row, col) cursor by `width` cells, respecting terminal pre-wrap
/// behavior for wide chars and pending-wrap at row boundaries.
fn advance_layout(
    row: &mut usize,
    col: &mut usize,
    pending_wrap: &mut bool,
    width: usize,
    term_w: usize,
) {
    let width = width.min(term_w);
    if width == 0 {
        return;
    }
    if *pending_wrap {
        *row = row.saturating_add(1);
        *col = 0;
        *pending_wrap = false;
    }
    if width > 1 && *col + width > term_w {
        *row = row.saturating_add(1);
        *col = 0;
    }
    *col += width;
    if *col == term_w {
        if width > 1 {
            *row = row.saturating_add(1);
            *col = 0;
        } else {
            *col = term_w - 1;
            *pending_wrap = true;
        }
    }
}

/// Deprecated: kept for any external/test reference. Use `layout_position`.
#[cfg(test)]
fn display_position(display_width: usize, term_w: usize) -> (u16, u16) {
    let term_w = term_w.max(1);
    if display_width == 0 {
        return (0, 0);
    }
    let row = (display_width - 1) / term_w;
    let col = if display_width % term_w == 0 {
        term_w - 1
    } else {
        display_width % term_w
    };
    (
        row.min(u16::MAX as usize) as u16,
        col.min(u16::MAX as usize) as u16,
    )
}

// ── Interactive select menu ──────────────────────────────────────────────────

/// An item in the select menu.
pub struct SelectItem {
    pub label: String,
    pub description: String,
    pub is_current: bool,
}

/// Show an interactive select menu. Returns the index of the selected item,
/// or `None` if the user pressed Esc.
pub fn select_menu(title: &str, subtitle: &str, items: &[SelectItem]) -> io::Result<Option<usize>> {
    if !io::stdin().is_terminal() || !io::stdout().is_terminal() {
        return Ok(None);
    }

    // Start with current item selected, or 0
    let mut sel: usize = items.iter().position(|item| item.is_current).unwrap_or(0);

    terminal::enable_raw_mode()?;

    // Drain any leftover key events (e.g. Enter release from the line editor)
    while event::poll(std::time::Duration::from_millis(50))? {
        let _ = event::read()?;
    }

    let result = select_menu_raw(title, subtitle, items, &mut sel);
    terminal::disable_raw_mode()?;

    // Clear the menu area
    let mut stdout = io::stdout();
    writeln!(stdout)?;
    stdout.flush()?;

    result
}

fn select_menu_raw(
    title: &str,
    subtitle: &str,
    items: &[SelectItem],
    sel: &mut usize,
) -> io::Result<Option<usize>> {
    let mut stdout = io::stdout();
    draw_select_menu(&mut stdout, title, subtitle, items, *sel)?;

    loop {
        let ev = event::read()?;
        let Event::Key(KeyEvent { code, kind, .. }) = ev else {
            if let Event::Resize(..) = ev {
                draw_select_menu(&mut stdout, title, subtitle, items, *sel)?;
            }
            continue;
        };
        if kind == KeyEventKind::Release {
            continue;
        }

        match code {
            KeyCode::Up | KeyCode::Char('k') => {
                if *sel > 0 {
                    *sel -= 1;
                }
            }
            KeyCode::Down | KeyCode::Char('j') => {
                if *sel + 1 < items.len() {
                    *sel += 1;
                }
            }
            KeyCode::Enter => {
                clear_select_menu(&mut stdout, title, subtitle, items)?;
                return Ok(Some(*sel));
            }
            KeyCode::Esc | KeyCode::Char('q') => {
                clear_select_menu(&mut stdout, title, subtitle, items)?;
                return Ok(None);
            }
            _ => continue,
        }

        draw_select_menu(&mut stdout, title, subtitle, items, *sel)?;
    }
}

fn draw_select_menu(
    stdout: &mut io::Stdout,
    title: &str,
    subtitle: &str,
    items: &[SelectItem],
    sel: usize,
) -> io::Result<()> {
    stdout.queue(cursor::MoveToColumn(0))?;
    stdout.queue(terminal::Clear(ClearType::FromCursorDown))?;

    // Title
    stdout.queue(Print(format!("\x1b[1m{title}\x1b[0m")))?;
    stdout.queue(Print("\r\n"))?;
    stdout.queue(SetForegroundColor(Color::DarkGrey))?;
    stdout.queue(Print(subtitle))?;
    stdout.queue(ResetColor)?;
    stdout.queue(Print("\r\n\r\n"))?;

    // Compute column width for labels
    let max_label = items.iter().map(|i| i.label.len()).max().unwrap_or(10);
    let label_col = max_label.max(12) + 4;

    for (idx, item) in items.iter().enumerate() {
        let is_sel = idx == sel;
        let marker = if item.is_current { " ✔" } else { "" };

        if is_sel {
            stdout.queue(Print(format!(
                "\x1b[1;34m❯ {}. {:<width$}\x1b[0m",
                idx + 1,
                format!("{}{marker}", item.label),
                width = label_col,
            )))?;
            if !item.description.is_empty() {
                stdout.queue(SetForegroundColor(Color::DarkGrey))?;
                stdout.queue(Print(&item.description))?;
                stdout.queue(ResetColor)?;
            }
        } else {
            stdout.queue(Print(format!(
                "  {}. {:<width$}",
                idx + 1,
                format!("{}{marker}", item.label),
                width = label_col,
            )))?;
            if !item.description.is_empty() {
                stdout.queue(SetForegroundColor(Color::DarkGrey))?;
                stdout.queue(Print(&item.description))?;
                stdout.queue(ResetColor)?;
            }
        }
        stdout.queue(Print("\r\n"))?;
    }

    stdout.queue(Print("\r\n"))?;
    stdout.queue(SetForegroundColor(Color::DarkGrey))?;
    stdout.queue(Print("Enter to confirm · Esc to exit"))?;
    stdout.queue(ResetColor)?;

    // Move cursor back to top of menu
    let total_lines = items.len() as u16 + 4; // title + subtitle + blank + items + footer
    stdout.queue(cursor::MoveToPreviousLine(total_lines))?;

    stdout.flush()
}

fn clear_select_menu(
    stdout: &mut io::Stdout,
    _title: &str,
    _subtitle: &str,
    _items: &[SelectItem],
) -> io::Result<()> {
    stdout.queue(cursor::MoveToColumn(0))?;
    stdout.queue(terminal::Clear(ClearType::FromCursorDown))?;
    stdout.flush()
}

/// Count display width, stripping ANSI escape sequences.
/// CJK and wide characters count as 2 columns.
fn visible_len(s: &str) -> usize {
    let mut count = 0;
    let mut in_escape = false;
    for ch in s.chars() {
        if in_escape {
            if ch.is_ascii_alphabetic() {
                in_escape = false;
            }
        } else if ch == '\x1b' {
            in_escape = true;
        } else {
            count += char_width(ch);
        }
    }
    count
}

/// Display width of a character in terminal columns.
// v0.4.20 (#6): pub(crate) so the markdown table renderer (render.rs) can use
// the same CJK/fullwidth display-cell width for column alignment.
pub(crate) fn char_width(ch: char) -> usize {
    let cp = ch as u32;
    // CJK Unified Ideographs and common wide ranges
    if (0x1100..=0x115F).contains(&cp)    // Hangul Jamo
        || (0x2E80..=0x303E).contains(&cp)  // CJK Radicals, Kangxi, CJK Symbols
        || (0x3040..=0x33BF).contains(&cp)  // Hiragana, Katakana, Bopomofo, CJK Compat
        || (0x3400..=0x4DBF).contains(&cp)  // CJK Extension A
        || (0x4E00..=0x9FFF).contains(&cp)  // CJK Unified Ideographs
        || (0xA000..=0xA4CF).contains(&cp)  // Yi
        || (0xAC00..=0xD7AF).contains(&cp)  // Hangul Syllables
        || (0xF900..=0xFAFF).contains(&cp)  // CJK Compat Ideographs
        || (0xFE30..=0xFE6F).contains(&cp)  // CJK Compat Forms
        || (0xFF01..=0xFF60).contains(&cp)  // Fullwidth Forms
        || (0xFFE0..=0xFFE6).contains(&cp)  // Fullwidth Signs
        || (0x20000..=0x2FA1F).contains(&cp) // CJK Extensions B-F
        || (0x30000..=0x3134F).contains(&cp)
    // CJK Extension G
    {
        2
    } else {
        1
    }
}

fn clip(s: &str, max: usize) -> String {
    if s.len() <= max {
        return s.to_string();
    }
    // Truncate by chars, not bytes, to avoid splitting multi-byte UTF-8
    let truncated: String = s.chars().take(max.saturating_sub(1)).collect();
    format!("{truncated}…")
}

/// Truncate `s` to at most `max_cells` **display columns** (CJK/wide-char
/// aware via [`char_width`]), appending an ellipsis `…` when truncated. Unlike
/// [`clip`] (which counts chars), this counts display cells, so a run of wide
/// characters cannot overflow a fixed-width line — required by the Ctrl+R
/// search prompt to stay a single terminal row (codex Phase-1 fix). Assumes
/// `s` has no ANSI escapes (the search prompt builds plain text).
fn clip_cells(s: &str, max_cells: usize) -> String {
    if max_cells == 0 {
        return String::new();
    }
    let total: usize = s.chars().map(char_width).sum();
    if total <= max_cells {
        return s.to_string();
    }
    // Reserve one cell for the ellipsis.
    let budget = max_cells.saturating_sub(1);
    let mut out = String::new();
    let mut used = 0usize;
    for ch in s.chars() {
        let w = char_width(ch);
        if used + w > budget {
            break;
        }
        out.push(ch);
        used += w;
    }
    out.push('…');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_editor() -> LineEditor {
        LineEditor::new(
            "> ",
            vec![
                ("/help".to_string(), "Show help".to_string()),
                ("/research-review".to_string(), "Deep review".to_string()),
                ("/research-lit".to_string(), "Literature search".to_string()),
                ("/status".to_string(), "Session status".to_string()),
            ],
        )
    }

    #[test]
    fn matches_slash_prefix() {
        let ed = make_editor();
        let m = ed.compute_matches("/res");
        assert_eq!(m.len(), 2);
        assert!(m.iter().any(|&i| ed.completions[i].0 == "/research-review"));
        assert!(m.iter().any(|&i| ed.completions[i].0 == "/research-lit"));
    }

    #[test]
    fn no_matches_for_plain_text() {
        let ed = make_editor();
        assert!(ed.compute_matches("hello").is_empty());
        assert!(ed.compute_matches("").is_empty());
    }

    #[test]
    fn exact_match_returns_one() {
        let ed = make_editor();
        let m = ed.compute_matches("/help");
        assert_eq!(m.len(), 1);
        assert_eq!(ed.completions[m[0]].0, "/help");
    }

    #[test]
    fn clip_truncates_long_strings() {
        assert_eq!(clip("hello world", 5), "hell…");
        assert_eq!(clip("short", 10), "short");
    }

    #[test]
    fn clip_cells_truncates_by_display_width() {
        // ASCII (1 cell each): same as clip.
        assert_eq!(clip_cells("hello", 10), "hello");
        assert_eq!(clip_cells("hello world", 5), "hell…");
        // Wide CJK chars are 2 cells each: "中文" fits exactly in 4.
        assert_eq!(clip_cells("中文", 4), "中文");
        assert_eq!(clip_cells("中文字", 3), "中…");
        // The load-bearing property: a run of wide chars must NEVER exceed the
        // budget in DISPLAY cells (clip(), counting chars, would fail this).
        let wide = "一二三四五"; // 5 chars = 10 cells
        let out = clip_cells(wide, 5);
        let cells: usize = out.chars().map(char_width).sum();
        assert!(cells <= 5, "clipped display width {cells} must be <= 5");
        // Zero budget → empty.
        assert_eq!(clip_cells("x", 0), "");
    }

    #[test]
    fn layout_position_handles_cjk_non_boundary() {
        let mut buf = vec!['a'; 100];
        buf.push('你');
        assert_eq!(super::layout_position(0, &buf, buf.len(), 120), (0, 102));
        buf.push('是');
        assert_eq!(super::layout_position(0, &buf, buf.len(), 120), (0, 104));
    }

    #[test]
    fn layout_position_keeps_cursor_out_of_wide_char_at_wrap_boundary() {
        // 118 ASCII chars fill cols 0..117 on row 0. Wide char at col 118
        // would need cols 118..119; that exactly fits, takes both cells,
        // col reaches term_w → wide char triggers row += 1, col = 0.
        // Cursor lands at (1, 0).
        let mut ends_at_boundary = vec!['a'; 118];
        ends_at_boundary.push('是');
        assert_eq!(
            super::layout_position(0, &ends_at_boundary, ends_at_boundary.len(), 120),
            (1, 0)
        );
        assert_eq!(super::layout_rows(0, &ends_at_boundary, 120), 2);

        // 119 ASCII chars: cols 0..118 ASCII, col 119 = last ASCII char,
        // col reaches term_w → pending_wrap = true. Wide char sees
        // pending_wrap → jumps to (1, 0), takes cols 0..1, cursor (1, 2).
        let mut wraps_before_wide = vec!['a'; 119];
        wraps_before_wide.push('谁');
        assert_eq!(
            super::layout_position(0, &wraps_before_wide, wraps_before_wide.len(), 120),
            (1, 2)
        );
    }

    #[test]
    fn normalize_paste_text_flattens_newlines_and_tabs() {
        let normalized: String =
            super::normalize_paste_text("one\ntwo\r\nthree\rfour\tfive\x01end")
                .into_iter()
                .collect();
        assert_eq!(normalized, "one two three four five end");
    }

    #[test]
    fn push_history_ignores_blank() {
        let mut ed = make_editor();
        ed.push_history("   ");
        ed.push_history("/help");
        assert_eq!(ed.history.len(), 1);
    }

    // === v0.4.16 Phase 0 characterization: lock the IN-MEMORY push_history
    // contract. Track A adds a disk-append to push_history; these pin that the
    // in-memory Vec semantics (used by Up/Down navigation) stay byte-identical.

    #[test]
    fn push_history_stores_raw_untrimmed_content() {
        // Current behaviour: the blank CHECK trims, but a non-blank entry is
        // stored verbatim (surrounding whitespace preserved). The REPL pushes
        // the raw Submit(input) string (main.rs:1170), so history holds raw
        // content. Track A's secret-skip / disk write must not alter this.
        let mut ed = make_editor();
        ed.push_history("  hello world  ");
        assert_eq!(ed.history.len(), 1);
        assert_eq!(ed.history[0], "  hello world  ");
    }

    #[test]
    fn push_history_does_not_dedup() {
        // Current behaviour: no de-duplication. Pushing the same entry twice
        // keeps two copies. (Persistence must preserve this; bash-style dedup
        // would be a behaviour change, out of scope for v0.4.16.)
        let mut ed = make_editor();
        ed.push_history("/status");
        ed.push_history("/status");
        assert_eq!(ed.history.len(), 2);
    }

    // === v0.4.16 Track A: reverse_search match-selection logic (pure, no TTY).
    // The terminal-rendering side (prompt draw/erase + cursor parking) is
    // exercised only by the manual TTY smoke test in Phase 3.

    fn hist(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    fn chars(s: &str) -> Vec<char> {
        s.chars().collect()
    }

    #[test]
    fn reverse_search_empty_query_picks_newest_at_anchor() {
        let h = hist(&["alpha", "beta", "gamma"]);
        // Empty query, anchor at newest (idx 2) → newest entry.
        assert_eq!(super::reverse_search_match(&h, &[], 2), Some(2));
        // Anchor lower → that entry.
        assert_eq!(super::reverse_search_match(&h, &[], 1), Some(1));
    }

    #[test]
    fn reverse_search_finds_newest_match_first() {
        let h = hist(&["run tests", "fix bug", "run server", "deploy"]);
        // Query "run", anchor at newest → newest matching = idx 2 ("run server").
        let q = chars("run");
        assert_eq!(super::reverse_search_match(&h, &q, h.len() - 1), Some(2));
        // Step older from idx 1 → idx 0 ("run tests").
        assert_eq!(super::reverse_search_match(&h, &q, 1), Some(0));
    }

    #[test]
    fn reverse_search_is_case_insensitive() {
        let h = hist(&["Hello World", "FOO"]);
        assert_eq!(super::reverse_search_match(&h, &chars("hello"), 1), Some(0));
        assert_eq!(super::reverse_search_match(&h, &chars("foo"), 1), Some(1));
    }

    #[test]
    fn reverse_search_handles_cjk_substring() {
        let h = hist(&["请帮我写代码", "explain this"]);
        // CJK substring match is char-based, not byte-based.
        assert_eq!(super::reverse_search_match(&h, &chars("写代码"), 1), Some(0));
        assert_eq!(super::reverse_search_match(&h, &chars("没有"), 1), None);
    }

    #[test]
    fn reverse_search_no_match_returns_none() {
        let h = hist(&["alpha", "beta"]);
        assert_eq!(super::reverse_search_match(&h, &chars("zzz"), 1), None);
    }

    #[test]
    fn reverse_search_empty_history_returns_none() {
        let h: Vec<String> = Vec::new();
        assert_eq!(super::reverse_search_match(&h, &chars("x"), 0), None);
        assert_eq!(super::reverse_search_match(&h, &[], 0), None);
    }

    #[test]
    fn reverse_search_clamps_out_of_range_anchor() {
        let h = hist(&["one", "two"]);
        // Anchor past the end is clamped to the last index.
        assert_eq!(super::reverse_search_match(&h, &[], 99), Some(1));
        assert_eq!(super::reverse_search_match(&h, &chars("one"), 99), Some(0));
    }

    #[test]
    fn reverse_search_result_accept_loads_entry() {
        // Mirror the caller mapping: Accept(entry) → buf = entry.
        let entry: Vec<char> = chars("/research-review");
        let result = super::ReverseSearchResult::Accept(entry.clone());
        match result {
            super::ReverseSearchResult::Accept(e) => assert_eq!(e, entry),
            super::ReverseSearchResult::Cancel => panic!("expected Accept"),
        }
    }

    #[test]
    fn push_history_is_oldest_first() {
        // Current behaviour: chronological order, index 0 = oldest, last =
        // newest. Up-arrow walks backward from the end (input.rs:212-228), so
        // this ordering is load-bearing. The persistence file format is
        // oldest-first specifically to reproduce this on reload.
        let mut ed = make_editor();
        ed.push_history("first");
        ed.push_history("second");
        ed.push_history("third");
        assert_eq!(ed.history, vec!["first", "second", "third"]);
    }

    /// v0.4.17 A5.4 — slash commands now enter the in-memory history
    /// (deliberately flipped in v0.4.17 (A5.4): slash commands now enter
    /// history per maintainer decision 2026-06-05). The v0.4.16 REPL
    /// `continue`d past `push_history` for slash input — a call-site-only
    /// contract with no explicit test. This locks the new positive contract:
    /// a slash entry is stored like any other, lands NEWEST (so a single
    /// Up-arrow recalls it), and is recallable via reverse search (Ctrl+R).
    #[test]
    fn slash_commands_enter_in_memory_history() {
        let mut ed = make_editor();
        ed.push_history("explain tokenization");
        ed.push_history("/status");
        assert_eq!(ed.history, vec!["explain tokenization", "/status"]);
        // Up-arrow walks backward from the end: newest entry (the slash
        // command) is recalled first.
        assert_eq!(ed.history.last().map(String::as_str), Some("/status"));
        // Ctrl+R can find it too.
        let q: Vec<char> = "/sta".chars().collect();
        assert_eq!(
            super::reverse_search_match(&ed.history, &q, ed.history.len() - 1),
            Some(1)
        );
    }

    // ── v0.4.25 (#430): Windows paste-burst merge ────────────────────────────

    fn key(code: KeyCode, modifiers: KeyModifiers) -> Event {
        Event::Key(KeyEvent::new(code, modifiers))
    }

    /// The shape Windows delivers for a pasted block: one key record per
    /// character, `\n` as Enter, `\t` as Tab (no `Event::Paste` ever).
    fn windows_paste_events(text: &str) -> Vec<Event> {
        text.chars()
            .map(|c| match c {
                '\n' => key(KeyCode::Enter, KeyModifiers::NONE),
                '\t' => key(KeyCode::Tab, KeyModifiers::NONE),
                c if c.is_uppercase() => key(KeyCode::Char(c), KeyModifiers::SHIFT),
                c => key(KeyCode::Char(c), KeyModifiers::NONE),
            })
            .collect()
    }

    #[test]
    fn merge_paste_burst_folds_newlines_and_tabs_to_spaces() {
        let merged = super::merge_paste_burst(&windows_paste_events("b\nc\tD"));
        assert_eq!(merged.inserted, chars("b c D"));
        assert!(merged.leftover.is_empty());
    }

    #[test]
    fn merge_paste_burst_matches_normalize_paste_text() {
        // The Windows path and the bracketed-paste path agree on the text.
        let text = "one\ntwo\tthree\nfour";
        let merged = super::merge_paste_burst(&windows_paste_events(text));
        assert_eq!(merged.inserted, super::normalize_paste_text(text));
    }

    #[test]
    fn merge_paste_burst_stops_at_control_keys_and_keeps_the_rest_in_order() {
        let mut events = windows_paste_events("ab\n");
        events.push(key(KeyCode::Char('c'), KeyModifiers::CONTROL));
        events.extend(windows_paste_events("cd\n"));
        let merged = super::merge_paste_burst(&events);
        assert_eq!(merged.inserted, chars("ab "));
        assert_eq!(merged.leftover.len(), 4);
        assert_eq!(merged.leftover[0], key(KeyCode::Char('c'), KeyModifiers::CONTROL));
        assert_eq!(merged.leftover[3], key(KeyCode::Enter, KeyModifiers::NONE));

        // arrows, Backspace, Esc and a real Paste event end the burst too
        for stop in [
            key(KeyCode::Left, KeyModifiers::NONE),
            key(KeyCode::Backspace, KeyModifiers::NONE),
            key(KeyCode::Esc, KeyModifiers::NONE),
            Event::Paste("x".to_string()),
        ] {
            let mut events = windows_paste_events("q");
            events.push(stop.clone());
            let merged = super::merge_paste_burst(&events);
            assert_eq!(merged.inserted, chars("q"));
            assert_eq!(merged.leftover, vec![stop]);
        }
    }

    #[test]
    fn merge_paste_burst_skips_release_resize_and_focus_events() {
        let mut events = vec![Event::Key(KeyEvent::new_with_kind(
            KeyCode::Enter,
            KeyModifiers::NONE,
            KeyEventKind::Release,
        ))];
        events.extend(windows_paste_events("a"));
        events.push(Event::Resize(80, 24));
        events.push(Event::FocusLost);
        events.extend(windows_paste_events("b"));
        let merged = super::merge_paste_burst(&events);
        assert_eq!(merged.inserted, chars("ab"));
        assert!(merged.leftover.is_empty());

        // an Enter followed only by its release is NOT a burst: nothing to
        // insert, so the caller submits normally
        let only_release = vec![Event::Key(KeyEvent::new_with_kind(
            KeyCode::Enter,
            KeyModifiers::NONE,
            KeyEventKind::Release,
        ))];
        assert_eq!(super::merge_paste_burst(&only_release), super::BurstMerge::default());
    }

    #[test]
    fn paste_burst_is_windows_only_and_honours_the_kill_switch() {
        assert!(super::paste_burst_enabled_from(None));
        assert!(super::paste_burst_enabled_from(Some("1")));
        assert!(!super::paste_burst_enabled_from(Some("0")));
        assert!(!super::paste_burst_enabled_from(Some(" 0 ")));
        assert!(super::paste_burst_collection_active(true, None));
        assert!(!super::paste_burst_collection_active(true, Some("0")));
        // Unix keeps bracketed paste; the heuristic never runs there
        assert!(!super::paste_burst_collection_active(false, None));
    }

    #[test]
    fn enter_decision_cancels_before_it_ever_submits() {
        use super::{enter_decision, merge_paste_burst, EnterDecision};
        // Ctrl+C is the FIRST thing queued behind the Enter → cancel now,
        // never "submit, then exit later from a saved Ctrl+C".
        let merged = merge_paste_burst(&[key(KeyCode::Char('c'), KeyModifiers::CONTROL)]);
        assert_eq!(enter_decision(false, &merged), EnterDecision::CancelInput);
        let merged = merge_paste_burst(&[key(KeyCode::Char('d'), KeyModifiers::CONTROL)]);
        assert_eq!(enter_decision(false, &merged), EnterDecision::ExitEditor);
        // pasted text then Ctrl+C: nothing is submitted — the burst is
        // discarded with the line and the editor cancels immediately
        let mut events = windows_paste_events("ab\n");
        events.push(key(KeyCode::Char('c'), KeyModifiers::CONTROL));
        let merged = merge_paste_burst(&events);
        assert_eq!(enter_decision(false, &merged), EnterDecision::CancelInput);
        // an edit key behind the Enter keeps the editor active
        let merged = merge_paste_burst(&[key(KeyCode::Left, KeyModifiers::NONE)]);
        assert_eq!(enter_decision(false, &merged), EnterDecision::InsertAsNewline);
        // pasted lines → insert; an Enter replayed from a burst → insert
        let merged = merge_paste_burst(&windows_paste_events("second line"));
        assert_eq!(enter_decision(false, &merged), EnterDecision::InsertAsNewline);
        assert_eq!(enter_decision(true, &super::BurstMerge::default()), EnterDecision::InsertAsNewline);
        // nothing (or only releases) behind the Enter → a plain submit
        assert_eq!(enter_decision(false, &super::BurstMerge::default()), EnterDecision::Submit);
    }

    #[test]
    fn pending_events_are_consumed_before_the_os_queue() {
        let mut ed = super::LineEditor::new("> ", Vec::new());
        ed.pending.push_back(key(KeyCode::Char('z'), KeyModifiers::NONE));
        let (ev, from_pending) = ed.next_event().unwrap();
        assert!(from_pending);
        assert_eq!(ev, key(KeyCode::Char('z'), KeyModifiers::NONE));
        ed.pending.push_back(key(KeyCode::Char('y'), KeyModifiers::NONE));
        ed.clear_pending();
        assert!(ed.pending.is_empty());
    }
}
