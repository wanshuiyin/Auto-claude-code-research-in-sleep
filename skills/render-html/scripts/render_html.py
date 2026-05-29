#!/usr/bin/env python3
"""render_html.py — convert ARIS Markdown / JSON artifacts to single-file HTML.

Pure-stdlib Python. No external pip deps.

Usage:
    render_html.py <input.md> [--template academic|dashboard]
                              [--out <output.html>]
                              [--title "..."] [--subtitle "..."]
                              [--eyebrow "..."]
                              [--state <state.json>]
                              [--json <sidecar.json>]
                              [--offline]
                              [--no-toc]

See skills/render-html/SKILL.md for the full contract.

Design invariants (see codex review consultation in commit message):
  - Markdown / JSON is canonical source, HTML is generated view.
  - HTML embeds source path + SHA256 + generated timestamp (drift detection).
  - Single-file output. MathJax + highlight.js loaded from CDN unless --offline.
  - Pure stdlib: re, html, hashlib, json, datetime, pathlib, argparse, sys.
  - Conservative Markdown subset matching what ARIS artifacts actually emit.
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# ---------------------------------------------------------------------------
# Inline parsing
# ---------------------------------------------------------------------------

# Placeholders used to protect inline content during multi-pass rewriting.
# Two non-printable PUA chars + index to avoid collisions with real content.
_PH_OPEN = ""
_PH_CLOSE = ""


def _ph(idx: int) -> str:
    return f"{_PH_OPEN}{idx}{_PH_CLOSE}"


_RE_CODE_INLINE = re.compile(r"`([^`\n]+)`")
_RE_MATH_DISPLAY = re.compile(r"\$\$([^\n][\s\S]*?)\$\$")
_RE_MATH_INLINE = re.compile(r"(?<!\\)\$([^\$\n]+?)\$")
_RE_IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
_RE_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
_RE_BOLD = re.compile(r"\*\*([^\*\n]+)\*\*")
_RE_ITALIC = re.compile(r"(?<!\*)\*([^\*\n]+)\*(?!\*)")
_RE_ITALIC_UNDERSCORE = re.compile(r"(?<!\w)_([^_\n]+)_(?!\w)")
_RE_STRIKE = re.compile(r"~~([^~\n]+)~~")
# Wikilink paper reference: [[key]] or [[key|display]]. Backslash-escaped form
# `\[[...]]` is left alone so authors can opt out.
_RE_PAPER_REF = re.compile(
    r"(?<!\\)\[\[([A-Za-z0-9][A-Za-z0-9_.:-]*)(?:\|([^\]\n]+))?\]\]"
)

# Inline HTML tags that should pass through inline (commonly used in ARIS docs).
_INLINE_HTML_TAGS = ("br", "img", "a", "span", "sub", "sup", "code", "kbd", "b", "i", "u", "strong", "em")

# URL schemes considered safe for href/src. javascript:, data:, vbscript: blocked.
_SAFE_URL_SCHEMES = ("http:", "https:", "mailto:", "ftp:", "tel:", "#", "/", "./", "../")


def _safe_url(url: str) -> str:
    """Return url if scheme is safe, else '#'. Defensive against javascript: links."""
    s = url.strip().lower()
    # Relative paths and fragments are fine
    if s.startswith(("#", "/", "./", "../")) or s == "":
        return url
    if s.startswith(_SAFE_URL_SCHEMES):
        return url
    # Bare path like "foo/bar.md" or "page.html" — no scheme prefix, safe.
    if ":" not in s.split("/", 1)[0]:
        return url
    # Block javascript:, data:, vbscript:, file:, etc.
    return "#blocked-unsafe-url"


# Tags stripped wholesale from HTML passthrough (block and inline).
# Even if the workflow LLM hallucinates these, they never reach output.
_RE_STRIP_TAG = re.compile(
    r"<\s*(script|style|iframe|object|embed|form|input|button|link|meta|base)\b[^>]*>.*?</\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_RE_STRIP_TAG_SELF = re.compile(
    r"<\s*(script|style|iframe|object|embed|form|input|button|link|meta|base)\b[^>]*/?\s*>",
    re.IGNORECASE,
)
# Event-handler attributes like onclick=, onload=, etc. — strip these.
_RE_STRIP_EVENT_ATTR = re.compile(
    r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)
# javascript:/vbscript:/data: in href/src — replace with #blocked.
_RE_STRIP_DANGEROUS_URL_ATTR = re.compile(
    r"""(\b(?:href|src|action|formaction|poster)\s*=\s*["']?)\s*(?:javascript|vbscript|data)\s*:""",
    re.IGNORECASE,
)


def sanitize_html(s: str) -> str:
    """Strip dangerous tags / event handlers / javascript: URLs from raw HTML.

    Applied to: (a) inline-HTML spans we pass through, (b) block-HTML
    passthrough content. Markdown text content is HTML-escaped separately
    and never reaches this function. ARIS workflow artifacts should not
    contain these tags; this is defense-in-depth in case an LLM hallucinates
    one.
    """
    s = _RE_STRIP_TAG.sub("", s)
    s = _RE_STRIP_TAG_SELF.sub("", s)
    s = _RE_STRIP_EVENT_ATTR.sub("", s)
    s = _RE_STRIP_DANGEROUS_URL_ATTR.sub(r"\1#blocked-unsafe-url:", s)
    return s


def render_inline(text: str) -> str:
    """Convert Markdown inline syntax to HTML. Escape everything else.

    Order matters:
      1. Stash inline code, math (display+inline), and raw HTML tag-shaped
         spans into placeholders (so we don't expand markdown inside them).
      2. HTML-escape the remaining text.
      3. Apply images, links, bold, italic, strike.
      4. Restore placeholders.
    """
    stash: list[str] = []

    def store(replacement: str) -> str:
        idx = len(stash)
        stash.append(replacement)
        return _ph(idx)

    # 1a. Inline code -- escape inner content fully.
    def _code_sub(m: re.Match[str]) -> str:
        return store(f"<code>{html_lib.escape(m.group(1))}</code>")

    text = _RE_CODE_INLINE.sub(_code_sub, text)

    # 1b. Display math (passthrough; MathJax will render).
    def _md_sub(m: re.Match[str]) -> str:
        body = m.group(1)
        return store(f"$${body}$$")

    text = _RE_MATH_DISPLAY.sub(_md_sub, text)

    # 1c. Inline math (passthrough).
    def _mi_sub(m: re.Match[str]) -> str:
        body = m.group(1)
        return store(f"${body}$")

    text = _RE_MATH_INLINE.sub(_mi_sub, text)

    # 1d. Wikilink paper refs [[key]] or [[key|display]] — stash as a clickable
    # span with data-ref="key". The template JS wires up the popover from
    # window.PAPER_REGISTRY (sidecar JSON loaded via --papers). Default display
    # is the key uppercased; explicit display via |label form.
    def _ref_sub(m: re.Match[str]) -> str:
        key = m.group(1)
        display = m.group(2) if m.group(2) is not None else key.upper()
        return store(
            f'<span data-ref="{html_lib.escape(key, quote=True)}">{html_lib.escape(display)}</span>'
        )

    text = _RE_PAPER_REF.sub(_ref_sub, text)

    # 1e. Inline HTML spans (very limited allowlist + sanitize before stash).
    _re_tag = re.compile(
        r"<(/?)(" + "|".join(_INLINE_HTML_TAGS) + r")(\s[^<>]*)?>",
        re.IGNORECASE,
    )

    def _tag_sub(m: re.Match[str]) -> str:
        return store(sanitize_html(m.group(0)))

    text = _re_tag.sub(_tag_sub, text)

    # 2. HTML-escape remainder.
    text = html_lib.escape(text, quote=False)

    # 3. Apply markdown emphasis & links.
    def _img_sub(m: re.Match[str]) -> str:
        alt = html_lib.escape(m.group(1), quote=True)
        src = html_lib.escape(_safe_url(m.group(2)), quote=True)
        title = m.group(3)
        title_attr = f' title="{html_lib.escape(title, quote=True)}"' if title else ""
        return f'<img src="{src}" alt="{alt}"{title_attr} />'

    text = _RE_IMG.sub(_img_sub, text)

    def _link_sub(m: re.Match[str]) -> str:
        label = m.group(1)  # inner label can still contain code placeholders; ok.
        href = html_lib.escape(_safe_url(m.group(2)), quote=True)
        title = m.group(3)
        title_attr = f' title="{html_lib.escape(title, quote=True)}"' if title else ""
        return f'<a href="{href}"{title_attr}>{label}</a>'

    text = _RE_LINK.sub(_link_sub, text)
    text = _RE_BOLD.sub(r"<strong>\1</strong>", text)
    text = _RE_ITALIC.sub(r"<em>\1</em>", text)
    text = _RE_ITALIC_UNDERSCORE.sub(r"<em>\1</em>", text)
    text = _RE_STRIKE.sub(r"<del>\1</del>", text)

    # 4. Restore placeholders.
    def _restore(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        return stash[idx]

    text = re.sub(rf"{_PH_OPEN}(\d+){_PH_CLOSE}", _restore, text)
    return text


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------

_RE_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_RE_HR = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_RE_CODE_FENCE = re.compile(
    r"^```\s*(?:(?P<lang>[A-Za-z0-9_+.#-]+)\s*)?(?:\{(?P<flags>[^}\n]+)\}\s*)?$"
)
_RE_TABLE_DIVIDER = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
_RE_ORDERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_RE_UNORDERED = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_RE_BLOCKQUOTE = re.compile(r"^>\s?(.*)$")
_RE_HTML_BLOCK_OPEN = re.compile(
    r"^\s*<(details|div|figure|table|p|ul|ol|nav|section|aside|header|footer|main|article|blockquote)(\s|>|/>)",
    re.IGNORECASE,
)

_CALLOUT_PREFIX_MAP = [
    # (regex on first content, css class, default title)
    (re.compile(r"^[⚠️⚠]️?\s*"), "callout-warn", "Warning"),
    (re.compile(r"^💡\s*"), "callout-info", "Tip"),
    (re.compile(r"^✅\s*"), "callout-good", "OK"),
    (re.compile(r"^✓\s*"), "callout-good", "OK"),
    (re.compile(r"^❌\s*"), "callout-bad", "Blocked"),
    (re.compile(r"^🔒\s*"), "callout-good", "Guarantee"),
    (re.compile(r"^📝\s*"), "callout-info", "Note"),
    (re.compile(r"^🚨\s*"), "callout-bad", "Critical"),
    (re.compile(r"^🛠\s*"), "callout-info", "Note"),
    (re.compile(r"^🆕\s*"), "callout-info", "New"),
    (re.compile(r"^⚙️⚡?\s*"), "callout-info", "Config"),
    (re.compile(r"^🔁\s*"), "callout-info", "Loop"),
    (re.compile(r"^🌱\s*"), "callout-info", "Note"),
    (re.compile(r"^📚\s*"), "callout-info", "Reference"),
    (re.compile(r"^🧬\s*"), "callout-info", "Meta"),
]


def _slugify(text: str) -> str:
    text = re.sub(r"[`*_~$]", "", text)
    text = re.sub(r"\s+", "-", text.strip().lower())
    text = re.sub(r"[^a-z0-9一-鿿\-]", "", text)
    return text.strip("-") or "section"


def parse_blocks(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.rstrip()

        # Blank line — skip.
        if not stripped.strip():
            i += 1
            continue

        # Code fence.
        m = _RE_CODE_FENCE.match(stripped)
        if m:
            lang = (m.group("lang") or "").strip()
            flags_raw = (m.group("flags") or "").strip()
            flags: set[str] = set()
            if flags_raw:
                for tok in flags_raw.split(","):
                    tok = tok.strip()
                    if tok:
                        flags.add(tok)
            body: list[str] = []
            i += 1
            while i < n and not _RE_CODE_FENCE.match(lines[i].rstrip()):
                body.append(lines[i])
                i += 1
            if i < n:  # consume closing fence
                i += 1
            blocks.append({
                "type": "code",
                "lang": lang,
                "content": "\n".join(body),
                "flags": flags,
            })
            continue

        # ATX heading.
        m = _RE_HEADING.match(stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            blocks.append({"type": "heading", "level": level, "text": text})
            i += 1
            continue

        # Horizontal rule.
        if _RE_HR.match(stripped):
            blocks.append({"type": "hr"})
            i += 1
            continue

        # Table: current line has at least one `|`, AND next line is a divider.
        if "|" in stripped and i + 1 < n and _RE_TABLE_DIVIDER.match(lines[i + 1].rstrip()):
            header = stripped
            divider = lines[i + 1].rstrip()
            rows: list[str] = []
            j = i + 2
            while j < n and "|" in lines[j] and lines[j].strip():
                rows.append(lines[j].rstrip())
                j += 1
            blocks.append({"type": "table", "header": header, "divider": divider, "rows": rows})
            i = j
            continue

        # HTML block — passthrough until the closing tag is reached. Per
        # CommonMark §4.6 (loosely): treat the block as ending on the first
        # line that *starts* with the matching </tag>. We track depth only
        # for opening/closing tags that appear at line start (after optional
        # whitespace), so inline mentions like `<details>` inside backticks
        # in a paragraph don't perturb the counter.
        if _RE_HTML_BLOCK_OPEN.match(line):
            tag_m = _RE_HTML_BLOCK_OPEN.match(line)
            assert tag_m is not None
            tag = tag_m.group(1).lower()
            line_open_re = re.compile(rf"^\s*<{re.escape(tag)}(?=[\s/>])", re.IGNORECASE)
            line_close_re = re.compile(rf"^\s*</{re.escape(tag)}(?=[\s>])", re.IGNORECASE)
            body = [line]
            depth = 1
            # Self-closing tag on the same line: <tag .../>
            if re.search(rf"<{re.escape(tag)}\b[^>]*/\s*>", line, re.IGNORECASE):
                depth = 0
            # Same-line full close: <tag>...</tag> or </tag> on same line as open
            elif re.search(rf"</{re.escape(tag)}(?=[\s>])", line, re.IGNORECASE):
                depth = 0
            i += 1
            while i < n and depth > 0:
                cur = lines[i]
                body.append(cur)
                # Count nested opens/closes at line start only.
                if line_open_re.match(cur):
                    depth += 1
                if line_close_re.match(cur):
                    depth -= 1
                i += 1
            content = "\n".join(body)
            # Sanitize: strip dangerous tags / event handlers / unsafe URL schemes.
            content = sanitize_html(content)
            blocks.append({"type": "html", "content": content})
            continue

        # Blockquote.
        if _RE_BLOCKQUOTE.match(stripped):
            quote_lines: list[str] = []
            while i < n:
                m_bq = _RE_BLOCKQUOTE.match(lines[i].rstrip())
                if not m_bq:
                    break
                quote_lines.append(m_bq.group(1))
                i += 1
            blocks.append({"type": "blockquote", "lines": quote_lines})
            continue

        # Ordered or unordered list. Indent-aware: a marker at the same
        # indent as the first item starts a sibling; a marker at deeper
        # indent (or any deeper-indented continuation line) becomes part
        # of the current item's content and is re-parsed recursively in
        # render_list (so nested lists / paragraphs / code blocks work).
        if _RE_ORDERED.match(stripped) or _RE_UNORDERED.match(stripped):
            first_m = _RE_ORDERED.match(lines[i]) or _RE_UNORDERED.match(lines[i])
            base_indent = len(first_m.group(1))
            ordered = bool(_RE_ORDERED.match(lines[i]))
            items: list[str] = []
            current: list[str] = []
            while i < n:
                cur_line = lines[i]
                # Blank line — peek ahead to decide if list continues.
                if cur_line.strip() == "":
                    if i + 1 < n:
                        nxt = lines[i + 1]
                        m_o_next = _RE_ORDERED.match(nxt)
                        m_u_next = _RE_UNORDERED.match(nxt)
                        if (m_o_next or m_u_next) and len(
                            (m_o_next or m_u_next).group(1)
                        ) >= base_indent:
                            # Continue list; consume blank.
                            current.append("")
                            i += 1
                            continue
                        if nxt.startswith(" " * (base_indent + 2)) or nxt.startswith("\t"):
                            current.append("")
                            i += 1
                            continue
                    break
                m_o = _RE_ORDERED.match(cur_line)
                m_u = _RE_UNORDERED.match(cur_line)
                if m_o or m_u:
                    marker_indent = len((m_o or m_u).group(1))
                    if marker_indent == base_indent:
                        # Sibling item at same level.
                        if current:
                            items.append("\n".join(current).rstrip())
                            current = []
                        current.append((m_o or m_u).group(3 if m_o else 2))
                        i += 1
                        continue
                    if marker_indent > base_indent:
                        # Nested item — append the line with reduced indent
                        # (strip base_indent + 2 spaces so the nested parse
                        # sees the marker at column 0 of its own context).
                        strip = base_indent + 2
                        current.append(
                            cur_line[strip:] if cur_line[:strip].strip() == "" else cur_line.lstrip()
                        )
                        i += 1
                        continue
                    # Marker at shallower indent — list ends here.
                    break
                # Non-marker line: continuation of current item if indented
                # past base_indent + 2 (or any indent for the "lazy continuation"
                # convention).
                if cur_line.startswith(" " * (base_indent + 2)) or cur_line.startswith("\t"):
                    strip = base_indent + 2
                    current.append(
                        cur_line[strip:] if cur_line[:strip].strip() == "" else cur_line.lstrip()
                    )
                    i += 1
                    continue
                # Anything else at base_indent or shallower → list ends.
                break
            if current:
                items.append("\n".join(current).rstrip())
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue

        # Paragraph: gather lines until blank or block boundary.
        para: list[str] = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].rstrip()
            if not nxt.strip():
                break
            if (_RE_HEADING.match(nxt) or _RE_CODE_FENCE.match(nxt) or _RE_HR.match(nxt) or
                _RE_BLOCKQUOTE.match(nxt) or _RE_ORDERED.match(nxt) or
                _RE_UNORDERED.match(nxt) or _RE_HTML_BLOCK_OPEN.match(lines[i]) or
                ("|" in nxt and i + 1 < n and _RE_TABLE_DIVIDER.match(lines[i + 1].rstrip()))):
                break
            para.append(nxt)
            i += 1
        blocks.append({"type": "paragraph", "text": " ".join(para)})
    return blocks


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------


def render_table(header: str, divider: str, rows: list[str]) -> str:
    def split_row(s: str) -> list[str]:
        s = s.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    header_cells = split_row(header)
    align = []
    for cell in split_row(divider):
        cell = cell.strip()
        if cell.startswith(":") and cell.endswith(":"):
            align.append("center")
        elif cell.endswith(":"):
            align.append("right")
        else:
            align.append("left")

    def cell_attr(idx: int) -> str:
        if idx < len(align) and align[idx] != "left":
            return f' style="text-align:{align[idx]}"'
        return ""

    out: list[str] = ["<table>", "<thead><tr>"]
    for idx, cell in enumerate(header_cells):
        out.append(f"<th{cell_attr(idx)}>{render_inline(cell)}</th>")
    out.append("</tr></thead>")
    out.append("<tbody>")
    for row in rows:
        out.append("<tr>")
        for idx, cell in enumerate(split_row(row)):
            out.append(f"<td{cell_attr(idx)}>{render_inline(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def render_blockquote(quote_lines: list[str]) -> str:
    """Detect callout style (emoji prefix) and render with callout class."""
    if not quote_lines:
        return "<blockquote></blockquote>"
    first = quote_lines[0]
    css_class = None
    title = None
    body_lines = list(quote_lines)
    # Try matching callout prefix on the first non-empty line.
    first_nonempty_idx = 0
    while first_nonempty_idx < len(body_lines) and not body_lines[first_nonempty_idx].strip():
        first_nonempty_idx += 1
    if first_nonempty_idx < len(body_lines):
        line0 = body_lines[first_nonempty_idx].lstrip()
        for pattern, klass, default_title in _CALLOUT_PREFIX_MAP:
            m = pattern.match(line0)
            if m:
                css_class = klass
                title = default_title
                # Strip emoji + try to extract a **Bold:** title prefix.
                rest = pattern.sub("", line0, count=1)
                m_title = re.match(r"\*\*([^*\n]+?)\*\*[:：\s\-—]+\s*", rest)
                if m_title:
                    title = m_title.group(1)
                    rest = rest[m_title.end():]
                body_lines[first_nonempty_idx] = rest
                break

    inner_md = "\n".join(body_lines).strip("\n")
    inner_blocks = parse_blocks(inner_md.split("\n")) if inner_md else []
    inner_html, _ = _render_blocks(inner_blocks, collect_toc=False)
    if css_class:
        title_html = f'<div class="callout-title">{html_lib.escape(title or "")}</div>' if title else ""
        return f'<div class="callout {css_class}">{title_html}{inner_html}</div>'
    return f"<blockquote>{inner_html}</blockquote>"


def render_list(ordered: bool, items: list[str]) -> str:
    tag = "ol" if ordered else "ul"
    out = [f"<{tag}>"]
    for item in items:
        # Nested lists are possible — parse the item body as blocks.
        item_blocks = parse_blocks(item.split("\n"))
        # Common case: single paragraph — emit inline directly.
        if len(item_blocks) == 1 and item_blocks[0]["type"] == "paragraph":
            out.append(f"<li>{render_inline(item_blocks[0]['text'])}</li>")
        else:
            inner, _ = _render_blocks(item_blocks, collect_toc=False)
            out.append(f"<li>{inner}</li>")
    out.append(f"</{tag}>")
    return "".join(out)


def render_code(lang: str, content: str, flags: set | None = None) -> str:
    escaped = html_lib.escape(content)
    # Per-block override for the auto-collapse JS in the template:
    #   ```python {collapsed}  → force fold
    #   ```python {open}       → force expanded
    # Anything else leaves the decision to the auto-threshold (default 30 lines).
    attr = ""
    if flags:
        if "collapsed" in flags:
            attr = ' data-collapse="collapsed"'
        elif "open" in flags:
            attr = ' data-collapse="open"'
    if lang:
        return f'<pre{attr}><code class="language-{html_lib.escape(lang, quote=True)}">{escaped}</code></pre>'
    # Heuristic: if content looks like an ASCII art diagram (mostly box-drawing
    # chars and pipes), tag the surrounding <pre> with class="diagram".
    diagram_chars = set("│─┌┐└┘├┤┬┴┼▲▼◀▶━┃┏┓┗┛╭╮╰╯═║╔╗╚╝╠╣╦╩╬║▶▼─")
    sample = content[:200]
    if sample and sum(1 for c in sample if c in diagram_chars) >= 4:
        return f'<pre{attr} class="diagram"><code>{escaped}</code></pre>'
    return f"<pre{attr}><code>{escaped}</code></pre>"


def _render_blocks(
    blocks: list[dict],
    collect_toc: bool,
    used_ids: dict | None = None,
) -> tuple[str, list[dict]]:
    if used_ids is None:
        used_ids = {}
    out: list[str] = []
    toc: list[dict] = []
    for b in blocks:
        t = b["type"]
        if t == "heading":
            level = b["level"]
            text = b["text"]
            inline = render_inline(text)
            base_id = _slugify(text)
            uid = base_id
            n = used_ids.get(base_id, 0)
            if n > 0:
                uid = f"{base_id}-{n}"
            used_ids[base_id] = n + 1
            out.append(f'<h{level} id="{uid}">{inline}</h{level}>')
            if collect_toc and 2 <= level <= 3:
                toc.append({"level": level, "id": uid, "text": text})
        elif t == "paragraph":
            out.append(f"<p>{render_inline(b['text'])}</p>")
        elif t == "hr":
            out.append("<hr />")
        elif t == "code":
            out.append(render_code(b.get("lang", ""), b["content"], b.get("flags")))
        elif t == "blockquote":
            out.append(render_blockquote(b["lines"]))
        elif t == "list":
            out.append(render_list(b["ordered"], b["items"]))
        elif t == "table":
            out.append(render_table(b["header"], b["divider"], b["rows"]))
        elif t == "html":
            out.append(_render_html_block(b["content"]))
        else:
            out.append(f"<!-- unknown block: {html_lib.escape(t)} -->")
    return "\n".join(out), toc


def _render_html_block(content: str) -> str:
    """For <details>...</details> blocks, parse the inner content as Markdown.

    Matches GitHub-flavored convention: when a `<details>` block has a blank
    line separating its `<summary>` from the body, the body is parsed as
    markdown (lists, headings, code, callouts all work). For non-<details>
    HTML blocks, content passes through verbatim.
    """
    lines = content.split("\n")
    if not lines or not lines[0].lstrip().lower().startswith("<details"):
        return content
    # Locate opening boundary: after </summary> if present, else after the
    # <details> line itself.
    open_end = 1  # default: just past the <details> line
    summary_close_re = re.compile(r"</summary\s*>", re.IGNORECASE)
    for j in range(1, len(lines)):
        if summary_close_re.search(lines[j]):
            open_end = j + 1
            break
        # If we hit non-summary content first, no `<summary>` block; stop scanning.
        if lines[j].strip() and not re.match(r"\s*<summary", lines[j], re.IGNORECASE):
            break
    # Locate closing boundary: the last </details> line.
    close_start = len(lines) - 1
    close_re = re.compile(r"^\s*</details\s*>", re.IGNORECASE)
    while close_start > 0 and not close_re.match(lines[close_start]):
        close_start -= 1
    if open_end >= close_start:
        # Degenerate or empty body; emit raw.
        return content
    open_part = "\n".join(lines[:open_end])
    inner_md = "\n".join(lines[open_end:close_start]).strip("\n")
    close_part = "\n".join(lines[close_start:])
    if not inner_md.strip():
        return content
    inner_blocks = parse_blocks(inner_md.split("\n"))
    inner_html, _ = _render_blocks(inner_blocks, collect_toc=False)
    return f"{open_part}\n{inner_html}\n{close_part}"


def render_toc(toc: list[dict]) -> str:
    """Render a nested TOC. Groups consecutive H3s under their preceding H2.

    Orphan H3 (H3 without a preceding H2 in this run) is promoted to a
    top-level <li>. Output is well-formed `<ol><li>...<ul><li>...</li></ul>...</li></ol>`.
    """
    if not toc:
        return ""
    grouped: list[tuple[dict, list[dict]]] = []  # [(h2_entry, [h3_children])]
    current_parent: dict | None = None
    current_children: list[dict] = []
    for entry in toc:
        if entry["level"] == 2:
            if current_parent is not None:
                grouped.append((current_parent, current_children))
            current_parent = entry
            current_children = []
        elif entry["level"] == 3:
            if current_parent is None:
                # Orphan H3 — promote to top level so the TOC stays well-formed.
                grouped.append((entry, []))
            else:
                current_children.append(entry)
    if current_parent is not None:
        grouped.append((current_parent, current_children))

    out: list[str] = ["<ol>"]
    for parent, children in grouped:
        pid = html_lib.escape(parent["id"], quote=True)
        ptext = html_lib.escape(parent["text"])
        out.append(f'<li><a href="#{pid}">{ptext}</a>')
        if children:
            out.append("<ul>")
            for c in children:
                cid = html_lib.escape(c["id"], quote=True)
                ctext = html_lib.escape(c["text"])
                out.append(f'<li><a href="#{cid}">{ctext}</a></li>')
            out.append("</ul>")
        out.append("</li>")
    out.append("</ol>")
    return "\n".join(out)


def strip_frontmatter(md: str) -> str:
    """Strip leading YAML frontmatter (--- ... ---) if present at start.

    Also strips a leading UTF-8 BOM so frontmatter detection still fires
    on files saved by editors that prepend it.
    """
    md = md.lstrip("﻿")
    lines = md.split("\n", 1)
    if not lines or lines[0].strip() != "---":
        return md
    # find closing ---
    rest = lines[1] if len(lines) > 1 else ""
    parts = rest.split("\n---\n", 1)
    if len(parts) == 2:
        return parts[1].lstrip("\n")
    # try also \n--- at the very end of a line
    parts = rest.split("\n---", 1)
    if len(parts) == 2 and (parts[1] == "" or parts[1].startswith("\n")):
        return parts[1].lstrip("\n")
    return md


# ---------------------------------------------------------------------------
# Template loading + main
# ---------------------------------------------------------------------------

CDN_BLOCK_FULL = """<!-- MathJax 3 -->
<script>
window.MathJax = {
  tex: { inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']], processEscapes: true },
  options: { skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'] }
};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>

<!-- highlight.js -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/atom-one-light.min.css">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
<script>document.addEventListener('DOMContentLoaded', () => hljs.highlightAll());</script>
"""

CDN_BLOCK_OFFLINE = "<!-- offline mode: MathJax + highlight.js skipped; math and code blocks render as plain text -->"


def load_template(name: str) -> str:
    path = TEMPLATES_DIR / f"{name}.html"
    if not path.exists():
        raise SystemExit(
            f"error: template '{name}' not found at {path}. "
            f"Available: {[p.stem for p in TEMPLATES_DIR.glob('*.html')]}"
        )
    return path.read_text(encoding="utf-8")


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_json_as_pre(json_path: Path) -> str:
    """Render a sidecar JSON file as a collapsed <details> block of pretty-printed JSON."""
    try:
        obj = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return f'<div class="callout callout-bad"><div class="callout-title">JSON parse error</div><p>{html_lib.escape(str(e))}</p></div>'
    pretty = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
    return (
        f'<details><summary>Sidecar JSON: <code>{html_lib.escape(str(json_path))}</code></summary>'
        f'<pre><code class="language-json">{html_lib.escape(pretty)}</code></pre>'
        f'</details>'
    )


def substitute(template: str, vars: dict) -> str:
    out = template
    for k, v in vars.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def json_for_script(obj: object) -> str:
    """Serialize JSON for direct embedding inside a classic <script> block.

    json.dumps() alone is unsafe because a string value containing '</script>'
    will break out of the host <script> tag. Escape <, >, & and line/paragraph
    separators as \\uXXXX so the result is always safe inside a <script>.
    """
    return (
        json.dumps(obj, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def _repo_relative(input_path: Path) -> str:
    """Return a display-friendly repo-relative path. Avoids leaking absolute
    /Users/<name>/... in the generated HTML meta + footer.

    Order: cwd-relative if input is under cwd; else git-root-relative if in
    a git repo; else basename only (parent dirs stripped) so we never
    surface the home directory.
    """
    try:
        return str(input_path.relative_to(Path.cwd()))
    except ValueError:
        pass
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=input_path.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            git_root = Path(result.stdout.strip())
            try:
                return str(input_path.relative_to(git_root))
            except ValueError:
                pass
    except Exception:
        pass
    return input_path.name


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Render an ARIS Markdown artifact to single-file HTML.",
    )
    ap.add_argument("input", help="Path to input .md (or .json — wrapped in a <pre>)")
    ap.add_argument("--template", default="academic", choices=["academic", "dashboard"])
    ap.add_argument("--out", help="Output HTML path (default: <input>.html)")
    ap.add_argument("--title", help="Page title (default: first H1, or filename)")
    ap.add_argument("--subtitle", default="", help="Optional italic subtitle line")
    ap.add_argument("--eyebrow", default="", help="Optional uppercase eyebrow above H1")
    ap.add_argument("--author", default="", help="Optional author byline (e.g., 'Name (姓名), Affiliation')")
    ap.add_argument("--lang", default="zh-CN", help='<html lang="…"> attribute (default zh-CN)')
    ap.add_argument("--state", help="Optional sidecar state JSON to append as <details>")
    ap.add_argument("--json", dest="json_sidecar", help="Optional sidecar JSON to append (e.g., KILL_ARGUMENT.json)")
    ap.add_argument("--offline", action="store_true", help="Skip MathJax / highlight.js CDN blocks")
    ap.add_argument("--no-toc", action="store_true", help="Skip TOC sidebar (forces TOC_LABEL/TOC_HTML to empty)")
    ap.add_argument(
        "--papers",
        help="Sidecar JSON file with paper registry for [[key]] popovers. "
             "Schema: {key: {title, authors, date, inst, key, arxiv}, ...}",
    )
    ap.add_argument(
        "--blog-mode",
        action="store_true",
        help="Enable blog/talk mode (adds .aris-blog body class, opt-in active-H2 highlighting)",
    )
    ap.add_argument(
        "--collapse-code-min",
        type=int,
        default=30,
        help="Auto-collapse code blocks with >= N lines (default 30). Override per-block with ```lang {open}/{collapsed}.",
    )
    args = ap.parse_args(argv)

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"error: input not found: {input_path}", file=sys.stderr)
        return 2
    display_source_path = _repo_relative(input_path)

    raw = input_path.read_text(encoding="utf-8")
    source_hash = sha256_of(raw)

    # If the input is JSON, wrap it as a single code block.
    is_json = input_path.suffix.lower() == ".json"
    if is_json:
        try:
            obj = json.loads(raw)
            pretty = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
        except json.JSONDecodeError:
            pretty = raw
        md_source = f"# {input_path.name}\n\n```json\n{pretty}\n```\n"
    else:
        md_source = strip_frontmatter(raw)

    blocks = parse_blocks(md_source.split("\n"))
    body_html, toc = _render_blocks(blocks, collect_toc=not args.no_toc)

    # Title autodetection.
    title = args.title
    if not title:
        # Look for first H1 block.
        for b in blocks:
            if b.get("type") == "heading" and b.get("level") == 1:
                title = b["text"]
                break
        if not title:
            title = input_path.stem.replace("_", " ").replace("-", " ").title()

    # Append sidecar JSON if requested.
    extra_html_blocks: list[str] = []
    for label, path_str in (("state", args.state), ("json", args.json_sidecar)):
        if path_str:
            p = Path(path_str).resolve()
            if p.exists():
                extra_html_blocks.append(f'<h2 id="sidecar-{label}">Sidecar — <code>{html_lib.escape(p.name)}</code></h2>')
                extra_html_blocks.append(render_json_as_pre(p))
            else:
                extra_html_blocks.append(
                    f'<div class="callout callout-warn"><div class="callout-title">Sidecar missing</div>'
                    f'<p><code>{html_lib.escape(path_str)}</code> not found.</p></div>'
                )

    body_html = body_html + ("\n" + "\n".join(extra_html_blocks) if extra_html_blocks else "")

    template_str = load_template(args.template)

    toc_html = render_toc(toc) if not args.no_toc else ""
    toc_label = "Contents" if not args.no_toc else ""
    if args.no_toc:
        # Hide TOC entirely by emitting an empty <nav> (template has <nav>, we'd
        # rather just leave structure intact; CSS won't visually break).
        toc_html = ""

    eyebrow_block = f'<div class="eyebrow">{html_lib.escape(args.eyebrow)}</div>' if args.eyebrow else ""
    subtitle_block = f'<p class="subtitle">{html_lib.escape(args.subtitle)}</p>' if args.subtitle else ""
    byline_block = (
        f'<p class="byline">By <strong>{html_lib.escape(args.author)}</strong></p>'
        if args.author else ""
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Paper registry sidecar (for [[key]] popovers). Validate as JSON before
    # embedding; on parse error, log a warning and emit "{}" so the template
    # still works (popover JS just no-ops when key is missing).
    papers_json = "{}"
    if args.papers:
        p = Path(args.papers).resolve()
        if p.exists():
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
                papers_json = json_for_script(obj)
            except json.JSONDecodeError as e:
                print(f"warning: --papers JSON parse error: {e}", file=sys.stderr)
        else:
            print(f"warning: --papers file not found: {p}", file=sys.stderr)

    vars_ = {
        "LANG": html_lib.escape(args.lang, quote=True),
        "TITLE": html_lib.escape(title),
        "SUBTITLE_BLOCK": subtitle_block,
        "EYEBROW_BLOCK": eyebrow_block,
        "BYLINE_BLOCK": byline_block,
        "SOURCE_PATH": html_lib.escape(display_source_path),
        "SOURCE_SHA256": source_hash,
        "SOURCE_SHA256_SHORT": source_hash[:12],
        "GENERATED_AT": generated_at,
        "HEAD_CDN": CDN_BLOCK_OFFLINE if args.offline else CDN_BLOCK_FULL,
        "TOC_HTML": toc_html,
        "TOC_LABEL": toc_label,
        "BODY_HTML": body_html,
        "EXTRA_META": "",
        "PAPER_REGISTRY_JSON": papers_json,
        "COLLAPSE_CODE_MIN": str(args.collapse_code_min),
        "BODY_CLASS": "aris-blog" if args.blog_mode else "",
    }

    rendered = substitute(template_str, vars_)

    out_path = Path(args.out).resolve() if args.out else input_path.with_suffix(".html")
    if out_path.is_dir():
        print(
            f"error: --out points to a directory: {out_path}. "
            f"Specify a file path ending in .html.",
            file=sys.stderr,
        )
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"wrote {out_path} ({len(rendered):,} bytes, {len(toc)} TOC entries, source sha256 {source_hash[:12]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
