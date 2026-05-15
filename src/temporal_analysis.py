from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def classify_period(program_value: str) -> str:
    value = str(program_value).lower()
    if "h2020" in value:
        return "H2020"
    if "he_" in value or "horizon" in value:
        return "Horizon Europe"
    if "fp7" in value:
        return "FP7"
    return "Other"


def run(processed_dir: Path, graphs_dir: Path) -> Path:
    projects_path = processed_dir / "projects.csv"
    edges_org_project_path = processed_dir / "edges_org_project.csv"

    if not projects_path.exists() or not edges_org_project_path.exists():
        raise FileNotFoundError("Missing processed CORDIS tables. Run clean_normalize.py first.")

    projects = pd.read_csv(projects_path, encoding="utf-8")
    edges = pd.read_csv(edges_org_project_path, encoding="utf-8")
    projects["period"] = projects["program"].map(classify_period)

    merged = edges.merge(projects[["project_id", "period"]], left_on="target_project_id", right_on="project_id", how="left")
    summary = (
        merged.groupby("period", as_index=False)
        .agg(
            n_org_project_edges=("source_org_id", "count"),
            n_unique_orgs=("source_org_id", "nunique"),
            n_unique_projects=("target_project_id", "nunique"),
            total_funding_eur=("weight_eur", "sum"),
        )
        .sort_values("period")
    )

    graphs_dir.mkdir(parents=True, exist_ok=True)
    output_path = graphs_dir / "temporal_summary.csv"
    summary.to_csv(output_path, index=False, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute temporal snapshots FP7/H2020/HE")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output = run(processed_dir=args.processed_dir, graphs_dir=args.graphs_dir)
    print(f"Temporal summary written to: {output}")
