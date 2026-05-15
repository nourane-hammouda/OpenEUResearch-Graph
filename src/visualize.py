from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path("data/graphs/.mpl-cache")))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx


def run(graphs_dir: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
    graph_path = graphs_dir / "collab_explicit.gexf"
    if not graph_path.exists():
        raise FileNotFoundError("Missing collab_explicit.gexf. Run build_graph.py first.")

    graph = nx.read_gexf(graph_path)
    org_nodes = [node for node, data in graph.nodes(data=True) if data.get("node_type") == "organization"]
    org_graph = graph.subgraph(org_nodes).copy()
    if org_graph.number_of_nodes() == 0:
        raise ValueError("No organization nodes found in explicit graph.")

    # Spring layout is enough for quick structural inspection.
    positions = nx.spring_layout(org_graph, seed=42, k=0.18, iterations=120)
    fig = plt.figure(figsize=(13, 10))
    axis = fig.add_subplot(111)
    axis.set_title("Reseau explicite de co-participation (organisations)")
    nx.draw_networkx_edges(org_graph, positions, alpha=0.18, width=0.5, edge_color="#5f6a72", ax=axis)
    nx.draw_networkx_nodes(org_graph, positions, node_size=18, node_color="#d62728", alpha=0.85, ax=axis)
    axis.axis("off")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create quick static visualization for explicit network")
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/graphs/collab_explicit_overview.png"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output = run(graphs_dir=args.graphs_dir, output_path=args.output)
    print(f"Visualization written to: {output}")
