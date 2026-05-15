from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx
import pandas as pd


def to_float(value: object, default: float = 0.0) -> float:
    number = pd.to_numeric([value], errors="coerce")[0]
    if pd.isna(number):
        return default
    return float(number)


def to_int(value: object, default: int = 0) -> int:
    number = pd.to_numeric([value], errors="coerce")[0]
    if pd.isna(number):
        return default
    return int(number)


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8", low_memory=False)


def build_explicit_graph(processed_dir: Path) -> nx.Graph:
    organizations = load_csv(processed_dir / "organizations.csv")
    projects = load_csv(processed_dir / "projects.csv")
    publications = load_csv(processed_dir / "publications.csv")
    edges_org_project = load_csv(processed_dir / "edges_org_project.csv")
    edges_org_org = load_csv(processed_dir / "edges_org_org_explicit.csv")
    edges_org_publication = load_csv(processed_dir / "edges_org_publication.csv")

    graph = nx.Graph()

    for row in organizations.itertuples(index=False):
        graph.add_node(
            str(row.org_id),
            node_type="organization",
            label=str(row.org_name),
            country=str(row.country),
            org_type=str(row.org_type),
            budget_total_received=to_float(row.budget_total_received),
            nb_projects=to_int(row.nb_projects),
        )

    for row in projects.itertuples(index=False):
        graph.add_node(
            str(row.project_id),
            node_type="project",
            label=str(row.project_title),
            program=str(row.program),
            topic_label=str(row.topic_label),
            project_budget_eur=to_float(row.project_budget_eur),
        )

    for row in publications.itertuples(index=False):
        graph.add_node(
            str(row.publication_id),
            node_type="publication",
            label=str(row.title),
            doi=str(row.doi),
            year=to_int(row.year),
            journal=str(row.journal),
        )

    for row in edges_org_project.itertuples(index=False):
        graph.add_edge(
            str(row.source_org_id),
            str(row.target_project_id),
            edge_type="org_project_funding",
            weight=to_float(row.weight_eur),
        )

    for row in edges_org_org.itertuples(index=False):
        graph.add_edge(
            str(row.org_a),
            str(row.org_b),
            edge_type="org_org_explicit",
            weight=to_float(row.weight_common_projects),
        )

    for row in edges_org_publication.itertuples(index=False):
        graph.add_edge(
            str(row.source_org_id),
            str(row.publication_id),
            edge_type="org_publication_authorship",
            weight=1.0,
        )

    return graph


def export_json(graph: nx.Graph, path: Path) -> None:
    payload = nx.node_link_data(graph)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run(processed_dir: Path, graphs_dir: Path) -> dict[str, str]:
    explicit = build_explicit_graph(processed_dir=processed_dir)
    graphs_dir.mkdir(parents=True, exist_ok=True)

    collab_path = graphs_dir / "collab_explicit.gexf"

    # Heavy duplicate exports (multiplex_full.graphml ~246 MB, .json ~231 MB)
    # are intended for external Gephi inspection only and are never read back
    # by the pipeline. They are skipped to keep data/graphs/ light.
    nx.write_gexf(explicit, collab_path)

    return {
        "collab_explicit": str(collab_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build explicit collaboration graph layers")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"), help="Processed data folder")
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"), help="Graph output folder")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    out = run(processed_dir=args.processed_dir, graphs_dir=args.graphs_dir)
    print("Generated graph files:")
    for key, value in out.items():
        print(f"- {key}: {value}")
