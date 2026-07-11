#!/usr/bin/env python3
"""poster_check — unified CLI for HTML academic posters.

Four subcommands:

  measure        Print-emulate HTML in headless Chromium, measure all
                 ``[data-measure-role]`` elements, report column-bottom
                 spread and gap to the next horizontal strip. The HARD
                 alignment gate (spread < 5 px is non-negotiable).
  preflight      Static HTML scan: LaTeX residue, raw '<' inside
                 ``$…$`` / ``$$…$$`` / ``\\(…\\)`` / ``\\[…\\]``,
                 missing local images, missing data-measure-role.
  polish         Visual-polish warnings on figure sizing, broken
                 images, typography orphans, and space-between fill.
                 Soft gate; warns by default. ``--strict`` to fail.
                 Hard-fails if there's no measurement markup at all.
  verify-final   Run ``pdfinfo`` on a rendered PDF; check page count,
                 dimensions match the expected canvas (``--canvas`` or
                 ``--from-html``), and file size under a limit.

All logic lives in the ``_posterly`` package next to this file. This
script is a thin argparse dispatcher.
"""
from __future__ import annotations

import argparse
import os
import sys

# Make `_posterly` importable when this file is run directly via
# `python tools/poster_check.py …`.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from _posterly import canvas as _canvas  # noqa: E402
from _posterly import measure as _measure  # noqa: E402
from _posterly import polish as _polish  # noqa: E402
from _posterly import preflight as _preflight  # noqa: E402
from _posterly import verify_final as _verify_final  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="poster_check",
        description="Measure / preflight / polish / verify a poster "
                    "HTML+PDF pair.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # --- measure --------------------------------------------------------
    pm = sub.add_parser(
        "measure",
        help="alignment + gap gate (print-emulated, HARD gate)",
    )
    pm.add_argument("html", help="path to poster.html")
    pm.add_argument(
        "--max-spread", type=float, default=5.0,
        help="hard gate: max column-bottom spread in px "
             "(default 5.0; aim < 3.0)",
    )
    pm.add_argument(
        "--min-gap", type=float, default=30.0,
        help="min gap to footer-strip/footer (default 30 px)",
    )
    pm.add_argument(
        "--max-gap", type=float, default=50.0,
        help="max gap to footer-strip/footer (default 50 px)",
    )
    pm.add_argument(
        "--canvas", type=_canvas.parse_canvas_arg, default=None,
        help="override canvas (e.g. '60x36in' or 'A0 portrait'); "
             "by default we parse @page from the HTML",
    )
    pm.add_argument(
        "--allow-empty-column", action="store_true",
        help="don't fail when a column has no cards "
             "(fallback to column.bottom; risky)",
    )
    pm.add_argument(
        "--allow-no-footer-gap", action="store_true",
        help="don't fail when neither footer-strip nor footer exists "
             "below the content",
    )
    pm.add_argument(
        "--settle-ms", type=int, default=500,
        help="extra wait after MathJax + fonts.ready settle "
             "(default 500)",
    )
    pm.add_argument(
        "--mathjax-timeout-ms", type=int, default=15000,
        help="hard timeout for MathJax typeset (default 15000); "
             "exceeding it FAILS the gate, not warns",
    )
    pm.add_argument(
        "--min-canvas-fill", type=float, default=0.95,
        help="hard gate: [data-measure-role='poster'] must fill at "
             "least this fraction of the print viewport in BOTH "
             "dimensions (default 0.95). Catches the silent 'forgot "
             "the print media-query unit override' bug where the "
             "poster renders at screen scale into a much bigger "
             "print page.",
    )
    pm.add_argument(
        "--max-canvas-fill", type=float, default=1.01,
        help="hard gate: poster must NOT exceed this fraction of the "
             "print viewport (default 1.01; i.e. <=1%% overshoot is "
             "tolerated for sub-pixel rounding). The symmetric of "
             "--min-canvas-fill catches the case where a hardcoded "
             "`width` in px exceeds `@page size`.",
    )
    pm.add_argument(
        "--position-tol-px", type=float, default=2.0,
        help="hard gate: poster's bbox edges must align with the print "
             "viewport's origin within this many px (default 2.0). "
             "Catches `transform: translate*`, mis-positioned absolute "
             "layout, and stray body margin in print.",
    )
    pm.add_argument(
        "--max-clip-px", type=float, default=2.0,
        help="hard gate: a card/column/hero whose content is clipped by "
             "overflow:hidden|clip|scroll|auto by MORE than this many px "
             "(scrollHeight-clientHeight) FAILS -- clipped content is "
             "silently lost in print while the box still looks aligned "
             "(default 2.0; sub-pixel rounding tolerated).",
    )
    pm.add_argument(
        "--max-intercard-gap", type=float,
        default=_measure.DEFAULT_MAX_INTERCARD_GAP,
        help="hard gate: max whitespace between consecutive stacked "
             "cards in a column (default 50 px, same ceiling as the "
             "footer gap). Catches `justify-content: space-between` "
             "faking bottom alignment on an under-filled column -- "
             "spread reads ~0 while a void sits mid-column.",
    )
    pm.add_argument(
        "--min-intercard-gap", type=float,
        default=_measure.DEFAULT_MIN_INTERCARD_GAP,
        help="hard gate: min whitespace between consecutive stacked "
             "cards (default 12 px). Tighter gaps bury the card's drop "
             "shadow (templates ship `0 2u 6u`) under the next card, "
             "fusing the stack into one slab. Set 0 to disable for "
             "shadowless themes.",
    )
    pm.add_argument(
        "--json-out", default=None,
        help="dump raw measurement to JSON",
    )
    pm.set_defaults(func=_measure.cmd_measure)

    # --- preflight ------------------------------------------------------
    pp = sub.add_parser(
        "preflight",
        help="static HTML lint (LaTeX residue, math, images, roles)",
    )
    pp.add_argument("html", help="path to poster.html")
    pp.set_defaults(func=_preflight.cmd_preflight)

    # --- polish ---------------------------------------------------------
    ppl = sub.add_parser(
        "polish",
        help="visual-polish warnings (figure size, orphans, "
             "space-between, flex/<br>)",
    )
    ppl.add_argument("html", help="path to poster.html")
    ppl.add_argument(
        "--canvas", type=_canvas.parse_canvas_arg, default=None,
        help="override canvas (default: parse @page from HTML)",
    )
    ppl.add_argument(
        "--settle-ms", type=int, default=500,
        help="extra wait after layout settles (default 500)",
    )
    ppl.add_argument(
        "--mathjax-timeout-ms", type=int, default=15000,
        help="hard timeout for MathJax typeset (default 15000)",
    )
    ppl.add_argument(
        "--wide-min-ratio", type=float, default=0.65,
        help="wide figures (AR>1.3) must occupy >= this fraction of "
             "card width (default 0.65)",
    )
    ppl.add_argument(
        "--tall-max-ratio", type=float, default=0.70,
        help="tall figures (AR<0.8) above this fraction trigger a "
             "text-right recommendation (default 0.70)",
    )
    ppl.add_argument(
        "--square-min-ratio", type=float, default=0.55,
        help="square figures (0.8<=AR<=1.3) must occupy >= this "
             "fraction (default 0.55)",
    )
    ppl.add_argument(
        "--max-space-between-fill", type=float, default=0.05,
        help="warn if a space-between column has an inter-card gap "
             "exceeding this fraction of column height (default 0.05)",
    )
    ppl.add_argument(
        "--max-card-trailing", type=float, default=0.10,
        help="warn (CARD/TRAILING) if a card leaves more than this "
             "fraction of its height blank below the last line "
             "(default 0.10); catches a flex-stretched card padded "
             "with whitespace to fake a full page",
    )
    ppl.add_argument(
        "--strict", action="store_true",
        help="exit non-zero when any warning is emitted",
    )
    ppl.set_defaults(func=_polish.cmd_polish)

    # --- verify-final ---------------------------------------------------
    pv = sub.add_parser(
        "verify-final",
        help="run pdfinfo + size/dimension/page checks on PDF",
    )
    pv.add_argument("pdf", help="path to poster.pdf")
    pv.add_argument(
        "--canvas", type=_canvas.parse_canvas_arg, default=None,
        help="expected canvas (e.g. '60x36in' or 'A0 portrait'); "
             "either this or --from-html is required",
    )
    pv.add_argument(
        "--from-html", default=None,
        help="read expected canvas from `@page { size }` in this "
             "HTML; mutually exclusive with --canvas",
    )
    pv.add_argument(
        "--dim-tol-in", type=float, default=0.05,
        help="dimension tolerance in inches (default 0.05)",
    )
    pv.add_argument(
        "--max-size-mb", type=float, default=20.0,
        help="max file size in MB (default 20)",
    )
    pv.add_argument(
        "--allow-rotated", action="store_true",
        help="accept swapped W/H even when PDF declares no page "
             "rotation (most posters should NOT need this)",
    )
    pv.set_defaults(func=_verify_final.cmd_verify_final)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
