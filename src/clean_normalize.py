from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from pathlib import Path

import pandas as pd


def normalize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", str(value).upper())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_token(value: object) -> str:
    cleaned = normalize_name(str(value or ""))
    return cleaned.replace(" ", "_")


def has_real_identifier(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.lower() not in {"nan", "none", "null"}


def make_org_id(country: object, org_id_raw: object, org_name_norm: object, city: object, org_type: object) -> str:
    country_code = str(country or "").upper().strip()[:2] or "XX"
    raw_text = str(org_id_raw or "").strip()
    if has_real_identifier(raw_text):
        base = normalize_token(raw_text)[:60] or "ORG"
        signature = raw_text
    else:
        base = normalize_token(org_name_norm)[:60] or "ORG"
        signature = "|".join(
            [
                str(org_name_norm or "").strip(),
                str(city or "").strip().upper(),
                str(org_type or "").strip().upper(),
            ]
        )
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:10]
    return f"{country_code}_{base}_{digest}"


def pick_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lowered = {column.lower(): column for column in frame.columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def parse_geolocation(value: object) -> tuple[float | None, float | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        return None, None
    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except Exception:  # noqa: BLE001
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon


def load_cordis_projects(cordis_dir: Path) -> pd.DataFrame:
    files = [cordis_dir / "h2020_projects_trimmed.csv", cordis_dir / "he_projects_trimmed.csv"]
    frames: list[pd.DataFrame] = []
    for file_path in files:
        if file_path.exists():
            frame = pd.read_csv(file_path, encoding="utf-8", low_memory=False)
            frame["program_file"] = file_path.stem
            frames.append(frame)
    if not frames:
        raise FileNotFoundError("No CORDIS projects file found. Run fetch_cordis.py first.")
    projects = pd.concat(frames, ignore_index=True)
    project_id_col = pick_column(projects, ["id", "projectID", "project_id", "rcn"])
    title_col = pick_column(projects, ["title", "acronym", "projectAcronym"])
    start_col = pick_column(projects, ["startDate", "start_date"])
    end_col = pick_column(projects, ["endDate", "end_date"])
    topic_col = pick_column(projects, ["topics", "euroSciVocPath", "objective"])
    budget_col = pick_column(projects, ["totalCost", "ecMaxContribution", "ecContribution"])

    out = pd.DataFrame(
        {
            "project_id": projects[project_id_col].astype(str) if project_id_col else projects.index.astype(str),
            "project_title": projects[title_col].astype(str) if title_col else "",
            "program": projects["program_file"].astype(str),
            "start_date": projects[start_col].astype(str) if start_col else "",
            "end_date": projects[end_col].astype(str) if end_col else "",
            "topic_label": projects[topic_col].astype(str) if topic_col else "",
            "project_budget_eur": pd.to_numeric(
                projects[budget_col].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            ).fillna(0.0)
            if budget_col
            else 0.0,
        }
    )
    out["project_title"] = out["project_title"].fillna("").astype(str).str.strip()
    out.loc[out["project_title"].eq(""), "project_title"] = out["project_id"]
    return out.drop_duplicates(subset=["project_id"]).reset_index(drop=True)


def load_cordis_organizations(cordis_dir: Path) -> pd.DataFrame:
    files = [cordis_dir / "h2020_organizations_trimmed.csv", cordis_dir / "he_organizations_trimmed.csv"]
    frames: list[pd.DataFrame] = []
    for file_path in files:
        if file_path.exists():
            frame = pd.read_csv(file_path, encoding="utf-8", low_memory=False)
            frame["program_file"] = file_path.stem
            frames.append(frame)
    if not frames:
        # CORDIS frequently provides participant-level rows inside project extracts.
        fallback_files = [cordis_dir / "h2020_projects_trimmed.csv", cordis_dir / "he_projects_trimmed.csv"]
        for file_path in fallback_files:
            if file_path.exists():
                frame = pd.read_csv(file_path, encoding="utf-8", low_memory=False)
                frame["program_file"] = file_path.stem
                frames.append(frame)
    if not frames:
        raise FileNotFoundError("No CORDIS organization-compatible file found. Run fetch_cordis.py first.")

    organizations = pd.concat(frames, ignore_index=True)
    org_name_col = pick_column(organizations, ["name", "legalName", "organizationName"])
    org_id_col = pick_column(organizations, ["id", "organizationID", "pic", "vatNumber"])
    project_id_col = pick_column(organizations, ["projectID", "project_id", "projectRcn"])
    country_col = pick_column(organizations, ["country", "countryCode"])
    city_col = pick_column(organizations, ["city"])
    amount_col = pick_column(organizations, ["ecContribution", "netEcContribution", "totalCost"])
    type_col = pick_column(organizations, ["organizationType", "activityType", "type"])
    geolocation_col = pick_column(organizations, ["geolocation", "geoLocation", "latlon"])

    out = pd.DataFrame(
        {
            "org_id_raw": organizations[org_id_col].astype(str) if org_id_col else organizations.index.astype(str),
            "org_name": organizations[org_name_col].astype(str) if org_name_col else "UNKNOWN_ORG",
            "project_id": organizations[project_id_col].astype(str) if project_id_col else "",
            "country": organizations[country_col].astype(str) if country_col else "",
            "city": organizations[city_col].astype(str) if city_col else "",
            "org_type": organizations[type_col].astype(str) if type_col else "",
            "geolocation": organizations[geolocation_col].astype(str) if geolocation_col else "",
            "amount_eur": pd.to_numeric(organizations[amount_col], errors="coerce").fillna(0.0)
            if amount_col
            else 0.0,
        }
    )
    out["org_name_norm"] = out["org_name"].map(normalize_name)
    out["org_id"] = out.apply(
        lambda row: make_org_id(
            country=row.get("country", ""),
            org_id_raw=row.get("org_id_raw", ""),
            org_name_norm=row.get("org_name_norm", ""),
            city=row.get("city", ""),
            org_type=row.get("org_type", ""),
        ),
        axis=1,
    )
    geos = out["geolocation"].map(parse_geolocation)
    out["latitude"] = geos.map(lambda item: item[0])
    out["longitude"] = geos.map(lambda item: item[1])
    return out


def build_openalex_tables(openalex_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not openalex_path.exists():
        return (
            pd.DataFrame(columns=["publication_id", "doi", "year", "title", "journal"]),
            pd.DataFrame(columns=["org_name_norm", "publication_id"]),
            pd.DataFrame(columns=["publication_id", "concept_label", "concept_score"]),
        )

    works = json.loads(openalex_path.read_text(encoding="utf-8"))
    publication_rows: list[dict] = []
    org_pub_rows: list[dict] = []
    concept_rows: list[dict] = []

    for work in works:
        publication_id = str(work.get("id", ""))
        if not publication_id:
            continue
        source = (work.get("primary_location") or {}).get("source") or {}
        publication_rows.append(
            {
                "publication_id": publication_id,
                "doi": str(work.get("doi") or ""),
                "year": int(work.get("publication_year") or 0),
                "title": str(work.get("title") or ""),
                "journal": str(source.get("display_name") or ""),
            }
        )

        for authorship in work.get("authorships", []) or []:
            for institution in authorship.get("institutions", []) or []:
                name = str(institution.get("display_name") or "")
                if not name:
                    continue
                org_pub_rows.append(
                    {
                        "org_name_norm": normalize_name(name),
                        "publication_id": publication_id,
                    }
                )

        for concept in work.get("concepts", []) or []:
            label = str(concept.get("display_name") or "")
            if not label:
                continue
            concept_rows.append(
                {
                    "publication_id": publication_id,
                    "concept_label": label,
                    "concept_score": float(concept.get("score") or 0.0),
                }
            )

    publications = pd.DataFrame(publication_rows).drop_duplicates(subset=["publication_id"])
    org_publication = pd.DataFrame(org_pub_rows).drop_duplicates()
    publication_concepts = pd.DataFrame(concept_rows)
    return publications, org_publication, publication_concepts


def build_processed_tables(raw_dir: Path, processed_dir: Path) -> dict[str, str]:
    cordis_dir = raw_dir / "cordis"
    openalex_path = raw_dir / "openalex" / "works_ec_funded.json"

    projects = load_cordis_projects(cordis_dir)
    org_project_raw = load_cordis_organizations(cordis_dir)

    organizations = (
        org_project_raw.groupby(["org_id"], as_index=False)
        .agg(
            org_name_norm=("org_name_norm", "first"),
            org_name=("org_name", "first"),
            country=("country", "first"),
            city=("city", "first"),
            org_type=("org_type", "first"),
            budget_total_received=("amount_eur", "sum"),
            nb_projects=("project_id", "nunique"),
            latitude=("latitude", "max"),
            longitude=("longitude", "max"),
        )
        .reset_index(drop=True)
    )

    edges_org_project = org_project_raw[["org_id", "project_id", "amount_eur"]].copy()
    edges_org_project = edges_org_project[edges_org_project["project_id"].astype(str).str.len() > 0]
    edges_org_project = edges_org_project.rename(
        columns={
            "org_id": "source_org_id",
            "project_id": "target_project_id",
            "amount_eur": "weight_eur",
        }
    )

    co_rows: list[dict] = []
    grouped = org_project_raw.groupby("project_id")["org_id"].apply(lambda series: sorted(set(series.astype(str))))
    for project_id, orgs in grouped.items():
        if not project_id or len(orgs) < 2:
            continue
        for left, right in itertools.combinations(orgs, 2):
            co_rows.append({"org_a": left, "org_b": right, "project_id": str(project_id)})
    if co_rows:
        co_df = pd.DataFrame(co_rows)
        edges_org_org = (
            co_df.groupby(["org_a", "org_b"], as_index=False)["project_id"]
            .count()
            .rename(columns={"project_id": "weight_common_projects"})
        )
    else:
        edges_org_org = pd.DataFrame(columns=["org_a", "org_b", "weight_common_projects"])

    publications, org_publication_raw, publication_concepts = build_openalex_tables(openalex_path=openalex_path)

    org_lookup = organizations[["org_id", "org_name_norm"]].drop_duplicates().copy()
    edges_org_publication = org_publication_raw.merge(org_lookup, on="org_name_norm", how="inner")
    edges_org_publication = edges_org_publication[["org_id", "publication_id"]].drop_duplicates()
    edges_org_publication = edges_org_publication.rename(columns={"org_id": "source_org_id"})

    edges_org_concept = pd.DataFrame(columns=["source_org_id", "concept_label", "weight"])
    if not edges_org_publication.empty and not publication_concepts.empty:
        edges_org_concept = (
            edges_org_publication.merge(publication_concepts, on="publication_id", how="inner")
            .groupby(["source_org_id", "concept_label"], as_index=False)["concept_score"]
            .sum()
            .rename(columns={"concept_score": "weight"})
        )

    processed_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "organizations": processed_dir / "organizations.csv",
        "projects": processed_dir / "projects.csv",
        "publications": processed_dir / "publications.csv",
        "concepts": processed_dir / "concepts.csv",
        "edges_org_project": processed_dir / "edges_org_project.csv",
        "edges_org_org_explicit": processed_dir / "edges_org_org_explicit.csv",
        "edges_org_publication": processed_dir / "edges_org_publication.csv",
        "edges_org_concept": processed_dir / "edges_org_concept.csv",
    }

    organizations.to_csv(outputs["organizations"], index=False, encoding="utf-8")
    projects.to_csv(outputs["projects"], index=False, encoding="utf-8")
    publications.to_csv(outputs["publications"], index=False, encoding="utf-8")
    publication_concepts.to_csv(outputs["concepts"], index=False, encoding="utf-8")
    edges_org_project.to_csv(outputs["edges_org_project"], index=False, encoding="utf-8")
    edges_org_org.to_csv(outputs["edges_org_org_explicit"], index=False, encoding="utf-8")
    edges_org_publication.to_csv(outputs["edges_org_publication"], index=False, encoding="utf-8")
    edges_org_concept.to_csv(outputs["edges_org_concept"], index=False, encoding="utf-8")

    return {key: str(value) for key, value in outputs.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize CORDIS/OpenAlex into processed tables")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"), help="Raw data folder")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"), help="Processed output folder")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    files = build_processed_tables(raw_dir=args.raw_dir, processed_dir=args.processed_dir)
    print("Generated processed tables:")
    for key, file_path in files.items():
        print(f"- {key}: {file_path}")
