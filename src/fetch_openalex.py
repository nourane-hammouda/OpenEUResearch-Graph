from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

OPENALEX_WORKS_URL = "https://api.openalex.org/works"


def fetch_works(
    output_path: Path,
    max_pages: int = 8,
    per_page: int = 200,
    mailto: str = "research-graph@example.org",
    works_filter: str = "awards.funder_id:F4320332161",
    ec_only: bool = False,
    search_term: str | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cursor = "*"
    collected: list[dict] = []

    headers = {"User-Agent": f"projet-graphe-recherche-eu ({mailto})"}
    for page in range(max_pages):
        params = {
            "filter": works_filter,
            "per-page": per_page,
            "cursor": cursor,
            "mailto": mailto,
        }
        if search_term:
            params["search"] = search_term
        response = requests.get(OPENALEX_WORKS_URL, params=params, headers=headers, timeout=120)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        if not results:
            break
        if ec_only:
            for work in results:
                grants = work.get("grants", []) or []
                names = [str(grant.get("funder_display_name") or "").lower() for grant in grants]
                if any("european commission" in name for name in names):
                    collected.append(work)
        else:
            collected.extend(results)
        cursor = payload.get("meta", {}).get("next_cursor")
        print(f"[ok] openalex page {page + 1}: raw={len(results)} kept={len(collected)}")
        if not cursor:
            break

    output_path.write_text(json.dumps(collected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] saved {len(collected)} OpenAlex works to {output_path}")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch real OpenAlex works funded by EC")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/openalex/works_ec_funded.json"),
        help="Output JSON file",
    )
    parser.add_argument("--max-pages", type=int, default=8, help="Max OpenAlex pages")
    parser.add_argument("--per-page", type=int, default=200, help="Rows per page")
    parser.add_argument(
        "--mailto",
        type=str,
        default="research-graph@example.org",
        help="Contact email sent to API for fair-use",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default="awards.funder_id:F4320332161",
        help="OpenAlex API filter string (default = European Commission funder id)",
    )
    parser.add_argument("--ec-only", action="store_true", help="Keep only works tagged with European Commission grant")
    parser.add_argument("--search", type=str, default=None, help="Optional OpenAlex full-text search term")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    fetch_works(
        output_path=args.output,
        max_pages=args.max_pages,
        per_page=args.per_page,
        mailto=args.mailto,
        works_filter=args.filter,
        ec_only=args.ec_only,
        search_term=args.search,
    )
