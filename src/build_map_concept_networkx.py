from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx
import pandas as pd
from networkx.readwrite import json_graph


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8", low_memory=False)


def safe_float(value: object, default: float = 0.0) -> float:
    number = pd.to_numeric([value], errors="coerce")[0]
    if pd.isna(number):
        return default
    return float(number)


def safe_int(value: object, default: int = 0) -> int:
    number = pd.to_numeric([value], errors="coerce")[0]
    if pd.isna(number):
        return default
    return int(number)


def compute_broker_map(metrics: pd.DataFrame) -> dict[str, bool]:
    if metrics.empty or "org_id" not in metrics.columns:
        return {}

    rows = metrics.copy()
    rows["org_id"] = rows["org_id"].astype(str)
    rows["burt_constraint_thematic"] = pd.to_numeric(rows.get("burt_constraint_thematic"), errors="coerce").fillna(0.0)
    rows["betweenness_collab"] = pd.to_numeric(rows.get("betweenness_collab"), errors="coerce").fillna(0.0)

    positive = rows[rows["burt_constraint_thematic"] > 0].sort_values("burt_constraint_thematic", ascending=True).copy()
    if positive.empty:
        return {org_id: False for org_id in rows["org_id"].tolist()}

    cutoff = max(5, int(len(positive) * 0.30))
    top_ids = set(positive.head(cutoff)["org_id"].astype(str).tolist())
    broker_map: dict[str, bool] = {}
    for row in rows.itertuples(index=False):
        org_id = str(getattr(row, "org_id"))
        bet = safe_float(getattr(row, "betweenness_collab", 0.0))
        broker_map[org_id] = org_id in top_ids and bet > 0
    return broker_map


def run(
    processed_dir: Path,
    graphs_dir: Path,
    output_prefix: str,
    max_collab_edges: int,
    max_gap_edges: int,
    full: bool,
) -> dict[str, str]:
    organizations = load_csv(processed_dir / "organizations.csv")
    edges_org_org = load_csv(processed_dir / "edges_org_org_explicit.csv")

    gap_json_path = graphs_dir / "gap_analysis_top.json"
    gap_rows: list[dict[str, object]] = json.loads(gap_json_path.read_text(encoding="utf-8")) if gap_json_path.exists() else []

    metrics_path = graphs_dir / "organization_metrics.json"
    metrics = pd.DataFrame(json.loads(metrics_path.read_text(encoding="utf-8"))) if metrics_path.exists() else pd.DataFrame()
    broker_map = compute_broker_map(metrics)

    graph = nx.MultiGraph()
    org_rows = organizations.copy()
    org_rows["org_id"] = org_rows["org_id"].astype(str)
    org_rows["budget_total_received"] = pd.to_numeric(org_rows.get("budget_total_received"), errors="coerce").fillna(0.0)
    org_rows["nb_projects"] = pd.to_numeric(org_rows.get("nb_projects"), errors="coerce").fillna(0).astype(int)
    org_rows["latitude"] = pd.to_numeric(org_rows.get("latitude"), errors="coerce")
    org_rows["longitude"] = pd.to_numeric(org_rows.get("longitude"), errors="coerce")

    for row in org_rows.itertuples(index=False):
        org_id = str(getattr(row, "org_id"))
        lat = safe_float(getattr(row, "latitude", 0.0))
        lon = safe_float(getattr(row, "longitude", 0.0))
        graph.add_node(
            org_id,
            node_type="organization",
            label=str(getattr(row, "org_name", org_id)),
            country=str(getattr(row, "country", "")),
            city=str(getattr(row, "city", "")),
            org_type=str(getattr(row, "org_type", "")),
            budget_total_received=safe_float(getattr(row, "budget_total_received", 0.0)),
            nb_projects=safe_int(getattr(row, "nb_projects", 0)),
            latitude=lat,
            longitude=lon,
            has_coordinates=bool(lat and lon),
            is_broker=bool(broker_map.get(org_id, False)),
        )

    collab = edges_org_org.copy()
    if not collab.empty:
        collab["org_a"] = collab["org_a"].astype(str)
        collab["org_b"] = collab["org_b"].astype(str)
        collab["weight_common_projects"] = pd.to_numeric(collab.get("weight_common_projects"), errors="coerce").fillna(0.0)
        collab = collab.sort_values("weight_common_projects", ascending=False)
        if not full:
            collab = collab.head(max_collab_edges)

        for row in collab.itertuples(index=False):
            left = str(getattr(row, "org_a"))
            right = str(getattr(row, "org_b"))
            if not graph.has_node(left) or not graph.has_node(right):
                continue
            weight = safe_float(getattr(row, "weight_common_projects", 0.0))
            graph.add_edge(
                left,
                right,
                key=f"explicit:{left}:{right}",
                edge_type="explicit_collaboration",
                weight_common_projects=weight,
                weight=weight,
            )

    if not full:
        gap_iterable = gap_rows[:max_gap_edges]
    else:
        gap_iterable = gap_rows

    for idx, item in enumerate(gap_iterable):
        left = str(item.get("org_a", ""))
        right = str(item.get("org_b", ""))
        if not left or not right or not graph.has_node(left) or not graph.has_node(right):
            continue
        thematic_score = safe_float(item.get("thematic_score", 0.0))
        priority_score = safe_float(item.get("priority_score", 0.0))
        graph.add_edge(
            left,
            right,
            key=f"gap:{idx}",
            edge_type="gap_opportunity",
            thematic_score=thematic_score,
            priority_score=priority_score,
            priority_label=str(item.get("priority_label", "")),
            cross_country=bool(item.get("cross_country", False)),
            cross_type=bool(item.get("cross_type", False)),
            weight=priority_score if priority_score > 0 else thematic_score,
        )

    graphs_dir.mkdir(parents=True, exist_ok=True)
    graphml_path = graphs_dir / f"{output_prefix}.graphml"
    gexf_path = graphs_dir / f"{output_prefix}.gexf"
    json_path = graphs_dir / f"{output_prefix}.json"

    nx.write_graphml(graph, graphml_path)
    nx.write_gexf(graph, gexf_path)
    payload = json_graph.node_link_data(graph)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "nodes_total": graph.number_of_nodes(),
        "edges_total": graph.number_of_edges(),
        "explicit_edges": sum(1 for _, _, _, data in graph.edges(keys=True, data=True) if data.get("edge_type") == "explicit_collaboration"),
        "gap_edges": sum(1 for _, _, _, data in graph.edges(keys=True, data=True) if data.get("edge_type") == "gap_opportunity"),
        "full_mode": full,
    }
    summary_path = graphs_dir / f"{output_prefix}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "graphml": str(graphml_path),
        "gexf": str(gexf_path),
        "json": str(json_path),
        "summary": str(summary_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a NetworkX graph with the same concept as the Folium research map")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"))
    parser.add_argument("--output-prefix", type=str, default="map_concept_networkx")
    parser.add_argument("--max-collab-edges", type=int, default=400)
    parser.add_argument("--max-gap-edges", type=int, default=2000)
    parser.add_argument("--full", action="store_true", help="Include all explicit and gap edges")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    outputs = run(
        processed_dir=args.processed_dir,
        graphs_dir=args.graphs_dir,
        output_prefix=args.output_prefix,
        max_collab_edges=args.max_collab_edges,
        max_gap_edges=args.max_gap_edges,
        full=args.full,
    )
    print("Generated NetworkX map-concept files:")
    for key, value in outputs.items():
        print(f"- {key}: {value}")
