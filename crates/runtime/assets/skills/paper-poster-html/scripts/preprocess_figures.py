#!/usr/bin/env python3
"""preprocess_figures -- clean up extracted crops before they go on a poster.

A bbox crop off a PDF page (see ``extract_pdf_figures.py crop``) almost
always carries a band of near-white page margin: the bbox is read off a
coordinate grid by eye, so it's deliberately generous. Those margins make
the figure render small inside its card and trip the asset_check
"natural >= 1.5x rendered" resolution gate for the WRONG reason (the real
pixels are fine; they're just padded with whitespace). This script:

  * autocrops the near-white border (PIL ImageChops.difference against a
    white backdrop, configurable threshold), leaving ``--pad`` px of
    breathing room so nothing touches the card edge;
  * reports each image's natural pixel size;
  * warns when an image is below ``--min-px`` (low-res crops upscale ugly
    on a printed A0); and
  * keeps FIGURE_MANIFEST.json honest -- when a crop is modified, its
    ``natural_px`` and ``sha256`` in the manifest are updated to match,
    so the sha chain asset_check relies on stays valid.

PIL is imported lazily so ``--help`` works without it and a missing dep
yields a readable install hint instead of an import traceback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from _posterly.textutil import ascii_safe  # noqa: E402

# Near-white threshold: pixels at/above this in all channels count as
# "blank margin". 248 (of 255) keeps faint antialiased plot edges while
# trimming JPEG-ish off-white page background.
DEFAULT_WHITE_THRESHOLD = 248


def _eprint(*args: object, **kw: object) -> None:
    print(*args, file=sys.stderr, **kw)  # type: ignore[arg-type]


def _load_pil():
    """Import PIL pieces or exit(2) with an actionable message."""
    try:
        from PIL import Image, ImageChops  # type: ignore
        return Image, ImageChops
    except ImportError:
        _eprint(
            "ERROR: Pillow (PIL) not installed -- required for "
            "preprocess_figures. Install with:\n"
            "  python -m pip install pillow"
        )
        raise SystemExit(2)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _autocrop_box(img, ImageChops, threshold: int):
    """Return the bbox of the non-white content, or None if all-white.

    We build a white backdrop the same size, take the absolute per-pixel
    difference, then threshold to a 1-bit mask whose ``getbbox`` is the
    tight content box. Using difference-vs-white (rather than scanning for
    exact 255) tolerates the slightly-off-white background of rasterised
    PDF pages.
    """
    rgb = img.convert("RGB")
    bg = rgb.point(lambda _p: 255)            # solid white, same size/mode
    diff = ImageChops.difference(rgb, bg)
    # Map "close to white" (diff small) -> 0, content -> 255.
    cutoff = 255 - threshold                   # e.g. threshold 248 -> 7
    mask = diff.convert("L").point(
        lambda p: 255 if p > cutoff else 0)
    return mask.getbbox()


def _apply_pad(box, pad: int, size):
    """Expand a (l,t,r,b) box by ``pad`` px, clamped to image size."""
    w, h = size
    l, t, r, b = box
    return (max(0, l - pad), max(0, t - pad),
            min(w, r + pad), min(h, b + pad))


def _load_manifest(path: Path) -> dict | None:
    if not path.exists():
        _eprint(f"WARN: manifest not found, skipping sync: "
                f"{ascii_safe(path)}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _eprint(f"ERROR: manifest unreadable: {ascii_safe(exc)}")
        raise SystemExit(1)


def _sync_manifest_entry(manifest: dict, manifest_path: Path,
                         img_path: Path, natural_px, sha: str) -> bool:
    """Update natural_px + sha256 for the manifest entry whose 'file'
    resolves to this image. Match by resolved absolute path so a relative
    manifest 'file' (assets/paper_figures/x.png) still matches an image
    given by any path spelling. Returns True if an entry was updated.
    """
    target = img_path.resolve()
    updated = False
    for fig in manifest.get("figures", []):
        fpath = (manifest_path.parent / fig.get("file", "")).resolve()
        if fpath == target:
            fig["natural_px"] = [natural_px[0], natural_px[1]]
            fig["sha256"] = sha
            updated = True
    return updated


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="preprocess_figures",
        description="Autocrop near-white margins, report natural size, "
                    "warn on low-res, and sync FIGURE_MANIFEST.json.",
    )
    p.add_argument("images", nargs="+", metavar="IMG",
                   help="one or more image files to process in place")
    p.add_argument("--autocrop", action="store_true",
                   help="trim near-white border (default: report only)")
    p.add_argument("--pad", type=int, default=6,
                   help="px of padding kept around content after autocrop "
                        "(default 6)")
    p.add_argument("--threshold", type=int, default=DEFAULT_WHITE_THRESHOLD,
                   help="near-white cutoff 0-255; pixels brighter than this "
                        f"are margin (default {DEFAULT_WHITE_THRESHOLD})")
    p.add_argument("--min-px", type=int, nargs=2, metavar=("W", "H"),
                   default=None,
                   help="warn if natural size is below W x H px "
                        "(e.g. --min-px 1200 700)")
    p.add_argument("--manifest", default=None,
                   help="FIGURE_MANIFEST.json to keep in sync after edits")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    Image, ImageChops = _load_pil()

    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    manifest = _load_manifest(manifest_path) if manifest_path else None
    manifest_dirty = False

    any_warn = False
    any_missing = False
    for img_arg in args.images:
        img_path = Path(img_arg)
        if not img_path.exists():
            _eprint(f"ERROR: image not found: {ascii_safe(img_path)}")
            any_missing = True
            continue
        try:
            img = Image.open(img_path)
            img.load()
        except Exception as exc:
            _eprint(f"ERROR: cannot open {ascii_safe(img_path)}: "
                    f"{ascii_safe(exc)}")
            any_missing = True
            continue

        before = img.size
        changed = False

        if args.autocrop:
            box = _autocrop_box(img, ImageChops, args.threshold)
            if box is None:
                _eprint(f"[preprocess] WARN: {ascii_safe(img_path.name)} "
                        f"is all near-white; skipping autocrop.")
            else:
                box = _apply_pad(box, args.pad, img.size)
                if box != (0, 0, img.width, img.height):
                    img = img.crop(box)
                    img.save(img_path)
                    changed = True

        natural = img.size
        crop_note = (f"  (autocropped from {before[0]}x{before[1]})"
                     if changed else "")
        print(f"[preprocess] {ascii_safe(img_path.name)}: "
              f"{natural[0]}x{natural[1]}px{crop_note}")

        # Low-res warning -- a printed A0 poster magnifies every missing pixel.
        if args.min_px is not None:
            mw, mh = args.min_px
            if natural[0] < mw or natural[1] < mh:
                _eprint(f"[preprocess] WARN: {ascii_safe(img_path.name)} "
                        f"{natural[0]}x{natural[1]}px is below "
                        f"--min-px {mw}x{mh}; may upscale poorly in print.")
                any_warn = True

        # Manifest sync: refresh natural_px + sha256 for the matching entry.
        # We re-hash whenever a manifest is supplied (even without a crop)
        # so a manifest can be reconciled to images edited out-of-band.
        if manifest is not None:
            sha = _sha256_file(img_path)
            if _sync_manifest_entry(manifest, manifest_path, img_path,
                                    natural, sha):
                manifest_dirty = True
            else:
                _eprint(f"[preprocess] note: no manifest entry references "
                        f"{ascii_safe(img_path.name)}; not synced.")

    if manifest is not None and manifest_dirty:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[preprocess] manifest synced: {ascii_safe(manifest_path)}")

    if any_missing:
        return 2
    if any_warn:
        # Low-res is a WARN, not a hard fail -- the asset gate decides
        # severity. Return 0 so a pipeline keeps going but the WARN lines
        # are visible on stderr.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
