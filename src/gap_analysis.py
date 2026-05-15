from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import networkx as nx
import pandas as pd


def run(processed_dir: Path, graphs_dir: Path, min_score: float = 0.4) -> dict[str, str]:
    thematic_path = graphs_dir / "thematic_implicit.gexf"
    explicit_edges_path = processed_dir / "edges_org_org_explicit.csv"
    organizations_path = processed_dir / "organizations.csv"
    metrics_path = graphs_dir / "organization_metrics.json"

    if not thematic_path.exists():
        raise FileNotFoundError("Missing thematic_implicit.gexf. Run build_thematic_layer.py first.")
    thematic_graph = nx.read_gexf(thematic_path)

    organizations = pd.read_csv(organizations_path, encoding="utf-8") if organizations_path.exists() else pd.DataFrame()
    metrics = pd.DataFrame(json.loads(metrics_path.read_text(encoding="utf-8"))) if metrics_path.exists() else pd.DataFrame()

    org_meta: dict[str, dict[str, object]] = {}
    if not organizations.empty and "org_id" in organizations.columns:
        organizations = organizations.copy()
        organizations["org_id"] = organizations["org_id"].astype(str)
        organizations["country"] = organizations.get("country", "").astype(str)
        organizations["org_type"] = organizations.get("org_type", "").astype(str)
        organizations["nb_projects"] = pd.to_numeric(organizations.get("nb_projects"), errors="coerce").fillna(0).astype(int)
        organizations["budget_total_received"] = pd.to_numeric(
            organizations.get("budget_total_received"), errors="coerce"
        ).fillna(0.0)
        organizations = organizations.drop_duplicates(subset=["org_id"], keep="first").copy()
        org_meta = organizations.set_index("org_id").to_dict(orient="index")

    metric_map: dict[str, dict[str, object]] = {}
    if not metrics.empty and "org_id" in metrics.columns:
        metric_map = {str(row["org_id"]): row for row in metrics.to_dict(orient="records")}

    positive_burt = sorted(
        (
            (oid, float(row.get("burt_constraint_thematic", 0.0) or 0.0))
            for oid, row in metric_map.items()
            if float(row.get("burt_constraint_thematic", 0.0) or 0.0) > 0
        ),
        key=lambda item: item[1],
    )
    burt_rank = {oid: idx for idx, (oid, _) in enumerate(positive_burt, start=1)}
    broker_cutoff = max(5, int(len(positive_burt) * 0.30)) if positive_burt else 0

    def is_broker(org_id: str) -> bool:
        row = metric_map.get(org_id, {})
        betweenness = float(row.get("betweenness_collab", 0.0) or 0.0)
        return betweenness > 0 and burt_rank.get(org_id, 10**9) <= broker_cutoff

    def size_balance_score(org_a: str, org_b: str) -> float:
        a = org_meta.get(org_a, {})
        b = org_meta.get(org_b, {})
        a_projects = max(1, int(a.get("nb_projects", 0) or 0))
        b_projects = max(1, int(b.get("nb_projects", 0) or 0))
        ratio = min(a_projects, b_projects) / max(a_projects, b_projects)
        return float(ratio)

    def compute_priority_score(org_a: str, org_b: str, thematic_score: float) -> float:
        a = org_meta.get(org_a, {})
        b = org_meta.get(org_b, {})
        country_bonus = 1.0 if str(a.get("country", "")) and str(a.get("country", "")) != str(b.get("country", "")) else 0.0
        type_bonus = 1.0 if str(a.get("org_type", "")) and str(a.get("org_type", "")) != str(b.get("org_type", "")) else 0.0
        broker_bonus = 1.0 if is_broker(org_a) or is_broker(org_b) else 0.0
        balance = size_balance_score(org_a, org_b)
        score = (
            0.60 * thematic_score
            + 0.15 * broker_bonus
            + 0.10 * country_bonus
            + 0.10 * type_bonus
            + 0.05 * balance
        )
        return round(float(min(1.0, max(0.0, score))), 6)

    def priority_label(score: float) -> str:
        if score >= 0.80:
            return "Tres forte"
        if score >= 0.65:
            return "Forte"
        if score >= 0.55:
            return "Intermediaire"
        return "A surveiller"

    explicit_pairs: set[tuple[str, str]] = set()
    if explicit_edges_path.exists():
        explicit = pd.read_csv(explicit_edges_path, encoding="utf-8")
        for row in explicit.itertuples(index=False):
            explicit_pairs.add(tuple(sorted([str(row.org_a), str(row.org_b)])))

    gap_graph = nx.Graph()
    gaps: list[dict[str, str | float]] = []
    for left, right, data in thematic_graph.edges(data=True):
        score = float(data.get("weight", 0.0))
        if score < min_score:
            continue
        pair = tuple(sorted([str(left), str(right)]))
        if pair in explicit_pairs:
            continue
        gap_graph.add_node(str(left), **thematic_graph.nodes[str(left)])
        gap_graph.add_node(str(right), **thematic_graph.nodes[str(right)])
        a = str(left)
        b = str(right)
        priority = compute_priority_score(a, b, score)
        left_meta = org_meta.get(a, {})
        right_meta = org_meta.get(b, {})
        left_is_broker = is_broker(a)
        right_is_broker = is_broker(b)
        same_country = str(left_meta.get("country", "")) == str(right_meta.get("country", ""))
        same_type = str(left_meta.get("org_type", "")) == str(right_meta.get("org_type", ""))
        balance = size_balance_score(a, b)
        gap_graph.add_edge(
            a,
            b,
            edge_type="gap_opportunity",
            weight=score,
            priority_score=priority,
            left_broker=left_is_broker,
            right_broker=right_is_broker,
        )
        gaps.append(
            {
                "org_a": a,
                "org_b": b,
                "thematic_score": round(score, 6),
                "priority_score": priority,
                "priority_label": priority_label(priority),
                "org_a_country": str(left_meta.get("country", "")),
                "org_b_country": str(right_meta.get("country", "")),
                "org_a_type": str(left_meta.get("org_type", "")),
                "org_b_type": str(right_meta.get("org_type", "")),
                "org_a_projects": int(left_meta.get("nb_projects", 0) or 0),
                "org_b_projects": int(right_meta.get("nb_projects", 0) or 0),
                "org_a_budget": round(float(left_meta.get("budget_total_received", 0.0) or 0.0), 2),
                "org_b_budget": round(float(right_meta.get("budget_total_received", 0.0) or 0.0), 2),
                "org_a_broker": left_is_broker,
                "org_b_broker": right_is_broker,
                "cross_country": not same_country,
                "cross_type": not same_type,
                "size_balance_score": round(balance, 6),
            }
        )

    gaps = sorted(
        gaps,
        key=lambda item: (
            float(item.get("priority_score", 0.0)),
            float(item.get("thematic_score", 0.0)),
        ),
        reverse=True,
    )
    graphs_dir.mkdir(parents=True, exist_ok=True)
    gap_json_path = graphs_dir / "gap_analysis_top.json"
    # GEXF export was for external Gephi inspection only; the pipeline reads
    # gap_analysis_top.json so we no longer write the duplicate graph file.
    gap_json_path.write_text(json.dumps(gaps[:3000], ensure_ascii=False, indent=2), encoding="utf-8")

    return {"gap_top": str(gap_json_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute thematic-vs-explicit collaboration gaps")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"))
    parser.add_argument("--min-score", type=float, default=0.4)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output = run(processed_dir=args.processed_dir, graphs_dir=args.graphs_dir, min_score=args.min_score)
    print("Generated gap analysis files:")
    for key, value in output.items():
        print(f"- {key}: {value}")
