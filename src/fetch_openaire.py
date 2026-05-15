from __future__ import annotations

import argparse
from pathlib import Path

import requests

OPENAIRE_GRAPH_URL = "https://api.openaire.eu/graph/v1/publications"


def fetch_publications(output_path: Path, size: int = 200) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    params = {
        "size": size,
        "funderName": "European Commission",
    }
    response = requests.get(OPENAIRE_GRAPH_URL, params=params, timeout=120)
    response.raise_for_status()
    output_path.write_text(response.text, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch OpenAIRE publications linked to EU funding")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/openaire/publications_ec.json"),
        help="Output raw response file",
    )
    parser.add_argument("--size", type=int, default=200, help="Requested records count")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        path = fetch_publications(output_path=args.output, size=args.size)
        print(f"[ok] OpenAIRE response saved to {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] OpenAIRE fetch failed: {exc}")
