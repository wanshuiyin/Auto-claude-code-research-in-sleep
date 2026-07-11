"""Canvas (page-size) parsing utilities, shared by all CLIs.

Two input sources for canvas dimensions:
  1. The ``@page { size: W H }`` declaration inside the poster HTML's
     ``<style>`` blocks. This is the canonical source — every CLI parses
     it first so layout decisions stay tied to what Chromium actually
     renders.
  2. The ``--canvas`` CLI argument as an override. Accepts:
       - ``60x36in``, ``914x1194mm`` (numeric W x H + unit)
       - ``A0 portrait``, ``A1 landscape`` (ISO 216 named sizes)

Returns inches everywhere; callers convert to viewport px via
``viewport_for(canvas_in)`` at 96 ppi (Chromium's print pixel basis).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from .textutil import ascii_safe


# Conversion factors → inches.
UNIT_TO_IN: dict[str, float] = {
    "in": 1.0,
    "mm": 1.0 / 25.4,
    "cm": 1.0 / 2.54,
    "pt": 1.0 / 72.0,
}

# ISO 216 paper sizes (portrait W x H, in mm).
NAMED_SIZES_MM: dict[str, tuple[float, float]] = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
}


def _extract_style_css(html_text: str) -> str:
    """Concatenate the contents of all ``<style>…</style>`` blocks with
    CSS comments stripped. The only place to look for ``@page`` — never
    raw HTML body, never ``<script>``.
    """
    blocks = re.findall(
        r"<style[^>]*>(.*?)</style>",
        html_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    css = "\n".join(blocks)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return css


def read_canvas_from_html(html_path: Path) -> tuple[float, float] | None:
    """Parse ``@page { size: ... }`` from ``<style>`` blocks.

    Supports both numeric and named-size forms:

      - ``@page { size: 60in 36in; }`` (numeric, `in`/`mm`/`cm`/`pt`)
      - ``@page { size: A0 portrait; }`` / ``A1 landscape`` (CSS named
        page sizes — same set as ``parse_canvas_arg``)

    Numeric dimensions may mix units (``24in 914mm``). Named pages
    (``@page poster { size: ... }``) are recognised too. Returns
    ``(width_in, height_in)`` or ``None`` on parse failure — callers
    must either require ``--canvas`` or exit non-zero. We refuse to
    silently fall back to a hardcoded default.
    """
    txt = html_path.read_text(encoding="utf-8", errors="ignore")
    css = _extract_style_css(txt)

    # Find EVERY `@page … { … size: <value>; … }` candidate (numeric
    # or named) and try to parse each. Earlier versions stopped at the
    # first numeric match, so an `@page { size: auto }` declaration
    # before a real `@page { size: A0 landscape }` would mask the latter
    # and the parser returned None. Iterate and accept the LAST that
    # parses — matching CSS cascade for paged media.
    pattern = re.compile(
        r"@page(?:\s+[A-Za-z_-][\w:-]*)?\s*\{[^}]*?size\s*:\s*"
        r"([^;{}]+?)\s*(?:!\s*important\s*)?[;}]",
        re.IGNORECASE,
    )
    last_parsed: tuple[float, float] | None = None
    for m in pattern.finditer(css):
        raw = m.group(1).strip()
        # 1) Numeric form: `<num><unit> <num><unit>` (units may differ).
        m_num = re.fullmatch(
            r"((?:\d+(?:\.\d*)?|\.\d+))\s*(in|mm|cm|pt)\s+"
            r"((?:\d+(?:\.\d*)?|\.\d+))\s*(in|mm|cm|pt)",
            raw,
            re.IGNORECASE,
        )
        if m_num:
            w = float(m_num.group(1)) * UNIT_TO_IN[m_num.group(2).lower()]
            h = float(m_num.group(3)) * UNIT_TO_IN[m_num.group(4).lower()]
            last_parsed = (w, h)
            continue
        # 2) Named form: delegate to parse_canvas_arg so both code paths
        #    agree on what counts as a valid `<NamedSize> [orient]` /
        #    `<orient> <NamedSize>` value.
        try:
            last_parsed = parse_canvas_arg(raw)
        except argparse.ArgumentTypeError:
            # Skip this @page (e.g. `size: auto`) and keep looking.
            continue
    return last_parsed


def parse_canvas_arg(s: str) -> tuple[float, float]:
    """Argparse-friendly parser for ``--canvas`` values.

    Accepts:
      - ``60x36in``, ``914x1194mm``, ``60x36cm`` (one unit at end)
      - ``A0 portrait``, ``A0 landscape``, ``A1 portrait``, …
    Returns ``(width_in, height_in)``.

    Raises ``argparse.ArgumentTypeError`` so argparse formats the error
    cleanly without a stack trace.
    """
    s = s.strip()
    # Form 1: <W>x<H><unit>
    m = re.fullmatch(
        r"((?:\d+(?:\.\d*)?|\.\d+))\s*[x×]\s*"
        r"((?:\d+(?:\.\d*)?|\.\d+))\s*(in|mm|cm|pt)",
        s,
        re.IGNORECASE,
    )
    if m:
        unit = m.group(3).lower()
        w = float(m.group(1)) * UNIT_TO_IN[unit]
        h = float(m.group(2)) * UNIT_TO_IN[unit]
        return w, h
    # Form 2: CSS Paged Media value `<NamedSize> | <Orient> |
    # <NamedSize> <Orient> | <Orient> <NamedSize>` (the spec lets
    # orientation appear before OR after the size keyword).
    parts = re.split(r"\s+", s)
    if 1 <= len(parts) <= 2:
        name_token = orient_token = None
        for part in parts:
            up = part.upper()
            lo = part.lower()
            if up in NAMED_SIZES_MM and name_token is None:
                name_token = up
            elif lo in ("portrait", "landscape") and orient_token is None:
                orient_token = lo
            else:
                name_token = orient_token = None
                break
        if name_token is not None:
            orient = orient_token or "portrait"
            w_mm, h_mm = NAMED_SIZES_MM[name_token]
            if orient == "landscape":
                w_mm, h_mm = h_mm, w_mm
            return w_mm / 25.4, h_mm / 25.4
    raise argparse.ArgumentTypeError(
        f"--canvas expects '<W>x<H><unit>' (e.g. '60x36in') or "
        f"'<NamedSize> [portrait|landscape]' (e.g. 'A0 portrait'); "
        f"got {ascii_safe(s)!r}. Named sizes: "
        f"{', '.join(sorted(NAMED_SIZES_MM))}."
    )


def viewport_for(canvas_in: tuple[float, float]) -> tuple[int, int]:
    """Convert (W_in, H_in) to (W_px, H_px) at 96 ppi.

    Playwright's print-emulation uses CSS pixels at 96 ppi, so the
    viewport must match that basis or measurement units shift.
    """
    w_in, h_in = canvas_in
    return (int(round(w_in * 96)), int(round(h_in * 96)))


def resolve_canvas(
    html_path: Path,
    canvas_override: tuple[float, float] | None,
    label: str,
) -> tuple[tuple[float, float], tuple[int, int]] | None:
    """Resolve canvas from CLI override (preferred) or HTML's ``@page``.

    Prints a one-liner to stdout describing which source was used.
    Returns ``(canvas_in, viewport_px)`` on success, ``None`` on failure
    (caller exits 2 after this). ``label`` is the CLI's logger prefix
    (e.g. ``[measure]``).
    """
    if canvas_override is not None:
        canvas = canvas_override
        print(f"{label} canvas (--canvas override) = "
              f"{canvas[0]:.2f}in x {canvas[1]:.2f}in")
    else:
        parsed = read_canvas_from_html(html_path)
        if parsed is None:
            return None
        canvas = parsed
        print(f"{label} canvas = {canvas[0]:.2f}in x {canvas[1]:.2f}in")
    viewport = viewport_for(canvas)
    print(f"{label} viewport = {viewport[0]} x {viewport[1]} px")
    return canvas, viewport
