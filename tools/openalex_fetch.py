#!/usr/bin/env python3
"""
OpenAlex API client for academic paper search.
Documentation: https://developers.openalex.org/
"""

import requests
import argparse
import json
import sys
import os
from typing import List, Dict, Optional


class OpenAlexClient:
    BASE_URL = "https://api.openalex.org"

    def __init__(self, api_key: Optional[str] = None, email: Optional[str] = None):
        """
        Initialize OpenAlex client.

        Args:
            api_key: Optional API key for higher rate limits
            email: Optional email for polite pool (faster response)
        """
        self.api_key = api_key or os.environ.get("OPENALEX_API_KEY")
        self.email = email or os.environ.get("OPENALEX_EMAIL")
        self.session = requests.Session()

        # Set user agent with email for polite pool
        if self.email:
            self.session.headers.update({
                "User-Agent": f"mailto:{self.email}"
            })

    def search_works(
        self,
        query: str,
        max_results: int = 10,
        publication_year: Optional[str] = None,
        work_type: Optional[str] = None,
        open_access: Optional[bool] = None,
        min_citations: Optional[int] = None,
        sort: str = "relevance_score:desc",
        fields: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Search for academic works.

        Args:
            query: Search query string
            max_results: Maximum number of results (default: 10)
            publication_year: Year filter, e.g., "2023" or "2020-2023"
            work_type: Type filter, e.g., "article", "preprint", "book"
            open_access: Filter by open access status
            min_citations: Minimum citation count
            sort: Sort order (default: relevance_score:desc)
            fields: Specific fields to return (default: all)

        Returns:
            List of work dictionaries
        """
        url = f"{self.BASE_URL}/works"

        # Build filter string
        filters = []
        if publication_year:
            filters.append(f"publication_year:{publication_year}")
        if work_type:
            filters.append(f"type:{work_type}")
        if open_access is not None:
            filters.append(f"is_oa:{str(open_access).lower()}")
        if min_citations:
            filters.append(f"cited_by_count:>{min_citations}")

        params = {
            "search": query,
            "per_page": min(max_results, 200),  # API max is 200
            "sort": sort
        }

        if filters:
            params["filter"] = ",".join(filters)

        if self.api_key:
            params["api_key"] = self.api_key

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            results = []
            for work in data.get("results", []):
                results.append(self._parse_work(work))

            return results[:max_results]

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("Rate limit exceeded. Consider using an API key or reducing request frequency.", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Error fetching from OpenAlex: {e}", file=sys.stderr)
            raise

    def get_work(self, work_id: str) -> Dict:
        """
        Get a specific work by ID, DOI, or OpenAlex ID.

        Args:
            work_id: Work identifier (DOI, OpenAlex ID, etc.)

        Returns:
            Work dictionary
        """
        # Handle different ID formats
        if work_id.startswith("10."):  # DOI
            url = f"{self.BASE_URL}/works/doi:{work_id}"
        elif work_id.startswith("W"):  # OpenAlex ID
            url = f"{self.BASE_URL}/works/{work_id}"
        else:
            url = f"{self.BASE_URL}/works/{work_id}"

        params = {}
        if self.api_key:
            params["api_key"] = self.api_key

        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()

        return self._parse_work(response.json())

    def _parse_work(self, work: Dict) -> Dict:
        """Parse OpenAlex work object into simplified format."""
        # Extract authors
        authors = []
        for authorship in work.get("authorships", []):
            author = authorship.get("author", {})
            author_name = author.get("display_name", "Unknown")
            authors.append(author_name)

        # Extract venue/source
        primary_location = work.get("primary_location", {})
        source = primary_location.get("source", {})
        venue = source.get("display_name", "Unknown")

        # Extract open access info
        oa_info = work.get("open_access", {})
        oa_status = oa_info.get("oa_status", "closed")
        oa_url = oa_info.get("oa_url")

        # Extract abstract (inverted index format)
        abstract_inverted = work.get("abstract_inverted_index")
        abstract = self._reconstruct_abstract(abstract_inverted) if abstract_inverted else None

        # Extract topics/keywords
        topics = [t.get("display_name") for t in work.get("topics", [])[:3]]
        keywords = [k.get("display_name") for k in work.get("keywords", [])[:5]]

        return {
            "id": work.get("id"),
            "openalex_id": work.get("id", "").split("/")[-1],
            "doi": work.get("doi", "").replace("https://doi.org/", "") if work.get("doi") else None,
            "title": work.get("display_name") or work.get("title", "Untitled"),
            "authors": authors,
            "author_count": len(authors),
            "publication_year": work.get("publication_year"),
            "publication_date": work.get("publication_date"),
            "venue": venue,
            "venue_type": source.get("type"),
            "cited_by_count": work.get("cited_by_count", 0),
            "is_oa": work.get("is_oa", False),
            "oa_status": oa_status,
            "oa_url": oa_url,
            "abstract": abstract,
            "topics": topics,
            "keywords": keywords,
            "type": work.get("type"),
            "language": work.get("language"),
            "referenced_works_count": work.get("referenced_works_count", 0),
            "url": work.get("id")
        }

    def _reconstruct_abstract(self, inverted_index: Dict) -> str:
        """Reconstruct abstract from inverted index format."""
        if not inverted_index:
            return None

        # Create list of (position, word) tuples
        words = []
        for word, positions in inverted_index.items():
            for pos in positions:
                words.append((pos, word))

        # Sort by position and join
        words.sort(key=lambda x: x[0])
        return " ".join(word for _, word in words)


def main():
    parser = argparse.ArgumentParser(
        description="Search OpenAlex for academic papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search
  %(prog)s search "semantic communication" --max 10

  # Filter by year and type
  %(prog)s search "diffusion models" --year 2023- --type article --max 20

  # Open access papers only
  %(prog)s search "machine learning" --open-access --min-citations 50

  # Get specific work by DOI
  %(prog)s work "10.1109/TWC.2024.1234567"

  # Sort by citations
  %(prog)s search "neural networks" --sort citations --max 10
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search for works")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--max", type=int, default=10, help="Maximum results (default: 10)")
    search_parser.add_argument("--year", help="Publication year filter (e.g., '2023' or '2020-2023')")
    search_parser.add_argument("--type", choices=["article", "preprint", "book", "book-chapter", "dataset", "dissertation"],
                              help="Work type filter")
    search_parser.add_argument("--open-access", action="store_true", help="Only open access papers")
    search_parser.add_argument("--min-citations", type=int, help="Minimum citation count")
    search_parser.add_argument("--sort", choices=["relevance", "citations", "date"],
                              default="relevance", help="Sort order (default: relevance)")
    search_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Work command
    work_parser = subparsers.add_parser("work", help="Get specific work by ID/DOI")
    work_parser.add_argument("work_id", help="Work ID (DOI, OpenAlex ID, etc.)")
    work_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize client
    client = OpenAlexClient()

    try:
        if args.command == "search":
            # Map sort option to API format
            sort_map = {
                "relevance": "relevance_score:desc",
                "citations": "cited_by_count:desc",
                "date": "publication_date:desc"
            }

            results = client.search_works(
                query=args.query,
                max_results=args.max,
                publication_year=args.year,
                work_type=args.type,
                open_access=args.open_access if args.open_access else None,
                min_citations=args.min_citations,
                sort=sort_map[args.sort]
            )

            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print(f"Found {len(results)} papers:\n")
                for i, work in enumerate(results, 1):
                    print(f"{i}. {work['title']}")
                    print(f"   Authors: {', '.join(work['authors'][:3])}{' et al.' if len(work['authors']) > 3 else ''}")
                    print(f"   Year: {work['publication_year']} | Venue: {work['venue']}")
                    print(f"   Citations: {work['cited_by_count']} | OA: {'Yes' if work['is_oa'] else 'No'}")
                    if work['doi']:
                        print(f"   DOI: {work['doi']}")
                    if work['oa_url']:
                        print(f"   PDF: {work['oa_url']}")
                    if work['abstract']:
                        abstract_preview = work['abstract'][:200] + "..." if len(work['abstract']) > 200 else work['abstract']
                        print(f"   Abstract: {abstract_preview}")
                    print()

        elif args.command == "work":
            work = client.get_work(args.work_id)

            if args.json:
                print(json.dumps(work, indent=2))
            else:
                print(f"Title: {work['title']}")
                print(f"Authors: {', '.join(work['authors'])}")
                print(f"Year: {work['publication_year']} | Venue: {work['venue']}")
                print(f"Citations: {work['cited_by_count']} | OA: {'Yes' if work['is_oa'] else 'No'}")
                if work['doi']:
                    print(f"DOI: {work['doi']}")
                if work['oa_url']:
                    print(f"PDF: {work['oa_url']}")
                if work['topics']:
                    print(f"Topics: {', '.join(work['topics'])}")
                if work['abstract']:
                    print(f"\nAbstract:\n{work['abstract']}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
