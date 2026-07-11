"""Final-PDF sanity check via ``pdfinfo``.

Checks the rendered PDF is exactly what was asked for:

  - **page count == 1** (a multi-page export almost always means the
    canvas size and ``@page { size }`` disagreed)
  - **dimensions match the expected canvas** within ±0.05 in
    (default; ``--dim-tol-in`` to tune)
  - **file size <= --max-size-mb** (overlarge PDFs often mean an
    accidentally embedded raw image or 600 dpi figure)

The expected canvas can come from:

  - ``--canvas '<W>x<H><unit>'`` (e.g. ``60x36in`` / ``A0 portrait``)
  - ``--from-html poster.html`` (parses the same ``@page`` rule the
    HTML uses, so the verification can't drift from the source)

Exactly one of those must be supplied — no hardcoded landscape default.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import canvas as _canvas
from .textutil import ascii_safe


def _eprint(*args: Any, **kw: Any) -> None:
    print(*args, file=sys.stderr, **kw)


def cmd_verify_final(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf).resolve()
    if not pdf.exists():
        _eprint(f"ERROR: PDF not found: {ascii_safe(pdf)}")
        return 2

    # Resolve expected canvas.
    if args.canvas is None and args.from_html is None:
        _eprint(
            "ERROR: verify-final needs either `--canvas <W>x<H><unit>` "
            "(e.g. '60x36in' or 'A0 portrait') or `--from-html "
            "<poster.html>` so the expected size can't be wrong by "
            "default."
        )
        return 2
    if args.canvas is not None and args.from_html is not None:
        _eprint(
            "ERROR: --canvas and --from-html are mutually exclusive; "
            "pick one."
        )
        return 2
    if args.canvas is not None:
        exp_w, exp_h = args.canvas
        src = "--canvas"
    else:
        html_path = Path(args.from_html).resolve()
        if not html_path.exists():
            _eprint(f"ERROR: --from-html path not found: {ascii_safe(html_path)}")
            return 2
        parsed = _canvas.read_canvas_from_html(html_path)
        if parsed is None:
            _eprint(
                f"ERROR: no `@page {{ size }}` found in "
                f"{ascii_safe(html_path)}. Fall back to --canvas."
            )
            return 2
        exp_w, exp_h = parsed
        src = f"--from-html ({ascii_safe(html_path.name)})"

    # Preserve user PATH (Homebrew/conda/etc.) but force C locale so
    # pdfinfo number formatting is consistent across systems.
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    try:
        out = subprocess.check_output(
            ["pdfinfo", str(pdf)],
            text=True, stderr=subprocess.STDOUT, env=env,
        )
    except FileNotFoundError:
        _eprint(
            "ERROR: pdfinfo not installed. Install poppler:\n"
            "  Linux:   apt install poppler-utils  "
            "(or `dnf install poppler-utils`)\n"
            "  macOS:   brew install poppler\n"
            "  Windows: choco install poppler  (or download from "
            "poppler-windows)"
        )
        return 2
    except subprocess.CalledProcessError as e:
        _eprint(f"ERROR: pdfinfo failed: {ascii_safe(e.output)}")
        return 2

    info: dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()

    pages = int(info.get("Pages", "0"))
    page_size = info.get("Page size", "")
    page_rot = int(info.get("Page rot", "0") or "0")
    file_size_b = pdf.stat().st_size
    file_size_mb = file_size_b / (1024 * 1024)

    print(f"[verify-final] {ascii_safe(pdf)}")
    print(f"  expected canvas = {exp_w:.2f}in x {exp_h:.2f}in  "
          f"(from {src})")
    print(f"  pages           = {pages}")
    print(f"  page size       = {ascii_safe(page_size)}")
    print(f"  page rot        = {page_rot}")
    print(f"  file size       = {file_size_mb:.2f} MB")

    problems: list[str] = []

    if pages != 1:
        problems.append(f"page count = {pages}, expected 1")

    # pdfinfo's Page size is in points (1pt = 1/72 in).
    m = re.search(r"([\d.]+)\s*x\s*([\d.]+)\s*pts", page_size)
    if not m:
        problems.append(
            f"could not parse pdfinfo `Page size`: {ascii_safe(page_size)!r}"
        )
    else:
        w_in = float(m.group(1)) / 72.0
        h_in = float(m.group(2)) / 72.0
        print(f"  -> {w_in:.2f}in x {h_in:.2f}in")
        tol = args.dim_tol_in
        direct_ok = (
            abs(w_in - exp_w) <= tol and abs(h_in - exp_h) <= tol
        )
        swap_ok = (
            abs(w_in - exp_h) <= tol and abs(h_in - exp_w) <= tol
        )
        allow_swap = args.allow_rotated or page_rot in (90, 270)
        if direct_ok:
            pass
        elif swap_ok and allow_swap:
            print(
                f"  (swapped dimensions accepted -- page rot = "
                f"{page_rot}deg"
                + (" + --allow-rotated" if args.allow_rotated else "")
                + ")"
            )
        else:
            problems.append(
                f"dimensions {w_in:.2f}x{h_in:.2f}in "
                f"do not match canvas {exp_w}x{exp_h}in "
                f"(tol +/-{tol}in, page rot {page_rot}deg)"
            )

    if file_size_mb > args.max_size_mb:
        problems.append(
            f"file {file_size_mb:.2f} MB > limit "
            f"{args.max_size_mb} MB"
        )

    for p in problems:
        _eprint(f"  FAIL: {p}")
    if problems:
        return 1
    print("[verify-final] PASS")
    return 0
