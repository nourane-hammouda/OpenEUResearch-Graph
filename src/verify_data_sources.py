from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def file_info(path: Path) -> dict[str, str | int | bool]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": int(stat.st_size),
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    }


def quick_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        frame = pd.read_csv(path, nrows=200000, low_memory=False)
        return int(len(frame))
    except Exception:
        return -1


def run(raw_dir: Path, processed_dir: Path, output: Path) -> Path:
    cordis_files = [
        raw_dir / "cordis" / "h2020_projects_trimmed.csv",
        raw_dir / "cordis" / "h2020_organizations_trimmed.csv",
        raw_dir / "cordis" / "he_projects_trimmed.csv",
        raw_dir / "cordis" / "he_organizations_trimmed.csv",
    ]
    openalex_file = raw_dir / "openalex" / "works_ec_funded.json"

    report = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "sources": {
            "cordis": {
                "official_portal": "https://cordis.europa.eu/data",
                "downloads": [file_info(path) for path in cordis_files],
                "row_estimates": {str(path): quick_csv_rows(path) for path in cordis_files},
            },
            "openalex": {
                "official_api": "https://api.openalex.org/works",
                "ec_funder_id": "F4320332161",
                "dump": file_info(openalex_file),
            },
        },
        "processed_tables": {
            "organizations": file_info(processed_dir / "organizations.csv"),
            "projects": file_info(processed_dir / "projects.csv"),
            "publications": file_info(processed_dir / "publications.csv"),
            "edges_org_project": file_info(processed_dir / "edges_org_project.csv"),
            "edges_org_org_explicit": file_info(processed_dir / "edges_org_org_explicit.csv"),
            "edges_org_publication": file_info(processed_dir / "edges_org_publication.csv"),
            "edges_org_concept": file_info(processed_dir / "edges_org_concept.csv"),
        },
        "integrity_checks": {},
    }

    org_path = processed_dir / "organizations.csv"
    proj_path = processed_dir / "projects.csv"
    edge_path = processed_dir / "edges_org_project.csv"
    if org_path.exists() and proj_path.exists() and edge_path.exists():
        org = pd.read_csv(org_path, low_memory=False)
        proj = pd.read_csv(proj_path, low_memory=False)
        edge = pd.read_csv(edge_path, low_memory=False)
        report["integrity_checks"] = {
            "n_organizations": int(len(org)),
            "n_projects": int(len(proj)),
            "n_edges_org_project": int(len(edge)),
            "funding_non_negative": bool((pd.to_numeric(edge["weight_eur"], errors="coerce").fillna(0) >= 0).all()),
            "org_edge_coverage": float(edge["source_org_id"].astype(str).isin(org["org_id"].astype(str)).mean())
            if len(edge)
            else 1.0,
            "project_edge_coverage": float(edge["target_project_id"].astype(str).isin(proj["project_id"].astype(str)).mean())
            if len(edge)
            else 1.0,
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create data provenance and integrity report")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output", type=Path, default=Path("data/graphs/data_provenance_report.json"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    path = run(raw_dir=args.raw_dir, processed_dir=args.processed_dir, output=args.output)
    print(f"Data provenance report written to: {path}")
