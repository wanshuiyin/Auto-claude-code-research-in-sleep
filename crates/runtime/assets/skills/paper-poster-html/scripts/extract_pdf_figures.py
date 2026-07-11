#!/usr/bin/env python3
"""extract_pdf_figures -- pull real figures out of a paper PDF.

The poster pipeline forbids fabricated visuals (DESIGN_FINAL Sec. 4): every
``data-source="paper"`` image must be traceable back to a page+bbox of the
source PDF, recorded in ``FIGURE_MANIFEST.json`` with a sha256 chain. This
script is the acquisition end of that chain. It has three subcommands:

  contact-sheet  Render every page at a modest dpi into
                 ``DIR/contact_sheet_pNN.png`` with a labelled PDF-point
                 coordinate grid overlaid. The grid lets a human (or an
                 agent reading the PNG) read crop bboxes straight off the
                 page, in the same point units that ``crop`` expects.
  auto           Detect candidate figure regions on each page from three
                 cheap signals -- vector-drawing clusters
                 (``page.get_drawings``), embedded raster bboxes
                 (``page.get_images``/``get_image_rects``), and the big
                 vertical gaps between text blocks -- merge overlapping
                 candidates, and print a table of (page, bbox, w x h,
                 kind-guess). It NEVER writes images: it only proposes
                 bboxes for a human/agent to pass to ``crop``.
  crop           Render one page clipped to ``--bbox`` at ``--dpi`` into
                 ``DIR/<name>.png`` and upsert that figure into
                 ``FIGURE_MANIFEST.json`` (located at DIR's PARENT) with
                 the full schema-D field set, incl. sha256 of the crop,
                 its natural pixel size, and the source-PDF sha256.

All bbox coordinates are PDF points (72 dpi, fitz's native top-left
origin), so a number read off a contact-sheet axis can be fed verbatim to
``crop --bbox``. PyMuPDF (``fitz``) and PIL are imported lazily inside the
functions that need them, so ``--help`` works in a stripped environment and
a missing dep yields a readable hint instead of an import traceback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# Make `_posterly` importable when run directly (consistent with the other
# scripts in this dir); we reuse its ascii_safe output-boundary escaper.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from _posterly.textutil import ascii_safe  # noqa: E402

SCHEMA_VERSION = 1
CONTACT_DPI = 110          # contact-sheet render dpi (readable, small files)
GRID_STEP_PT = 50          # gridline spacing in PDF points
PT_PER_INCH = 72.0


def _eprint(*args: object, **kw: object) -> None:
    print(*args, file=sys.stderr, **kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Lazy dependency loaders. Kept tiny so the import error message is the only
# thing the caller sees when a dep is missing -- no half-initialised state.
# --------------------------------------------------------------------------
def _load_fitz():
    """Import PyMuPDF or exit(2) with an actionable message.

    PyMuPDF is the engine for everything here (page raster, drawings,
    image bboxes), so a missing import is a hard environment error, not a
    degradation we can route around.
    """
    try:
        import fitz  # type: ignore  # noqa: F401
        return fitz
    except ImportError:
        _eprint(
            "ERROR: PyMuPDF (fitz) not installed -- required for all "
            "extract_pdf_figures subcommands. Install with:\n"
            "  python -m pip install pymupdf"
        )
        raise SystemExit(2)


def _load_pil():
    """Import PIL pieces or exit(2). Only the image-writing paths
    (contact-sheet, crop) need PIL; ``auto`` does not, so it stays usable
    even if PIL is absent."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
        return Image, ImageDraw, ImageFont
    except ImportError:
        _eprint(
            "ERROR: Pillow (PIL) not installed -- required for "
            "contact-sheet / crop rendering. Install with:\n"
            "  python -m pip install pillow"
        )
        raise SystemExit(2)


# --------------------------------------------------------------------------
# Small shared helpers.
# --------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    """Stream a file through sha256 (figures can be many MB; don't slurp)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pix_to_pil(pix, Image):
    """Convert a fitz Pixmap to a PIL RGB image without a temp file.

    fitz hands us raw interleaved samples; an alpha plane (n==4) or a
    grayscale plane (n==1) is normalised to RGB so the grid overlay and
    downstream PNG are uniform.
    """
    mode = "RGB"
    if pix.n == 1:
        mode = "L"
    elif pix.n == 4:
        mode = "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return img.convert("RGB")


def _open_doc(fitz, pdf_path: Path):
    """Open the PDF or exit(2) with a readable error (corrupt/missing)."""
    try:
        return fitz.open(str(pdf_path))
    except Exception as exc:  # fitz raises a variety of types
        _eprint(f"ERROR: could not open PDF {ascii_safe(pdf_path)}: "
                f"{ascii_safe(exc)}")
        raise SystemExit(2)


# --------------------------------------------------------------------------
# contact-sheet
# --------------------------------------------------------------------------
def cmd_contact_sheet(args: argparse.Namespace) -> int:
    """Render each page to a gridded PNG so bboxes can be read by eye.

    The grid is drawn in PDF-point space (every GRID_STEP_PT points) and
    labelled with the point value on both axes. Because ``crop`` consumes
    point bboxes, a reader can line a figure up against the gridlines and
    transcribe ``x0,y0,x1,y1`` directly -- no dpi arithmetic.
    """
    fitz = _load_fitz()
    Image, ImageDraw, ImageFont = _load_pil()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        _eprint(f"ERROR: PDF not found: {ascii_safe(pdf_path)}")
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = _open_doc(fitz, pdf_path)
    scale = CONTACT_DPI / PT_PER_INCH        # px per point
    matrix = fitz.Matrix(scale, scale)
    font = ImageFont.load_default()

    written: list[str] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        pix = page.get_pixmap(matrix=matrix)
        img = _pix_to_pil(pix, Image)
        draw = ImageDraw.Draw(img)

        rect = page.rect                      # page box in points
        w_pt, h_pt = rect.width, rect.height

        # Light gridlines + axis labels. Vertical lines step across X,
        # horizontal lines step down Y; both labelled with the point value.
        grid_rgb = (170, 200, 230)
        label_rgb = (40, 90, 150)
        x = 0.0
        while x <= w_pt + 0.1:
            px = x * scale
            draw.line([(px, 0), (px, img.height)], fill=grid_rgb, width=1)
            draw.text((px + 2, 2), str(int(x)), fill=label_rgb, font=font)
            x += GRID_STEP_PT
        y = 0.0
        while y <= h_pt + 0.1:
            py = y * scale
            draw.line([(0, py), (img.width, py)], fill=grid_rgb, width=1)
            draw.text((2, py + 2), str(int(y)), fill=label_rgb, font=font)
            y += GRID_STEP_PT

        # Header caption: page index (1-based) + page size in points, so a
        # reader knows the coordinate frame the grid is drawn in.
        caption = (f"page {pno + 1}/{doc.page_count}  "
                   f"size={int(round(w_pt))}x{int(round(h_pt))}pt  "
                   f"grid={GRID_STEP_PT}pt")
        draw.rectangle([0, 0, max(2, len(caption) * 7), 14],
                       fill=(255, 255, 255))
        draw.text((2, 1), caption, fill=label_rgb, font=font)

        out_path = out_dir / f"contact_sheet_p{pno + 1:02d}.png"
        img.save(out_path)
        written.append(str(out_path))
        print(f"[contact-sheet] page {pno + 1}: "
              f"{int(round(w_pt))}x{int(round(h_pt))}pt -> "
              f"{ascii_safe(out_path)}")

    doc.close()
    if not written:
        _eprint("ERROR: PDF has no pages.")
        return 1
    print(f"[contact-sheet] wrote {len(written)} sheet(s) to "
          f"{ascii_safe(out_dir)} at {CONTACT_DPI} dpi.")
    return 0


# --------------------------------------------------------------------------
# auto -- candidate region detection
# --------------------------------------------------------------------------
def _rects_overlap(a, b) -> bool:
    """True if two (x0,y0,x1,y1) point rects overlap or touch."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _union_rect(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]),
            max(a[2], b[2]), max(a[3], b[3]))


def _merge_candidates(cands: list[dict]) -> list[dict]:
    """Greedily merge overlapping candidate rects.

    Candidates come from three independent signals (vectors, rasters, text
    gaps) that frequently describe the SAME figure (a plot is both vector
    strokes and an embedded raster). Merging overlaps collapses those into
    one region. ``kind`` is concatenated so the table still shows what
    signals contributed (e.g. ``vector+image``).
    """
    merged: list[dict] = []
    for c in sorted(cands, key=lambda d: (d["page"], d["bbox"][1])):
        placed = False
        for m in merged:
            if m["page"] == c["page"] and _rects_overlap(m["bbox"], c["bbox"]):
                m["bbox"] = _union_rect(m["bbox"], c["bbox"])
                kinds = set(m["kind"].split("+")) | set(c["kind"].split("+"))
                m["kind"] = "+".join(sorted(kinds))
                placed = True
                break
        if not placed:
            merged.append(dict(c))
    return merged


def _text_gap_candidates(page, min_gap_pt: float) -> list[dict]:
    """Propose figure regions from big vertical voids between text blocks.

    A figure with no vector strokes and no embedded raster (e.g. a
    flattened image drawn as a single form XObject, or a wide table laid
    out with rules) still shows up as a tall blank band between two text
    blocks. We scan the gaps between consecutive text-block y-extents and
    flag any taller than ``min_gap_pt`` as a 'gap' candidate spanning the
    page's text column width.
    """
    rect = page.rect
    blocks = [b for b in page.get_text("blocks") if (b[4] or "").strip()]
    if not blocks:
        return []
    blocks.sort(key=lambda b: b[1])           # by top y
    # Text column extent (min x0 .. max x1) bounds the candidate width.
    col_x0 = min(b[0] for b in blocks)
    col_x1 = max(b[2] for b in blocks)
    out: list[dict] = []
    for prev, cur in zip(blocks, blocks[1:]):
        gap_top = prev[3]                     # bottom of previous block
        gap_bot = cur[1]                      # top of next block
        if gap_bot - gap_top >= min_gap_pt:
            out.append({
                "page": page.number + 1,
                "bbox": (round(col_x0, 1), round(gap_top, 1),
                         round(col_x1, 1), round(gap_bot, 1)),
                "kind": "gap",
            })
    # Also a leading gap at top-of-page (banner figure above first block).
    top_lead = blocks[0][1] - rect.y0
    if top_lead >= min_gap_pt:
        out.append({
            "page": page.number + 1,
            "bbox": (round(col_x0, 1), round(rect.y0, 1),
                     round(col_x1, 1), round(blocks[0][1], 1)),
            "kind": "gap",
        })
    return out


def _vector_candidates(page, min_area_pt2: float) -> list[dict]:
    """Cluster vector drawings into figure-sized regions.

    Individual ``get_drawings`` items are tiny (one stroke); we union all
    drawing rects that overlap into clusters, then keep clusters whose
    area clears ``min_area_pt2`` (filters out rules, underlines, and box
    borders that aren't really figures).
    """
    draws = page.get_drawings()
    rects = []
    for d in draws:
        r = d.get("rect")
        if r is None:
            continue
        # Skip zero-area / degenerate strokes.
        if r.width <= 0 or r.height <= 0:
            continue
        rects.append((r.x0, r.y0, r.x1, r.y1))
    if not rects:
        return []
    # Union-by-overlap clustering (same greedy merge as candidates).
    clusters: list[list[float]] = []
    for r in sorted(rects, key=lambda t: t[1]):
        placed = False
        for c in clusters:
            if _rects_overlap(c, r):
                c[0], c[1] = min(c[0], r[0]), min(c[1], r[1])
                c[2], c[3] = max(c[2], r[2]), max(c[3], r[3])
                placed = True
                break
        if not placed:
            clusters.append(list(r))
    out = []
    for c in clusters:
        area = (c[2] - c[0]) * (c[3] - c[1])
        if area >= min_area_pt2:
            out.append({
                "page": page.number + 1,
                "bbox": (round(c[0], 1), round(c[1], 1),
                         round(c[2], 1), round(c[3], 1)),
                "kind": "vector",
            })
    return out


def _image_candidates(page) -> list[dict]:
    """Embedded-raster bboxes via get_image_rects (placed location)."""
    out = []
    for img in page.get_images(full=True):
        xref = img[0]
        try:
            for r in page.get_image_rects(xref):
                if r.width <= 0 or r.height <= 0:
                    continue
                out.append({
                    "page": page.number + 1,
                    "bbox": (round(r.x0, 1), round(r.y0, 1),
                             round(r.x1, 1), round(r.y1, 1)),
                    "kind": "image",
                })
        except Exception:
            # Some xrefs aren't placed on the page (soft mask, inline);
            # skip rather than abort the whole scan.
            continue
    return out


def _guess_kind(kind: str, bbox) -> str:
    """Refine the merged signal label into a human-facing guess.

    Pure 'gap' regions that are much wider than tall read like tables/banners;
    we surface that as 'table?' so a reviewer doesn't crop a table expecting
    a plot. Image/vector signals are reported as-is (most reliable).
    """
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    if kind == "gap":
        if h > 0 and (w / h) >= 3.0:
            return "table?"
        return "region?"
    return kind


def cmd_auto(args: argparse.Namespace) -> int:
    """Detect + print candidate figure regions; write nothing.

    The output table is the contract: page, bbox(points), w x h, kind-guess.
    Bboxes are point rects directly usable as ``crop --bbox x0,y0,x1,y1``.
    """
    fitz = _load_fitz()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        _eprint(f"ERROR: PDF not found: {ascii_safe(pdf_path)}")
        return 2
    # `auto` writes nothing, but --out is a required top-level arg; tolerate
    # its absence (don't create dirs we won't use).

    doc = _open_doc(fitz, pdf_path)
    min_area = args.min_area
    min_gap = args.min_gap

    all_cands: list[dict] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        all_cands += _vector_candidates(page, min_area)
        all_cands += _image_candidates(page)
        all_cands += _text_gap_candidates(page, min_gap)

    merged = _merge_candidates(all_cands)
    # Drop merged regions below the min area floor (a tiny vector that only
    # survived because it merged with a text gap, say).
    merged = [m for m in merged
              if (m["bbox"][2] - m["bbox"][0]) * (m["bbox"][3] - m["bbox"][1])
              >= min_area]
    merged.sort(key=lambda m: (m["page"], m["bbox"][1]))

    doc.close()

    # Print a fixed-width table. kind-guess folds the merged signal label.
    print(f"# candidate figure regions for {ascii_safe(pdf_path.name)} "
          f"(units: PDF points; bbox = x0,y0,x1,y1)")
    print(f"{'page':>4}  {'bbox (x0,y0,x1,y1)':<30}  "
          f"{'w x h':<16}  kind-guess")
    print("-" * 70)
    if not merged:
        print("(no candidates >= min-area; lower --min-area or use "
              "contact-sheet to pick a bbox by hand)")
    for m in merged:
        b = m["bbox"]
        w = b[2] - b[0]
        h = b[3] - b[1]
        bbox_s = f"{b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f}"
        wh_s = f"{w:.0f} x {h:.0f}"
        kind = _guess_kind(m["kind"], b)
        print(f"{m['page']:>4}  {bbox_s:<30}  {wh_s:<16}  {kind}")
    print("-" * 70)
    print(f"# {len(merged)} candidate(s). Crop one with:\n"
          f"#   python3 extract_pdf_figures.py {ascii_safe(pdf_path.name)} "
          f"--out DIR crop --page P --bbox x0,y0,x1,y1 --name fig_id")
    return 0


# --------------------------------------------------------------------------
# crop -- render region + manifest upsert
# --------------------------------------------------------------------------
def _parse_bbox(s: str) -> tuple[float, float, float, float]:
    """Parse 'x0,y0,x1,y1' point bbox or raise argparse error."""
    parts = s.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"--bbox must be 'x0,y0,x1,y1' (4 numbers), got {s!r}")
    try:
        x0, y0, x1, y1 = (float(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--bbox values must be numbers, got {s!r}")
    if x1 <= x0 or y1 <= y0:
        raise argparse.ArgumentTypeError(
            f"--bbox must have x1>x0 and y1>y0, got {s!r}")
    return (x0, y0, x1, y1)


def _manifest_path_for(out_dir: Path) -> Path:
    """Manifest lives at DIR's PARENT (contract C/D): the convention is
    ``poster_html/FIGURE_MANIFEST.json`` while crops land in
    ``poster_html/assets/paper_figures/``."""
    return out_dir.resolve().parent / "FIGURE_MANIFEST.json"


def _rel_file_path(manifest_path: Path, png_path: Path) -> str:
    """Manifest 'file' field is relative to the manifest's directory when
    possible (matches the schema-D example 'assets/paper_figures/x.png');
    fall back to an absolute path if the crop lives outside the manifest
    tree."""
    try:
        return str(png_path.resolve().relative_to(manifest_path.parent))
    except ValueError:
        return str(png_path.resolve())


def _load_manifest(manifest_path: Path, pdf_path: Path,
                   pdf_sha: str) -> dict:
    """Load an existing manifest or seed a fresh one.

    If a manifest exists for a DIFFERENT source PDF we keep its recorded
    source_pdf untouched only when the sha matches; otherwise we overwrite
    source_pdf with the current PDF (the common case is re-running against
    the same paper, and a sha mismatch means the old record is stale).
    """
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _eprint(f"ERROR: existing manifest is unreadable: "
                    f"{ascii_safe(exc)}")
            raise SystemExit(1)
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("figures", [])
        # Refresh source_pdf if missing or pointing at a different file.
        src = data.get("source_pdf") or {}
        if src.get("sha256") != pdf_sha:
            data["source_pdf"] = {"path": str(pdf_path), "sha256": pdf_sha}
        return data
    return {
        "schema_version": SCHEMA_VERSION,
        "source_pdf": {"path": str(pdf_path), "sha256": pdf_sha},
        "figures": [],
    }


def _upsert_figure(manifest: dict, entry: dict) -> None:
    """Insert or replace the figure with this asset_id (upsert by id)."""
    figs = manifest["figures"]
    for i, f in enumerate(figs):
        if f.get("asset_id") == entry["asset_id"]:
            figs[i] = entry
            return
    figs.append(entry)


def cmd_crop(args: argparse.Namespace) -> int:
    """Render one page clipped to a point bbox at --dpi, then upsert the
    manifest with the full schema-D field set (incl. sha chains)."""
    fitz = _load_fitz()
    Image, _ImageDraw, _ImageFont = _load_pil()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        _eprint(f"ERROR: PDF not found: {ascii_safe(pdf_path)}")
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = _open_doc(fitz, pdf_path)
    page_idx = args.page - 1                   # CLI page is 1-based
    if page_idx < 0 or page_idx >= doc.page_count:
        _eprint(f"ERROR: --page {args.page} out of range "
                f"(PDF has {doc.page_count} page(s)).")
        doc.close()
        return 2
    page = doc[page_idx]

    x0, y0, x1, y1 = args.bbox
    clip = fitz.Rect(x0, y0, x1, y1)
    # Clamp the bbox to the page so a slightly-too-wide crop (common when
    # reading off the grid) doesn't error -- but warn so the caller knows.
    page_rect = page.rect
    clamped = clip & page_rect                 # intersection
    if clamped.is_empty:
        _eprint(f"ERROR: --bbox {x0},{y0},{x1},{y1} does not intersect "
                f"page {args.page} (size "
                f"{page_rect.width:.0f}x{page_rect.height:.0f}pt).")
        doc.close()
        return 2
    if (abs(clamped.x0 - x0) > 0.5 or abs(clamped.y0 - y0) > 0.5
            or abs(clamped.x1 - x1) > 0.5 or abs(clamped.y1 - y1) > 0.5):
        _eprint(f"[crop] WARN: bbox clamped to page bounds: "
                f"{clamped.x0:.0f},{clamped.y0:.0f},"
                f"{clamped.x1:.0f},{clamped.y1:.0f}")
    clip = clamped

    scale = args.dpi / PT_PER_INCH
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, clip=clip)
    img = _pix_to_pil(pix, Image)

    name = args.name
    if not name.lower().endswith(".png"):
        png_path = out_dir / f"{name}.png"
    else:
        png_path = out_dir / name
        name = name[:-4]
    img.save(png_path)
    natural_px = [img.width, img.height]
    crop_sha = _sha256_file(png_path)
    pdf_sha = _sha256_file(pdf_path)

    manifest_path = _manifest_path_for(out_dir)
    manifest = _load_manifest(manifest_path, pdf_path, pdf_sha)
    entry = {
        "asset_id": name,
        "file": _rel_file_path(manifest_path, png_path),
        "from_paper": True,
        "page": args.page,
        # Record the (possibly clamped) bbox actually rendered, rounded to
        # match schema-D's float-point style.
        "bbox": [round(clip.x0, 1), round(clip.y0, 1),
                 round(clip.x1, 1), round(clip.y1, 1)],
        "dpi": args.dpi,
        "sha256": crop_sha,
        "natural_px": natural_px,
        "caption_hint": args.caption_hint or "",
    }
    _upsert_figure(manifest, entry)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    doc.close()
    print(f"[crop] page {args.page} bbox=({clip.x0:.0f},{clip.y0:.0f},"
          f"{clip.x1:.0f},{clip.y1:.0f})pt @ {args.dpi}dpi -> "
          f"{ascii_safe(png_path)} ({natural_px[0]}x{natural_px[1]}px)")
    print(f"[crop] manifest upserted: {ascii_safe(manifest_path)} "
          f"(asset_id={name})")
    return 0


# --------------------------------------------------------------------------
# argument parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="extract_pdf_figures",
        description="Extract real paper figures from a PDF (contact-sheet "
                    "/ auto / crop). bbox units = PDF points.",
    )
    p.add_argument("pdf", help="source paper PDF")
    p.add_argument("--out", required=True,
                   help="output directory for PNGs (manifest is written to "
                        "this dir's PARENT as FIGURE_MANIFEST.json)")
    p.add_argument("--dpi", type=int, default=350,
                   help="crop render dpi (default 350; contact-sheet is "
                        "fixed at a modest dpi for readability)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser(
        "contact-sheet",
        help="render every page with a labelled PDF-point grid overlay",
    )
    pc.set_defaults(func=cmd_contact_sheet)

    pa = sub.add_parser(
        "auto",
        help="detect + print candidate figure regions (writes nothing)",
    )
    pa.add_argument(
        "--min-area", type=float, default=10000.0,
        help="ignore candidate regions below this area in point^2 "
             "(default 10000, ~ 100x100pt; filters rules and borders)",
    )
    pa.add_argument(
        "--min-gap", type=float, default=60.0,
        help="min vertical void between text blocks (points) to flag as a "
             "figure-region candidate (default 60)",
    )
    pa.set_defaults(func=cmd_auto)

    pcr = sub.add_parser(
        "crop",
        help="render page clipped to --bbox and upsert FIGURE_MANIFEST.json",
    )
    pcr.add_argument("--page", type=int, required=True,
                     help="1-based page number")
    pcr.add_argument("--bbox", type=_parse_bbox, required=True,
                     help="crop bbox in PDF points: x0,y0,x1,y1")
    pcr.add_argument("--name", required=True,
                     help="asset_id / output PNG stem (e.g. fig_method)")
    pcr.add_argument("--caption-hint", default=None,
                     help="optional caption hint stored in the manifest")
    pcr.set_defaults(func=cmd_crop)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
