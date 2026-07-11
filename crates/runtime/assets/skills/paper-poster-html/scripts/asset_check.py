#!/usr/bin/env python3
"""asset_check - the "real-figure provenance" gate (DESIGN_FINAL.md §4).

A poster passes this gate only when its paper figures are genuinely
sourced from the paper and rendered large/sharp enough to read:

  1. Provenance. Every ``<img data-source="paper">`` must carry a
     ``data-asset-id`` that resolves to a FIGURE_MANIFEST.json entry
     with ``from_paper: true`` and ALL required fields (§D schema).
     The referenced file must exist and its sha256 must match the
     manifest -- so a swapped/edited PNG can't masquerade as the
     vetted figure.

  2. Count. At least ``--min-paper-figs`` such figures (default 2):
     a poster with one tiny figure or none is the failure mode we
     are guarding against.

  3. Per-figure rendered area >= ``--min-fig-area`` of the poster
     (default 1.5%), and total paper-image area >= ``--min-total-area``
     of the body (default 12%). The 12% total rule is the only one
     ``--waive-total-area`` can waive (pure-theory posters; §12.5 nit 2).

  4. Resolution. A raster's natural pixel size must be >= 1.5x its
     rendered size (HARD below 1.5x, WARN between 1.5x and 2x; aim 2x).
     Catches up-scaled low-res crops that print blurry.

Rendered-area + rendered-resolution checks (3, 4) need real geometry,
which requires print-emulating the poster in Chromium via Playwright.
Playwright is lazy-imported INSIDE the render path: when it is missing
(or ``--no-render`` is passed), those checks degrade to an estimate
computed from ``natural_px`` and CSS ``width`` hints, are marked
ESTIMATED in the output, and do NOT hard-fail on the area thresholds
(a NOTICE is printed instead). The provenance/count/manifest checks
(1, 2, and the field/file/sha256 parts) are pure-static and always run.

JSON output (``--json``):
    {"gate": "asset", "status": "PASS|FAIL|WARN", "checks": [ ... ]}
where each check is
    {"id": "...", "severity": "hard|warn", "status": "PASS|FAIL|WARN|
     NOTICE|ESTIMATED", "detail": "..."}

Exit code: 0 = pass (no hard failures), 1 = hard fail, 2 = usage /
environment error (bad args, missing file, unparseable manifest).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# Make `_posterly` importable when run directly via
# `python asset_check.py …`, mirroring poster_check.py / render_preview.py.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from _posterly import canvas as _canvas  # noqa: E402
from _posterly.textutil import ascii_safe  # noqa: E402


# Required manifest fields per figure (§D schema). ``from_paper`` is
# validated separately (it must be exactly True), so it is not in the
# "presence" list but IS required to exist -- see _validate_manifest.
_REQUIRED_FIG_FIELDS: tuple[str, ...] = (
    "asset_id", "file", "from_paper", "page", "bbox", "dpi",
    "sha256", "natural_px",
)

# Resolution thresholds (§4): natural >= 1.5x rendered is the HARD floor;
# between 1.5x and 2.0x is a WARN (target is 2x).
_RES_HARD_FACTOR = 1.5
_RES_WARN_FACTOR = 2.0


def _eprint(*args: object, **kw: object) -> None:
    print(*args, file=sys.stderr, **kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# HTML parsing: collect <img> elements (esp. data-source="paper").
# --------------------------------------------------------------------------
class _ImgCollector(HTMLParser):
    """Collect every ``<img>``'s attributes as a flat dict.

    Why a real parser and not a regex: the AR-opt-out path lets a paper
    image carry ``style="width: NN%"`` (the one inline-style exception in
    §B), and attribute order is free-form. HTMLParser hands us a clean
    ``{attr: value}`` map regardless of quoting/order, and lower-cases the
    keys, so downstream lookups (``data-source``, ``data-asset-id``,
    ``class``, ``style``, ``width``) are robust.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # One dict per <img>, in source order. Keys are lower-cased attr
        # names; missing attrs simply absent.
        self.imgs: list[dict[str, str]] = []

    def _record_img(self, attrs: list[tuple[str, str | None]]) -> None:
        d: dict[str, str] = {}
        for k, v in attrs:
            d[k.lower()] = "" if v is None else v
        d["_line"] = str(self.getpos()[0])
        self.imgs.append(d)

    def handle_starttag(self, tag: str,
                        attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "img":
            self._record_img(attrs)

    def handle_startendtag(self, tag: str,
                           attrs: list[tuple[str, str | None]]) -> None:
        # `<img ... />` self-closing form: identical handling.
        if tag.lower() == "img":
            self._record_img(attrs)


def collect_imgs(html: str) -> list[dict[str, str]]:
    """Return one attr-dict per ``<img>`` in source order. Pure function
    so the provenance rules are unit-testable without a browser."""
    p = _ImgCollector()
    p.feed(html)
    p.close()
    return p.imgs


def paper_imgs(imgs: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter to images tagged as sourced from the paper.

    The contract (§B) is ``data-source="paper"``; we match
    case-insensitively on the value but the attribute name is fixed.
    """
    return [d for d in imgs if d.get("data-source", "").strip().lower()
            == "paper"]


# --------------------------------------------------------------------------
# Manifest loading + schema validation (§D).
# --------------------------------------------------------------------------
def load_manifest(path: Path) -> dict:
    """Parse FIGURE_MANIFEST.json. Raises ``ValueError`` (caught by the
    caller -> exit 2) on missing file or bad JSON, with a readable msg."""
    if not path.exists():
        raise ValueError(f"manifest not found: {ascii_safe(path)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"manifest is not valid JSON: {ascii_safe(e)}"
        ) from e
    if not isinstance(data, dict):
        raise ValueError("manifest top-level must be a JSON object")
    return data


def index_figures(manifest: dict) -> dict[str, dict]:
    """Map ``asset_id`` -> figure entry. Entries without an ``asset_id``
    are skipped here (the missing-field check reports them per-image)."""
    figs = manifest.get("figures")
    out: dict[str, dict] = {}
    if isinstance(figs, list):
        for f in figs:
            if isinstance(f, dict) and isinstance(f.get("asset_id"), str):
                out[f["asset_id"]] = f
    return out


def _missing_fields(fig: dict) -> list[str]:
    """Required §D fields absent from a figure entry (presence only)."""
    return [k for k in _REQUIRED_FIG_FIELDS if k not in fig]


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Check accumulation. A "check" is one row in the JSON ``checks`` array.
# --------------------------------------------------------------------------
class Checks:
    """Accumulate check rows and derive the overall gate status.

    Status semantics:
      - any ``hard`` check FAIL  -> gate FAIL (exit 1)
      - else any WARN            -> gate WARN (exit 0)
      - else                     -> gate PASS (exit 0)
    NOTICE / ESTIMATED are informational (degraded render path) and
    never by themselves flip the gate.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def add(self, cid: str, severity: str, status: str, detail: str
            ) -> None:
        self.rows.append({
            "id": cid,
            "severity": severity,
            "status": status,
            "detail": ascii_safe(detail),
        })

    def overall(self) -> str:
        if any(r["severity"] == "hard" and r["status"] == "FAIL"
               for r in self.rows):
            return "FAIL"
        if any(r["status"] == "WARN" for r in self.rows):
            return "WARN"
        return "PASS"


# --------------------------------------------------------------------------
# Static provenance + manifest checks (always run).
# --------------------------------------------------------------------------
def check_provenance(
    checks: Checks,
    p_imgs: list[dict[str, str]],
    fig_index: dict[str, dict],
    manifest_dir: Path,
    min_paper_figs: int,
) -> list[tuple[dict[str, str], dict]]:
    """Validate count + per-image manifest linkage (id resolves,
    from_paper True, fields present, file exists, sha256 matches).

    Returns the list of ``(img_attrs, manifest_entry)`` pairs that fully
    validated -- callers use these for the area/resolution checks.
    """
    # 2) Count gate.
    n = len(p_imgs)
    if n >= min_paper_figs:
        checks.add(
            "paper_fig_count", "hard", "PASS",
            f"{n} img[data-source=paper] (>= {min_paper_figs} required)",
        )
    else:
        checks.add(
            "paper_fig_count", "hard", "FAIL",
            f"only {n} img[data-source=paper]; need >= {min_paper_figs}. "
            f"Pull at least {min_paper_figs} real figures from the paper "
            f"(or use a human-checkpoint waiver per DESIGN_FINAL §4).",
        )

    validated: list[tuple[dict[str, str], dict]] = []
    for img in p_imgs:
        line = img.get("_line", "?")
        asset_id = img.get("data-asset-id", "").strip()
        tag = f"L{line} src={ascii_safe(img.get('src', '?'))}"

        # 1a) data-asset-id present?
        if not asset_id:
            checks.add(
                "asset_id_present", "hard", "FAIL",
                f"{tag}: data-source=paper without data-asset-id; "
                f"cannot trace to the manifest.",
            )
            continue
        # 1b) Resolves to a manifest entry?
        entry = fig_index.get(asset_id)
        if entry is None:
            checks.add(
                "asset_id_resolves", "hard", "FAIL",
                f"{tag}: data-asset-id={ascii_safe(asset_id)!r} not found "
                f"in manifest figures[].",
            )
            continue
        # 1c) from_paper exactly True?
        if entry.get("from_paper") is not True:
            checks.add(
                "from_paper", "hard", "FAIL",
                f"asset {ascii_safe(asset_id)}: from_paper is "
                f"{ascii_safe(entry.get('from_paper'))!r}, must be true.",
            )
            continue
        # 1d) All required §D fields present?
        missing = _missing_fields(entry)
        if missing:
            checks.add(
                "manifest_fields", "hard", "FAIL",
                f"asset {ascii_safe(asset_id)}: missing required field(s) "
                f"{missing}.",
            )
            continue
        # 1e) Referenced file exists? `file` is relative to the manifest
        #     directory (the manifest lives alongside the poster output).
        rel = str(entry.get("file", ""))
        fpath = (manifest_dir / rel).resolve()
        if not fpath.exists():
            checks.add(
                "asset_file_exists", "hard", "FAIL",
                f"asset {ascii_safe(asset_id)}: file {ascii_safe(rel)} "
                f"does not exist at {ascii_safe(fpath)}.",
            )
            continue
        # 1f) sha256 matches the manifest? A mismatch means the on-disk
        #     bytes are NOT the vetted figure (re-saved, edited, swapped).
        want = str(entry.get("sha256", "")).strip().lower()
        got = _sha256_of(fpath).lower()
        if want != got:
            checks.add(
                "asset_sha256", "hard", "FAIL",
                f"asset {ascii_safe(asset_id)}: sha256 mismatch "
                f"(manifest {want[:12]}..., file {got[:12]}...). The "
                f"on-disk file is not the manifested figure.",
            )
            continue

        checks.add(
            "asset_provenance", "hard", "PASS",
            f"asset {ascii_safe(asset_id)}: resolves, from_paper, fields "
            f"complete, file exists, sha256 matches.",
        )
        validated.append((img, entry))

    return validated


# --------------------------------------------------------------------------
# CSS width hint extraction (for the --no-render estimate).
# --------------------------------------------------------------------------
def _width_fraction_hint(img: dict[str, str]) -> float | None:
    """Best-effort fraction-of-container width for an <img>, from CSS hints.

    Sources, in priority order:
      1. ``style="width: NN%"`` (the one allowed inline-style, §B).
      2. A ``w-NN`` utility class (``.w-45 … .w-100``, §B): NN percent.
    Returns the fraction in [0, 1], or None when no width hint is present.
    This is only an ESTIMATE input -- the real number comes from render.
    """
    style = img.get("style", "")
    m = re.search(r"width\s*:\s*([\d.]+)\s*%", style, re.IGNORECASE)
    if m:
        try:
            return max(0.0, min(1.0, float(m.group(1)) / 100.0))
        except ValueError:
            pass
    cls = img.get("class", "")
    m = re.search(r"\bw-(\d{2,3})\b", cls)
    if m:
        try:
            return max(0.0, min(1.0, float(m.group(1)) / 100.0))
        except ValueError:
            pass
    return None


# --------------------------------------------------------------------------
# Rendered-geometry path (Playwright). Lazy import inside.
# --------------------------------------------------------------------------
def measure_rendered(
    html_path: Path,
    viewport: tuple[int, int],
    asset_ids: list[str],
    mathjax_timeout_ms: int,
) -> dict[str, dict[str, float]] | None:
    """Print-emulate the poster and read each paper image's rendered box
    plus the poster + body boxes. Returns a dict keyed by asset_id:

        {asset_id: {"w": px, "h": px, "area": px2}}
        plus pseudo-keys "__poster__" and "__body__" with their areas.

    Returns ``None`` when Playwright is unavailable -- the caller then
    falls back to the ESTIMATED path. Playwright is imported HERE (not at
    module top) so the static checks run even while playwright is still
    installing / absent.
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeoutError
    except ImportError:
        _eprint(
            "[asset_check] NOTICE: playwright not available; cannot "
            "measure rendered figure areas. Falling back to a "
            "natural_px + CSS-width ESTIMATE. To get the real geometry "
            "gate, install it once:\n"
            "  python -m pip install playwright\n"
            "  python -m playwright install chromium\n"
            "...or re-run with --no-render to silence this notice."
        )
        return None

    from _posterly import render as _render  # local: needs playwright too

    w, h = viewport
    result: dict[str, dict[str, float]] = {}
    with sync_playwright() as p_:
        browser, _ctx, page = _render.open_print_emulated_page(p_, (w, h))
        try:
            page.goto(html_path.as_uri(), timeout=mathjax_timeout_ms)
        except PWTimeoutError:
            _eprint(
                f"[asset_check] WARN: page.goto did not reach `load` "
                f"within {mathjax_timeout_ms} ms; measuring whatever "
                f"loaded (a CDN/external resource is likely blocked)."
            )
        # Settle fonts/layout (best-effort) so image boxes are final.
        _render.settle_page(
            page, mathjax_timeout_ms=mathjax_timeout_ms, settle_ms=300,
        )
        # One round-trip: collect every paper image's box + the poster
        # and body boxes. We key on data-asset-id.
        boxes = page.evaluate(
            """(ids) => {
                const out = {};
                const poster = document.querySelector(
                        '[data-measure-role="poster"]')
                        || document.querySelector('.poster')
                        || document.body;
                const body = document.querySelector(
                        '[data-measure-role="body"]') || poster;
                const rp = poster.getBoundingClientRect();
                const rb = body.getBoundingClientRect();
                out["__poster__"] = {w: rp.width, h: rp.height,
                                     area: rp.width * rp.height};
                out["__body__"] = {w: rb.width, h: rb.height,
                                   area: rb.width * rb.height};
                for (const id of ids) {
                    const el = document.querySelector(
                        'img[data-source="paper"][data-asset-id="'
                        + id.replace(/"/g, '\\\\"') + '"]');
                    if (!el) continue;
                    const r = el.getBoundingClientRect();
                    out[id] = {w: r.width, h: r.height,
                               area: r.width * r.height};
                }
                return out;
            }""",
            asset_ids,
        )
        browser.close()
    for k, v in boxes.items():
        result[k] = {kk: float(vv) for kk, vv in v.items()}
    return result


# --------------------------------------------------------------------------
# Area + resolution checks. Two code paths: rendered vs estimated.
# --------------------------------------------------------------------------
def check_areas_rendered(
    checks: Checks,
    validated: list[tuple[dict[str, str], dict]],
    boxes: dict[str, dict[str, float]],
    min_fig_area: float,
    min_total_area: float,
    waive_total_area: bool,
    warn_fig_area: float = 0.10,
    max_fig_area: float = 0.13,
    warn_total_area: float = 0.24,
    max_total_area: float = 0.28,
) -> None:
    """Per-figure area (min AND max bands), total area (min AND max
    bands), and natural>=1.5x rendered checks using REAL geometry from
    ``measure_rendered``. Upper bands exist because the failure mode is
    symmetric: too-small figures read as decoration, too-big figures
    crowd out the content (user-reported regression, 2026-06-05).
    Mins stay poster-based for back-compat; maxes are body-based per the
    codex-converged density bands (target total 14-22%% of body)."""
    poster_area = boxes.get("__poster__", {}).get("area", 0.0)
    body_area = boxes.get("__body__", {}).get("area", 0.0) or poster_area

    total_fig_area = 0.0
    for img, entry in validated:
        asset_id = str(entry.get("asset_id"))
        box = boxes.get(asset_id)
        if box is None:
            # Image validated statically but not found in the DOM render
            # (e.g. display:none, off-canvas). Treat as a HARD fail: it
            # is not actually contributing a visible figure.
            checks.add(
                "fig_area", "hard", "FAIL",
                f"asset {ascii_safe(asset_id)}: not found / zero-size in "
                f"the rendered poster (hidden or detached?).",
            )
            continue
        area = box["area"]
        total_fig_area += area
        frac = (area / poster_area) if poster_area > 0 else 0.0
        if frac >= min_fig_area:
            checks.add(
                "fig_area", "hard", "PASS",
                f"asset {ascii_safe(asset_id)}: {frac * 100:.2f}% of "
                f"poster (>= {min_fig_area * 100:.2f}%).",
            )
        else:
            checks.add(
                "fig_area", "hard", "FAIL",
                f"asset {ascii_safe(asset_id)}: only {frac * 100:.2f}% of "
                f"poster (need >= {min_fig_area * 100:.2f}%). Widen the "
                f"figure (.w-NN / style=width) or move it to a larger card.",
            )
        body_frac = (area / body_area) if body_area > 0 else 0.0
        if body_frac > max_fig_area:
            checks.add(
                "fig_area_max", "hard", "FAIL",
                f"asset {ascii_safe(asset_id)}: {body_frac * 100:.2f}% of "
                f"body (> {max_fig_area * 100:.0f}% hard max). A figure "
                f"this dominant crowds out content: shrink (.w-NN), merge "
                f"siblings into a .figure--duo, or use the hero template "
                f"(--hero).",
            )
        elif body_frac > warn_fig_area:
            checks.add(
                "fig_area_max", "warn", "WARN",
                f"asset {ascii_safe(asset_id)}: {body_frac * 100:.2f}% of "
                f"body (> {warn_fig_area * 100:.0f}%); target per-figure "
                f"band is 4-8%. Consider shrinking or pairing.",
            )
        _check_resolution(checks, entry, box["w"], box["h"], estimated=False)

    # Total paper-image area vs body. The ONLY rule --waive-total-area
    # affects (§12.5 nit 2).
    total_frac = (total_fig_area / body_area) if body_area > 0 else 0.0
    if waive_total_area:
        checks.add(
            "total_fig_area", "hard", "NOTICE",
            f"total paper-image area = {total_frac * 100:.2f}% of body; "
            f"WAIVED via --waive-total-area (pure-theory poster).",
        )
    elif total_frac >= min_total_area:
        checks.add(
            "total_fig_area", "hard", "PASS",
            f"total paper-image area = {total_frac * 100:.2f}% of body "
            f"(>= {min_total_area * 100:.2f}%).",
        )
    else:
        checks.add(
            "total_fig_area", "hard", "FAIL",
            f"total paper-image area = {total_frac * 100:.2f}% of body "
            f"(need >= {min_total_area * 100:.2f}%). Add/enlarge real "
            f"figures, or --waive-total-area for a pure-theory poster.",
        )
    if total_frac > max_total_area:
        checks.add(
            "total_fig_area_max", "hard", "FAIL",
            f"total paper-image area = {total_frac * 100:.2f}% of body "
            f"(> {max_total_area * 100:.0f}% hard max). Figures are "
            f"crowding out content: shrink, merge into .figure--duo, or "
            f"switch to the hero template (--hero).",
        )
    elif total_frac > warn_total_area:
        checks.add(
            "total_fig_area_max", "warn", "WARN",
            f"total paper-image area = {total_frac * 100:.2f}% of body "
            f"(> {warn_total_area * 100:.0f}%); target band is 14-22%.",
        )


def check_areas_estimated(
    checks: Checks,
    validated: list[tuple[dict[str, str], dict]],
    canvas_in: tuple[float, float],
    min_fig_area: float,
    min_total_area: float,
    waive_total_area: bool,
) -> None:
    """Degraded area + resolution checks for the ``--no-render`` (or
    no-playwright) path.

    We have no real layout, so we ESTIMATE each figure's rendered box from
    its ``natural_px`` aspect ratio scaled by a CSS width hint applied to
    a coarse column-width assumption. These estimates are reported with
    status ESTIMATED and DO NOT hard-fail the area thresholds -- a NOTICE
    is emitted when an estimate is below threshold so the human knows to
    re-run with rendering. The resolution check still runs (HARD/WARN),
    but against the ESTIMATED rendered size, so it is reported ESTIMATED.
    """
    checks.add(
        "render_mode", "warn", "NOTICE",
        "no rendering available (--no-render or playwright missing); "
        "area + resolution checks are ESTIMATED and not enforced as hard "
        "gates. Re-run with rendering for the real geometry gate.",
    )

    # Coarse layout model: assume a typical 3-column body, so a figure at
    # 100% width spans ~1/3 of poster WIDTH. width-hint scales that. This
    # is intentionally rough -- it only flags figures that are obviously
    # too small even under generous assumptions.
    poster_w_px, poster_h_px = _canvas.viewport_for(canvas_in)
    poster_area = float(poster_w_px * poster_h_px)
    assumed_col_frac = 1.0 / 3.0  # column ~1/3 poster width

    total_est_area = 0.0
    any_below = False
    for img, entry in validated:
        asset_id = str(entry.get("asset_id"))
        nat = entry.get("natural_px")
        if not (isinstance(nat, (list, tuple)) and len(nat) == 2):
            checks.add(
                "fig_area", "warn", "ESTIMATED",
                f"asset {ascii_safe(asset_id)}: natural_px missing/invalid; "
                f"cannot estimate area.",
            )
            continue
        nat_w, nat_h = float(nat[0]), float(nat[1])
        aspect = (nat_h / nat_w) if nat_w > 0 else 1.0
        wfrac = _width_fraction_hint(img)
        if wfrac is None:
            wfrac = 0.95  # template default for paper figures (.w-95)
        # Estimated rendered width/height in px.
        rend_w = poster_w_px * assumed_col_frac * wfrac
        rend_h = rend_w * aspect
        est_area = rend_w * rend_h
        total_est_area += est_area
        frac = (est_area / poster_area) if poster_area > 0 else 0.0
        below = frac < min_fig_area
        any_below = any_below or below
        checks.add(
            "fig_area", "warn", "ESTIMATED",
            f"asset {ascii_safe(asset_id)}: ~{frac * 100:.2f}% of poster "
            f"(threshold {min_fig_area * 100:.2f}%, "
            f"{'BELOW' if below else 'ok'}; estimate from natural_px + "
            f"width hint).",
        )
        _check_resolution(checks, entry, rend_w, rend_h, estimated=True)

    total_frac = (total_est_area / poster_area) if poster_area > 0 else 0.0
    if waive_total_area:
        checks.add(
            "total_fig_area", "warn", "NOTICE",
            f"total paper-image area ~{total_frac * 100:.2f}% of poster "
            f"(ESTIMATED); WAIVED via --waive-total-area.",
        )
    else:
        below_total = total_frac < min_total_area
        any_below = any_below or below_total
        checks.add(
            "total_fig_area", "warn", "ESTIMATED",
            f"total paper-image area ~{total_frac * 100:.2f}% of poster "
            f"(threshold {min_total_area * 100:.2f}% of body, "
            f"{'BELOW' if below_total else 'ok'}; estimate -- not enforced "
            f"without rendering).",
        )

    if any_below:
        checks.add(
            "area_estimate_notice", "warn", "NOTICE",
            "one or more ESTIMATED areas are below threshold; this is NOT "
            "a hard failure (no rendering). Re-run WITHOUT --no-render (and "
            "with playwright installed) to enforce the real area gate.",
        )


def _check_resolution(
    checks: Checks,
    entry: dict,
    rendered_w: float,
    rendered_h: float,
    *,
    estimated: bool,
) -> None:
    """natural_px vs rendered px: HARD below 1.5x, WARN in [1.5x, 2x).

    We compare on the larger dimension's ratio (a figure can be scaled
    differently per axis only if its aspect is distorted, which the
    template AR rules already discourage; the min-axis ratio is the
    binding constraint for sharpness). The status carries an ESTIMATED
    suffix in the detail when ``estimated`` -- and crucially, in the
    estimated path the rule is reported as a WARN-severity row so a
    rough estimate can never HARD-fail the gate.
    """
    asset_id = str(entry.get("asset_id"))
    nat = entry.get("natural_px")
    if not (isinstance(nat, (list, tuple)) and len(nat) == 2):
        checks.add(
            "fig_resolution", "warn", "ESTIMATED" if estimated else "WARN",
            f"asset {ascii_safe(asset_id)}: natural_px missing/invalid; "
            f"cannot check resolution.",
        )
        return
    nat_w, nat_h = float(nat[0]), float(nat[1])
    # Per-axis ratio; the minimum is what governs perceived sharpness.
    rx = (nat_w / rendered_w) if rendered_w > 0 else float("inf")
    ry = (nat_h / rendered_h) if rendered_h > 0 else float("inf")
    ratio = min(rx, ry)
    src = "estimated rendered" if estimated else "rendered"

    if ratio >= _RES_WARN_FACTOR:
        status = "ESTIMATED" if estimated else "PASS"
        checks.add(
            "fig_resolution", "warn" if estimated else "hard", status,
            f"asset {ascii_safe(asset_id)}: natural {nat_w:.0f}x{nat_h:.0f} "
            f"= {ratio:.2f}x {src} ({rendered_w:.0f}x{rendered_h:.0f}); "
            f">= {_RES_WARN_FACTOR}x target.",
        )
    elif ratio >= _RES_HARD_FACTOR:
        # In [1.5x, 2x): WARN in both paths (target not met but readable).
        checks.add(
            "fig_resolution", "warn",
            "ESTIMATED" if estimated else "WARN",
            f"asset {ascii_safe(asset_id)}: natural {nat_w:.0f}x{nat_h:.0f} "
            f"= {ratio:.2f}x {src} ({rendered_w:.0f}x{rendered_h:.0f}); "
            f">= {_RES_HARD_FACTOR}x floor but below {_RES_WARN_FACTOR}x "
            f"target -- consider a higher-DPI crop.",
        )
    else:
        # Below 1.5x: HARD when rendered for real; WARN-severity (reported
        # ESTIMATED) when only estimated, so the estimate never hard-fails.
        if estimated:
            checks.add(
                "fig_resolution", "warn", "ESTIMATED",
                f"asset {ascii_safe(asset_id)}: natural "
                f"{nat_w:.0f}x{nat_h:.0f} = {ratio:.2f}x {src} "
                f"({rendered_w:.0f}x{rendered_h:.0f}); below "
                f"{_RES_HARD_FACTOR}x floor (ESTIMATED -- re-render to "
                f"enforce).",
            )
        else:
            checks.add(
                "fig_resolution", "hard", "FAIL",
                f"asset {ascii_safe(asset_id)}: natural "
                f"{nat_w:.0f}x{nat_h:.0f} = {ratio:.2f}x {src} "
                f"({rendered_w:.0f}x{rendered_h:.0f}); below "
                f"{_RES_HARD_FACTOR}x floor -- prints blurry. Re-crop at "
                f"higher DPI (target {_RES_WARN_FACTOR}x).",
            )


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="asset_check",
        description="Real-figure provenance + area + resolution gate "
                    "for HTML academic posters (DESIGN_FINAL.md §4).",
    )
    p.add_argument("html", metavar="POSTER.html", help="path to poster.html")
    p.add_argument(
        "--manifest", required=True, metavar="FIGURE_MANIFEST.json",
        help="path to FIGURE_MANIFEST.json (schema: DESIGN_FINAL §D)",
    )
    p.add_argument(
        "--json", default=None, metavar="OUT.json",
        help="write the {gate, status, checks} report to this JSON file",
    )
    p.add_argument(
        "--min-paper-figs", type=int, default=2,
        help="min number of img[data-source=paper] (default 2)",
    )
    p.add_argument(
        "--min-fig-area", type=float, default=0.015,
        help="min rendered area per figure, fraction of poster "
             "(default 0.015 = 1.5%%)",
    )
    p.add_argument(
        "--min-total-area", type=float, default=0.12,
        help="min total paper-image area, fraction of body "
             "(default 0.12 = 12%%)",
    )
    p.add_argument(
        "--warn-fig-area", type=float, default=0.10,
        help="WARN when a single figure exceeds this fraction of body "
             "(default 0.10); figure-dominance early warning",
    )
    p.add_argument(
        "--max-fig-area", type=float, default=0.13,
        help="HARD max per-figure rendered area, fraction of body "
             "(default 0.13). Raised to 0.42 by --hero.",
    )
    p.add_argument(
        "--warn-total-area", type=float, default=0.24,
        help="WARN when total paper-image area exceeds this fraction of "
             "body (default 0.24); target band is 0.14-0.22",
    )
    p.add_argument(
        "--max-total-area", type=float, default=0.28,
        help="HARD max total paper-image area, fraction of body "
             "(default 0.28). Figures should illustrate, not crowd out "
             "the content (non-hero templates).",
    )
    p.add_argument(
        "--hero", action="store_true",
        help="hero-template mode: the hero figure may legitimately take "
             "30-40%% of body, so per-figure maxes relax (warn 0.40, "
             "hard 0.42) and the total hard max rises to 0.50",
    )
    p.add_argument(
        "--waive-total-area", action="store_true",
        help="waive ONLY the total-area (>=12%% of body) rule for "
             "pure-theory posters (DESIGN_FINAL §12.5 nit 2)",
    )
    p.add_argument(
        "--no-render", action="store_true",
        help="skip Playwright; estimate areas from natural_px + CSS "
             "width hints. Area checks become ESTIMATED and are not "
             "enforced as hard gates (a NOTICE is printed instead).",
    )
    p.add_argument(
        "--mathjax-timeout-ms", type=int, default=15000,
        help="render path: bound on page load / MathJax settle "
             "(default 15000); only used when actually rendering",
    )
    return p


def run(args: argparse.Namespace) -> int:
    html_path = Path(args.html).resolve()
    if not html_path.exists():
        _eprint(f"ERROR: HTML not found: {ascii_safe(html_path)}")
        return 2

    manifest_path = Path(args.manifest).resolve()
    try:
        manifest = load_manifest(manifest_path)
    except ValueError as e:
        _eprint(f"ERROR: {ascii_safe(e)}")
        return 2
    # Manifest `file` paths are resolved relative to the manifest's dir
    # (the poster output dir holds both the manifest and assets/).
    manifest_dir = manifest_path.parent
    fig_index = index_figures(manifest)

    html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    all_imgs = collect_imgs(html_text)
    p_imgs = paper_imgs(all_imgs)

    checks = Checks()

    # 1+2) Static provenance + count + manifest (always run).
    validated = check_provenance(
        checks, p_imgs, fig_index, manifest_dir, args.min_paper_figs,
    )

    # 3+4) Area + resolution. Real geometry if rendering; else estimate.
    canvas_in = _canvas.read_canvas_from_html(html_path)
    if canvas_in is None:
        # Without @page we cannot derive poster area for the estimate, and
        # render would also fail to size. Refuse silently-wrong areas.
        checks.add(
            "canvas", "hard", "FAIL",
            "could not parse @page { size } from the poster HTML; cannot "
            "determine poster area for figure-area checks. Add an @page "
            "rule (DESIGN_FINAL §A unit contract).",
        )
    else:
        boxes = None
        if not args.no_render:
            asset_ids = [str(e.get("asset_id")) for _i, e in validated]
            viewport = _canvas.viewport_for(canvas_in)
            boxes = measure_rendered(
                html_path, viewport, asset_ids, args.mathjax_timeout_ms,
            )
        if boxes is not None:
            # --hero: a hero-template centerpiece legitimately dominates.
            warn_fig = 0.40 if args.hero else args.warn_fig_area
            max_fig = 0.42 if args.hero else args.max_fig_area
            max_total = 0.50 if args.hero else args.max_total_area
            check_areas_rendered(
                checks, validated, boxes,
                args.min_fig_area, args.min_total_area,
                args.waive_total_area,
                warn_fig_area=warn_fig, max_fig_area=max_fig,
                warn_total_area=args.warn_total_area,
                max_total_area=max_total,
            )
        else:
            # --no-render OR playwright unavailable: degrade to estimate.
            check_areas_estimated(
                checks, validated, canvas_in,
                args.min_fig_area, args.min_total_area,
                args.waive_total_area,
            )

    status = checks.overall()
    report = {"gate": "asset", "status": status, "checks": checks.rows}

    # Human-readable summary to stdout.
    print(f"[asset_check] gate=asset status={status} "
          f"({len(checks.rows)} checks)")
    for r in checks.rows:
        print(f"  [{r['status']:9s}] {r['severity']:4s} {r['id']}: "
              f"{r['detail']}")

    if args.json:
        out = Path(args.json)
        out.write_text(json.dumps(report, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[asset_check] report -> {ascii_safe(out)}")

    return 1 if status == "FAIL" else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
