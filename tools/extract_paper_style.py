#!/usr/bin/env python3
"""
extract_paper_style.py — extract a *skeleton-only* style profile from a
reference paper, for opt-in use by writer skills via the `--style-ref` flag.

================================================================
CONTRACT (read this before consuming the output in a writer skill)
================================================================

Purpose
-------
Some users want a generated paper / poster / slide / grant draft to *match
the structural style* of a reference paper they admire (section ordering,
section name conventions, sentence-length cadence, theorem density, figure
density, bibliography style, etc.) — *without* copying the reference's prose
or claims. This helper resolves the reference, derives a compact, neutral
"style profile", and writes it to a deterministic cache path.

Writer skills that accept `--style-ref <source>`:
  - paper-write, paper-plan, paper-writing
  - paper-illustration, paper-poster, paper-slides
  - grant-proposal, auto-paper-improvement-loop

Strict rules for the calling skill
----------------------------------
1. **Opt-in only.** When the user does NOT pass `--style-ref`, behavior is
   unchanged. Do not auto-discover reference papers from the working tree.

2. **Run this script first**, before drafting:
       python3 tools/extract_paper_style.py --source <SRC> [--out <DIR>]
   On exit code 0, read the printed cache directory and consume:
       <cache>/source_manifest.json   (provenance)
       <cache>/style_profile.md       (the style guidance)
   On exit code 2 (missing optional dep), print a one-line warning and
   continue without style guidance.
   On exit code 3 (source failure), print the error and FAIL the writer
   step — do NOT silently fall back, the user explicitly asked for a ref.

3. **Use the profile as STRUCTURAL guidance only.** Do not copy sentences,
   phrases, claim bullets, or any concrete content from anything reachable
   through the cache. The profile is intentionally aggregate / statistical;
   if you find yourself reaching for copied prose, stop.

4. **Never pass `--style-ref` to reviewer / auditor sub-agents.**
   Cross-model review independence (`shared-references/reviewer-independence.md`)
   requires reviewers see only the artifact and the user's prompt, not the
   author's stylistic context. Style ref is a *writer-side* affordance.

5. **Cache is deterministic.** Same source → same cache dir. The calling
   skill should pass the resolved cache path explicitly when invoking
   sub-tools that need it; it should NOT mutate the cache.

Source types accepted
---------------------
  - Local directory:      /path/to/paper/         (scans *.tex)
  - Local TeX file:       /path/to/paper.tex
  - Local PDF file:       /path/to/paper.pdf      (uses pdftotext if installed)
  - arXiv ID:             arxiv:2501.12345        (fetches abstract HTML)
                          (also: 2501.12345 alone is auto-detected)
  - HTTP/HTTPS URL:        https://...            (PDF or HTML)
  - Overleaf URL/ID:       https://www.overleaf.com/project/<id>
                          ↑ rejected with guidance: clone via overleaf-sync
                          first, then pass the local clone path.

Output schema
-------------
<cache>/source_manifest.json:
    {
      "source_input":   "<original argument>",
      "source_type":    "local_dir|local_tex|local_pdf|arxiv|http",
      "resolved_path":  "<absolute path or URL>",
      "fetched_at":     "<ISO 8601 UTC>",
      "content_sha256": "<hex>",
      "tool_version":   "1"
    }

<cache>/style_profile.md:
    Compact markdown (≤ ~200 lines). Sections:
      - Section structure  (ordered list of sec names)
      - Length distribution (per-section approx word counts)
      - Theorem-environment density
      - Figure / table density
      - Citation density and style (numeric vs author-year, if detectable)
      - Sentence cadence (mean/median/p90 word count)
      - Math display ratio (inline vs display)
      - Captioning conventions (caption length stats)
      - Notable structural patterns (e.g., "Contributions" bullet block,
        "Setup → Result → Interpretation" theorem rhythm)
    Explicitly NOT included: any copied sentences, claim text, author names,
    affiliations, acknowledgements, or specific numerical results.

Cache layout
------------
Default cache root: $ARIS_STYLE_REF_CACHE (env) or `~/.cache/aris-style-refs/`
                    (XDG-friendly; avoids polluting the user's project repo
                    when the user runs the writer skill from inside their
                    paper directory)
Per-source dir:     <root>/<sha256(source_input)[:16]>/
                       source_manifest.json
                       style_profile.md

Exit codes
----------
  0 — success (cache written; cache path printed to stdout, last line)
  2 — missing optional Python dep; nothing written (caller may continue)
  3 — source resolution / network / parse failure (caller should fail)
  1 — generic runtime error
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOL_VERSION = "1"
ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
# Match any URL whose host is overleaf.com (or *.overleaf.com) AND whose path
# contains "/project/...". Rejects regardless of trailing slash, query string,
# fragment, or extra path segments like "/file/main.tex".
OVERLEAF_URL_RE = re.compile(
    r"^https?://([A-Za-z0-9-]+\.)*overleaf\.com(:\d+)?/project(/|$)",
    re.IGNORECASE,
)
# Bare hex blob that looks like an Overleaf project id (24+ hex chars, no path).
OVERLEAF_BARE_ID_RE = re.compile(r"^[A-Fa-f0-9]{24,}$")


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------

def _classify_source(src: str) -> str:
    if OVERLEAF_URL_RE.match(src) or OVERLEAF_BARE_ID_RE.match(src):
        return "overleaf"
    if src.startswith("arxiv:"):
        return "arxiv"
    if ARXIV_ID_RE.match(src):
        return "arxiv"
    if src.startswith("http://") or src.startswith("https://"):
        return "http"
    p = Path(src).expanduser()
    if p.is_dir():
        return "local_dir"
    if p.is_file():
        if p.suffix.lower() == ".pdf":
            return "local_pdf"
        return "local_tex"
    return "unknown"


def _read_local_dir(p: Path) -> str:
    parts: list[str] = []
    tex_files = sorted(p.rglob("*.tex"))
    if not tex_files:
        raise SourceError(f"No .tex files under {p}")
    for f in tex_files:
        try:
            parts.append(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
    return "\n\n% --- file boundary ---\n\n".join(parts)


def _read_local_tex(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _read_local_pdf(p: Path) -> str:
    if not shutil.which("pdftotext"):
        raise MissingDep("pdftotext (poppler) is required to read PDFs")
    out = subprocess.run(
        ["pdftotext", "-layout", str(p), "-"],
        capture_output=True,
        timeout=120,
    )
    if out.returncode != 0:
        raise SourceError(f"pdftotext failed: {out.stderr.decode(errors='replace')[:200]}")
    return out.stdout.decode("utf-8", errors="replace")


def _read_arxiv(arxiv_id: str) -> str:
    try:
        import requests
    except ImportError:
        raise MissingDep("requests (pip install requests) needed for arXiv fetch")
    arxiv_id = arxiv_id.removeprefix("arxiv:")
    url = f"https://export.arxiv.org/abs/{arxiv_id}"
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "aris-extract-paper-style/1"})
    except Exception as e:
        raise SourceError(f"arXiv fetch failed: {e}")
    if r.status_code != 200:
        raise SourceError(f"arXiv fetch returned HTTP {r.status_code}")
    return r.text


def _read_http(url: str) -> str:
    try:
        import requests
    except ImportError:
        raise MissingDep("requests (pip install requests) needed for HTTP fetch")
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "aris-extract-paper-style/1"})
    except Exception as e:
        raise SourceError(f"HTTP fetch failed: {e}")
    if r.status_code != 200:
        raise SourceError(f"HTTP fetch returned HTTP {r.status_code}")
    ctype = r.headers.get("content-type", "").lower()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        if not shutil.which("pdftotext"):
            raise MissingDep("pdftotext (poppler) needed to parse downloaded PDF")
        with subprocess.Popen(
            ["pdftotext", "-layout", "-", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as proc:
            stdout, _ = proc.communicate(input=r.content, timeout=120)
            if proc.returncode != 0:
                raise SourceError("pdftotext failed on downloaded PDF")
            return stdout.decode("utf-8", errors="replace")
    return r.text


# ---------------------------------------------------------------------------
# Style extraction
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(r"\\section\*?\{([^}]*)\}")
SUBSECTION_RE = re.compile(r"\\subsection\*?\{([^}]*)\}")
THM_RE = re.compile(
    r"\\begin\{(theorem|lemma|proposition|corollary|definition|assumption|remark)\}",
    re.IGNORECASE,
)
FIG_RE = re.compile(r"\\begin\{figure\*?\}")
TAB_RE = re.compile(r"\\begin\{table\*?\}")
CAPTION_RE = re.compile(r"\\caption\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
CITE_RE = re.compile(r"\\cite[a-zA-Z]*\*?\{([^}]+)\}")
DISPLAY_MATH_RE = re.compile(r"\\begin\{(equation|align|gather|multline)\*?\}")
INLINE_MATH_RE = re.compile(r"(?<!\\)\$[^$]+?(?<!\\)\$")


def _strip_tex(text: str) -> str:
    """Strip TeX commands to leave roughly natural-language prose for sentence stats."""
    text = re.sub(r"\\begin\{[^}]+\}.*?\\end\{[^}]+\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"%.*", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})*", " ", text)
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"\$[^$]*\$", " MATHEXPR ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _sentence_stats(prose: str) -> dict[str, Any]:
    sentences = re.split(r"(?<=[.!?])\s+", prose.strip())
    sentences = [s for s in sentences if len(s) > 4]
    if not sentences:
        return {"count": 0, "mean_words": 0, "median_words": 0, "p90_words": 0}
    word_counts = [len(s.split()) for s in sentences]
    word_counts_sorted = sorted(word_counts)
    p90_idx = max(0, int(0.9 * len(word_counts_sorted)) - 1)
    return {
        "count": len(sentences),
        "mean_words": round(statistics.mean(word_counts), 1),
        "median_words": int(statistics.median(word_counts)),
        "p90_words": word_counts_sorted[p90_idx],
    }


def _build_profile(src_kind: str, raw: str) -> str:
    """Generate a markdown style profile. Skeleton-only; no copied prose."""
    if src_kind in ("local_dir", "local_tex"):
        return _profile_from_tex(raw)
    return _profile_from_text(raw)


def _profile_from_tex(tex: str) -> str:
    sections = SECTION_RE.findall(tex)
    subsecs = SUBSECTION_RE.findall(tex)
    thm_kinds = THM_RE.findall(tex)
    n_fig = len(FIG_RE.findall(tex))
    n_tab = len(TAB_RE.findall(tex))
    captions = CAPTION_RE.findall(tex)
    citations = CITE_RE.findall(tex)
    n_display = len(DISPLAY_MATH_RE.findall(tex))
    n_inline = len(INLINE_MATH_RE.findall(tex))

    cite_keys: list[str] = []
    for c in citations:
        for k in c.split(","):
            cite_keys.append(k.strip())

    prose = _strip_tex(tex)
    sstats = _sentence_stats(prose)

    section_word_counts: list[tuple[str, int]] = []
    parts = re.split(SECTION_RE, tex)
    if len(parts) >= 3:
        for i in range(1, len(parts) - 1, 2):
            name = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            wc = len(_strip_tex(body).split())
            section_word_counts.append((name, wc))

    caption_lens = [len(c.split()) for c in captions] if captions else []
    caption_summary = ""
    if caption_lens:
        caption_summary = (
            f"- Captions: {len(caption_lens)} captions, "
            f"mean {round(statistics.mean(caption_lens), 1)} words, "
            f"median {int(statistics.median(caption_lens))} words"
        )

    thm_counter: dict[str, int] = {}
    for k in thm_kinds:
        thm_counter[k.lower()] = thm_counter.get(k.lower(), 0) + 1

    md = ["# Style profile (skeleton-only)\n"]
    md.append("**Use as structural guidance for the writer agent. Do NOT copy prose.**\n")

    md.append("\n## Top-level section structure\n")
    if sections:
        for i, s in enumerate(sections, 1):
            md.append(f"{i}. {s}")
    else:
        md.append("- (no `\\section{...}` markers detected — treat as freeform prose)")

    if subsecs:
        md.append(f"\n- Subsection density: {len(subsecs)} subsections / {max(1,len(sections))} sections "
                  f"= {round(len(subsecs)/max(1,len(sections)), 2)} per section")

    md.append("\n## Approximate length per section (words after TeX strip)\n")
    if section_word_counts:
        for name, wc in section_word_counts:
            md.append(f"- {name}: ~{wc} words")
    else:
        md.append("- (not measurable)")

    md.append("\n## Theorem-environment density\n")
    if thm_counter:
        for k, v in sorted(thm_counter.items(), key=lambda kv: -kv[1]):
            md.append(f"- {k}: {v}")
        md.append(f"- Total proof-style env: {sum(thm_counter.values())}")
    else:
        md.append("- (no theorem-style environments)")

    md.append("\n## Figures / tables\n")
    md.append(f"- Figures: {n_fig}")
    md.append(f"- Tables: {n_tab}")
    if caption_summary:
        md.append(caption_summary)

    md.append("\n## Math density\n")
    md.append(f"- Display equations (equation/align/gather/multline): {n_display}")
    md.append(f"- Inline math `$...$`: {n_inline}")
    if n_inline + n_display > 0:
        ratio = n_display / (n_inline + n_display)
        md.append(f"- Display-math share: {round(ratio*100, 1)}%")

    md.append("\n## Citation usage\n")
    md.append(f"- Total `\\cite*{{...}}` invocations: {len(citations)}")
    md.append(f"- Distinct cite keys: {len(set(cite_keys))}")
    bib_hint = "unknown"
    if re.search(r"\\bibliographystyle\{(plainnat|abbrvnat|authoryear)", tex):
        bib_hint = "author-year (natbib-style)"
    elif re.search(r"\\bibliographystyle\{(plain|unsrt|ieee|alpha)", tex):
        bib_hint = "numeric"
    md.append(f"- Bibliography style hint: {bib_hint}")

    md.append("\n## Sentence cadence (after TeX strip)\n")
    md.append(f"- Sentence count: {sstats['count']}")
    md.append(f"- Mean words/sentence: {sstats['mean_words']}")
    md.append(f"- Median words/sentence: {sstats['median_words']}")
    md.append(f"- p90 words/sentence: {sstats['p90_words']}")

    md.append("\n## Notable structural cues\n")
    cues: list[str] = []
    if any(re.search(r"contribution", s, re.IGNORECASE) for s in sections + subsecs):
        cues.append("- Has explicit \"Contributions\" subsection")
    if any(re.search(r"related work|prior work", s, re.IGNORECASE) for s in sections):
        cues.append("- Has dedicated \"Related Work\" section")
    if any(re.search(r"limitation|broader impact", s, re.IGNORECASE) for s in sections + subsecs):
        cues.append("- Has explicit Limitations / Broader Impact discussion")
    if "\\paragraph{" in tex:
        n_para = tex.count("\\paragraph{")
        cues.append(f"- Uses `\\paragraph{{...}}` headings ({n_para} occurrences) — implies short titled paragraphs")
    if cues:
        md.extend(cues)
    else:
        md.append("- (no salient cues detected)")

    md.append("\n## Reminder to the writer\n")
    md.append("- Match *structural* tendencies above (section count, theorem density, ")
    md.append("  caption length, sentence cadence, math display ratio).")
    md.append("- Do **not** copy prose, claims, examples, or terminology unique to the reference.")
    md.append("- This profile is intentionally aggregate; if you need substance, use the user's own outline.\n")

    return "\n".join(md) + "\n"


def _profile_from_text(text: str) -> str:
    """Best-effort profile from non-TeX text (PDF text dump or HTML)."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s for s in sentences if 8 < len(s) < 1000]
    word_counts = [len(s.split()) for s in sentences] if sentences else [0]
    headings = re.findall(r"^([A-Z][A-Za-z ]{2,40})$", text, re.MULTILINE)
    headings = [h.strip() for h in headings if 3 <= len(h.split()) <= 6][:30]

    md = ["# Style profile (skeleton-only, from non-TeX source)\n"]
    md.append("**Use as structural guidance for the writer agent. Do NOT copy prose.**\n")
    md.append("\n## Heuristic section-name candidates (best effort)\n")
    if headings:
        for h in headings[:20]:
            md.append(f"- {h}")
    else:
        md.append("- (no headings recovered)")
    md.append("\n## Sentence cadence\n")
    if word_counts:
        md.append(f"- Sentence count (heuristic): {len(sentences)}")
        md.append(f"- Mean words/sentence: {round(statistics.mean(word_counts), 1)}")
        md.append(f"- Median words/sentence: {int(statistics.median(word_counts))}")
    md.append("\n## Caveat\n")
    md.append("- Source is not LaTeX, so theorem density, citation style, and figure")
    md.append("  density cannot be measured. Treat the section list as a hint only.\n")
    return "\n".join(md) + "\n"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MissingDep(RuntimeError):
    """Optional Python or system dependency is unavailable. Caller may skip."""


class SourceError(RuntimeError):
    """Source could not be resolved or parsed. Caller should fail."""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _cache_root() -> Path:
    env = os.environ.get("ARIS_STYLE_REF_CACHE")
    if env:
        return Path(env).expanduser().resolve()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "aris-style-refs"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract a skeleton-only style profile from a reference paper "
                    "for opt-in use by ARIS writer skills via --style-ref.",
    )
    ap.add_argument("--source", required=True,
                    help="Local path, arXiv ID, http(s) URL, or 'arxiv:<id>'. "
                         "Overleaf URLs are rejected — clone via overleaf-sync first "
                         "and pass the local clone path instead.")
    ap.add_argument("--out", default=None,
                    help="Override cache root (default: $ARIS_STYLE_REF_CACHE, "
                         "$XDG_CACHE_HOME/aris-style-refs/, or ~/.cache/aris-style-refs/)")
    ap.add_argument("--force", action="store_true",
                    help="Refetch and overwrite even if cache hit exists.")
    args = ap.parse_args()

    src = args.source.strip()
    if not src:
        print("error: --source is required", file=sys.stderr)
        return 1

    kind = _classify_source(src)
    if kind == "overleaf":
        print(
            "Overleaf URLs / project IDs are rejected by design (private content).\n"
            "Workflow: clone the project locally first via `/overleaf-sync setup <id>`,\n"
            "then re-run with --source <local-clone-path>.",
            file=sys.stderr,
        )
        return 3
    if kind == "unknown":
        print(f"error: could not classify source '{src}'. "
              f"Pass a local path, arXiv id, or http(s) URL.", file=sys.stderr)
        return 3

    digest = hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]
    cache_root = Path(args.out).expanduser().resolve() if args.out else _cache_root()
    cache_dir = cache_root / digest
    manifest_path = cache_dir / "source_manifest.json"
    profile_path = cache_dir / "style_profile.md"

    if manifest_path.exists() and profile_path.exists() and not args.force:
        print(f"# cache hit: {cache_dir}", file=sys.stderr)
        print(str(cache_dir))
        return 0

    try:
        if kind == "local_dir":
            raw = _read_local_dir(Path(src).expanduser())
            resolved = str(Path(src).expanduser().resolve())
        elif kind == "local_tex":
            raw = _read_local_tex(Path(src).expanduser())
            resolved = str(Path(src).expanduser().resolve())
        elif kind == "local_pdf":
            raw = _read_local_pdf(Path(src).expanduser())
            resolved = str(Path(src).expanduser().resolve())
        elif kind == "arxiv":
            raw = _read_arxiv(src)
            resolved = src
        elif kind == "http":
            raw = _read_http(src)
            resolved = src
        else:
            print(f"error: unsupported source kind '{kind}'", file=sys.stderr)
            return 3
    except MissingDep as e:
        print(f"warning: missing optional dependency: {e}", file=sys.stderr)
        return 2
    except SourceError as e:
        print(f"error: source could not be resolved: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"error: unexpected failure: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    profile_md = _build_profile(kind, raw)

    cache_dir.mkdir(parents=True, exist_ok=True)
    content_sha = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    manifest = {
        "source_input": src,
        "source_type": kind,
        "resolved_path": resolved,
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "content_sha256": content_sha,
        "tool_version": TOOL_VERSION,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    profile_path.write_text(profile_md, encoding="utf-8")

    print(str(cache_dir))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
