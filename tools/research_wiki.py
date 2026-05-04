#!/usr/bin/env python3
"""
ARIS Research Wiki — Helper utilities.
Canonical helper for the /research-wiki skill and integration hooks in other
skills. The SKILL.md prose for paper-reading skills (research-lit, arxiv,
alphaxiv, deepxiv, semantic-scholar, exa-search) delegates ingest to this
script; no skill duplicates the page-creation schema.

Usage:
    python3 research_wiki.py init <wiki_root>
    python3 research_wiki.py slug "<paper title>" --author "<last name>" --year 2025
    python3 research_wiki.py add_edge <wiki_root> --from <node_id> --to <node_id> --type <edge_type> --evidence "<text>"
    python3 research_wiki.py rebuild_query_pack <wiki_root> [--max-chars 8000]
    python3 research_wiki.py rebuild_index <wiki_root>
    python3 research_wiki.py stats <wiki_root>
    python3 research_wiki.py log <wiki_root> "<message>"

    # Canonical paper ingest (preferred by integration hooks):
    python3 research_wiki.py ingest_paper <wiki_root> --arxiv-id <id> \
        [--thesis "<one-line>"] [--tags tag1,tag2] [--update-on-exist]

    # Manual ingest when arXiv metadata is not available:
    python3 research_wiki.py ingest_paper <wiki_root> \
        --title "<full title>" --authors "A, B, C" --year 2025 \
        --venue <venue> [--external-id-doi <doi>] [--thesis "..."] [--tags ...]

    # Batch backfill:
    python3 research_wiki.py sync <wiki_root> --arxiv-ids id1,id2,id3
    python3 research_wiki.py sync <wiki_root> --from-file ids.txt
"""

# `from __future__ import annotations` defers annotation evaluation so that
# PEP 604 union syntax (`Path | None`) used below works on Python 3.7+ —
# without it the module fails to import on the macOS system default
# (`/usr/bin/python3` = 3.9.6), which is a path that many community users
# end up on if they have not installed a newer Python via miniforge / brew /
# pyenv. The helper is otherwise pure-stdlib.
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

_ARXIV_API = "http://export.arxiv.org/api/query?id_list={ids}"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom",
             "arxiv": "http://arxiv.org/schemas/atom"}


def slugify(title: str, author_last: str = "", year: int = 0) -> str:
    """Generate a canonical slug: author_last + year + keyword."""
    # Extract first meaningful word from title
    stop_words = {"a", "an", "the", "of", "for", "in", "on", "with", "via", "and", "to", "by"}
    words = re.sub(r"[^a-z0-9\s]", "", title.lower()).split()
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    keyword = "_".join(keywords[:3]) if keywords else "untitled"

    author = re.sub(r"[^a-z]", "", author_last.lower()) if author_last else "unknown"
    yr = str(year) if year else "0000"
    return f"{author}{yr}_{keyword}"


def init_wiki(wiki_root: str):
    """Initialize wiki directory structure."""
    root = Path(wiki_root)
    dirs = ["papers", "ideas", "experiments", "claims", "graph"]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)

    # Create empty files if they don't exist
    for f in ["index.md", "log.md", "gap_map.md", "query_pack.md"]:
        path = root / f
        if not path.exists():
            if f == "index.md":
                path.write_text("# Research Wiki Index\n\n_Auto-generated. Do not edit._\n")
            elif f == "log.md":
                path.write_text("# Research Wiki Log\n\n_Append-only timeline._\n")
            elif f == "gap_map.md":
                path.write_text("# Gap Map\n\n_Field gaps with stable IDs._\n")
            elif f == "query_pack.md":
                path.write_text("# Query Pack\n\n_Auto-generated for /idea-creator. Max 8000 chars._\n")

    # Create empty edges file
    edges_path = root / "graph" / "edges.jsonl"
    if not edges_path.exists():
        edges_path.write_text("")

    append_log(wiki_root, "Wiki initialized")
    print(f"Research wiki initialized at {root}")


def add_edge(wiki_root: str, from_id: str, to_id: str, edge_type: str, evidence: str = ""):
    """Add a typed edge to the relationship graph."""
    VALID_TYPES = {
        "extends", "contradicts", "addresses_gap", "inspired_by",
        "tested_by", "supports", "invalidates", "supersedes",
    }
    if edge_type not in VALID_TYPES:
        print(f"Warning: unknown edge type '{edge_type}'. Valid: {VALID_TYPES}", file=sys.stderr)

    edges_path = Path(wiki_root) / "graph" / "edges.jsonl"

    # Dedup check
    existing_edges = []
    if edges_path.exists():
        for line in edges_path.read_text().strip().split("\n"):
            if line.strip():
                try:
                    existing_edges.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Check if edge already exists
    for e in existing_edges:
        if e.get("from") == from_id and e.get("to") == to_id and e.get("type") == edge_type:
            print(f"Edge already exists: {from_id} --{edge_type}--> {to_id}")
            return

    edge = {
        "from": from_id,
        "to": to_id,
        "type": edge_type,
        "evidence": evidence,
        "added": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with open(edges_path, "a") as f:
        f.write(json.dumps(edge, ensure_ascii=False) + "\n")

    print(f"Edge added: {from_id} --{edge_type}--> {to_id}")


def rebuild_query_pack(wiki_root: str, max_chars: int = 8000):
    """Generate a compressed query_pack.md for /idea-creator."""
    root = Path(wiki_root)
    sections = []

    # 1. Project direction (300 chars)
    brief_path = root.parent / "RESEARCH_BRIEF.md"
    if brief_path.exists():
        brief = brief_path.read_text()[:300]
        sections.append(f"## Project Direction\n{brief}\n")

    # 2. Gap map (1200 chars)
    gap_path = root / "gap_map.md"
    if gap_path.exists():
        gaps = gap_path.read_text()[:1200]
        if gaps.strip() and gaps.strip() != "# Gap Map\n\n_Field gaps with stable IDs._":
            sections.append(f"## Open Gaps\n{gaps}\n")

    # 3. Failed ideas (1400 chars) — highest anti-repetition value
    ideas_dir = root / "ideas"
    if ideas_dir.exists():
        failed = []
        for f in sorted(ideas_dir.glob("*.md")):
            content = f.read_text()
            if "outcome: negative" in content or "outcome: mixed" in content:
                # Extract frontmatter title and failure notes
                lines = content.split("\n")
                title = ""
                failure = ""
                for line in lines:
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"')
                    if "failure" in line.lower() or "lesson" in line.lower():
                        idx = lines.index(line)
                        failure = "\n".join(lines[idx:idx+3])
                if title:
                    failed.append(f"- **{title}**: {failure[:200]}")
        if failed:
            failed_text = "\n".join(failed)[:1400]
            sections.append(f"## Failed Ideas (avoid repeating)\n{failed_text}\n")

    # 4. Paper summaries (1800 chars) — top by relevance
    papers_dir = root / "papers"
    if papers_dir.exists():
        paper_summaries = []
        for f in sorted(papers_dir.glob("*.md")):
            content = f.read_text()
            # Extract one-line thesis and key fields
            node_id = ""
            title = ""
            thesis = ""
            for line in content.split("\n"):
                if line.startswith("node_id:"):
                    node_id = line.split(":", 1)[1].strip()
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"')
                if line.startswith("# One-line thesis"):
                    idx = content.split("\n").index(line)
                    next_lines = content.split("\n")[idx+1:idx+3]
                    thesis = " ".join(l for l in next_lines if l.strip() and not l.startswith("#"))
            if title:
                paper_summaries.append(f"- [{node_id}] {title}: {thesis[:150]}")

        if paper_summaries:
            papers_text = "\n".join(paper_summaries[:12])[:1800]
            sections.append(f"## Key Papers ({len(paper_summaries)} total)\n{papers_text}\n")

    # 5. Active relationship chains (900 chars)
    edges_path = root / "graph" / "edges.jsonl"
    if edges_path.exists():
        edges = []
        for line in edges_path.read_text().strip().split("\n"):
            if line.strip():
                try:
                    edges.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if edges:
            chains = []
            for e in edges[-20:]:  # recent edges
                chains.append(f"  {e['from']} --{e['type']}--> {e['to']}")
            chains_text = "\n".join(chains)[:900]
            sections.append(f"## Recent Relationships ({len(edges)} total)\n{chains_text}\n")

    # Assemble
    pack = "# Research Wiki Query Pack\n\n_Auto-generated. Do not edit._\n\n"
    for s in sections:
        if len(pack) + len(s) <= max_chars:
            pack += s
        else:
            remaining = max_chars - len(pack) - 20
            if remaining > 100:
                pack += s[:remaining] + "\n...(truncated)\n"
            break

    pack_path = root / "query_pack.md"
    pack_path.write_text(pack)
    print(f"query_pack.md rebuilt: {len(pack)} chars")


def get_stats(wiki_root: str):
    """Print wiki statistics."""
    root = Path(wiki_root)

    def count_files(subdir):
        d = root / subdir
        return len(list(d.glob("*.md"))) if d.exists() else 0

    def count_by_field(subdir, field, value):
        d = root / subdir
        if not d.exists():
            return 0
        count = 0
        for f in d.glob("*.md"):
            if f"{field}: {value}" in f.read_text():
                count += 1
        return count

    papers = count_files("papers")
    ideas = count_files("ideas")
    experiments = count_files("experiments")
    claims = count_files("claims")

    edges_path = root / "graph" / "edges.jsonl"
    edge_count = 0
    if edges_path.exists():
        edge_count = sum(1 for line in edges_path.read_text().strip().split("\n") if line.strip())

    print(f"📚 Research Wiki Stats")
    print(f"Papers:      {papers}")
    print(f"Ideas:       {ideas} ({count_by_field('ideas', 'outcome', 'negative')} failed, "
          f"{count_by_field('ideas', 'outcome', 'positive')} succeeded)")
    print(f"Experiments: {experiments}")
    print(f"Claims:      {claims} ({count_by_field('claims', 'status', 'supported')} supported, "
          f"{count_by_field('claims', 'status', 'invalidated')} invalidated)")
    print(f"Edges:       {edge_count}")
    print(f"Wiki root:   {root}")


def _normalize_arxiv_id(arxiv_id: str) -> str:
    """Strip common prefixes and version suffix from arxiv id.

    Preserves legacy category-prefixed IDs: `cs/0601001`, `cs.LG/0703124`
    stay as-is (minus any trailing vN); modern IDs like `2501.12345v2`
    become `2501.12345`. The arXiv API accepts both forms via `id_list=`.
    """
    s = arxiv_id.strip()
    for prefix in ("arXiv:", "arxiv:", "http://arxiv.org/abs/", "https://arxiv.org/abs/"):
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):]
    # Never split on '/' — legacy IDs are `category/NNNNNNN`.
    s = re.sub(r"v\d+$", "", s)
    return s


def _yaml_quote(s: str) -> str:
    """YAML double-quoted string escape: backslash and double-quote.

    Frontmatter values containing a literal `"` (e.g. titles like
    `Foo "Bar" Baz`) would otherwise corrupt the page. Tabs and
    newlines inside metadata fields are also normalized.
    """
    if s is None:
        return '""'
    s = str(s).replace("\r", "").replace("\t", " ")
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def fetch_arxiv_metadata(arxiv_id: str, timeout: float = 15.0) -> dict:
    """Query arXiv Atom API for one paper. Returns a metadata dict.

    Raises RuntimeError on network failure or malformed response — callers
    decide whether to abort the ingest or fall back to manual metadata.
    """
    aid = _normalize_arxiv_id(arxiv_id)
    url = _ARXIV_API.format(ids=aid)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"arXiv API fetch failed for {aid}: {e}")

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise RuntimeError(f"arXiv API returned unparseable XML for {aid}: {e}")

    entry = root.find("atom:entry", _ARXIV_NS)
    if entry is None:
        raise RuntimeError(f"arXiv API returned no entry for {aid}")

    def _txt(el, default=""):
        return el.text.strip() if el is not None and el.text else default

    title = _txt(entry.find("atom:title", _ARXIV_NS))
    title = re.sub(r"\s+", " ", title)
    summary = _txt(entry.find("atom:summary", _ARXIV_NS))
    summary = re.sub(r"\s+", " ", summary)
    published = _txt(entry.find("atom:published", _ARXIV_NS))
    year = int(published[:4]) if published[:4].isdigit() else 0

    authors = []
    for a in entry.findall("atom:author", _ARXIV_NS):
        n = _txt(a.find("atom:name", _ARXIV_NS))
        if n:
            authors.append(n)

    primary = entry.find("arxiv:primary_category", _ARXIV_NS)
    primary_cat = primary.get("term") if primary is not None else ""

    # Check for published journal reference
    journal_ref = _txt(entry.find("arxiv:journal_ref", _ARXIV_NS))
    venue = journal_ref if journal_ref else "arXiv"

    return {
        "arxiv_id": aid,
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
        "abstract": summary,
        "primary_category": primary_cat,
    }


def _last_name(full_name: str) -> str:
    """Crude last-name extraction for slug generation."""
    parts = full_name.strip().split()
    return parts[-1] if parts else ""


def _load_paper_frontmatter(path: Path) -> dict:
    """Parse the YAML-ish frontmatter of a wiki paper page. Returns {} on failure."""
    if not path.exists():
        return {}
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).split("\n"):
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def _find_existing_page_by_arxiv(wiki_root: Path, arxiv_id: str) -> Path | None:
    papers = wiki_root / "papers"
    if not papers.exists():
        return None
    for p in papers.glob("*.md"):
        text = p.read_text()
        # Match either the frontmatter line or a URL reference
        if re.search(r'arxiv:\s*["\']?' + re.escape(arxiv_id) + r'["\']?', text):
            return p
        if re.search(r"arxiv\.org/abs/" + re.escape(arxiv_id), text):
            return p
    return None


def _render_paper_page(meta: dict, slug: str, thesis: str, tags: list[str]) -> str:
    """Render the markdown paper page following research-wiki SKILL.md schema."""
    fm = {
        "type": "paper",
        "node_id": f"paper:{slug}",
        "title": meta.get("title", ""),
        "authors": meta.get("authors", []),
        "year": meta.get("year", 0),
        "venue": meta.get("venue", "arXiv"),
        "tags": tags,
    }
    external_ids = {
        "arxiv": meta.get("arxiv_id", ""),
        "doi": meta.get("doi", ""),
        "s2": meta.get("s2_id", ""),
    }

    lines = ["---"]
    lines.append(f"type: {fm['type']}")
    lines.append(f"node_id: {fm['node_id']}")
    lines.append(f"title: {_yaml_quote(fm['title'])}")
    lines.append("authors: [" + ", ".join(_yaml_quote(a) for a in fm["authors"]) + "]")
    lines.append(f"year: {fm['year']}")
    lines.append(f"venue: {_yaml_quote(fm['venue'])}")
    lines.append("external_ids:")
    for k, v in external_ids.items():
        value_str = _yaml_quote(v) if v else "null"
        lines.append(f"  {k}: {value_str}")
    lines.append("tags: [" + ", ".join(_yaml_quote(t) for t in tags) + "]")
    lines.append(f"added: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {fm['title']}")
    lines.append("")
    lines.append("## One-line thesis")
    lines.append(thesis or "_TODO: fill in after reading._")
    lines.append("")
    lines.append("## Problem / Gap")
    lines.append("_TODO._")
    lines.append("")
    lines.append("## Method")
    lines.append("_TODO._")
    lines.append("")
    lines.append("## Key Results")
    lines.append("_TODO._")
    lines.append("")
    lines.append("## Assumptions")
    lines.append("_TODO._")
    lines.append("")
    lines.append("## Limitations / Failure Modes")
    lines.append("_TODO._")
    lines.append("")
    lines.append("## Reusable Ingredients")
    lines.append("_TODO._")
    lines.append("")
    lines.append("## Open Questions")
    lines.append("_TODO._")
    lines.append("")
    lines.append("## Claims")
    lines.append("_TODO._")
    lines.append("")
    lines.append("## Connections")
    lines.append("_Edges are recorded in `graph/edges.jsonl`; summarize here for human readers._")
    lines.append("")
    lines.append("## Relevance to This Project")
    lines.append("_TODO._")
    lines.append("")
    if meta.get("abstract"):
        lines.append("## Abstract (original)")
        lines.append("")
        lines.append("> " + meta["abstract"])
        lines.append("")

    return "\n".join(lines) + "\n"


def ingest_paper(wiki_root: str, *, arxiv_id: str = "", title: str = "",
                 authors: list[str] | None = None, year: int = 0,
                 venue: str = "", doi: str = "", thesis: str = "",
                 tags: list[str] | None = None,
                 update_on_exist: bool = False) -> Path:
    """Canonical paper-ingest entrypoint.

    Preferred: pass --arxiv-id and let the helper fetch metadata. If the
    arXiv lookup fails (offline, unknown id), callers may supply
    title/authors/year/venue manually; doi is optional.

    Always:
      - slugs the title (author + year + keyword)
      - dedups by arxiv_id first, then by slug — `update_on_exist=False`
        skips rewriting an existing page
      - creates papers/<slug>.md with the schema from research-wiki SKILL.md
      - rebuilds index.md and query_pack.md
      - appends to log.md
    """
    root = Path(wiki_root)
    if not (root / "papers").exists():
        raise RuntimeError(f"{root} is not an initialized wiki (papers/ missing). "
                           f"Run `init` first.")

    tags = tags or []
    authors = authors or []

    meta: dict = {}
    existing: Path | None = None  # populated when we find a prior page (by arxiv or slug)
    if arxiv_id:
        aid = _normalize_arxiv_id(arxiv_id)
        existing = _find_existing_page_by_arxiv(root, aid)
        if existing and not update_on_exist:
            # Contract §3: every activation leaves a receipt. Log the skip
            # so a repeated hook invocation is still observable.
            append_log(str(root), f"ingest_paper: skipped existing paper "
                                  f"{existing.name} (arxiv:{aid})")
            print(f"Paper already ingested: {existing.name} (arxiv:{aid}) — skipping.")
            return existing
        try:
            meta = fetch_arxiv_metadata(aid)
        except RuntimeError as e:
            if title:  # caller provided manual fallback
                print(f"Warning: {e} — falling back to manual metadata.", file=sys.stderr)
                meta = {"arxiv_id": aid}
            else:
                raise
        # Manual overrides on top of fetched metadata
        if title:
            meta["title"] = title
        if authors:
            meta["authors"] = authors
        if year:
            meta["year"] = year
        if venue:
            meta["venue"] = venue
    else:
        if not (title and authors and year):
            raise RuntimeError("Manual ingest requires --title, --authors, and --year "
                               "when --arxiv-id is not supplied.")
        meta = {
            "arxiv_id": "",
            "title": title,
            "authors": authors,
            "year": year,
            "venue": venue or "unknown",
        }
    if doi:
        meta["doi"] = doi

    author_last = _last_name(meta["authors"][0]) if meta.get("authors") else ""
    slug = slugify(meta["title"], author_last, meta.get("year", 0))

    # If we already found a prior page by arXiv-id dedup, reuse its path and
    # slug even if the newly-computed slug differs (e.g., title metadata
    # fluctuated between runs). Otherwise check slug-based dedup.
    if existing:
        page_path = existing
        slug = existing.stem
        was_update = True
    else:
        page_path = root / "papers" / f"{slug}.md"
        if page_path.exists():
            if not update_on_exist:
                append_log(str(root), f"ingest_paper: skipped existing paper "
                                      f"{page_path.name} (slug dedup)")
                print(f"Paper already ingested: {page_path.name} (slug dedup) — skipping.")
                return page_path
            was_update = True
        else:
            was_update = False

    rendered = _render_paper_page(meta, slug, thesis, tags)
    page_path.write_text(rendered)

    # Rebuild derived artifacts
    rebuild_index(str(root))
    rebuild_query_pack(str(root))

    action = "updated" if was_update else "ingested"
    append_log(str(root), f"ingest_paper: {action} paper:{slug} "
                          f"(arxiv:{meta.get('arxiv_id','-')})")
    print(f"Paper {action}: {page_path}")
    return page_path


def sync_papers(wiki_root: str, arxiv_ids: list[str], update_on_exist: bool = False) -> None:
    """Batch backfill: ingest each arxiv id; dedup is handled per-id."""
    errors = []
    for aid in arxiv_ids:
        aid = aid.strip()
        if not aid:
            continue
        try:
            ingest_paper(wiki_root, arxiv_id=aid, update_on_exist=update_on_exist)
        except RuntimeError as e:
            print(f"ERROR: {aid}: {e}", file=sys.stderr)
            errors.append((aid, str(e)))
    if errors:
        print(f"\nsync: {len(errors)} error(s)", file=sys.stderr)
        sys.exit(1)


def rebuild_index(wiki_root: str) -> None:
    """Regenerate index.md from wiki entity files."""
    root = Path(wiki_root)
    lines = ["# Research Wiki Index", "",
             "_Auto-generated by `research_wiki.py rebuild_index`. Do not edit._", ""]

    for subdir, header in [("papers", "Papers"), ("ideas", "Ideas"),
                            ("experiments", "Experiments"), ("claims", "Claims")]:
        d = root / subdir
        if not d.exists():
            continue
        entries = []
        for f in sorted(d.glob("*.md")):
            meta = _load_paper_frontmatter(f)
            node_id = meta.get("node_id", f.stem)
            title = meta.get("title", f.stem)
            year = meta.get("year", "")
            entries.append(f"- `{node_id}` — {title}" + (f" ({year})" if year else ""))
        if entries:
            lines.append(f"## {header} ({len(entries)})")
            lines.extend(entries)
            lines.append("")

    (root / "index.md").write_text("\n".join(lines) + "\n")


def append_log(wiki_root: str, message: str):
    """Append a timestamped entry to log.md."""
    log_path = Path(wiki_root) / "log.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"- `{ts}` {message}\n"

    if log_path.exists():
        with open(log_path, "a") as f:
            f.write(entry)
    else:
        log_path.write_text(f"# Research Wiki Log\n\n{entry}")


def main():
    parser = argparse.ArgumentParser(description="ARIS Research Wiki utilities")
    subparsers = parser.add_subparsers(dest="command")

    # init
    p_init = subparsers.add_parser("init")
    p_init.add_argument("wiki_root")

    # slug
    p_slug = subparsers.add_parser("slug")
    p_slug.add_argument("title")
    p_slug.add_argument("--author", default="")
    p_slug.add_argument("--year", type=int, default=0)

    # add_edge
    p_edge = subparsers.add_parser("add_edge")
    p_edge.add_argument("wiki_root")
    p_edge.add_argument("--from", dest="from_id", required=True)
    p_edge.add_argument("--to", dest="to_id", required=True)
    p_edge.add_argument("--type", dest="edge_type", required=True)
    p_edge.add_argument("--evidence", default="")

    # rebuild_query_pack
    p_qp = subparsers.add_parser("rebuild_query_pack")
    p_qp.add_argument("wiki_root")
    p_qp.add_argument("--max-chars", type=int, default=8000)

    # rebuild_index
    p_idx = subparsers.add_parser("rebuild_index")
    p_idx.add_argument("wiki_root")

    # stats
    p_stats = subparsers.add_parser("stats")
    p_stats.add_argument("wiki_root")

    # log
    p_log = subparsers.add_parser("log")
    p_log.add_argument("wiki_root")
    p_log.add_argument("message")

    # ingest_paper — the canonical ingest entrypoint called by integration hooks
    p_ing = subparsers.add_parser("ingest_paper",
                                   help="Create (or update) a papers/<slug>.md page")
    p_ing.add_argument("wiki_root")
    p_ing.add_argument("--arxiv-id", default="",
                       help="arXiv identifier (2501.12345 or with v2); metadata auto-fetched")
    p_ing.add_argument("--title", default="",
                       help="Paper title; required when --arxiv-id is absent")
    p_ing.add_argument("--authors", default="",
                       help='Comma-separated author list, e.g. "Alice Smith, Bob Jones"')
    p_ing.add_argument("--year", type=int, default=0)
    p_ing.add_argument("--venue", default="")
    p_ing.add_argument("--external-id-doi", dest="doi", default="")
    p_ing.add_argument("--thesis", default="",
                       help="One-line thesis; otherwise left as TODO for later enrichment")
    p_ing.add_argument("--tags", default="",
                       help="Comma-separated tag list")
    p_ing.add_argument("--update-on-exist", action="store_true",
                       help="Overwrite an existing page instead of skipping (default: skip)")

    # sync — batch backfill
    p_sync = subparsers.add_parser("sync",
                                    help="Batch ingest from a list of arXiv IDs")
    p_sync.add_argument("wiki_root")
    p_sync.add_argument("--arxiv-ids", default="",
                        help="Comma-separated list of arXiv IDs")
    p_sync.add_argument("--from-file", default="",
                        help="Path to a newline-delimited file of arXiv IDs (# comments ok)")
    p_sync.add_argument("--update-on-exist", action="store_true")

    args = parser.parse_args()

    if args.command == "init":
        init_wiki(args.wiki_root)
    elif args.command == "slug":
        print(slugify(args.title, args.author, args.year))
    elif args.command == "add_edge":
        add_edge(args.wiki_root, args.from_id, args.to_id, args.edge_type, args.evidence)
    elif args.command == "rebuild_query_pack":
        rebuild_query_pack(args.wiki_root, args.max_chars)
    elif args.command == "rebuild_index":
        rebuild_index(args.wiki_root)
    elif args.command == "stats":
        get_stats(args.wiki_root)
    elif args.command == "log":
        append_log(args.wiki_root, args.message)
    elif args.command == "ingest_paper":
        authors = [a.strip() for a in args.authors.split(",") if a.strip()]
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        ingest_paper(args.wiki_root,
                     arxiv_id=args.arxiv_id, title=args.title,
                     authors=authors, year=args.year, venue=args.venue,
                     doi=args.doi, thesis=args.thesis, tags=tags,
                     update_on_exist=args.update_on_exist)
    elif args.command == "sync":
        ids: list[str] = []
        if args.arxiv_ids:
            ids.extend([i.strip() for i in args.arxiv_ids.split(",") if i.strip()])
        if args.from_file:
            fp = Path(args.from_file)
            if not fp.exists():
                print(f"--from-file not found: {fp}", file=sys.stderr)
                sys.exit(2)
            for line in fp.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    ids.append(line)
        if not ids:
            print("sync: no arxiv ids supplied (use --arxiv-ids or --from-file)",
                  file=sys.stderr)
            sys.exit(2)
        # Dedup the id list before we hit the network
        seen: set[str] = set()
        uniq_ids: list[str] = []
        for i in ids:
            key = _normalize_arxiv_id(i)
            if key in seen:
                continue
            seen.add(key)
            uniq_ids.append(i)
        print(f"sync: {len(uniq_ids)} unique arxiv id(s)")
        sync_papers(args.wiki_root, uniq_ids, update_on_exist=args.update_on_exist)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
