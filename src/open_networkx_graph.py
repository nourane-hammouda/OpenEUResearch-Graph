from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

import networkx as nx
from pyvis.network import Network


def as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_view_subgraph(graph: nx.Graph, max_nodes: int, max_edges: int) -> nx.Graph:
    if graph.number_of_nodes() <= max_nodes and graph.number_of_edges() <= max_edges:
        return graph.copy()

    degree_sorted = sorted(graph.degree, key=lambda item: item[1], reverse=True)
    selected_nodes = {node for node, _ in degree_sorted[:max_nodes]}
    subgraph = graph.subgraph(selected_nodes).copy()

    if subgraph.number_of_edges() <= max_edges:
        return subgraph

    weighted_edges = []
    for left, right, data in subgraph.edges(data=True):
        edge_weight = as_float(data.get("weight", data.get("weight_common_projects", data.get("thematic_score", 1.0))), 1.0)
        weighted_edges.append((left, right, edge_weight, data))
    weighted_edges.sort(key=lambda item: item[2], reverse=True)

    pruned = nx.Graph()
    pruned.add_nodes_from(subgraph.nodes(data=True))
    for left, right, _, data in weighted_edges[:max_edges]:
        pruned.add_edge(left, right, **data)
    return pruned


def render_pyvis(graph: nx.Graph, output_html: Path, title: str) -> None:
    net = Network(height="900px", width="100%", bgcolor="#ffffff", font_color="#111827")
    net.barnes_hut(gravity=-30000, central_gravity=0.25, spring_length=170, spring_strength=0.04, damping=0.9)

    for node_id, data in graph.nodes(data=True):
        node_type = str(data.get("node_type", "organization"))
        label = str(data.get("label", node_id))
        country = str(data.get("country", "N/A"))
        budget = as_float(data.get("budget_total_received", 0.0))
        is_broker = bool(data.get("is_broker", False))
        node_color = "#1d4ed8"
        if node_type != "organization":
            node_color = "#7c3aed"
        if is_broker:
            node_color = "#f59e0b"
        size = 7 + min(30, budget / 50_000_000.0)
        tooltip = (
            f"<b>{label}</b><br>"
            f"ID: {node_id}<br>"
            f"Type: {node_type}<br>"
            f"Pays: {country}<br>"
            f"Budget: {budget:,.0f} EUR<br>"
            f"Broker: {'Oui' if is_broker else 'Non'}"
        )
        net.add_node(str(node_id), label=label[:80], title=tooltip, color=node_color, size=size)

    for left, right, data in graph.edges(data=True):
        edge_type = str(data.get("edge_type", "link"))
        if edge_type == "explicit_collaboration":
            color = "#dc2626"
            weight = as_float(data.get("weight_common_projects", data.get("weight", 1.0)), 1.0)
            title_edge = (
                f"<b>Collaboration explicite</b><br>"
                f"Poids (projets communs): {weight:,.0f}"
            )
        elif edge_type == "gap_opportunity":
            color = "#7c3aed"
            thematic = as_float(data.get("thematic_score", 0.0))
            priority = as_float(data.get("priority_score", 0.0))
            title_edge = (
                f"<b>Opportunité de collaboration</b><br>"
                f"Score thématique: {thematic:.3f}<br>"
                f"Priorité: {priority:.3f}"
            )
            weight = max(1.0, priority * 5)
        else:
            color = "#6b7280"
            weight = as_float(data.get("weight", 1.0))
            title_edge = f"<b>Lien</b><br>Poids: {weight:,.3f}"

        net.add_edge(str(left), str(right), color=color, value=max(1.0, weight), title=title_edge)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    net.save_graph(str(output_html))

    html_text = output_html.read_text(encoding="utf-8")
    html_text = html_text.replace("<title>Pyvis network</title>", f"<title>{title}</title>")
    output_html.write_text(html_text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open a NetworkX graph in browser with Python 3")
    parser.add_argument("--input-gexf", type=Path, default=Path("data/graphs/map_concept_networkx.gexf"))
    parser.add_argument("--output-html", type=Path, default=Path("data/graphs/map_concept_networkx_view.html"))
    parser.add_argument("--max-nodes", type=int, default=2500, help="Max nodes shown in the browser view")
    parser.add_argument("--max-edges", type=int, default=8000, help="Max edges shown in the browser view")
    parser.add_argument("--no-open", action="store_true", help="Generate HTML only, do not open browser")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input_gexf.exists():
        raise FileNotFoundError(f"Input graph not found: {args.input_gexf}")

    graph = nx.read_gexf(args.input_gexf)
    view_graph = build_view_subgraph(graph, max_nodes=args.max_nodes, max_edges=args.max_edges)
    render_pyvis(view_graph, args.output_html, "Map Concept NetworkX View")

    print("Generated browser graph view:")
    print(f"- input: {args.input_gexf}")
    print(f"- output: {args.output_html}")
    print(f"- nodes_shown: {view_graph.number_of_nodes()}")
    print(f"- edges_shown: {view_graph.number_of_edges()}")

    if not args.no_open:
        webbrowser.open(args.output_html.resolve().as_uri())
        print("- opened_in_browser: yes")
    else:
        print("- opened_in_browser: no")


if __name__ == "__main__":
    main()
