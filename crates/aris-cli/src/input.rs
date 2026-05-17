use std::io::{self, IsTerminal, Write};

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

pub struct LineEditor {
    prompt: String,
    completions: Vec<(String, String)>,
    history: Vec<String>,
}

impl LineEditor {
    #[must_use]
    pub fn new(prompt: impl Into<String>, completions: Vec<(String, String)>) -> Self {
        Self {
            prompt: prompt.into(),
            completions,
            history: Vec::new(),
        }
    }

    pub fn push_history(&mut self, entry: impl Into<String>) {
        let entry = entry.into();
        if !entry.trim().is_empty() {
            self.history.push(entry);
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
        let mut render = RenderState::default();

        self.redraw(&mut stdout, &mut render, &buf, cursor_pos, sel)?;

        loop {
            let ev = event::read()?;

            // Handle terminal resize
            if let Event::Resize(..) = ev {
                self.redraw(&mut stdout, &mut render, &buf, cursor_pos, sel)?;
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
                    self.redraw(&mut stdout, &mut render, &buf, cursor_pos, sel)?;
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
            let matches = self.compute_matches(&line);

            match (code, modifiers) {
                // ── Exit / Cancel ──────────────────────────────────────────
                (KeyCode::Char('c'), KeyModifiers::CONTROL) => {
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
                    if !matches.is_empty() {
                        let (name, _) = &self.completions[matches[sel]];
                        let result = name.clone();
                        self.accept_and_clear(&mut stdout, &mut render, &result)?;
                        return Ok(ReadOutcome::Submit(result));
                    }
                    self.accept_and_clear(&mut stdout, &mut render, &line)?;
                    return Ok(ReadOutcome::Submit(line));
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
                    // Fall through to redraw with empty matches
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

            self.redraw(&mut stdout, &mut render, &buf, cursor_pos, sel)?;
        }
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
    ) -> io::Result<()> {
        let line: String = buf.iter().collect();
        let matches = self.compute_matches(&line);
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
fn char_width(ch: char) -> usize {
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
}
