from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run_step(command: list[str], cwd: Path) -> None:
    print(f"[run] {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd), check=True)  # noqa: S603


def main(project_root: Path, max_rows: int, max_pages: int, include_openaire: bool) -> None:
    run_step(["python", "src/fetch_cordis.py", "--max-rows", str(max_rows)], cwd=project_root)
    run_step(["python", "src/fetch_openalex.py", "--max-pages", str(max_pages), "--per-page", "200"], cwd=project_root)
    if include_openaire:
        run_step(["python", "src/fetch_openaire.py", "--size", "500"], cwd=project_root)
    run_step(["python", "src/clean_normalize.py"], cwd=project_root)
    run_step(["python", "src/build_graph.py"], cwd=project_root)
    run_step(["python", "src/build_thematic_layer.py"], cwd=project_root)
    run_step(["python", "src/gap_analysis.py"], cwd=project_root)
    run_step(["python", "src/algorithms.py"], cwd=project_root)
    run_step(["python", "src/temporal_analysis.py"], cwd=project_root)
    run_step(["python", "src/verify_data_sources.py"], cwd=project_root)
    # src/visualize.py produces a static matplotlib PNG that is unreadable
    # for the full graph; the interactive Folium pipeline below replaces it.
    run_step(["python", "src/visualize_folium.py"], cwd=project_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute full European research graph pipeline")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--max-rows", type=int, default=40000)
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--include-openaire", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        project_root=args.project_root,
        max_rows=args.max_rows,
        max_pages=args.max_pages,
        include_openaire=args.include_openaire,
    )
