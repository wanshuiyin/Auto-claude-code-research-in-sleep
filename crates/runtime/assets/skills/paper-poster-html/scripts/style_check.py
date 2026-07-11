#!/usr/bin/env python3
"""style_check — the style HARD gate for HTML academic posters.

Implements the 12 style rules of DESIGN_FINAL.md §3 (plus the §12.5 nit-1
refinement on rule 8) split across two gates:

  Source gate (rules 1,2,3,5,6,7,8,9,10,11) — pure static analysis. We
    parse the HTML with ``html.parser`` to walk tags+attributes, extract
    the ``<style>`` blocks, strip CSS comments, locate the design-token
    block via the canonical comment pair, and then scan for: color
    literals outside the token block, forbidden ``style=`` attributes,
    gradients, font-family stacks against the whitelist, font-size values
    against the ``--fs-*`` scale, font-size token count, and the
    data-attribute / inline-SVG contracts.

  Render gate (rules 4 and 12) — needs computed style, so it lazy-imports
    Playwright, prints-emulates the poster at the @page viewport (reusing
    the vendored ``_posterly`` canvas+render helpers so the viewport basis
    matches ``measure``/``polish`` exactly), reads every element's
    computed colors, and runs the non-neutral hue-clustering check (rule
    4) and the large-dark-area check (rule 12).

WHY two gates: the source gate is cheap, deterministic, and runnable with
no browser — it is what Phase 3 scaffolding relies on. The render gate
catches what static analysis cannot (a token resolving to an off-palette
hue, or a dark slab assembled from many small boxes). ``--no-render``
keeps the source gate live while the heavier render gate is SKIPPED — the
overall status can still PASS from the source gate alone, but we print a
notice so the user knows two rules were not evaluated.

CLI (IMPLEMENTATION_CONVENTIONS.md §C):
  python3 style_check.py POSTER.html [--tokens TOKENS.json] [--json OUT.json]
                         [--no-render]

Exit codes: 0 = PASS (no hard failures), 1 = at least one HARD rule
failed, 2 = usage / environment error.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

# Make `_posterly` importable when this file is run directly via
# `python style_check.py …` (it lives in the same scripts/ dir).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from _posterly.textutil import ascii_safe  # noqa: E402


def _eprint(*args: Any, **kw: Any) -> None:
    print(*args, file=sys.stderr, **kw)


# ---------------------------------------------------------------------------
# Whitelists (DESIGN_FINAL §2 / IMPLEMENTATION_CONVENTIONS §A).
# ---------------------------------------------------------------------------

#: Serif families allowed for body text (and the `--font-serif` token).
SERIF_WHITELIST = {
    "charter", "source serif pro", "georgia", "times new roman", "serif",
}
#: Sans families allowed for headings / headers / table labels (and
#: `--font-sans`). "aptos" and "helvetica neue" / "arial" per §2.
SANS_WHITELIST = {
    "inter", "aptos", "helvetica neue", "arial", "sans-serif",
}
#: Mono families allowed for code only.
MONO_WHITELIST = {"menlo", "consolas", "monospace"}

#: The canonical font-size scale tokens. font-size declarations must use
#: one of these via `var(--fs-N)` (rule 8); the count gate (rule 9) warns
#: when MORE than 9 distinct --fs tokens are *defined* in the token block.
FS_TOKEN_RE = re.compile(r"--fs-(\d+)\b")

#: A `var(--fs-N)` reference inside a font-size value.
FS_VAR_REF_RE = re.compile(r"var\(\s*--fs-\d+\s*\)")

#: A predefined component variant suffix on a selector: BEM-ish `--<word>`
#: appended to a class, e.g. `.eqn--large`, `.card--compact`,
#: `.figure--wide`. §12.5 nit 1: `calc(var(--fs-*) * k)` is allowed ONLY
#: in a rule whose selector carries such a variant suffix; everywhere else
#: it is a HARD fail (an arbitrary per-element font-size override sneaking
#: past the token scale).
VARIANT_SUFFIX_RE = re.compile(r"\.[A-Za-z][\w-]*--[A-Za-z][\w-]*")

#: A `calc(... var(--fs-N) ...)` expression inside a font-size value — the
#: only legal non-bare-token form, and only inside a variant rule.
CALC_FS_RE = re.compile(r"calc\([^)]*var\(\s*--fs-\d+\s*\)[^)]*\)")


# ---------------------------------------------------------------------------
# Color-literal detection (rules 1, 2, 3).
# ---------------------------------------------------------------------------

#: Matches any CSS color literal we forbid outside the token block:
#: #hex (3/4/6/8 digit), rgb()/rgba(), hsl()/hsla(). Named colors are NOT
#: matched — they are caught structurally where it matters (the templates
#: ship `transparent` / `currentColor` which are intentionally allowed),
#: and chasing the full CSS named-color list would create false positives
#: on words like "red" appearing in prose. The literals above are the
#: forms a hand-edited off-palette color actually takes.
COLOR_LITERAL_RE = re.compile(
    r"""
    (?:\#[0-9a-fA-F]{3,8}\b)            # #hex
    | (?:\brgba?\s*\([^)]*\))           # rgb( ) / rgba( )
    | (?:\bhsla?\s*\([^)]*\))           # hsl( ) / hsla( )
    """,
    re.VERBOSE,
)

#: A single rgb/rgba/hsl/hsla literal we need to PARSE (for the
#: radial-gradient alpha check in rule 5). Captures the function name and
#: the comma/space separated args.
_FUNC_COLOR_RE = re.compile(
    r"\b(rgb|rgba|hsl|hsla)\s*\(([^)]*)\)", re.IGNORECASE
)


def _parse_alpha(func: str, args: str) -> float | None:
    """Extract the alpha channel from an rgba()/hsla() literal.

    Returns 1.0 for the opaque rgb()/hsl() forms (no alpha), the parsed
    alpha for rgba()/hsla(), or ``None`` if the literal can't be parsed.
    We only need alpha here (rule 5's radial-gradient stop check), so we
    don't bother converting the color channels.
    """
    parts = [p.strip() for p in re.split(r"[,/]", args) if p.strip()]
    func = func.lower()
    if func in ("rgb", "hsl"):
        return 1.0
    if func in ("rgba", "hsla"):
        if len(parts) < 4:
            return None
        a = parts[3]
        try:
            if a.endswith("%"):
                return float(a[:-1]) / 100.0
            return float(a)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# HTML parsing: collect <style> CSS and every element's attributes.
# ---------------------------------------------------------------------------


class _PosterParser(HTMLParser):
    """Walk the poster HTML, recording two things the source gate needs:

      1. The concatenated text of all ``<style>`` blocks (so we can run
         CSS-level checks against the same content the browser sees).
      2. A flat list of ``(tag, attrs_dict, exempt_path)`` for every
         start/startend tag, where ``exempt_path`` flags whether the
         element sits inside a ``data-color-exempt="logo"`` subtree — so
         rule 1/2/11 exemptions can be applied without a full DOM.

    We track the exempt-subtree depth with a small stack: when we enter an
    element carrying ``data-color-exempt="logo"`` (or a ``data-source``
    "paper" subtree, for the SVG/style exemptions), every descendant
    inherits the exemption until the matching close tag.
    """

    #: Void elements never get a matching end tag, so they must not push
    #: onto the exempt stack (otherwise the stack desyncs).
    _VOID = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.style_css_parts: list[str] = []
        self._in_style = False
        # Each element record: tag, attrs(dict), inside_logo, inside_paper.
        self.elements: list[dict[str, Any]] = []
        # Stack of (tag, opened_logo, opened_paper) for open non-void
        # elements, used to inherit exemption to descendants.
        self._stack: list[tuple[str, bool, bool]] = []

    # -- exemption bookkeeping ------------------------------------------
    def _inside_logo(self) -> bool:
        return any(s[1] for s in self._stack)

    def _inside_paper(self) -> bool:
        return any(s[2] for s in self._stack)

    def _record(self, tag: str, attrs: list[tuple[str, str | None]],
                self_closing: bool) -> tuple[bool, bool]:
        d = {k.lower(): (v if v is not None else "") for k, v in attrs}
        opens_logo = d.get("data-color-exempt", "").lower() == "logo"
        opens_paper = d.get("data-source", "").lower() == "paper"
        inside_logo = self._inside_logo() or opens_logo
        inside_paper = self._inside_paper() or opens_paper
        self.elements.append({
            "tag": tag,
            "attrs": d,
            "inside_logo": inside_logo,
            "inside_paper": inside_paper,
            "self_closing": self_closing,
        })
        return opens_logo, opens_paper

    # -- HTMLParser hooks ----------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "style":
            self._in_style = True
        opens_logo, opens_paper = self._record(tag, attrs, self_closing=False)
        if tag not in self._VOID:
            self._stack.append((tag, opens_logo, opens_paper))

    def handle_startendtag(self, tag, attrs):
        # `<svg .../>`, `<img .../>` — self-closing; record but never push.
        self._record(tag.lower(), attrs, self_closing=True)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "style":
            self._in_style = False
        # Pop back to (and including) the matching open tag. Tolerant of
        # minor mismatches so a stray close tag can't desync the stack.
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._in_style:
            self.style_css_parts.append(data)

    @property
    def style_css(self) -> str:
        return "\n".join(self.style_css_parts)


def _strip_css_comments(css: str) -> str:
    """Strip ``/* … */`` comments. We must NOT strip before locating the
    token block (the markers ARE comments), so callers strip on a copy.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _blank_allowed_radial_stops(css: str) -> str:
    """Blank (space-fill) the contents of every ``radial-gradient(…)`` so
    its color stops don't trip the rule-1 literal scan.

    WHY: the ARIS fork keeps a faint radial tint on ``.poster``'s
    background with ``rgba(…)`` stops whose alpha is <= 0.06
    (IMPLEMENTATION_CONVENTIONS §E.2). Those rgba literals are the one
    documented place a color literal legitimately appears OUTSIDE the token
    block — rule 5 validates them (right selector, alpha bound), so rule 1
    must not double-flag them. We blank (not delete) to preserve char
    offsets. Selector/alpha legality is rule 5's job, not rule 1's.
    """
    out = []
    for pre, body, _close in _iter_radial_gradients(css):
        out.append(pre)
        out.append(" " * len(body))  # blank the (…) body (incl. parens)
    return "".join(out)


def _iter_radial_gradients(css: str):
    """Yield ``(text_before, gradient_text, end_index)`` for each
    ``radial-gradient(…)`` with BALANCED parentheses, so a nested
    ``rgba(…)`` stop is captured whole.

    ``gradient_text`` spans from ``radial-gradient`` through its matching
    ``)``. The naive ``radial-gradient\\((.*?)\\)`` regex stops at the
    first inner ``)`` (the rgba close), splitting the literal — so rule 5's
    alpha check missed stops and rule 1's blanker under-blanked. Balanced
    walking fixes both. Pure + stdlib.
    """
    low = css.lower()
    i = 0
    while i < len(css):
        j = low.find("radial-gradient(", i)
        if j == -1:
            yield css[i:], "", len(css)
            break
        pre = css[i:j]
        k = j + len("radial-gradient")
        depth = 0
        while k < len(css):
            if css[k] == "(":
                depth += 1
            elif css[k] == ")":
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
        yield pre, css[j:k], k
        i = k


# Canonical token-block markers (IMPLEMENTATION_CONVENTIONS §A). The
# token block is the ONLY place color literals are allowed (rule 1).
_TOKEN_START_RE = re.compile(
    r"/\*\s*=+\s*DESIGN TOKENS\s*=+\s*\*/", re.IGNORECASE
)
_TOKEN_END_RE = re.compile(
    r"/\*\s*=+\s*END DESIGN TOKENS\s*=+\s*\*/", re.IGNORECASE
)


def _locate_token_block(css: str) -> tuple[int, int] | None:
    """Return ``(start, end)`` char offsets of the token block content
    (between the two marker comments) in the *raw* (comment-bearing) CSS,
    or ``None`` if the canonical marker pair isn't present.
    """
    m_start = _TOKEN_START_RE.search(css)
    if not m_start:
        return None
    m_end = _TOKEN_END_RE.search(css, m_start.end())
    if not m_end:
        return None
    return m_start.end(), m_end.start()


# ---------------------------------------------------------------------------
# CSS rule splitting (for selector-scoped checks: rules 3, 5, 8).
# ---------------------------------------------------------------------------


def _iter_css_rules(css_no_comments: str):
    """Yield ``(selector, body)`` for each top-level ``sel { … }`` rule.

    Naive but adequate for the templates: it does not recurse into nested
    at-rules' inner braces beyond one level, which is fine because the
    declarations we inspect (color, font-size, background) live in flat
    rule bodies. ``@page``/``@media`` wrappers are skipped as selectors
    but their inner rules are still seen on the next pass via a second
    scan of the wrapper body. WHY a hand split instead of a CSS parser:
    stdlib has none, and the contract is "small functions, stdlib only".
    """
    # First, pull out @media/@supports wrapper bodies and re-scan them so
    # rules inside print/screen media are inspected too (the templates put
    # `@media print { :root { --u: 1mm } }` and component overrides there).
    def _scan(block: str):
        i = 0
        n = len(block)
        while i < n:
            brace = block.find("{", i)
            if brace == -1:
                break
            selector = block[i:brace].strip()
            depth = 1
            j = brace + 1
            while j < n and depth:
                if block[j] == "{":
                    depth += 1
                elif block[j] == "}":
                    depth -= 1
                j += 1
            body = block[brace + 1:j - 1]
            if selector.startswith("@") and "{" in body:
                # Nested at-rule: recurse one level into its body.
                yield from _scan(body)
            else:
                yield selector, body
            i = j

    yield from _scan(css_no_comments)


# ---------------------------------------------------------------------------
# Rule result container.
# ---------------------------------------------------------------------------


class RuleResult:
    """One row in the JSON ``rules`` array.

    ``status`` is PASS / FAIL / WARN / SKIPPED. ``detail`` is a single
    human-readable line (ascii-safe at output). A HARD rule with status
    FAIL drives the overall gate to FAIL; a WARN rule never does.
    """

    def __init__(self, rid: int, severity: str, title: str) -> None:
        self.id = rid
        self.severity = severity  # "hard" | "warn"
        self.title = title
        self.status = "PASS"
        self.detail = "ok"

    def fail(self, detail: str) -> "RuleResult":
        self.status = "FAIL"
        self.detail = detail
        return self

    def warn(self, detail: str) -> "RuleResult":
        self.status = "WARN"
        self.detail = detail
        return self

    def skip(self, detail: str) -> "RuleResult":
        self.status = "SKIPPED"
        self.detail = detail
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "status": self.status,
            "detail": ascii_safe(self.detail),
        }


# ---------------------------------------------------------------------------
# Source gate.
# ---------------------------------------------------------------------------


def run_source_gate(
    html_text: str, html_path: Path
) -> tuple[list[RuleResult], _PosterParser, str | None]:
    """Run rules 1,2,3,5,6,7,8,9,10,11 (the static rules).

    Returns ``(results, parser, token_block_or_None)``. The parser and
    located token block are returned so the render gate can reuse them
    (token block holds the :root --accent/--gold for hue centers fallback).
    """
    parser = _PosterParser()
    parser.feed(html_text)
    parser.close()

    raw_css = parser.style_css
    token_span = _locate_token_block(raw_css)
    token_block_text: str | None = None
    if token_span is not None:
        token_block_text = raw_css[token_span[0]:token_span[1]]

    results: list[RuleResult] = []

    # --- Rule 1: color literals only inside the token block / logo SVG ---
    r1 = RuleResult(1, "hard", "color literals only in token block")
    if token_span is None:
        r1.fail(
            "design-token block not found: expected the comment pair "
            "/* ===== DESIGN TOKENS ===== */ ... "
            "/* ===== END DESIGN TOKENS ===== */ inside a <style> block. "
            "Cannot locate where color literals are allowed."
        )
    else:
        # Build a comment-stripped copy where the token-block region is
        # blanked out (so literals inside it are exempt), then scan the
        # REMAINING CSS for color literals. We blank-not-delete to keep
        # char offsets meaningful for the error message.
        css_scan = (
            raw_css[:token_span[0]]
            + (" " * (token_span[1] - token_span[0]))
            + raw_css[token_span[1]:]
        )
        css_scan = _strip_css_comments(css_scan)
        # The documented radial-tint exemption: alpha<=0.06 rgba stops on
        # the .poster background are validated by rule 5, not rule 1.
        css_scan = _blank_allowed_radial_stops(css_scan)
        offenders = sorted(set(
            m.group(0) for m in COLOR_LITERAL_RE.finditer(css_scan)
        ))
        if offenders:
            r1.fail(
                "color literal(s) outside the token block: "
                + ", ".join(offenders[:8])
                + (" …" if len(offenders) > 8 else "")
                + ". Move them to a --token in the DESIGN TOKENS block and "
                "reference via var(--…) (rule 3)."
            )
    results.append(r1)

    # --- Rule 2: forbidden inline `style=` attributes --------------------
    # Zero tolerance EXCEPT the two documented exemptions:
    #   (a) any element inside a data-color-exempt="logo" subtree;
    #   (b) `style="width: NN%"` on an <img data-source="paper">.
    r2 = RuleResult(2, "hard", "no inline style= (two documented exemptions)")
    style_offenders: list[str] = []
    for el in parser.elements:
        style = el["attrs"].get("style")
        if style is None or style.strip() == "":
            continue
        if el["inside_logo"]:
            continue  # exemption (a)
        # exemption (b): img[data-source=paper] with only `width: NN%`.
        is_paper_img = (
            el["tag"] == "img"
            and el["attrs"].get("data-source", "").lower() == "paper"
        )
        if is_paper_img and re.fullmatch(
            r"\s*width\s*:\s*\d+(?:\.\d+)?%\s*;?\s*", style
        ):
            continue
        style_offenders.append(f"<{el['tag']} style=\"{style.strip()}\">")
    if style_offenders:
        r2.fail(
            f"{len(style_offenders)} inline style= attribute(s) "
            "(zero-tolerance; use utility classes). First: "
            + style_offenders[0]
            + ". Exemptions: inside data-color-exempt=\"logo\", or "
            "style=\"width: NN%\" on img[data-source=\"paper\"]."
        )
    results.append(r2)

    # --- Rule 3: component CSS colors must be var(--…) --------------------
    # Any color/background/border-color declaration in a NON-:root rule
    # whose value contains a color literal fails (literals belong only in
    # the token block, which is inside :root). This overlaps rule 1 but
    # targets the *property* level for a clearer message.
    r3 = RuleResult(3, "hard", "component colors use var(--…)")
    css_nc = _strip_css_comments(raw_css)
    color_prop_offenders: list[str] = []
    color_prop_re = re.compile(
        r"(?<![\w-])(color|background|background-color|border|border-color|"
        r"border-top-color|border-bottom-color|border-left-color|"
        r"border-right-color|fill|stroke|box-shadow|outline|outline-color)"
        r"\s*:\s*([^;{}]+)",
        re.IGNORECASE,
    )
    for selector, body in _iter_css_rules(css_nc):
        sel_l = selector.lower()
        # :root is where tokens live — literals there are expected.
        if ":root" in sel_l:
            continue
        # Same radial-tint exemption as rule 1: the alpha<=0.06 stops on
        # the .poster background are rule 5's responsibility, not rule 3's.
        body_scan = _blank_allowed_radial_stops(body)
        for m in color_prop_re.finditer(body_scan):
            value = m.group(2)
            if COLOR_LITERAL_RE.search(value):
                color_prop_offenders.append(
                    f"{selector.strip()[:40]} {{ {m.group(1)}: "
                    f"{value.strip()[:40]} }}"
                )
    if color_prop_offenders:
        r3.fail(
            f"{len(color_prop_offenders)} component color declaration(s) "
            "with a literal instead of var(--…). First: "
            + color_prop_offenders[0]
        )
    results.append(r3)

    # --- Rule 5: no linear-gradient; radial only on .poster, alpha<=0.06 -
    r5 = RuleResult(5, "hard", "no linear-gradient; radial only .poster bg")
    if re.search(r"\blinear-gradient\s*\(", css_nc, re.IGNORECASE):
        r5.fail(
            "linear-gradient is forbidden (flat, de-gradient design). "
            "Replace with a solid var(--…) fill."
        )
    else:
        radial_problems: list[str] = []
        for selector, body in _iter_css_rules(css_nc):
            if "radial-gradient" not in body.lower():
                continue
            sel_l = selector.lower()
            # Allowed ONLY on the .poster background.
            if ".poster" not in sel_l:
                radial_problems.append(
                    f"radial-gradient on '{selector.strip()[:50]}' "
                    "(only .poster background may use it)"
                )
                continue
            # Every color stop's alpha must be <= 0.06. Use balanced
            # extraction so a nested rgba() stop is captured whole.
            for _pre, grad_text, _end in _iter_radial_gradients(body):
                if not grad_text:
                    continue
                for fm in _FUNC_COLOR_RE.finditer(grad_text):
                    a = _parse_alpha(fm.group(1), fm.group(2))
                    if a is None:
                        continue
                    if a > 0.06 + 1e-9:
                        radial_problems.append(
                            f"radial-gradient stop alpha={a:g} > 0.06 on "
                            f"'{selector.strip()[:40]}'"
                        )
        if radial_problems:
            r5.fail("; ".join(radial_problems[:4]))
    results.append(r5)

    # --- Rules 6 + 7: font pairing + whitelist ---------------------------
    # We inspect every `font-family:` declaration. The token convention is
    # that body text uses `--font-serif` and headings/headers/table labels
    # use `--font-sans`; the actual stacks are DEFINED once on those two
    # tokens. So we (a) whitelist-check the families in --font-serif /
    # --font-sans / --font-mono token definitions (rule 7), and (b) verify
    # the serif token is a serif stack, the sans token a sans stack, and
    # that components reference the *right* token for their role (rule 6).
    r6 = RuleResult(6, "hard", "font pairing: serif body / sans heading")
    r7 = RuleResult(7, "hard", "font-family whitelist")

    # Pull token stack definitions from the token block (if present),
    # else from any :root.
    def _families(value: str) -> list[str]:
        out = []
        for raw in value.split(","):
            fam = raw.strip().strip('"').strip("'").lower()
            if fam:
                out.append(fam)
        return out

    serif_def = sans_def = mono_def = None
    scope = token_block_text if token_block_text is not None else css_nc
    m = re.search(r"--font-serif\s*:\s*([^;{}]+)", scope, re.IGNORECASE)
    if m:
        serif_def = _families(m.group(1))
    m = re.search(r"--font-sans\s*:\s*([^;{}]+)", scope, re.IGNORECASE)
    if m:
        sans_def = _families(m.group(1))
    m = re.search(r"--font-mono\s*:\s*([^;{}]+)", scope, re.IGNORECASE)
    if m:
        mono_def = _families(m.group(1))

    wl_problems: list[str] = []
    if serif_def is not None:
        bad = [f for f in serif_def if f not in SERIF_WHITELIST]
        if bad:
            wl_problems.append(
                f"--font-serif has non-whitelisted family/ies: "
                f"{', '.join(bad)}"
            )
    if sans_def is not None:
        bad = [f for f in sans_def if f not in SANS_WHITELIST]
        if bad:
            wl_problems.append(
                f"--font-sans has non-whitelisted family/ies: "
                f"{', '.join(bad)}"
            )
    if mono_def is not None:
        bad = [f for f in mono_def if f not in MONO_WHITELIST]
        if bad:
            wl_problems.append(
                f"--font-mono has non-whitelisted family/ies: "
                f"{', '.join(bad)}"
            )
    # Also catch literal font stacks used directly in component rules
    # (bypassing the tokens) and whitelist-check them.
    for selector, body in _iter_css_rules(css_nc):
        for fm in re.finditer(
            r"font-family\s*:\s*([^;{}]+)", body, re.IGNORECASE
        ):
            val = fm.group(1)
            if "var(" in val:
                continue  # token reference — checked via the token def
            fams = _families(val)
            allowed = SERIF_WHITELIST | SANS_WHITELIST | MONO_WHITELIST
            bad = [f for f in fams if f not in allowed]
            if bad:
                wl_problems.append(
                    f"literal font stack on '{selector.strip()[:30]}' has "
                    f"non-whitelisted: {', '.join(bad)}"
                )
    if wl_problems:
        r7.fail("; ".join(wl_problems[:4]))
    results.append(r7)

    # Rule 6 pairing: the --font-serif token must resolve to a serif stack
    # (last family `serif`) and --font-sans to a sans stack (last family
    # `sans-serif`). This is the structural guarantee that body=serif,
    # headings=sans hold once components reference the right token.
    pairing_problems: list[str] = []
    if serif_def is not None and (not serif_def or serif_def[-1] != "serif"):
        pairing_problems.append(
            "--font-serif must end in the generic `serif` family"
        )
    if sans_def is not None and (
        not sans_def or sans_def[-1] != "sans-serif"
    ):
        pairing_problems.append(
            "--font-sans must end in the generic `sans-serif` family"
        )
    if serif_def is None and sans_def is None:
        pairing_problems.append(
            "neither --font-serif nor --font-sans token is defined; cannot "
            "verify the serif-body / sans-heading pairing"
        )
    if pairing_problems:
        r6.fail("; ".join(pairing_problems))
    results.append(r6)

    # --- Rule 8 (+ §12.5 nit 1): font-size must use --fs-* token ---------
    # Every `font-size:` value must be either a bare `var(--fs-N)` ref OR a
    # `calc(... var(--fs-N) ...)` AND in that calc case the rule's selector
    # must carry a predefined `--variant` suffix (e.g. `.eqn--large`).
    # Anything else (raw px, raw calc(N*var(--u)), bare numbers) is a HARD
    # fail: it is an off-scale font-size drift.
    r8 = RuleResult(8, "hard", "font-size via --fs-* token / variant calc")
    fs_problems: list[str] = []
    for selector, body in _iter_css_rules(css_nc):
        sel_has_variant = bool(VARIANT_SUFFIX_RE.search(selector))
        for fm in re.finditer(
            r"font-size\s*:\s*([^;{}]+)", body, re.IGNORECASE
        ):
            value = fm.group(1).strip()
            if FS_VAR_REF_RE.fullmatch(value):
                continue  # bare var(--fs-N) — always allowed
            # Relative `em` <= 1.0 is allowed: it can only SHRINK a parent
            # whose size is already on the token scale (the standard
            # typographic pattern for sup/sub), so it cannot introduce a
            # new absolute size the way raw px / raw calc drift can.
            m_em = re.fullmatch(r"(0?\.\d+|1(?:\.0+)?)\s*em", value)
            if m_em and float(m_em.group(1)) <= 1.0:
                continue
            if CALC_FS_RE.search(value):
                # calc with an --fs token: allowed ONLY on a variant rule.
                if sel_has_variant:
                    continue
                fs_problems.append(
                    f"calc() font-size with --fs token on non-variant "
                    f"selector '{selector.strip()[:40]}' "
                    f"(value '{value[:40]}'): calc(var(--fs-*) * k) is only "
                    "allowed on a COMPONENTS.md variant like .eqn--large"
                )
                continue
            # No --fs token at all → off-scale drift.
            fs_problems.append(
                f"off-scale font-size on '{selector.strip()[:40]}': "
                f"'{value[:40]}' (use var(--fs-N))"
            )
    if fs_problems:
        r8.fail("; ".join(fs_problems[:4]) + (
            f" (+{len(fs_problems) - 4} more)" if len(fs_problems) > 4 else ""
        ))
    results.append(r8)

    # --- Rule 9 (WARN): > 9 distinct --fs tokens defined -----------------
    r9 = RuleResult(9, "warn", "<= 9 font-size tokens")
    defined_fs = sorted(set(
        int(m.group(1)) for m in FS_TOKEN_RE.finditer(
            token_block_text if token_block_text is not None else css_nc
        )
    ))
    if len(defined_fs) > 9:
        r9.warn(
            f"{len(defined_fs)} --fs-* tokens defined "
            f"({', '.join('--fs-%d' % n for n in defined_fs)}); the scale "
            "should stay <= 9 steps to keep the typographic hierarchy tight."
        )
    else:
        r9.detail = f"{len(defined_fs)} --fs-* token(s) defined"
    results.append(r9)

    # --- Rule 10: data-attribute contracts -------------------------------
    # img[data-source="paper"] MUST also carry data-asset-id; logo
    # exemptions MUST be explicitly marked data-color-exempt="logo".
    r10 = RuleResult(10, "hard", "data-source/asset-id + logo-exempt marks")
    contract_problems: list[str] = []
    for el in parser.elements:
        a = el["attrs"]
        if (el["tag"] == "img"
                and a.get("data-source", "").lower() == "paper"):
            if not a.get("data-asset-id", "").strip():
                src = a.get("src", "?")
                contract_problems.append(
                    f"<img data-source=\"paper\" src=\"{src[:40]}\"> is "
                    "missing data-asset-id"
                )
    if contract_problems:
        r10.fail("; ".join(contract_problems[:4]))
    results.append(r10)

    # --- Rule 11: no hand-rolled decorative SVG --------------------------
    # inline <svg> is allowed ONLY when it is (a) inside a logo-exempt
    # subtree, OR (b) itself marked as a catalogued structural diagram
    # (data-component="diagram"), OR (c) a QR fallback (data-component=
    # "qr"). Everything else is a forbidden decorative SVG.
    r11 = RuleResult(11, "hard", "no decorative inline SVG")
    svg_problems: list[str] = []
    for el in parser.elements:
        if el["tag"] != "svg":
            continue
        a = el["attrs"]
        comp = a.get("data-component", "").lower()
        if el["inside_logo"]:
            continue
        if comp in ("diagram", "qr"):
            continue
        svg_problems.append(
            "inline <svg> that is not inside a data-color-exempt=\"logo\" "
            "subtree and is not marked data-component=\"diagram\"/\"qr\""
        )
    if svg_problems:
        r11.fail(
            f"{len(svg_problems)} disallowed inline <svg>: "
            + svg_problems[0]
            + ". Decorative SVG is banned; only logos, QR fallbacks, and "
            "COMPONENTS.md-catalogued structural diagrams are allowed."
        )
    results.append(r11)

    return results, parser, token_block_text


# ---------------------------------------------------------------------------
# Hue-cluster helpers (rule 4) — pure functions, unit-testable.
# ---------------------------------------------------------------------------


def _hue_of_rgb(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Return (hue_deg, saturation, lightness) using HSL (colorsys.rgb_to_hls
    returns H,L,S — note the order). Hue in [0,360), S/L in [0,1].
    """
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s, l


def _hue_dist(a: float, b: float) -> float:
    """Circular distance between two hue angles in degrees (0..180)."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def cluster_hues(hues: list[float], radius_deg: float = 18.0) -> list[float]:
    """Greedy 1-D circular clustering of hue angles.

    Sort the hues, sweep once, and start a new cluster whenever the next
    hue is more than ``radius_deg`` (circular) from the current cluster's
    *seed*. Returns the list of cluster center hues (circular mean of each
    cluster's members). WHY greedy + seed-anchored: it is deterministic,
    matches the spec's "cluster radius 18 degrees", and is cheap. Pure so
    it can be unit-tested without a browser.
    """
    if not hues:
        return []
    ordered = sorted(hues)
    clusters: list[list[float]] = [[ordered[0]]]
    for h in ordered[1:]:
        # Anchor on the cluster seed (its first/min member) so a long run
        # of slowly drifting hues doesn't merge into one giant cluster.
        seed = clusters[-1][0]
        if _hue_dist(h, seed) <= radius_deg:
            clusters[-1].append(h)
        else:
            clusters.append([h])
    # The circular wrap-around case: if the last cluster's members are
    # within radius of the first cluster's seed, merge them (e.g. reds at
    # 350 deg and 5 deg are one hue family).
    if len(clusters) > 1:
        if _hue_dist(clusters[-1][-1], clusters[0][0]) <= radius_deg:
            clusters[0] = clusters[-1] + clusters[0]
            clusters.pop()
    return [_circular_mean(c) for c in clusters]


def _circular_mean(angles: list[float]) -> float:
    """Mean of angles on the unit circle, returned in [0,360)."""
    x = sum(math.cos(math.radians(a)) for a in angles)
    y = sum(math.sin(math.radians(a)) for a in angles)
    return math.degrees(math.atan2(y, x)) % 360.0


# JS that collects computed colors for every element NOT inside an exempt
# subtree, plus its on-screen area + background lightness (for rule 12).
_RENDER_JS = r"""
() => {
  // An element is exempt (rule 4) if it (or an ancestor) is an <img>, a
  // [data-color-exempt] subtree, a [data-source="paper"] subtree, or a
  // QR block ([data-component="qr"] / .qr-block). We walk up once per
  // element; cheap enough for a single-page poster.
  const isExempt = (el) => {
    let n = el;
    while (n && n.nodeType === 1) {
      const tag = n.tagName ? n.tagName.toLowerCase() : '';
      if (tag === 'img') return true;
      if (n.hasAttribute && n.hasAttribute('data-color-exempt')) return true;
      if (n.getAttribute && n.getAttribute('data-source') === 'paper')
        return true;
      const comp = n.getAttribute && n.getAttribute('data-component');
      if (comp === 'qr') return true;
      if (n.classList && n.classList.contains('qr-block')) return true;
      n = n.parentElement;
    }
    return false;
  };

  const poster = document.querySelector('[data-measure-role="poster"]')
               || document.querySelector('.poster')
               || document.body;
  const pr = poster.getBoundingClientRect();
  const posterArea = Math.max(1, pr.width * pr.height);

  const colors = [];      // {prop, rgba} for rule 4
  let darkArea = 0;       // sum of on-screen area with bg L < 0.18 (rule 12)

  const all = Array.from(document.querySelectorAll('*'));
  for (const el of all) {
    const cs = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const onscreen = r.width > 0 && r.height > 0;

    // Rule 12: large dark background area. Measure regardless of color
    // exemption (a dark slab is a dark slab even behind a figure), but
    // only count visible boxes inside the poster bbox.
    if (onscreen) {
      const bg = cs.backgroundColor;
      const L = bgLightness(bg);
      if (L !== null && L < 0.18) {
        // Clip to poster bounds so off-canvas overflow doesn't inflate.
        const w = Math.max(0, Math.min(r.right, pr.right)
                              - Math.max(r.left, pr.left));
        const h = Math.max(0, Math.min(r.bottom, pr.bottom)
                              - Math.max(r.top, pr.top));
        darkArea += w * h;
      }
    }

    if (isExempt(el)) continue;
    // Rule 4: collect every color-bearing computed property.
    colors.push({prop: 'color', rgba: cs.color});
    colors.push({prop: 'background-color', rgba: cs.backgroundColor});
    colors.push({prop: 'border-top-color', rgba: cs.borderTopColor});
    colors.push({prop: 'border-right-color', rgba: cs.borderRightColor});
    colors.push({prop: 'border-bottom-color', rgba: cs.borderBottomColor});
    colors.push({prop: 'border-left-color', rgba: cs.borderLeftColor});
    colors.push({prop: 'fill', rgba: cs.fill});
    colors.push({prop: 'stroke', rgba: cs.stroke});
  }

  function bgLightness(s) {
    const m = parseRGBA(s);
    if (!m || m.a < 0.5) return null;  // transparent-ish: not a dark slab
    const r = m.r / 255, g = m.g / 255, b = m.b / 255;
    return (Math.max(r, g, b) + Math.min(r, g, b)) / 2;
  }
  function parseRGBA(s) {
    const mm = /rgba?\(([^)]+)\)/i.exec(s || '');
    if (!mm) return null;
    const p = mm[1].split(/[ ,\/]+/).filter(Boolean);
    if (p.length < 3) return null;
    return {
      r: parseFloat(p[0]), g: parseFloat(p[1]), b: parseFloat(p[2]),
      a: p.length >= 4 ? parseFloat(p[3]) : 1,
    };
  }

  return {colors, posterArea, darkArea};
}
"""


def _parse_rgba_str(s: str) -> tuple[int, int, int, float] | None:
    """Parse a computed ``rgb()/rgba()`` string into (r,g,b,a). Returns
    None for non-rgb forms (e.g. ``transparent`` resolves to
    rgba(0,0,0,0), which DOES parse, so this only fails on unexpected
    formats).
    """
    m = re.search(
        r"rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)"
        r"(?:[ ,/]+([\d.]+%?))?\s*\)",
        s or "", re.IGNORECASE,
    )
    if not m:
        return None
    r, g, b = int(float(m.group(1))), int(float(m.group(2))), int(float(m.group(3)))
    a_raw = m.group(4)
    if a_raw is None:
        a = 1.0
    elif a_raw.endswith("%"):
        a = float(a_raw[:-1]) / 100.0
    else:
        a = float(a_raw)
    return r, g, b, a


def run_render_gate(
    html_path: Path,
    hue_centers: dict[str, float],
    *,
    cluster_radius_deg: float = 18.0,
    center_tol_deg: float = 22.0,
    nonneutral_alpha: float = 0.10,
    nonneutral_sat: float = 0.18,
    dark_area_frac: float = 0.08,
    mathjax_timeout_ms: int = 15000,
    settle_ms: int = 500,
) -> tuple[list[RuleResult], int | None]:
    """Run rules 4 and 12 via Playwright print-emulation.

    Returns ``(results, env_exit)``. ``env_exit`` is non-None (==2) only
    when the environment is unusable (no playwright, no @page canvas, nav
    failure) — the caller surfaces it as a usage/env error. Otherwise the
    two rule results carry PASS/FAIL/WARN as normal.

    WHY lazy import: playwright may still be installing; importing at
    module top would break the source-gate-only ``--no-render`` path.
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeoutError
    except ImportError:
        _eprint(
            "ERROR: playwright is not available, so the render gate "
            "(rules 4 and 12) cannot run. Install it with:\n"
            "  python -m pip install playwright\n"
            "  python -m playwright install chromium\n"
            "or re-run with --no-render to skip rules 4 and 12 (the source "
            "gate still runs and can PASS on its own)."
        )
        return [], 2

    # Reuse the vendored canvas+render helpers so the viewport basis and
    # MathJax settling exactly match measure/polish.
    from _posterly import canvas as _canvas
    from _posterly import render as _render

    resolved = _canvas.resolve_canvas(html_path, None, label="[style]")
    if resolved is None:
        _eprint(
            "ERROR: could not find `@page { size: <W> <H> }` in HTML for "
            "the render gate. Add an @page rule or re-run with --no-render."
        )
        return [], 2
    _canvas_in, viewport = resolved

    with sync_playwright() as p:
        browser, _ctx, page = _render.open_print_emulated_page(p, viewport)
        nav_timed_out = False
        try:
            page.goto(html_path.as_uri(), wait_until="networkidle",
                      timeout=mathjax_timeout_ms)
        except PWTimeoutError:
            nav_timed_out = True

        settle = _render.settle_page(
            page, mathjax_timeout_ms=mathjax_timeout_ms, settle_ms=settle_ms,
        )
        fail = _render.hard_fail_on_settle_problems(
            settle, mathjax_timeout_ms=mathjax_timeout_ms,
        )
        if fail is not None:
            browser.close()
            _eprint(f"ERROR (render gate): {fail}")
            return [], 2
        if nav_timed_out:
            browser.close()
            _eprint(
                "ERROR (render gate): page did not reach network-idle "
                f"within {mathjax_timeout_ms} ms; a blocked remote resource "
                "is the usual cause. Inline assets or re-run --no-render."
            )
            return [], 2

        data = page.evaluate(_RENDER_JS)
        browser.close()

    results: list[RuleResult] = []

    # --- Rule 4: non-neutral hue clustering ------------------------------
    r4 = RuleResult(4, "hard", "<=2 non-neutral hue clusters on palette")
    hues: list[float] = []
    for c in data["colors"]:
        parsed = _parse_rgba_str(c["rgba"])
        if parsed is None:
            continue
        r, g, b, a = parsed
        if a < nonneutral_alpha:
            continue
        hue, sat, _l = _hue_of_rgb(r, g, b)
        # Perceptual chroma, not raw saturation: HSL saturation blows up
        # near white/black (a warm paper tone like #F6F2F0 reads S=0.25 at
        # L=0.95 yet is visually neutral). Chroma = S * (1 - |2L - 1|)
        # discounts by lightness extremity, so near-white tints and
        # near-black shadows stay neutral while real accents still count.
        chroma = sat * (1.0 - abs(2.0 * _l - 1.0))
        if chroma < nonneutral_sat * 0.56:  # 0.18 * 0.56 ~= 0.10 chroma floor
            continue  # neutral (gray / near-white tint) — not a hue family
        hues.append(hue)

    centers = cluster_hues(hues, radius_deg=cluster_radius_deg)
    target_hues = [h for h in (
        hue_centers.get("accent"), hue_centers.get("gold")
    ) if h is not None]
    problems: list[str] = []
    if len(centers) > 2:
        problems.append(
            f"{len(centers)} non-neutral hue clusters "
            f"({', '.join('%.0f deg' % c for c in centers)}); at most 2 "
            "(accent + gold) are allowed."
        )
    if target_hues:
        for c in centers:
            nearest = min(_hue_dist(c, t) for t in target_hues)
            if nearest > center_tol_deg:
                problems.append(
                    f"hue cluster at {c:.0f} deg is {nearest:.0f} deg from "
                    f"the nearest palette center "
                    f"({'/'.join('%.0f' % t for t in target_hues)} deg); "
                    f"tolerance is {center_tol_deg:.0f} deg"
                )
    else:
        problems.append(
            "no accent/gold hue centers available (pass --tokens or define "
            "--accent/--gold in :root) — cannot verify cluster proximity"
        )
    if problems:
        r4.fail("; ".join(problems[:4]))
    else:
        r4.detail = (
            f"{len(centers)} hue cluster(s), all within {center_tol_deg:.0f}"
            f" deg of the palette"
        )
    results.append(r4)

    # --- Rule 12 (WARN): large dark area ---------------------------------
    r12 = RuleResult(12, "warn", "large dark area (kitsch warning)")
    frac = data["darkArea"] / data["posterArea"] if data["posterArea"] else 0.0
    if frac > dark_area_frac:
        r12.warn(
            f"dark (L<0.18) backgrounds cover {frac * 100:.1f}% of the "
            f"poster (> {dark_area_frac * 100:.0f}% threshold); large dark "
            "slabs read as 'kitsch'. Lighten or shrink them."
        )
    else:
        r12.detail = f"dark area = {frac * 100:.1f}% of poster (<= 8%)"
    results.append(r12)

    return results, None


# ---------------------------------------------------------------------------
# Hue-center resolution (--tokens JSON, else :root --accent/--gold).
# ---------------------------------------------------------------------------


def resolve_hue_centers(
    tokens_path: Path | None, token_block_text: str | None
) -> dict[str, float]:
    """Resolve accent/gold hue centers for rule 4.

    Priority: ``--tokens`` JSON ``hue_centers`` block (authoritative,
    IMPLEMENTATION_CONVENTIONS §F), then derive from the JSON's accent/gold
    base hexes, then fall back to parsing ``--accent`` / ``--gold`` literals
    out of the :root token block.
    """
    centers: dict[str, float] = {}
    if tokens_path is not None:
        try:
            doc = json.loads(tokens_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            _eprint(f"WARNING: could not read --tokens {ascii_safe(tokens_path)}"
                    f": {ascii_safe(e)}; falling back to :root.")
            doc = {}
        hc = doc.get("hue_centers") or {}
        for key in ("accent", "gold"):
            if key in hc:
                try:
                    centers[key] = float(hc[key]) % 360.0
                except (TypeError, ValueError):
                    pass
        # Derive from base hexes if hue_centers omitted a key.
        for key, sub in (("accent", "accent"), ("gold", "gold")):
            if key in centers:
                continue
            base = (doc.get(sub) or {}).get("base")
            h = _hue_from_hex(base) if base else None
            if h is not None:
                centers[key] = h
    # Fallback: parse --accent / --gold from the :root token block.
    if token_block_text:
        for key, var in (("accent", "--accent"), ("gold", "--gold")):
            if key in centers:
                continue
            m = re.search(
                re.escape(var) + r"\s*:\s*(#[0-9a-fA-F]{3,8})",
                token_block_text,
            )
            if m:
                h = _hue_from_hex(m.group(1))
                if h is not None:
                    centers[key] = h
    return centers


def _hue_from_hex(hex_str: str | None) -> float | None:
    """Hue (degrees) of a #RGB / #RRGGBB literal, or None if unparsable."""
    if not hex_str or not hex_str.startswith("#"):
        return None
    h = hex_str[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8):
        return None
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None
    hue, _s, _l = _hue_of_rgb(r, g, b)
    return hue


# ---------------------------------------------------------------------------
# Orchestration + CLI.
# ---------------------------------------------------------------------------


def _overall_status(results: list[RuleResult]) -> str:
    """PASS unless a HARD rule FAILED; WARN if no hard fail but a warning
    fired; else PASS. (SKIPPED rules never change the verdict.)
    """
    if any(r.severity == "hard" and r.status == "FAIL" for r in results):
        return "FAIL"
    if any(r.status == "WARN" for r in results):
        return "WARN"
    return "PASS"


def cmd_style_check(args: argparse.Namespace) -> int:
    html_path = Path(args.html).resolve()
    if not html_path.exists():
        _eprint(f"ERROR: HTML not found: {ascii_safe(html_path)}")
        return 2
    try:
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        _eprint(f"ERROR: cannot read HTML: {ascii_safe(e)}")
        return 2

    tokens_path = Path(args.tokens).resolve() if args.tokens else None
    if tokens_path is not None and not tokens_path.exists():
        _eprint(f"ERROR: --tokens not found: {ascii_safe(tokens_path)}")
        return 2

    # --- Source gate (always runs) --------------------------------------
    source_results, _parser, token_block_text = run_source_gate(
        html_text, html_path
    )

    # --- Render gate (rules 4, 12) --------------------------------------
    render_results: list[RuleResult]
    if args.no_render:
        render_results = [
            RuleResult(4, "hard", "<=2 non-neutral hue clusters").skip(
                "render gate skipped (--no-render)"
            ),
            RuleResult(12, "warn", "large dark area").skip(
                "render gate skipped (--no-render)"
            ),
        ]
        print("[style] NOTICE: --no-render set; rules 4 and 12 are SKIPPED. "
              "Overall status reflects the source gate only.")
    else:
        hue_centers = resolve_hue_centers(tokens_path, token_block_text)
        render_results, env_exit = run_render_gate(html_path, hue_centers)
        if env_exit is not None:
            # Environment unusable for the render gate. Per the CLI
            # contract an env error is exit 2 — don't masquerade as a PASS.
            return env_exit

    # Merge + order by rule id for stable output.
    all_results = sorted(
        source_results + render_results, key=lambda r: r.id
    )
    status = _overall_status(all_results)

    report = {
        "gate": "style",
        "status": status,
        "rules": [r.to_dict() for r in all_results],
    }

    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"[style] report -> {ascii_safe(args.json)}")

    # Human-readable summary to stdout.
    print(f"[style] overall = {status}")
    for r in all_results:
        print(f"  rule {r.id:>2} [{r.severity:>4}] {r.status:<7} "
              f"{ascii_safe(r.detail)}")

    return 1 if status == "FAIL" else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="style_check",
        description="Style HARD gate for HTML academic posters: 12 rules "
                    "(DESIGN_FINAL.md §3 + §12.5 nit 1). Source gate "
                    "(rules 1-3,5-11) is pure static analysis; render gate "
                    "(rules 4,12) print-emulates via Playwright.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="exit codes: 0=PASS (no hard fail), 1=hard fail, "
               "2=usage/environment error.",
    )
    p.add_argument("html", help="path to poster.html")
    p.add_argument(
        "--tokens", default=None,
        help="tokens JSON (IMPLEMENTATION_CONVENTIONS §F); its "
             "hue_centers/accent/gold drive rule 4. Default: derive accent/"
             "gold hue from the :root token block.",
    )
    p.add_argument(
        "--json", default=None,
        help="write the JSON report ({gate,status,rules}) to this path",
    )
    p.add_argument(
        "--no-render", action="store_true",
        help="skip the render gate; rules 4 and 12 are marked SKIPPED. The "
             "source gate still runs and can PASS on its own (a notice is "
             "printed).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return cmd_style_check(args)


if __name__ == "__main__":
    sys.exit(main())
