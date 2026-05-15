from __future__ import annotations

import argparse
import io
from pathlib import Path
import zipfile

import pandas as pd
import requests

CORDIS_URLS = {
    "h2020_projects": [
        "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip",
        "https://cordis.europa.eu/data/cordis-h2020projects.csv",
    ],
    "h2020_organizations": [
        "https://cordis.europa.eu/data/cordis-h2020organizations.csv",
        "https://cordis.europa.eu/data/cordis-h2020organizations-csv.zip",
    ],
    "he_projects": [
        "https://cordis.europa.eu/data/cordis-heprojects.csv",
        "https://cordis.europa.eu/data/cordis-HEprojects.csv",
        "https://cordis.europa.eu/data/cordis-heprojects-csv.zip",
        "https://cordis.europa.eu/data/cordis-HEprojects-csv.zip",
    ],
    "he_organizations": [
        "https://cordis.europa.eu/data/cordis-heorganizations.csv",
        "https://cordis.europa.eu/data/cordis-HEorganizations.csv",
        "https://cordis.europa.eu/data/cordis-heorganizations-csv.zip",
        "https://cordis.europa.eu/data/cordis-HEorganizations-csv.zip",
    ],
}


def download_file(url: str, destination: Path, timeout: int = 120) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with destination.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_handle.write(chunk)
    return destination


def extract_csv_from_archive(zip_path: Path, destination_csv: Path, preferred_names: list[str] | None = None) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No CSV found in archive: {zip_path}")
        selected = None
        preferred_names = preferred_names or []
        lower_map = {name.lower(): name for name in csv_names}
        for candidate in preferred_names:
            if candidate.lower() in lower_map:
                selected = lower_map[candidate.lower()]
                break
        if selected is None:
            selected = csv_names[0]
        with archive.open(selected) as source:
            content = source.read()
    destination_csv.write_bytes(content)
    return destination_csv


def read_cordis_csv_from_bytes(raw: bytes, max_rows: int | None = None) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(raw), sep=";", encoding="utf-8-sig", low_memory=False, nrows=max_rows)


def read_cordis_csv(path: Path, max_rows: int | None = None) -> pd.DataFrame:
    # CORDIS CSV commonly uses ';' and utf-8-sig.
    return pd.read_csv(
        path,
        sep=";",
        encoding="utf-8-sig",
        nrows=max_rows,
        engine="python",
        on_bad_lines="skip",
    )


def looks_like_projects_table(frame: pd.DataFrame) -> bool:
    columns = {column.lower() for column in frame.columns}
    return "title" in columns and ("id" in columns or "projectid" in columns)


def looks_like_organizations_table(frame: pd.DataFrame) -> bool:
    columns = {column.lower() for column in frame.columns}
    return "name" in columns and ("projectid" in columns or "organisationid" in columns or "organizationid" in columns)


def run(output_dir: Path, max_rows: int | None = None) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for key, urls in CORDIS_URLS.items():
        last_error: Exception | None = None
        for url in urls:
            try:
                if url.lower().endswith(".zip"):
                    zip_destination = output_dir / f"{key}.zip"
                    download_file(url=url, destination=zip_destination)
                    raw_csv = output_dir / f"{key}_raw.csv"
                    if key.endswith("_projects"):
                        extract_csv_from_archive(zip_destination, raw_csv, preferred_names=["project.csv"])
                        # Some project archives also embed participant-level organization.csv.
                        org_key = key.replace("_projects", "_organizations")
                        org_raw = output_dir / f"{org_key}_raw.csv"
                        org_trimmed = output_dir / f"{org_key}_trimmed.csv"
                        try:
                            extract_csv_from_archive(zip_destination, org_raw, preferred_names=["organization.csv"])
                            org_df = read_cordis_csv(org_raw, max_rows=max_rows)
                            if not looks_like_organizations_table(org_df):
                                raise ValueError("Embedded organization.csv schema is invalid")
                            org_df.to_csv(org_trimmed, index=False, encoding="utf-8")
                            if org_key not in outputs:
                                outputs[org_key] = str(org_trimmed)
                                print(f"[ok] {org_key}: {len(org_df)} rows (embedded in {url})")
                        except Exception:
                            pass
                    elif key.endswith("_organizations"):
                        extract_csv_from_archive(zip_destination, raw_csv, preferred_names=["organization.csv"])
                    else:
                        extract_csv_from_archive(zip_destination, raw_csv)
                    dataframe = read_cordis_csv(raw_csv, max_rows=max_rows)
                else:
                    raw_csv = output_dir / f"{key}_raw.csv"
                    download_file(url=url, destination=raw_csv)
                    dataframe = read_cordis_csv(raw_csv, max_rows=max_rows)

                if key.endswith("_projects") and not looks_like_projects_table(dataframe):
                    raise ValueError("Downloaded table does not match expected projects schema")
                if key.endswith("_organizations") and not looks_like_organizations_table(dataframe):
                    raise ValueError("Downloaded table does not match expected organizations schema")

                trimmed = output_dir / f"{key}_trimmed.csv"
                dataframe.to_csv(trimmed, index=False, encoding="utf-8")
                outputs[key] = str(trimmed)
                print(f"[ok] {key}: {len(dataframe)} rows ({url})")
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        if key not in outputs:
            print(f"[warn] {key}: {last_error}")
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download real CORDIS datasets")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/cordis"),
        help="Target folder for raw CORDIS CSV files",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional row cap to speed up local runs",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(output_dir=args.output_dir, max_rows=args.max_rows)
