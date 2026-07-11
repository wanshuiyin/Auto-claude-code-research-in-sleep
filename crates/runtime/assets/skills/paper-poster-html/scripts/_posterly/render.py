"""Shared Playwright launch + page-settle helpers.

Used by ``measure``, ``polish``, and ``render_preview``. Centralises:

1. Print-emulated Chromium context at the correct viewport.
2. MathJax detection + bounded typeset wait (so a stuck CDN can't
   hang the script forever).
3. ``document.fonts.ready`` + two RAFs + a fixed settle ms — so
   the layout is locked before any geometry is read.
4. A sanity check that catches the "page has ``$…$`` TeX in body text
   but no rendered ``<mjx-container>``" case — MathJax never ran
   (CDN blocked, script error, …). Measurement / polish must NOT
   silently pass against a raw-TeX layout.

The ``settle_page`` helper returns a :class:`SettleResult` with the raw
status flags. ``measure``/``polish`` treat MathJax issues as hard fails;
``render_preview`` warns and continues (rendering raw-TeX is at least
visible to the user, whereas a silent measure PASS isn't).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .textutil import ascii_safe


def _eprint(*args: Any, **kw: Any) -> None:
    print(*args, file=sys.stderr, **kw)


@dataclass
class SettleResult:
    mathjax_intended: bool
    """The page intended to load MathJax — either a ``<script src=…mathjax…>``
    tag is present or ``window.MathJax`` config was set. Used to gate the
    ``tex_without_mathjax`` failure: a poster that documents TeX syntax in
    prose without ever loading MathJax is a perfectly valid use case and
    must NOT trip the sanity check."""

    has_mathjax: bool
    """``window.MathJax.startup.promise`` was defined at settle time
    (MathJax actually initialized)."""

    mathjax_status: str
    """One of ``'ok'``, ``'timeout'``, ``'error'``, ``'not-needed'``."""

    mathjax_error: str | None
    """Exception message if ``mathjax_status == 'error'``, else None."""

    tex_without_mathjax: bool
    """Body innerText has TeX delimiters but no ``<mjx-container>`` rendered.
    Only counted as a failure when ``mathjax_intended`` is True (otherwise
    the ``$…$`` is most likely prose, not math)."""


def open_print_emulated_page(p, viewport_px: tuple[int, int]):
    """Launch headless Chromium, open a context+page at the viewport,
    emulate print media. Returns ``(browser, ctx, page)``.

    Print emulation is set BEFORE navigation by the caller (via
    ``page.emulate_media``), so MathJax typesets against ``@media print``
    layout from the start. Without that, the screen-mode ``--u`` value
    leaks in and measurement is unreliable.
    """
    w, h = viewport_px
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": w, "height": h})
    page = ctx.new_page()
    page.emulate_media(media="print")
    page.set_viewport_size({"width": w, "height": h})
    return browser, ctx, page


def settle_page(
    page,
    *,
    mathjax_timeout_ms: int = 15000,
    settle_ms: int = 500,
) -> SettleResult:
    """Wait for MathJax, fonts, two RAFs, and an extra fixed ms.

    Returns a :class:`SettleResult` rather than raising — the caller
    decides whether each flag is a hard fail or a soft warning.
    Idempotent on math-free pages: detection is synchronous and the
    typeset wait is skipped when MathJax wasn't loaded.
    """
    # 1a) Did the page INTEND to load MathJax? A <script src="…mathjax…">
    #     tag OR a window.MathJax config object counts. Used to decide
    #     whether stray `$…$` in body text is "math that failed to render"
    #     (intended) vs "prose that happens to mention TeX" (not intended).
    try:
        mathjax_intended = bool(page.evaluate(
            "() => !!(document.querySelector('script[src*=\"mathjax\" i]') "
            "|| (window.MathJax && Object.keys(window.MathJax).length > 0))"
        ))
    except Exception:
        mathjax_intended = False

    # 1b) Did MathJax actually initialise?
    try:
        has_mj = bool(page.evaluate(
            "() => !!(window.MathJax && window.MathJax.startup "
            "&& window.MathJax.startup.promise)"
        ))
    except Exception:
        has_mj = False

    mj_status = "not-needed"
    mj_error: str | None = None

    # 2) If present, bound the typeset wait with Promise.race so a
    #    stuck MathJax can't hang us.
    if has_mj:
        mj_js = (
            f"() => Promise.race(["
            f"  MathJax.startup.promise"
            f"    .then(() => (MathJax.typesetPromise"
            f"      ? MathJax.typesetPromise() : null))"
            f"    .then(() => 'ok'),"
            f"  new Promise(r => setTimeout("
            f"    () => r('timeout'), {mathjax_timeout_ms}))"
            f"])"
        )
        try:
            mj_status = page.evaluate(mj_js) or "timeout"
        except Exception as e:
            mj_status = "error"
            mj_error = str(e)

    # 3) Fonts (best-effort) + two RAFs + fixed settle ms.
    try:
        page.evaluate(
            "() => document.fonts && document.fonts.ready "
            "? document.fonts.ready : null"
        )
    except Exception:
        pass
    page.evaluate(
        "() => new Promise(r => "
        "requestAnimationFrame(() => requestAnimationFrame(r)))"
    )
    page.wait_for_timeout(settle_ms)

    # 4) Sanity check for the silent-fail case: page has TeX in body
    #    text but no rendered mjx-container. Covers all four delimiter
    #    pairs the templates configure (`$...$`, `$$...$$`, `\(...\)`,
    #    `\[...\]`). No length bound — earlier `{1,1500}` regex limits
    #    were Codex-flagged for letting long raw-TeX paste slip past.
    #    `[^$\n]+` (inline) and `[\s\S]+?` (display, non-greedy) avoid
    #    catastrophic backtracking even on multi-paragraph segments.
    try:
        sanity = page.evaluate(
            "() => {"
            "  const has_mjx = "
            "    document.querySelectorAll('mjx-container').length > 0;"
            "  const txt = document.body && document.body.innerText || '';"
            "  const has_dollar  = /\\$[^$\\n]+\\$/.test(txt);"
            "  const has_ddollar = /\\$\\$[\\s\\S]+?\\$\\$/.test(txt);"
            "  const has_paren   = /\\\\\\([\\s\\S]+?\\\\\\)/.test(txt);"
            "  const has_brack   = /\\\\\\[[\\s\\S]+?\\\\\\]/.test(txt);"
            "  return {has_mjx, has_tex: has_dollar || has_ddollar "
            "                          || has_paren  || has_brack};"
            "}"
        )
        tex_without_mathjax = bool(
            sanity.get("has_tex") and not sanity.get("has_mjx")
        )
    except Exception:
        tex_without_mathjax = False

    return SettleResult(
        mathjax_intended=mathjax_intended,
        has_mathjax=has_mj,
        mathjax_status=mj_status,
        mathjax_error=mj_error,
        tex_without_mathjax=tex_without_mathjax,
    )


def hard_fail_on_settle_problems(
    result: SettleResult,
    *,
    mathjax_timeout_ms: int,
) -> str | None:
    """Return a one-line failure message if ``measure`` / ``polish``
    must hard-fail given a settle result, else None.

    Centralised so the two strict gates agree on what counts as a fail.
    """
    if result.mathjax_status == "error":
        return (
            f"MathJax typeset error: {ascii_safe(result.mathjax_error)}. "
            f"Refusing to measure a broken-script page."
        )
    if result.mathjax_status == "timeout":
        return (
            f"MathJax typeset did not finish within "
            f"{mathjax_timeout_ms} ms. Refusing to measure a "
            f"partially typeset poster."
        )
    # Only fail when MathJax was INTENDED to load (script tag or config
    # present) but didn't render anything. A poster that documents TeX
    # syntax in prose without ever loading MathJax is a valid use case.
    if result.mathjax_intended and result.tex_without_mathjax:
        return (
            "page intended to load MathJax (script/config present) "
            "but no rendered <mjx-container> was found despite TeX "
            "delimiters in body text. MathJax likely failed to load "
            "(CDN block? script error?). Refusing to measure raw-TeX "
            "layout."
        )
    return None
