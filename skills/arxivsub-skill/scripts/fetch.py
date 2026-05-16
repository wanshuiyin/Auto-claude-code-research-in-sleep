"""
fetch.py — arXivSub paper detail fetcher
Bundled with arxivsub-skill.

Two modes:
  --for-ranking   Print concise [{id, title, what_about}, ...] for all papers
                  (feed into LLM to select relevant paper IDs before fetching full details)
  <id1> <id2>...  Print full details for the given paper IDs

Usage (called by Claude via bash_tool):
    python3 fetch.py ./tmp/arxivsub_papers.json --for-ranking
    python3 fetch.py ./tmp/arxivsub_papers.json <id1> <id2> ...
"""

import json
import sys


def main():
    if len(sys.argv) < 3:
        sys.stderr.write("Usage: fetch.py <papers_path> --for-ranking\n"
                         "       fetch.py <papers_path> <id1> [id2 ...]\n")
        sys.exit(1)

    papers_path = sys.argv[1]
    with open(papers_path) as f:
        papers = json.load(f)

    if sys.argv[2] == "--for-ranking":
        index = [{"id": p["id"], "title": p["title"], "what_about": p["what_about"]} for p in papers]
        print(json.dumps(index, ensure_ascii=False, indent=2))
        return

    requested_ids = set(sys.argv[2:])
    results = [p for p in papers if p.get("id") in requested_ids]

    if not results:
        sys.stderr.write("No papers found for the given IDs.\n")
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
