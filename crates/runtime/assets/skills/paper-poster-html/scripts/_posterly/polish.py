"""Soft visual-polish gate — runs at Step 6.

Three gates the hard alignment gate cannot see:

  - **Gate A: figure sizing by aspect ratio.** A wide figure (AR > 1.3)
    rendered at 38% of card width wastes 60% of the column even when
    columns align. The defaults match the documented "aim for" lower
    bounds in SKILL.md so any figure inside the recommended range
    passes cleanly.
  - **Gate B: typography orphans.** ``1.18-1.30× ↑`` whose ``↑``
    wrapped alone onto its own line. Detected on elements with
    ``[class*="stat"]`` / ``[class*="num"]`` / ``.takeaway-num`` /
    ``.headline-num`` that end with a known orphan-prone glyph but
    lack ``white-space: nowrap``.
  - **Gate C: space-between fill.** ``justify-content: space-between``
    on a column with one short card produces a giant whitespace gap
    that reads as "this column ran out of things to say". Detected
    when the largest inter-card gap exceeds the column's stated
    ``row-gap`` by > 5% of column height.

Warns by default; ``--strict`` to exit non-zero. Hard-fails if the
poster has no ``[data-measure-role]`` markup at all — a polish PASS on
"0 figures, 0 columns, 0 stat elements" would be misleading.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from . import canvas as _canvas
from . import preflight as _preflight
from . import render as _render


# Trailing glyphs that orphan when wrapped: arrows, multiplicative
# cross, division, plus-minus, footnote markers, degree, percent.
ORPHAN_GLYPHS = "↑↓↔×÷±§¶†‡*°%"


from .textutil import ascii_safe


def _eprint(*args: Any, **kw: Any) -> None:
    print(*args, file=sys.stderr, **kw)


_POLISH_JS = r"""
() => {
  // ---- 1) Figure sizing ----
  // For each card, list every <img> with rendered size, the card's
  // bounding width (the "budget"), and natural dimensions for AR.
  const figures = [];
  document.querySelectorAll('[data-measure-role="card"]')
    .forEach((card, ci) => {
      const cw = card.getBoundingClientRect().width;
      card.querySelectorAll('img').forEach(img => {
        const r = img.getBoundingClientRect();
        if (r.width < 50) return;  // skip inline icons
        figures.push({
          card_index: ci,
          role: 'card',
          src: img.getAttribute('src') || '',
          alt: img.getAttribute('alt') || '',
          fig_layout: img.getAttribute('data-fig-layout') || '',
          rendered_w: r.width,
          rendered_h: r.height,
          card_w: cw,
          natural_w: img.naturalWidth || 0,
          natural_h: img.naturalHeight || 0,
        });
      });
    });
  // Hero-panel images (the main figure of a hero-layout poster) get the
  // broken-image check too -- a blank centerpiece is the worst failure
  // mode and the card-only scan used to miss it. AR sizing gates are
  // skipped for these on the Python side (they are framed as % of card
  // width, which the full-bleed hero panel doesn't have).
  document.querySelectorAll('[data-measure-role="hero"]')
    .forEach(hero => {
      const hw = hero.getBoundingClientRect().width;
      hero.querySelectorAll('img').forEach(img => {
        const r = img.getBoundingClientRect();
        if (r.width < 50) return;  // skip venue badges / inline icons
        figures.push({
          card_index: -1,
          role: 'hero',
          src: img.getAttribute('src') || '',
          alt: img.getAttribute('alt') || '',
          fig_layout: img.getAttribute('data-fig-layout') || '',
          rendered_w: r.width,
          rendered_h: r.height,
          card_w: hw,
          natural_w: img.naturalWidth || 0,
          natural_h: img.naturalHeight || 0,
        });
      });
    });

  // ---- 2) Orphan-prone text elements ----
  const sel = '[class*="stat"], [class*="num"], .num, .takeaway-num,'
            + ' .headline-num';
  const seen = new Set();
  const orphans = [];
  document.querySelectorAll(sel).forEach(el => {
    if (seen.has(el)) return;
    seen.add(el);
    const txt = (el.innerText || '').replace(/\s+$/, '');
    if (!txt || txt.length > 80) return;
    const cs = window.getComputedStyle(el);
    orphans.push({
      tag: el.tagName.toLowerCase(),
      cls: el.className || '',
      text: txt,
      ws: cs.whiteSpace || '',
    });
  });

  // ---- 3) Space-between fill ----
  const cols = [];
  document.querySelectorAll('[data-measure-role="column"]')
    .forEach((col, ci) => {
      const cs = window.getComputedStyle(col);
      if (cs.justifyContent !== 'space-between') return;
      const colR = col.getBoundingClientRect();
      const children = Array.from(col.children).map(c => {
        const r = c.getBoundingClientRect();
        return {top: r.top, bottom: r.bottom, h: r.height};
      }).filter(c => c.h > 0);
      if (children.length < 2) return;
      const gapPx = parseFloat(cs.rowGap || cs.gap || '0') || 0;
      let maxExcess = 0;
      let pairIdx = -1;
      for (let i = 1; i < children.length; i++) {
        const actual = children[i].top - children[i - 1].bottom;
        const excess = actual - gapPx;
        if (excess > maxExcess) {
          maxExcess = excess;
          pairIdx = i;
        }
      }
      cols.push({
        column_index: ci,
        column_h: colR.height,
        stated_gap_px: gapPx,
        max_excess_px: maxExcess,
        pair_idx: pairIdx,
      });
    });

  // ---- 4) Card trailing whitespace (single stretched card) ----
  // A card with flex:1 (or any stretch-to-fill) whose content is top-
  // packed leaves blank space below the last line. `measure` only checks
  // the card's bottom edge so it passes; Gate C only looks BETWEEN cards.
  // Skip cards that distribute space on purpose (space-* / center / end)
  // -- that is Gate C's territory or an intentional layout.
  const cards = [];
  document.querySelectorAll('[data-measure-role="card"]')
    .forEach((card, ci) => {
      const cs = window.getComputedStyle(card);
      const jc = cs.justifyContent || '';
      if (jc.indexOf('space') !== -1 || jc === 'center'
          || jc === 'end' || jc === 'flex-end') return;
      const cr = card.getBoundingClientRect();
      if (cr.height <= 0) return;
      const padB = parseFloat(cs.paddingBottom) || 0;
      const padT = parseFloat(cs.paddingTop) || 0;
      const borderB = parseFloat(cs.borderBottomWidth) || 0;

      // Is `node` inside an absolutely/fixed-positioned subtree within the
      // card? A corner badge / QR / watermark sits at the card bottom but
      // is NOT the normal-flow content bottom -- counting it would mask a
      // top-packed void above it (false negative). Walk parents to card.
      const inAbs = (node) => {
        let el = node.nodeType === 1 ? node : node.parentElement;
        while (el && el !== card) {
          const pos = window.getComputedStyle(el).position;
          if (pos === 'absolute' || pos === 'fixed') return true;
          el = el.parentElement;
        }
        return false;
      };

      // Bottom-most rendered CONTENT = max over three sources (each kept
      // via `maxB`, so adding a source can only RAISE the content bottom,
      // never hide a void):
      //   (1) TEXT, via Range -- a plain-text tail that wraps onto a line
      //       BELOW an inline <span>/<b>/<code> is invisible to an element
      //       scan (its parent <p> has element children so it's skipped,
      //       and the inline leaf sits on an earlier line) -> undershoot.
      //   (2) REPLACED media (img/svg/canvas/...) -- even when it has child
      //       nodes (e.g. <svg> wrapping <path>s) and so isn't a leaf.
      //   (3) LEAF element boxes (no element children) -- re-covers a pure-
      //       CSS diagram node (an empty <div> bar/box) that carries no
      //       text and isn't replaced, which (1)+(2) alone would miss.
      // Non-leaf, non-replaced CONTAINERS are skipped: a stretched wrapper
      // box would over-measure to the card bottom and mask the void.
      let maxB = cr.top + padT;
      const bump = (r) => {
        if (r && r.height > 0 && r.bottom > maxB) maxB = r.bottom;
      };
      const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
      for (let tn = walker.nextNode(); tn; tn = walker.nextNode()) {
        if (!tn.nodeValue || !tn.nodeValue.trim()) continue;
        if (inAbs(tn)) continue;
        const rng = document.createRange();
        rng.selectNodeContents(tn);
        const rects = rng.getClientRects();
        for (let i = 0; i < rects.length; i++) bump(rects[i]);
      }
      const REPLACED = /^(IMG|SVG|CANVAS|VIDEO|IFRAME|HR|OBJECT|EMBED)$/;
      card.querySelectorAll('*').forEach(el => {
        if (inAbs(el)) return;
        // tagName is upper-case for HTML, but case-preserved (lower) for
        // SVG elements -- normalise before the replaced-tag test.
        if (!REPLACED.test(el.tagName.toUpperCase()) && el.children.length) {
          return;  // a non-replaced container: skip (only leaves + media)
        }
        bump(el.getBoundingClientRect());
      });

      cards.push({
        card_index: ci,
        card_h: cr.height,
        trailing_px: (cr.bottom - padB - borderB) - maxB,
      });
    });

  // ---- 5) <br> as a direct child of a flex container ----
  // A <br> that is an in-flow child of display:flex|inline-flex is
  // blockified into a flex ITEM and stops creating a line break -- so
  // intended multi-line content (e.g. an icon + label stacked with <br>)
  // silently collapses onto one row. `measure` can't see it (card bottom
  // is unchanged); only the eye catches it. Report each offending flex
  // parent once. Even in flex-direction:column the <br> does nothing (the
  // text runs already stack as separate items); row is where it visibly
  // breaks, so we report the direction to make the fix obvious.
  const flexbr = [];
  const seenFlexBr = new Set();
  document.querySelectorAll('br').forEach(br => {
    const parent = br.parentElement;
    if (!parent || seenFlexBr.has(parent)) return;
    const cs = window.getComputedStyle(parent);
    if (cs.display === 'flex' || cs.display === 'inline-flex') {
      seenFlexBr.add(parent);
      flexbr.push({
        tag: parent.tagName.toLowerCase(),
        cls: parent.className || '',
        dir: cs.flexDirection || 'row',
      });
    }
  });

  return {figures, orphans, cols, cards, flexbr};
}
"""


def cmd_polish(args: argparse.Namespace) -> int:
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeoutError
    except ImportError:
        _eprint("ERROR: playwright not installed. Run:")
        _eprint("  python -m pip install playwright")
        _eprint("  python -m playwright install chromium")
        return 2

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        _eprint(f"ERROR: HTML not found: {ascii_safe(html_path)}")
        return 2

    # Hard-fail if there's no measurement markup at all. A polish PASS
    # on "0 figures, 0 columns, 0 stat-like elements" would be silent
    # success on a file the tool can't reason about.
    role_counts = _preflight.has_required_roles_in_html(html_path)
    must_have = ("poster", "card", "column")
    missing = [r for r in must_have if role_counts.get(r, 0) == 0]
    if missing:
        _eprint(
            f"ERROR: polish requires data-measure-role markup on the "
            f"poster, columns, and cards. Missing or zero-count: "
            f"{missing}. Either add the roles or use a different tool."
        )
        return 2

    resolved = _canvas.resolve_canvas(
        html_path, args.canvas, label="[polish]"
    )
    if resolved is None:
        _eprint(
            "ERROR: could not find `@page { size: <W> <H> }` in HTML; "
            "pass `--canvas <W>x<H>in` or `--canvas 'A0 portrait'`."
        )
        return 2
    canvas, viewport = resolved

    with sync_playwright() as p:
        browser, _ctx, page = _render.open_print_emulated_page(p, viewport)
        nav_timed_out = False
        try:
            page.goto(html_path.as_uri(), wait_until="networkidle",
                      timeout=args.mathjax_timeout_ms)
        except PWTimeoutError:
            # Don't raw-traceback on a hung/slow resource. Record it and
            # let settle_page surface a MathJax-specific failure first;
            # otherwise fail-fast below. polish must NOT sample a poster
            # that never finished loading -- a blocked remote image or web
            # font would otherwise sneak through as a false PASS.
            nav_timed_out = True

        settle = _render.settle_page(
            page,
            mathjax_timeout_ms=args.mathjax_timeout_ms,
            settle_ms=args.settle_ms,
        )
        fail = _render.hard_fail_on_settle_problems(
            settle, mathjax_timeout_ms=args.mathjax_timeout_ms,
        )
        if fail is not None:
            browser.close()
            _eprint(f"FAIL: {fail}")
            return 1
        if nav_timed_out:
            browser.close()
            _eprint(
                "FAIL: page did not reach network-idle within "
                f"{args.mathjax_timeout_ms} ms; refusing to polish a "
                "partially loaded poster. A blocked/slow remote resource "
                "(CDN image, web font, MathJax) is the usual cause -- "
                "inline assets, or raise --mathjax-timeout-ms."
            )
            return 1

        data = page.evaluate(_POLISH_JS)
        browser.close()

    warns: list[str] = []

    # ---- Gate A: figure sizing by AR ----
    for f in data.get("figures", []):
        rw = float(f["rendered_w"])
        cw = float(f["card_w"])
        nw = float(f["natural_w"])
        nh = float(f["natural_h"])
        role = f.get("role", "card")
        src_l = str(f["src"]).lower()
        # A vector image (SVG) can legitimately report zero natural size
        # while rendering fine, so never flag it broken. Match the path
        # extension (after stripping any ?query / #fragment) plus inline
        # SVG data URIs. Imperfect: an SVG behind an extensionless URL
        # still slips through; an `img.decode()`-based JS probe would be
        # exact. Covers both card and hero <img> (see _POLISH_JS).
        src_path = src_l.split("?", 1)[0].split("#", 1)[0]
        is_svg = (
            src_path.endswith((".svg", ".svgz"))
            or src_l.startswith("data:image/svg")
        )
        if (nw <= 0 or nh <= 0) and not is_svg:
            warns.append(
                f"FIG/BROKEN: '{ascii_safe(f['src'])}' has zero natural "
                "size -- the image failed to load (missing file, 404, or "
                "an unreachable remote URL); it will be blank in print."
            )
            continue
        # Hero figures get the broken-image check above, but the AR sizing
        # gates below are framed as "% of card width" and don't apply to
        # the full-bleed hero panel. Skip them.
        if role == "hero":
            continue
        # Author opt-out for a DELIBERATE image-left/text-right card: a
        # wide figure that shares its card width with a meaningful text
        # column is sized below the AR thresholds on purpose. Marking the
        # <img> with `data-fig-layout="beside-text"` records that intent
        # in the markup -- so a later edit (human or agent) reads "this is
        # intentionally beside text" and leaves the layout alone instead
        # of widening the figure to silence the warning. It skips only the
        # AR width gates below; the FIG/BROKEN check above still applies
        # (a blank image is a bug regardless of layout). The gate stays
        # strict on the accidental case: a lone wide figure shrunk into a
        # gray margin has no such attribute and still warns.
        if str(f.get("fig_layout", "")).strip() == "beside-text":
            continue
        if cw <= 0 or rw <= 0 or nw <= 0 or nh <= 0:
            continue
        ar = nw / nh
        ratio = rw / cw
        if ar > 1.3 and ratio < args.wide_min_ratio:
            warns.append(
                f"FIG/WIDE: '{ascii_safe(f['src'])}' (AR={ar:.2f}) at "
                f"{ratio * 100:.0f}% of card width -- wide figures "
                f"should sit >= {args.wide_min_ratio * 100:.0f}%. "
                f"Enlarge, or drop the image-left/text-right wrapper."
            )
        elif ar < 0.8 and ratio > args.tall_max_ratio:
            warns.append(
                f"FIG/TALL: '{ascii_safe(f['src'])}' (AR={ar:.2f}) at "
                f"{ratio * 100:.0f}% of card width -- tall figures "
                f"usually pair better with text-right at 45-60%."
            )
        elif 0.8 <= ar <= 1.3 and ratio < args.square_min_ratio:
            warns.append(
                f"FIG/SQUARE: '{ascii_safe(f['src'])}' (AR={ar:.2f}) at "
                f"{ratio * 100:.0f}% of card width -- square figures "
                f"sit better at {args.square_min_ratio * 100:.0f}-75%."
            )

    # ---- Gate B: typography orphans ----
    for n in data.get("orphans", []):
        txt: str = n["text"]
        if not txt:
            continue
        last = txt[-1]
        if last not in ORPHAN_GLYPHS:
            continue
        if not re.search(r"\s", txt[:-1]):
            continue
        ws = (n["ws"] or "").lower()
        if "nowrap" in ws or "pre" in ws:
            continue
        warns.append(
            f"ORPHAN: <{ascii_safe(n['tag'])} class='{ascii_safe(n['cls'])}'> "
            f"text '{ascii_safe(txt[:48])}' ends with '{ascii_safe(last)}' "
            f"and may wrap alone. Apply `white-space: nowrap` or use &nbsp; "
            f"before the trailing glyph."
        )

    # ---- Gate C: space-between fill ----
    for c in data.get("cols", []):
        col_h = float(c["column_h"])
        excess = float(c["max_excess_px"])
        if col_h <= 0:
            continue
        fill = excess / col_h
        if fill > args.max_space_between_fill:
            warns.append(
                f"SPACE-BETWEEN: column {c['column_index']} has a "
                f"{excess:.0f} px inter-card gap "
                f"({fill * 100:.1f}% of column height, stated gap "
                f"{c['stated_gap_px']:.0f} px). Balance via "
                f"meaningful content, not justify-content. See "
                f"Gate C in SKILL.md."
            )

    # ---- Gate C (one card): trailing whitespace below the last line ----
    for c in data.get("cards", []):
        ch = float(c["card_h"])
        tr = float(c["trailing_px"])
        if ch <= 0 or tr <= 0:
            continue
        ratio = tr / ch
        if ratio > args.max_card_trailing:
            warns.append(
                f"CARD/TRAILING: card {c['card_index']} fills only "
                f"{100 - ratio * 100:.0f}% of its height -- {tr:.0f} px "
                f"({ratio * 100:.0f}%) blank below the last line. A card "
                f"stretched to align (flex:1) but padded with whitespace "
                f"clears the bottom-edge gate yet reads as unfinished. Fill "
                f"with real content, grow a figure, or shrink the canvas. "
                f"See Gate C in SKILL.md."
            )

    # ---- Gate D: <br> inside a flex container ----
    # A <br> that is a direct child of a flex container is blockified into
    # a flex item and creates NO line break, so intended multi-line text
    # collapses onto one row. Detectable only at render time (getComputed-
    # Style), which is why it lives here and not in preflight's static scan.
    for fb in data.get("flexbr", []):
        cls = str(fb.get("cls", ""))
        cls_attr = f' class="{ascii_safe(cls)}"' if cls else ""
        warns.append(
            f"LAYOUT/FLEX-BR: <{ascii_safe(fb['tag'])}{cls_attr}> is "
            f"display:flex (flex-direction:{fb['dir']}) with a direct <br> "
            f"child -- the <br> is blockified into a flex item and creates "
            f"NO line break, so intended multi-line content collapses onto "
            f"one row. Wrap each line in a <span> and use "
            f"flex-direction:column, or make the wrapper a plain block."
        )

    print(f"[polish] {ascii_safe(html_path.name)}")
    print(f"  figures checked     : {len(data.get('figures', []))}")
    print(f"  stat-like elements  : {len(data.get('orphans', []))}")
    print(f"  space-between cols  : {len(data.get('cols', []))}")
    print(f"  cards checked       : {len(data.get('cards', []))}")
    print(f"  flex/<br> parents   : {len(data.get('flexbr', []))}")
    print(f"  warnings            : {len(warns)}")
    for w in warns:
        print(f"  WARN: {w}")

    if args.strict and warns:
        _eprint("[polish] FAIL -- --strict and warnings present")
        return 1
    print("[polish] PASS" if not warns
          else "[polish] OK (warnings only)")
    return 0
