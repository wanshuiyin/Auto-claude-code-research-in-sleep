#!/usr/bin/env python3
"""render_preview - render a poster HTML to print-ready PDF + thumbnail.

Canvas-agnostic: reads ``@page { size: <W> <H> }`` from the input HTML
or accepts ``--canvas '<W>x<H>in'`` / ``--canvas 'A0 portrait'`` as
override. Print-emulates Chromium so MathJax typesets against the
``@media print`` layout from the start.

This is the SOFT path (vs the HARD ``measure`` gate): a MathJax
typeset timeout or a missing ``<mjx-container>`` warns and continues
— users would rather see raw ``$…$`` on the rendered PDF than a
silent abort.

Outputs:
    <stem>_preview.pdf   exact-size PDF
    <stem>_preview.png   scaled thumbnail (default 0.35×)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make `_posterly` importable when run directly.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from _posterly import canvas as _canvas  # noqa: E402
from _posterly import render as _render  # noqa: E402
from _posterly.textutil import ascii_safe  # noqa: E402


def _eprint(*args: object, **kw: object) -> None:
    print(*args, file=sys.stderr, **kw)  # type: ignore[arg-type]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0]
    )
    p.add_argument("html", help="poster HTML file")
    p.add_argument(
        "--pdf", default=None,
        help="output PDF path (default: <stem>_preview.pdf)",
    )
    p.add_argument(
        "--png", default=None,
        help="output PNG thumbnail path (default: <stem>_preview.png)",
    )
    p.add_argument(
        "--thumb-scale", type=float, default=0.35,
        help="thumbnail scale factor (default 0.35)",
    )
    p.add_argument(
        "--mathjax-timeout-ms", type=int, default=15000,
        help="timeout for MathJax typesetting (default 15000); "
             "render is the SOFT path; timeout warns, not fails",
    )
    p.add_argument(
        "--canvas", type=_canvas.parse_canvas_arg, default=None,
        help="override canvas (e.g. '60x36in' / 'A0 portrait'); "
             "by default we parse @page from the HTML",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        _eprint(f"ERROR: HTML not found: {ascii_safe(html_path)}")
        return 2

    pdf_path = (
        Path(args.pdf) if args.pdf
        else html_path.with_name(html_path.stem + "_preview.pdf")
    )
    png_path = (
        Path(args.png) if args.png
        else html_path.with_name(html_path.stem + "_preview.png")
    )

    resolved = _canvas.resolve_canvas(
        html_path, args.canvas, label="[render_preview]"
    )
    if resolved is None:
        _eprint(
            "ERROR: could not find `@page { size: <W> <H> }` in HTML. "
            "Add an @page rule (units: in/mm/cm/pt) or pass "
            "`--canvas <W>x<H>in` / `--canvas 'A0 portrait'`. "
            "Refusing to silently fall back."
        )
        return 2
    canvas, viewport = resolved
    w_in, h_in = canvas

    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeoutError
    except ImportError:
        _eprint("ERROR: playwright not installed. Run:")
        _eprint("  python -m pip install playwright")
        _eprint("  python -m playwright install chromium")
        return 2

    with sync_playwright() as p_:
        browser, _ctx, page = _render.open_print_emulated_page(
            p_, viewport
        )
        # Soft path: a hung CDN (blocked MathJax fetch, unreachable
        # web font) must not hard-crash render. Playwright's default
        # `page.goto` waits for `load` (all subresources), which can
        # block ~30s on a single blocked CDN. settle_page below has
        # its own bounded waits; let it surface MathJax issues as
        # warnings, not tracebacks.
        try:
            page.goto(html_path.as_uri(), timeout=args.mathjax_timeout_ms)
        except PWTimeoutError:
            _eprint(
                f"[render_preview] WARN: page.goto did not reach `load` "
                f"within {args.mathjax_timeout_ms} ms; continuing with "
                f"whatever has loaded (a CDN or external resource is "
                f"likely blocked)."
            )
        try:
            page.wait_for_load_state(
                "networkidle", timeout=args.mathjax_timeout_ms,
            )
        except PWTimeoutError:
            _eprint(
                f"[render_preview] WARN: network never went idle within "
                f"{args.mathjax_timeout_ms} ms; continuing with whatever "
                f"loaded (likely a slow/blocked external resource)."
            )

        settle = _render.settle_page(
            page,
            mathjax_timeout_ms=args.mathjax_timeout_ms,
            settle_ms=1500,
        )
        # Render is soft path: warn but continue, even on MathJax
        # problems — the user can SEE raw $...$ on the resulting PDF.
        if settle.mathjax_status == "timeout":
            _eprint(
                f"[render_preview] WARN: MathJax typeset timed out "
                f"after {args.mathjax_timeout_ms} ms."
            )
        elif settle.mathjax_status == "error":
            _eprint(
                f"[render_preview] WARN: MathJax error: "
                f"{ascii_safe(settle.mathjax_error)}"
            )
        if settle.mathjax_intended and settle.tex_without_mathjax:
            _eprint(
                "[render_preview] WARN: page intended to load MathJax "
                "but no <mjx-container> rendered -- MathJax may have "
                "failed to load. PDF will show raw $...$ text."
            )

        # ---- PDF: exact poster size, print-emulated ----
        page.pdf(
            path=str(pdf_path),
            width=f"{w_in}in",
            height=f"{h_in}in",
            print_background=True,
            margin={"top": "0", "bottom": "0",
                    "left": "0", "right": "0"},
        )

        # ---- PNG: scaled thumbnail of `.poster` (or document body) ----
        s = args.thumb_scale
        page.evaluate(
            f"""() => {{
                const el = document.querySelector(
                       '[data-measure-role="poster"]')
                       || document.querySelector('.poster')
                       || document.body;
                el.style.transformOrigin = 'top left';
                el.style.transform = 'scale({s})';
                document.body.style.width  =
                    (el.offsetWidth  * {s}) + 'px';
                document.body.style.height =
                    (el.offsetHeight * {s}) + 'px';
                document.body.style.overflow = 'hidden';
                document.body.style.margin = '0';
            }}"""
        )
        thumb_w = int(round(w_in * 96 * s))
        thumb_h = int(round(h_in * 96 * s))
        page.set_viewport_size(
            {"width": thumb_w, "height": thumb_h}
        )
        page.screenshot(
            path=str(png_path),
            full_page=False,
            clip={"x": 0, "y": 0,
                  "width": thumb_w, "height": thumb_h},
        )

        browser.close()

    print(
        f"[render_preview] PDF -> {ascii_safe(pdf_path)}  "
        f"({pdf_path.stat().st_size / 1024:.1f} KB)"
    )
    print(
        f"[render_preview] PNG -> {ascii_safe(png_path)}  "
        f"({png_path.stat().st_size / 1024:.1f} KB)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
