"""
search.py — arXivSub API client + parser
Bundled with arxivsub-skill.

Fetches papers from the arXivSub API, parses the response, and writes full
paper details to ./tmp/arxivsub_papers.json.

The API key is read from the ARXIVSUB_SKILL_KEY environment variable or a .env
file in the current directory. Never pass it as a command-line argument.

Usage (called by Claude via bash_tool):
    python3 search.py \
        --query  "LLM safety alignment" \
        --locations arxiv NeurIPS ICLR \
        --limit  10 \
        --arxiv-days 14 \
        --conf-years 2024 2025
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

API_URL = "https://qtevnmgyobilaanrzidq.supabase.co/functions/v1/agent-skills-gateway"


def load_api_key() -> str:
    """Read API key from environment or .env file. Exit with setup instructions if missing."""
    key = os.environ.get("ARXIVSUB_SKILL_KEY", "").strip()
    if key:
        return key

    # Fallback: parse a .env file in the current directory
    env_file = os.path.join(os.getcwd(), ".env")
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ARXIVSUB_SKILL_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if key:
                        return key

    sys.stderr.write(
        "ARXIVSUB_SKILL_KEY is not set.\n"
        "Set it up using one of these methods:\n"
        "  1. Export as an environment variable:\n"
        "       export ARXIVSUB_SKILL_KEY=your_key_here\n"
        "  2. Add it to a .env file in your working directory:\n"
        "       ARXIVSUB_SKILL_KEY=your_key_here\n"
        "Your API key can be found on the Skills page of the arXivSub website.\n"
    )
    sys.exit(1)


def _parse_summary(summary_content: str) -> dict:
    """
    Split summary_content by <SEG> and extract structured fields.

    Layout after adjustment (0-indexed):
      [0] what it's about   [1] innovations   [2] techniques
      [3] datasets          [4] results       [5] limitations
      [6] first_author_name [7] first_aff     [8] last_author_name [9] last_aff

    If 11 segments: skip segment[0] (duplicate title), use [1..10].
    If 10 segments: use [0..9] directly.
    """
    segments = summary_content.split("<SEG>")
    content = segments[1:] if len(segments) == 11 else segments

    if len(content) < 10:
        return {
            "what_about":  summary_content[:300],
            "innovations": "",
            "techniques":  "",
            "datasets":    "",
            "results":     "",
            "limitations": "",
        }

    return {
        "what_about":  content[0].strip(),
        "innovations": content[1].strip(),
        "techniques":  content[2].strip(),
        "datasets":    content[3].strip(),
        "results":     content[4].strip(),
        "limitations": content[5].strip(),
    }


def parse_response(raw: str):
    """
    Parse the raw JSON string returned by the arXivSub API.

    Returns (papers, quota):
        papers  — list of fully structured paper dicts
        quota   — quota_remaining (int) or None
    """
    data = json.loads(raw)

    all_papers = []
    for source in ("arxiv", "conferences"):
        for paper in data.get(source, []):
            paper["_source"] = source
            all_papers.append(paper)

    papers = []
    for p in all_papers:
        parsed = _parse_summary(p.get("summary_content", ""))

        authors = p.get("authors", [])
        first = next((a for a in authors if a.get("is_first_author")), authors[0] if authors else {})
        last  = next((a for a in authors if a.get("is_last_author")),  authors[-1] if authors else {})

        papers.append({
            "id":           p.get("id"),
            "title":        p.get("title"),
            "source":       p.get("_source"),
            "conference":   p.get("conference_name", "arXiv"),
            "year":         p.get("publish_year"),
            "arxiv_id":     p.get("arxiv_id"),
            "pdf_url":      p.get("pdf_url"),
            "first_author": first.get("name", ""),
            "first_aff":    first.get("affiliation", ""),
            "last_author":  last.get("name", ""),
            "last_aff":     last.get("affiliation", ""),
            "keywords":     [k["name"] for k in p.get("keywords", [])],
            **parsed,
        })

    quota = data.get("quota_remaining")
    return papers, quota


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query",       required=True,  help="Search query string")
    parser.add_argument("--locations",   nargs="+",      default=["arxiv"],
                        help="Sources: arxiv CVPR ICCV ICLR ICML NeurIPS AAAI MICCAI (case-sensitive)")
    parser.add_argument("--limit",       type=int,       default=10)
    parser.add_argument("--arxiv-days",  type=int,       default=None)
    parser.add_argument("--conf-years",  type=int,       nargs="+", default=None)
    parser.add_argument("--language",    default="en")
    args = parser.parse_args()

    api_key = load_api_key()

    body = {
        "query":     args.query,
        "language":  args.language,
        "locations": args.locations,
        "limit":     args.limit,
    }
    if args.arxiv_days is not None:
        body["arxiv_days"] = args.arxiv_days
    if args.conf_years is not None:
        body["conference_years"] = args.conf_years

    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-agent-skill-key": api_key,
    }

    req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        sys.stderr.write(f"HTTP {e.code}: {error_body}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(f"Request failed: {e.reason}\n")
        sys.exit(1)

    papers, quota = parse_response(raw)

    out_dir = os.path.join(os.getcwd(), "tmp")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "arxivsub_papers.json")
    with open(out_path, "w") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    print(f"quota_remaining={quota}, total_papers={len(papers)}, output={out_path}")


if __name__ == "__main__":
    main()
