from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def run(processed_dir: Path, output_path: Path) -> Path:
    edges_org_concept_path = processed_dir / "edges_org_concept.csv"
    if not edges_org_concept_path.exists():
        raise FileNotFoundError("Missing edges_org_concept.csv. Run clean_normalize.py first.")
    edges = pd.read_csv(edges_org_concept_path, encoding="utf-8")
    if edges.empty:
        pd.DataFrame(columns=["org_id", "concept_vector"]).to_csv(output_path, index=False, encoding="utf-8")
        return output_path

    # Lightweight fallback embedding: sparse topic profile serialized as JSON-like string.
    top = (
        edges.sort_values("weight", ascending=False)
        .groupby("source_org_id")
        .head(20)
        .groupby("source_org_id")
        .apply(lambda frame: ";".join(f"{row.concept_label}:{row.weight:.4f}" for row in frame.itertuples(index=False)))
        .reset_index(name="concept_vector")
        .rename(columns={"source_org_id": "org_id"})
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    top.to_csv(output_path, index=False, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build lightweight org embeddings from concept profiles")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/embeddings/organization_embeddings.csv"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output = run(processed_dir=args.processed_dir, output_path=args.output)
    print(f"Embeddings written to: {output}")
