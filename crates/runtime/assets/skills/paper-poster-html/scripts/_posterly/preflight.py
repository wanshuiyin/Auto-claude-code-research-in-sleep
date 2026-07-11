"""Static HTML lint — runs before any rendering.

Catches the classes of errors that would otherwise burn a render cycle:

- LaTeX residue (``\\ref{`` / ``\\cite{`` / ``\\textbf{`` / lone ``\\ ``).
- Raw ``<`` inside ``$…$`` / ``$$…$$`` / ``\\(…\\)`` / ``\\[…\\]`` —
  MathJax may HTML-parse it as a tag start depending on its loader mode.
- Local ``src="..."`` images that don't exist on disk.
- Missing or unknown ``data-measure-role`` values.
- Measure-role nesting: each role is checked against the templates'
  parent contract (e.g. ``card`` must sit inside a ``column``/``hero``,
  not directly under ``body``). A misplaced ``</div>`` that closes the
  body grid early would otherwise pass preflight + measure -- the body
  ``1fr`` row absorbs the lost children, and the gap-to-strip number
  goes off-canvas without surfacing the actual structural cause.

The line numbers reported by preflight refer to **the original HTML file**.
Earlier versions stripped ``<style>`` / ``<script>`` / ``<!-- … -->``
blocks with ``re.sub(... , "")``, which collapsed newlines and shifted
every subsequent line number by N. We now replace each stripped block
with the SAME NUMBER OF NEWLINES, so character offsets after the strip
still map to the same line in the original file.
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


# Roles understood by ``measure`` / ``polish``. Anything outside this
# set in a ``data-measure-role`` attribute is almost certainly a typo
# and would silently be ignored by the geometry pass.
KNOWN_ROLES: set[str] = {
    "poster", "header", "banner", "body",
    "column", "card", "hero", "footer-strip", "footer",
}


# Required parent role(s) for each measure role, derived from the three
# shipped templates (landscape_4col / landscape_hero / portrait_2col).
# Multiple entries mean "any of these is OK". Roles whose parent must be
# the document root (``poster``) are listed too. Empty tuple => no
# constraint (e.g. ``poster`` itself, which is the root).
#
# Background: a misplaced ``</div>`` was the precipitating bug for this
# gate. It closed ``.poster`` (the grid container) before its
# ``footer-strip`` and ``footer`` children appeared in source order, so
# those nodes ended up outside the grid. The browser tolerated it; the
# CSS ``grid-template-rows: auto auto 1fr auto auto`` collapsed two
# rows to 0 px without complaint; measure reported the strip top off-
# canvas. This rule turns that silent failure into a preflight error
# pointing at the role whose parent went wrong.
ROLE_PARENTS: dict[str, tuple[str, ...]] = {
    "header":       ("poster",),
    "banner":       ("poster",),
    "body":         ("poster",),
    # ``body`` is allowed for footer-strip/footer for the same reason
    # ``poster`` is allowed for column/hero below: a hand-rolled layout
    # may nest the strip inside the body container, and measure reads
    # the strip's rendered position regardless of where it sits. The
    # precipitating bug (strip escaping to the *document root* after a
    # stray ``</div>``) is still caught -- root has no role.
    "footer-strip": ("poster", "body"),
    "footer":       ("poster", "body"),
    # ``poster`` is allowed for column/hero because ``body`` was never
    # required by any gate -- a poster hanging its columns directly off
    # the root is valid today and measures fine.
    "column":       ("body", "poster"),
    "hero":         ("body", "poster"),
    "card":         ("column", "hero"),
}


# (regex, human description) pairs for LaTeX residue. The patterns are
# scanned over the body with style/script/comments stripped (newline-
# preserved), so each match's character offset still maps to the right
# line in the original file.
LATEX_PATTERNS: list[tuple[str, str]] = [
    (r"\\ref\{",        r"\\ref{...} residue"),
    (r"\\cite\{",       r"\\cite{...} residue"),
    (r"\\textbf\{",     r"\\textbf{...} residue (use <b> or **bold**)"),
    (r"\\textit\{",     r"\\textit{...} residue (use <i> or *italic*)"),
    (r"\\emph\{",       r"\\emph{...} residue"),
    (r"\\section\{",    r"\\section{...} residue"),
    (r"\\label\{",      r"\\label{...} residue"),
    (r"\\begin\{",      r"\\begin{...} residue (use HTML structures)"),
    (r"\\end\{",        r"\\end{...} residue"),
    (r"(?<![\\a-zA-Z])\\\s",
        r"backslash-space '\\ ' (will render literally)"),
]


from .textutil import ascii_safe


def _eprint(*args: Any, **kw: Any) -> None:
    print(*args, file=sys.stderr, **kw)


def _newline_preserving_sub(pattern: str, html: str, *,
                            flags: int = 0) -> str:
    """Replace each match with ``\\n`` * <newline-count-in-match>.

    This preserves line numbers across ``<style>`` / ``<script>`` /
    ``<!-- … -->`` blocks so a regex match's character offset in the
    stripped output still maps to the same line in the original file.
    """
    def keep_newlines(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")
    return re.sub(pattern, keep_newlines, html, flags=flags)


def strip_for_lint(html: str) -> str:
    """Remove ``<style>``, ``<script>``, and HTML comments while
    preserving newline counts. The output is what every preflight rule
    scans against.

    ONE document-order pass over all three so a construct nested inside
    another is consumed as a single unit by whichever delimiter opens
    FIRST. Stripping them in separate passes was a bug: a comment that
    contained ``<script>`` (e.g. ``<!-- ... change the <script> src -->``)
    had its closing ``-->`` eaten by the script pass, after which the
    comment pass ran past it and deleted real body markup downstream --
    the root ``<div data-measure-role="poster">`` went missing, so
    preflight false-failed "missing poster". The combined alternation
    also handles the reverse (a ``<style>``/``<script>`` body containing
    ``-->`` or ``<!--``): the tag opens first, so its whole body is taken
    before the comment rule can match inside it.
    """
    return _newline_preserving_sub(
        r"<!--.*?-->"
        r"|<style[^>]*>.*?</style>"
        r"|<script[^>]*>.*?</script>",
        html, flags=re.DOTALL | re.IGNORECASE,
    )


def find_math_segments(text: str) -> list[tuple[int, int, str]]:
    """Find inline + display math segments. Returns ``[(start, end, body)]``.

    Supports the four delimiter pairs every Claude-poster template
    configures MathJax for:

      - ``$$ … $$`` (display)
      - ``$ … $`` (inline; excludes already-covered ``$$`` regions)
      - ``\\[ … \\]`` (display)
      - ``\\( … \\)`` (inline)
    """
    out: list[tuple[int, int, str]] = []

    def add(s: int, e: int, body: str) -> None:
        out.append((s, e, body))

    # $$...$$
    for m in re.finditer(r"\$\$(.+?)\$\$", text, re.DOTALL):
        add(m.start(), m.end(), m.group(1))
    # \[...\]
    for m in re.finditer(r"\\\[(.+?)\\\]", text, re.DOTALL):
        add(m.start(), m.end(), m.group(1))

    covered = [(s, e) for s, e, _ in out]

    # $...$ — single-line only, not already inside a $$...$$
    for m in re.finditer(r"(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)", text):
        s, e = m.start(), m.end()
        if any(cs <= s < ce or cs < e <= ce for cs, ce in covered):
            continue
        add(s, e, m.group(1))
    # \(...\) — single-line only, not already inside a \[...\]
    for m in re.finditer(r"\\\(([^\n]+?)\\\)", text):
        s, e = m.start(), m.end()
        if any(cs <= s < ce or cs < e <= ce for cs, ce in covered):
            continue
        add(s, e, m.group(1))

    return out


def _delim_label(body: str, segment: str) -> str:
    """Try to label a math segment by its delimiter style in error
    output. ``segment`` is the raw matched text; we look at its first
    char(s)."""
    if segment.startswith("$$") and segment.endswith("$$"):
        return "$$...$$"
    if segment.startswith("$") and segment.endswith("$"):
        return "$...$"
    if segment.startswith("\\["):
        return "\\[...\\]"
    if segment.startswith("\\("):
        return "\\(...\\)"
    return "math"


# Tags that the HTML spec lists as void / self-closing -- they have no
# end tag and must never push onto the parser stack. Lower-cased; the
# parser hands us tag names already lowered. Includes the long-tail
# rare ones (``<keygen>``, ``<menuitem>``) the spec retains for parsers
# even if browsers no longer render them, so a poster importing legacy
# markup doesn't trip a false unbalance error.
_VOID_TAGS: frozenset[str] = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "keygen", "link", "menuitem", "meta", "param", "source",
    "track", "wbr",
})


class _RoleNestingChecker(HTMLParser):
    """Walk the HTML and record each ``data-measure-role`` element's
    nearest ancestor that itself carries a role.

    Why a stack-based scanner and not a regex pass: the bug we want to
    catch is a misplaced ``</div>`` that closes ``.poster`` early, so a
    ``footer-strip`` later in source order ends up *outside* the
    poster. A regex over ``data-measure-role`` would still see the
    strip and call it good. The browser tolerates the unbalanced markup
    silently; only an actual nesting model surfaces the lost ancestry.

    The parser intentionally does NOT bail on every minor unbalance --
    HTMLParser's recovery is generous and matches the browser's --
    because we only care about role-bearing ancestry. We do, however,
    catch the *gross* unbalance case: a ``</tag>`` that finds no
    matching opener on the stack. That is almost always the symptom of
    the same misplaced-``</div>`` bug.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # Stack entries: (tag, role_or_None, line_number).
        self.stack: list[tuple[str, str | None, int]] = []
        # One entry per role-bearing element seen, in source order:
        # (role, parent_role_or_None, line, tag).
        self.roles: list[tuple[str, str | None, int, str]] = []
        # Lines where ``</tag>`` had no matching opener.
        self.stray_close_lines: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]
                        ) -> None:
        role: str | None = None
        for k, v in attrs:
            if k == "data-measure-role" and v is not None:
                role = v.strip()
                break
        line = self.getpos()[0]
        if role is not None:
            # Parent role = the nearest ancestor on the stack that carries
            # a role. None means the element is at document root or only
            # nested inside non-role wrappers.
            parent_role: str | None = None
            for _t, r, _ln in reversed(self.stack):
                if r is not None:
                    parent_role = r
                    break
            self.roles.append((role, parent_role, line, tag))
        if tag.lower() not in _VOID_TAGS:
            self.stack.append((tag, role, line))

    def handle_startendtag(self, tag: str,
                           attrs: list[tuple[str, str | None]]) -> None:
        # ``<foo />`` self-closing form. Record any role but DON'T push.
        role: str | None = None
        for k, v in attrs:
            if k == "data-measure-role" and v is not None:
                role = v.strip()
                break
        if role is not None:
            line = self.getpos()[0]
            parent_role: str | None = None
            for _t, r, _ln in reversed(self.stack):
                if r is not None:
                    parent_role = r
                    break
            self.roles.append((role, parent_role, line, tag))

    def handle_endtag(self, tag: str) -> None:
        # Pop until we find the matching opener. If none is found, the
        # closer is stray -- record it and leave the stack alone (the
        # browser would do the same, just silently).
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                # Pop everything from i onward; entries above are
                # implicitly unclosed (HTMLParser does not auto-close)
                # but treating them as closed here matches browser
                # recovery and avoids a cascade of false stray-close
                # reports for the rest of the document.
                del self.stack[i:]
                return
        self.stray_close_lines.append((tag, self.getpos()[0]))


def check_role_nesting(html: str
                       ) -> tuple[list[tuple[str, str | None, int, str]],
                                  list[tuple[str, int]]]:
    """Return ``(roles, stray_closes)``.

    ``roles`` is one entry per role-bearing element in source order:
    ``(role, parent_role_or_None, line, tag)``. ``stray_closes`` lists
    every ``</tag>`` that had no opener on the stack at close time --
    almost always the proximate cause when ``measure`` reports the
    footer-strip rendered off-canvas. Pure function so the rule can be
    unit-tested without touching the filesystem or a browser.
    """
    parser = _RoleNestingChecker()
    parser.feed(html)
    parser.close()
    return parser.roles, parser.stray_close_lines


def cmd_preflight(args: argparse.Namespace) -> int:
    html_path = Path(args.html).resolve()
    if not html_path.exists():
        _eprint(f"ERROR: HTML not found: {ascii_safe(html_path)}")
        return 2
    raw = html_path.read_text(encoding="utf-8", errors="ignore")
    body = strip_for_lint(raw)

    problems: list[str] = []
    warnings: list[str] = []

    # 0) Unclosed <style>/<script>/<!-- --> . strip_for_lint needs the
    #    closer to remove the block, so an unclosed opener SURVIVES in
    #    `body`. A real browser swallows the rest of the document into that
    #    construct -- which makes every post-strip check below (LaTeX scan,
    #    raw-'<' scan, role-presence) untrustworthy: the linter "sees" a
    #    poster div the browser will never render. Fail loudly instead of
    #    silently PASSing on markup we can't actually see past.
    m_open = re.search(r"<!--|<style\b|<script\b", body, re.IGNORECASE)
    if m_open:
        ln = body[: m_open.start()].count("\n") + 1
        problems.append(
            f"L{ln}: unclosed '{ascii_safe(m_open.group(0))}' block -- add "
            "the matching '-->', '</style>', or '</script>'. The browser "
            "would otherwise swallow the rest of the poster into it."
        )

    # 1) LaTeX residue.
    for pat, desc in LATEX_PATTERNS:
        for m in re.finditer(pat, body):
            ln = body[: m.start()].count("\n") + 1
            problems.append(f"L{ln}: {desc} -> '{ascii_safe(m.group(0))}'")

    # 2) Raw '<' inside math segments. The common HTML-parse failure
    #    case is `a<b` / `x<y`. We catch '<' even after a letter/digit.
    #    Suppressed only when it's an escape `\<` or part of `</` / `<!`
    #    (HTML constructs MathJax never sees) or `<=` (a single MathJax
    #    token that is parsed atomically and does NOT trip the HTML
    #    tokenizer's tag-start lookahead).
    for s, e, mbody in find_math_segments(body):
        # Compute the math body's offset inside the original segment so
        # multi-line `$$ … \n a < b \n … $$` reports the `<`'s line,
        # not the segment-start line. find_math_segments hands back the
        # full `(start, end, body)` of the segment; the body's first
        # char is at `body[s + (segment_text_len - body_len)]` — easier
        # to recompute via `body.find(mbody, s)`.
        body_offset_in_body = body.find(mbody, s)
        if body_offset_in_body == -1:
            body_offset_in_body = s  # fallback shouldn't happen
        for m in re.finditer(r"(?<!\\)<(?![=/!])", mbody):
            abs_offset = body_offset_in_body + m.start()
            ln = body[: abs_offset].count("\n") + 1
            label = _delim_label(body[s:e], body[s:e])
            problems.append(
                f"L{ln}: raw '<' inside {label} "
                f"'{ascii_safe(mbody.strip()[:60])}' -- use \\lt"
            )

    # 3) Image src: local must exist; remote http(s) warns. A print
    #    poster should be self-contained -- a CDN image that 404s or is
    #    slow at render time silently breaks the figure, and the render
    #    gates can't see a missing remote image. data: URIs are inline.
    for m in re.finditer(r'src\s*=\s*["\']([^"\']+)["\']', body,
                         re.IGNORECASE):
        src = m.group(1)
        # Scheme matching is case-insensitive (browsers treat `HTTPS:` /
        # `DATA:` like `https:` / `data:`); lower-case only for the scheme
        # test, keep `src` raw for display and local-path resolution.
        src_l = src.lower()
        if src_l.startswith("data:"):
            continue
        if src_l.startswith(("http://", "https://", "//")):
            ln = body[: m.start()].count("\n") + 1
            warnings.append(
                f"L{ln}: remote image '{ascii_safe(src[:60])}' -- inline or "
                "localize "
                "it; a print poster should not depend on a CDN at render "
                "time"
            )
            continue
        # Strip ?query / #fragment and percent-decode before resolving a
        # LOCAL path -- a legit `fig.png?v=2` or `my%20fig.png` otherwise
        # reads as a missing file.
        local = unquote(urlsplit(src).path)
        candidate = (html_path.parent / local).resolve()
        if not candidate.exists():
            ln = body[: m.start()].count("\n") + 1
            problems.append(f"L{ln}: missing local image '{ascii_safe(src)}'")

    # 4) data-measure-role="poster" required on the root.
    if not re.search(r'data-measure-role\s*=\s*["\']poster["\']', body):
        problems.append(
            'missing required data-measure-role="poster" on root'
        )

    # 5) Unknown role values flag silent measure misses.
    for m in re.finditer(
        r'data-measure-role\s*=\s*["\']([^"\']+)["\']', body
    ):
        role = m.group(1).strip()
        if role not in KNOWN_ROLES:
            ln = body[: m.start()].count("\n") + 1
            problems.append(
                f"L{ln}: unknown data-measure-role='{ascii_safe(role)}' "
                f"(allowed: {sorted(KNOWN_ROLES)})"
            )

    # 6) Role nesting: each role must sit inside its required parent
    #    role per ROLE_PARENTS. The precipitating bug was a misplaced
    #    `</div>` that closed `.poster` early -- the count of opens and
    #    closes was still balanced (the extra `</div>` made some other
    #    legitimate close stray), but `footer-strip` ended up outside
    #    the grid so its row collapsed to 0 px. Catching it requires
    #    looking at the parent role of every role-bearing element, not
    #    just the totals.
    #
    #    Stray closer detection is intentionally NOT enforced here:
    #    HTMLParser's recovery (and the browser's) eagerly rebalances
    #    in ways that mask which `</tag>` was actually misplaced, so a
    #    naive "stray close" count fires on the wrong line. The
    #    parent-role check below catches the *visible symptom* (a role
    #    in the wrong layout slot) which is what measure would
    #    eventually report off-canvas anyway.
    #
    #    Note: the parser is fed RAW html (script/style intact) -- it
    #    already skips inside `<script>` and `<style>` properly.
    role_records, _stray = check_role_nesting(raw)
    for role, parent, ln, _tag in role_records:
        expected = ROLE_PARENTS.get(role)
        if not expected:
            continue
        if parent not in expected:
            shown_parent = parent if parent is not None else "(document root)"
            problems.append(
                f"L{ln}: data-measure-role='{ascii_safe(role)}' is nested "
                f"inside {ascii_safe(shown_parent)}; expected parent role "
                f"in {sorted(expected)}. A misplaced `</div>` is the usual "
                "cause -- it closes a grid container early so the role "
                "ends up outside its layout slot."
            )

    # 7) Soft sanity: no <title> / no <h1>. Warns, doesn't fail.
    if not re.search(r"<title[^>]*>.+?</title>", raw, re.DOTALL):
        warnings.append("no <title> set")
    if not re.search(r"<h1\b", raw):
        warnings.append(
            "no <h1> -- poster title block usually carries one"
        )

    print(f"[preflight] {ascii_safe(html_path)}")
    print(f"  problems: {len(problems)}   warnings: {len(warnings)}")
    for w in warnings:
        print(f"  WARN: {w}")
    for p in problems:
        _eprint(f"  FAIL: {p}")

    if problems:
        return 1
    print("[preflight] PASS")
    return 0


def has_required_roles_in_html(html_path: Path) -> dict[str, int]:
    """Cheap static count of each known role on disk. Used by ``polish``
    so it can hard-fail on a poster lacking ALL measurement markup,
    instead of silently PASSing on "0 figures, 0 columns, 0 stat
    elements"."""
    raw = html_path.read_text(encoding="utf-8", errors="ignore")
    body = strip_for_lint(raw)
    counts: dict[str, int] = {role: 0 for role in KNOWN_ROLES}
    for m in re.finditer(
        r'data-measure-role\s*=\s*["\']([^"\']+)["\']', body
    ):
        role = m.group(1).strip()
        if role in counts:
            counts[role] += 1
    return counts
