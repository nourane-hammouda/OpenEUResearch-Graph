from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx


def communities_to_map(communities: list[set[str]]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, community in enumerate(communities):
        for node in community:
            mapping[str(node)] = index
    return mapping


def run(graphs_dir: Path) -> dict[str, str]:
    collab_path = graphs_dir / "collab_explicit.gexf"
    thematic_path = graphs_dir / "thematic_implicit.gexf"
    if not collab_path.exists():
        raise FileNotFoundError("Missing collab_explicit.gexf. Run build_graph.py first.")
    if not thematic_path.exists():
        raise FileNotFoundError("Missing thematic_implicit.gexf. Run build_thematic_layer.py first.")

    collab = nx.read_gexf(collab_path)
    thematic = nx.read_gexf(thematic_path)

    org_nodes_collab = [node for node, data in collab.nodes(data=True) if data.get("node_type") == "organization"]
    collab_org = collab.subgraph(org_nodes_collab).copy()
    thematic_org = thematic.copy()

    pagerank = nx.pagerank(collab_org, weight="weight") if collab_org.number_of_nodes() else {}
    if collab_org.number_of_nodes():
        sample_k = min(500, collab_org.number_of_nodes())
        betweenness = nx.betweenness_centrality(
            collab_org,
            k=sample_k,
            weight="weight",
            normalized=True,
            seed=42,
        )
    else:
        betweenness = {}
    burt_constraint = nx.constraint(thematic_org) if thematic_org.number_of_nodes() else {}

    collab_communities = nx.community.louvain_communities(collab_org, weight="weight", seed=42) if collab_org.number_of_nodes() else []
    thematic_communities = (
        nx.community.louvain_communities(thematic_org, weight="weight", seed=42) if thematic_org.number_of_nodes() else []
    )
    collab_community_map = communities_to_map(collab_communities)
    thematic_community_map = communities_to_map(thematic_communities)

    metrics_rows: list[dict] = []
    for node in sorted(set(collab_org.nodes()).union(thematic_org.nodes())):
        metrics_rows.append(
            {
                "org_id": str(node),
                "pagerank_collab": float(pagerank.get(node, 0.0)),
                "betweenness_collab": float(betweenness.get(node, 0.0)),
                "burt_constraint_thematic": float(burt_constraint.get(node, 0.0)),
                "community_collab": collab_community_map.get(str(node), -1),
                "community_thematic": thematic_community_map.get(str(node), -1),
            }
        )

    summary = {
        "collab_nodes": collab_org.number_of_nodes(),
        "collab_edges": collab_org.number_of_edges(),
        "thematic_nodes": thematic_org.number_of_nodes(),
        "thematic_edges": thematic_org.number_of_edges(),
        "n_collab_communities": len(collab_communities),
        "n_thematic_communities": len(thematic_communities),
        "top_pagerank": sorted(
            [{"org_id": key, "score": value} for key, value in pagerank.items()],
            key=lambda item: item["score"],
            reverse=True,
        )[:30],
    }

    metrics_path = graphs_dir / "organization_metrics.json"
    summary_path = graphs_dir / "metrics_summary.json"
    metrics_path.write_text(json.dumps(metrics_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"metrics": str(metrics_path), "summary": str(summary_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PageRank, Louvain, betweenness, Burt constraint")
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    outputs = run(graphs_dir=args.graphs_dir)
    print("Generated analytics files:")
    for key, value in outputs.items():
        print(f"- {key}: {value}")
