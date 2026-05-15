from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


def cosine_similarity_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normalized = matrix / norms
    return normalized @ normalized.T


def build_org_concept_matrix(edges_org_concept: pd.DataFrame) -> tuple[list[str], list[str], np.ndarray]:
    org_ids = sorted(edges_org_concept["source_org_id"].astype(str).unique().tolist())
    concepts = sorted(edges_org_concept["concept_label"].astype(str).unique().tolist())
    org_index = {org_id: idx for idx, org_id in enumerate(org_ids)}
    concept_index = {concept: idx for idx, concept in enumerate(concepts)}
    matrix = np.zeros((len(org_ids), len(concepts)), dtype=float)
    for row in edges_org_concept.itertuples(index=False):
        matrix[org_index[str(row.source_org_id)], concept_index[str(row.concept_label)]] = float(row.weight)
    return org_ids, concepts, matrix


def run(processed_dir: Path, graphs_dir: Path, threshold: float = 0.30) -> dict[str, str]:
    edges_org_concept_path = processed_dir / "edges_org_concept.csv"
    edges_org_org_explicit_path = processed_dir / "edges_org_org_explicit.csv"
    organizations_path = processed_dir / "organizations.csv"

    if not edges_org_concept_path.exists():
        raise FileNotFoundError("Missing edges_org_concept.csv. Run clean_normalize.py first.")

    edges_org_concept = pd.read_csv(edges_org_concept_path, encoding="utf-8")
    organizations = pd.read_csv(organizations_path, encoding="utf-8")
    org_lookup = dict(zip(organizations["org_id"].astype(str), organizations["org_name"].astype(str), strict=False))

    explicit_pairs: set[tuple[str, str]] = set()
    if edges_org_org_explicit_path.exists():
        explicit = pd.read_csv(edges_org_org_explicit_path, encoding="utf-8")
        for row in explicit.itertuples(index=False):
            left, right = sorted([str(row.org_a), str(row.org_b)])
            explicit_pairs.add((left, right))

    org_ids, _, matrix = build_org_concept_matrix(edges_org_concept)
    similarity = cosine_similarity_matrix(matrix)

    thematic_graph = nx.Graph()
    for org_id in org_ids:
        thematic_graph.add_node(org_id, node_type="organization", label=org_lookup.get(org_id, org_id))

    opportunities: list[dict[str, str | float]] = []
    for i in range(len(org_ids)):
        for j in range(i + 1, len(org_ids)):
            score = float(similarity[i, j])
            if score < threshold:
                continue
            left, right = org_ids[i], org_ids[j]
            pair = tuple(sorted([left, right]))
            explicit_collab = pair in explicit_pairs
            thematic_graph.add_edge(
                left,
                right,
                edge_type="org_org_thematic",
                weight=score,
                explicit_collab=explicit_collab,
            )
            if not explicit_collab:
                opportunities.append({"org_a": left, "org_b": right, "thematic_score": score})

    opportunities = sorted(opportunities, key=lambda item: float(item["thematic_score"]), reverse=True)
    top_opportunities = opportunities[:3000]

    graphs_dir.mkdir(parents=True, exist_ok=True)
    thematic_path = graphs_dir / "thematic_implicit.gexf"
    # gap_candidates.json was an intermediate artifact superseded by
    # gap_analysis_top.json (produced by gap_analysis.py); we no longer write it.
    nx.write_gexf(thematic_graph, thematic_path)

    return {"thematic_graph": str(thematic_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build implicit thematic organization graph")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"), help="Processed input folder")
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"), help="Graph output folder")
    parser.add_argument("--threshold", type=float, default=0.30, help="Cosine similarity threshold")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    out = run(processed_dir=args.processed_dir, graphs_dir=args.graphs_dir, threshold=args.threshold)
    print("Generated thematic files:")
    for key, value in out.items():
        print(f"- {key}: {value}")
