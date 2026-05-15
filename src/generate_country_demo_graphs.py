from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

import folium
import pandas as pd
from folium import plugins


COUNTRY_COORDS: dict[str, tuple[float, float]] = {
    "ES": (40.4637, -3.7492),
    "FR": (46.2276, 2.2137),
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:80] if slug else "item"


def safe_float(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8", low_memory=False)


def resolve_coords(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["country"] = out["country"].astype(str).str.upper()
    out["latitude"] = pd.to_numeric(out.get("latitude"), errors="coerce")
    out["longitude"] = pd.to_numeric(out.get("longitude"), errors="coerce")
    out["lat"] = out["latitude"].fillna(out["country"].map(lambda c: COUNTRY_COORDS.get(c, (None, None))[0]))
    out["lon"] = out["longitude"].fillna(out["country"].map(lambda c: COUNTRY_COORDS.get(c, (None, None))[1]))
    return out.dropna(subset=["lat", "lon"]).copy()


def profile_link_for(org_id: str, org_name: str) -> str:
    return f"org_profiles/{slugify(org_name)}-{slugify(org_id)}.html"


def write_country_profiles(
    organizations: pd.DataFrame,
    projects: pd.DataFrame,
    edges_org_project: pd.DataFrame,
    edges_org_org: pd.DataFrame,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    links: dict[str, str] = {}

    projects_lookup = projects[["project_id", "project_title", "topic_label", "program"]].copy()
    projects_lookup["project_id"] = projects_lookup["project_id"].astype(str)
    edges = edges_org_project.copy()
    edges["source_org_id"] = edges["source_org_id"].astype(str)
    edges["target_project_id"] = edges["target_project_id"].astype(str)
    edges["weight_eur"] = pd.to_numeric(edges["weight_eur"], errors="coerce").fillna(0.0)
    org_projects = edges.merge(projects_lookup, left_on="target_project_id", right_on="project_id", how="left")

    org_names = dict(zip(organizations["org_id"].astype(str), organizations["org_name"].astype(str), strict=False))
    partner_rows: dict[str, list[dict[str, object]]] = {}
    for row in edges_org_org.sort_values("weight_common_projects", ascending=False).itertuples(index=False):
        a = str(getattr(row, "org_a"))
        b = str(getattr(row, "org_b"))
        w = int(getattr(row, "weight_common_projects") or 0)
        partner_rows.setdefault(a, []).append({"org_id": b, "org_name": org_names.get(b, b), "weight": w})
        partner_rows.setdefault(b, []).append({"org_id": a, "org_name": org_names.get(a, a), "weight": w})

    for row in organizations.itertuples(index=False):
        org_id = str(row.org_id)
        org_name = str(row.org_name)
        country = str(row.country)
        city = str(row.city or "N/A")
        budget = safe_float(getattr(row, "budget_total_received", 0.0))
        nb_projects = int(getattr(row, "nb_projects", 0) or 0)

        org_proj = org_projects[org_projects["source_org_id"].astype(str) == org_id].copy()
        org_proj = org_proj.sort_values("weight_eur", ascending=False)
        top_projects = org_proj.head(15)
        top_topics = (
            org_proj[org_proj["topic_label"].fillna("").astype(str).str.len() > 0]
            .groupby("topic_label", as_index=False)
            .agg(projects=("project_id", "nunique"), funding=("weight_eur", "sum"))
            .sort_values(["projects", "funding"], ascending=False)
            .head(10)
        )
        top_partners = partner_rows.get(org_id, [])[:12]

        projects_html = "".join(
            "<tr>"
            f"<td>{html.escape(str(p.project_title or p.project_id))}</td>"
            f"<td>{html.escape(str(p.topic_label or 'N/A'))}</td>"
            f"<td>{html.escape(str(p.program or 'N/A'))}</td>"
            f"<td style='text-align:right'>{safe_float(p.weight_eur):,.0f}</td>"
            "</tr>"
            for p in top_projects.itertuples(index=False)
        ) or "<tr><td colspan='4'>Aucun projet disponible.</td></tr>"

        topics_html = "".join(
            "<tr>"
            f"<td>{html.escape(str(t.topic_label))}</td>"
            f"<td style='text-align:right'>{int(t.projects)}</td>"
            f"<td style='text-align:right'>{safe_float(t.funding):,.0f}</td>"
            "</tr>"
            for t in top_topics.itertuples(index=False)
        ) or "<tr><td colspan='3'>Aucun sujet disponible.</td></tr>"

        partners_html = "".join(
            "<tr>"
            f"<td>{html.escape(str(item['org_name']))}</td>"
            f"<td style='text-align:right'>{int(item['weight'])}</td>"
            "</tr>"
            for item in top_partners
        ) or "<tr><td colspan='2'>Aucune collaboration explicite.</td></tr>"

        page = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(org_name)} - fiche FR/ES</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    .cards {{ display:grid; grid-template-columns: repeat(4, minmax(180px,1fr)); gap:12px; }}
    .card {{ border:1px solid #e5e7eb; border-radius:10px; padding:12px; background:#f9fafb; }}
    table {{ width:100%; border-collapse: collapse; margin-top:10px; }}
    th, td {{ border:1px solid #e5e7eb; padding:8px; font-size:14px; }}
    th {{ background:#f3f4f6; text-align:left; }}
    h2 {{ margin-top:28px; }}
  </style>
</head>
<body>
  <h1>{html.escape(org_name)}</h1>
  <div class="cards">
    <div class="card"><b>Pays</b><br>{html.escape(country)}</div>
    <div class="card"><b>Ville</b><br>{html.escape(city)}</div>
    <div class="card"><b>Budget reçu</b><br>{budget:,.0f} EUR</div>
    <div class="card"><b>Nombre de projets</b><br>{nb_projects}</div>
  </div>
  <h2>Principaux sujets de recherche</h2>
  <table><thead><tr><th>Sujet</th><th>Nb projets</th><th>Financement EUR</th></tr></thead><tbody>{topics_html}</tbody></table>
  <h2>Principaux projets financés</h2>
  <table><thead><tr><th>Projet</th><th>Sujet</th><th>Programme</th><th>Financement EUR</th></tr></thead><tbody>{projects_html}</tbody></table>
  <h2>Principaux partenaires explicites</h2>
  <table><thead><tr><th>Etablissement</th><th>Projets communs</th></tr></thead><tbody>{partners_html}</tbody></table>
</body>
</html>"""
        filename = f"{slugify(org_name)}-{slugify(org_id)}.html"
        (output_dir / filename).write_text(page, encoding="utf-8")
        links[org_id] = f"fr_es_profiles/{filename}"

    return links


def _edge_color_for(intensity: float) -> str:
    """Map [0..1] intensity to a perceptually-smooth warm color (yellow→red→purple)."""
    if intensity >= 0.85:
        return "#581c87"
    if intensity >= 0.65:
        return "#b91c1c"
    if intensity >= 0.45:
        return "#ea580c"
    if intensity >= 0.25:
        return "#f59e0b"
    return "#fbbf24"


def _budget_color_for(rank_ratio: float) -> str:
    """Map [0..1] rank ratio to a sequential blue (light → dark)."""
    if rank_ratio >= 0.85:
        return "#1e3a8a"
    if rank_ratio >= 0.65:
        return "#1d4ed8"
    if rank_ratio >= 0.45:
        return "#3b82f6"
    if rank_ratio >= 0.25:
        return "#60a5fa"
    return "#93c5fd"


def generate_fr_es_map(processed_dir: Path, output_path: Path) -> Path:
    """Build the global country-to-country collaborations map.

    The function name is kept for backward compatibility but produces a
    rich interactive map covering all countries with dynamic overlays.
    """
    organizations = resolve_coords(load_csv(processed_dir / "organizations.csv"))
    projects = load_csv(processed_dir / "projects.csv")
    edges_org_project = load_csv(processed_dir / "edges_org_project.csv")
    edges_org_org = load_csv(processed_dir / "edges_org_org_explicit.csv")
    org_by_id = organizations[["org_id", "org_name", "country", "city", "lat", "lon", "budget_total_received", "nb_projects"]].copy()
    org_by_id["org_id"] = org_by_id["org_id"].astype(str)
    org_by_id["country"] = org_by_id["country"].astype(str).str.upper()
    org_by_id["budget_total_received"] = pd.to_numeric(org_by_id["budget_total_received"], errors="coerce").fillna(0.0)
    org_by_id["nb_projects"] = pd.to_numeric(org_by_id["nb_projects"], errors="coerce").fillna(0).astype(int)
    org_lookup = org_by_id.drop_duplicates(subset=["org_id"]).set_index("org_id").to_dict(orient="index")

    country_summary = (
        org_by_id.groupby("country", as_index=False)
        .agg(
            lat=("lat", "mean"),
            lon=("lon", "mean"),
            org_count=("org_id", "nunique"),
            budget_total=("budget_total_received", "sum"),
            project_total=("nb_projects", "sum"),
        )
        .copy()
    )
    country_summary = country_summary[country_summary["country"].astype(str).str.len() > 0]
    country_centers = {
        str(row.country): (
            float(row.lat if pd.notna(row.lat) else COUNTRY_COORDS.get(str(row.country), (0.0, 0.0))[0]),
            float(row.lon if pd.notna(row.lon) else COUNTRY_COORDS.get(str(row.country), (0.0, 0.0))[1]),
        )
        for row in country_summary.itertuples(index=False)
    }

    fmap = folium.Map(location=[48.0, 8.0], zoom_start=4, tiles="cartodbpositron", control_scale=True)
    edge_layer = folium.FeatureGroup(name="Collaborations pays ↔ pays", show=True).add_to(fmap)
    marker_layer = folium.FeatureGroup(name="Pays (cercles dimensionnés par budget)", show=True).add_to(fmap)
    heatmap_layer = folium.FeatureGroup(name="Densité d'organisations (heatmap)", show=False).add_to(fmap)

    project_meta = projects[["project_id", "project_title", "topic_label"]].copy()
    project_meta["project_id"] = project_meta["project_id"].astype(str)
    topic_lookup = dict(zip(project_meta["project_id"], project_meta["topic_label"].fillna("").astype(str), strict=False))
    org_proj = edges_org_project.copy()
    org_proj["source_org_id"] = org_proj["source_org_id"].astype(str)
    org_proj["target_project_id"] = org_proj["target_project_id"].astype(str)
    org_proj["weight_eur"] = pd.to_numeric(org_proj["weight_eur"], errors="coerce").fillna(0.0)
    proj_by_org: dict[str, dict[str, float]] = {}
    for org_id, frame in org_proj.groupby("source_org_id"):
        proj_by_org[str(org_id)] = dict(zip(frame["target_project_id"].astype(str), frame["weight_eur"], strict=False))

    country_pair_summary: dict[tuple[str, str], dict[str, object]] = {}
    for row in edges_org_org.sort_values("weight_common_projects", ascending=False).itertuples(index=False):
        left = str(row.org_a)
        right = str(row.org_b)
        weight = int(row.weight_common_projects or 0)
        left_meta = org_lookup.get(left)
        right_meta = org_lookup.get(right)
        if not left_meta or not right_meta:
            continue
        left_country = str(left_meta["country"]).upper()
        right_country = str(right_meta["country"]).upper()
        if not left_country or not right_country or left_country == right_country:
            continue
        key = tuple(sorted([left_country, right_country]))
        entry = country_pair_summary.setdefault(
            key,
            {"pair_count": 0, "project_total": 0, "funding_total": 0.0, "samples": []},
        )
        common_projects = sorted(set(proj_by_org.get(left, {}).keys()).intersection(proj_by_org.get(right, {}).keys()))
        pair_funding = sum(proj_by_org.get(left, {}).get(pid, 0.0) + proj_by_org.get(right, {}).get(pid, 0.0) for pid in common_projects)
        topics = sorted({topic_lookup.get(pid, "") for pid in common_projects if topic_lookup.get(pid, "")})[:4]
        entry["pair_count"] = int(entry["pair_count"]) + 1
        entry["project_total"] = int(entry["project_total"]) + weight
        entry["funding_total"] = float(entry["funding_total"]) + pair_funding
        samples = entry["samples"]
        if isinstance(samples, list) and len(samples) < 25:
            if left_country == key[0]:
                first_id, first_name = left, str(left_meta["org_name"])
                second_id, second_name = right, str(right_meta["org_name"])
            else:
                first_id, first_name = right, str(right_meta["org_name"])
                second_id, second_name = left, str(left_meta["org_name"])
            samples.append(
                {
                    "first_id": first_id,
                    "first_name": first_name,
                    "second_id": second_id,
                    "second_name": second_name,
                    "weight": weight,
                    "pair_funding": pair_funding,
                    "topics": topics,
                }
            )

    # Aggregate per-country derived stats: how many distinct partner countries,
    # most active partner (used in tooltips and the side panel).
    country_partners: dict[str, dict[str, int]] = {}
    for (country_a, country_b), entry in country_pair_summary.items():
        country_partners.setdefault(country_a, {})[country_b] = int(entry["project_total"])
        country_partners.setdefault(country_b, {})[country_a] = int(entry["project_total"])

    # Sequential color scale for country circles, ranked by total budget.
    sorted_by_budget = country_summary.sort_values("budget_total", ascending=False).reset_index(drop=True)
    country_budget_rank = {
        str(row.country): (len(sorted_by_budget) - i - 1) / max(len(sorted_by_budget) - 1, 1)
        for i, row in enumerate(sorted_by_budget.itertuples(index=False))
    }

    # Build markers (one per country) with hover tooltip + click popup.
    heatmap_points: list[list[float]] = []
    for row in country_summary.sort_values("budget_total", ascending=False).itertuples(index=False):
        country = str(row.country).upper()
        center = country_centers.get(country)
        if not center:
            continue
        frame = org_by_id[org_by_id["country"] == country].copy()
        top_orgs = frame.sort_values("budget_total_received", ascending=False).head(8)
        top_orgs_html = "".join(
            "<li><span style='display:inline-block;max-width:240px;overflow:hidden;text-overflow:ellipsis;vertical-align:top'>"
            f"{html.escape(str(r.org_name))}</span>"
            f"<span style='float:right;color:#1d4ed8;font-weight:600'>{safe_float(r.budget_total_received):,.0f} €</span></li>"
            for r in top_orgs.itertuples(index=False)
        ) or "<li>Aucun établissement</li>"

        partners = country_partners.get(country, {})
        partner_count = len(partners)
        top_partner = max(partners.items(), key=lambda item: item[1]) if partners else (None, 0)

        rank_ratio = country_budget_rank.get(country, 0.0)
        circle_color = _budget_color_for(rank_ratio)
        radius = max(5.0, min(18.0, 4 + (int(row.org_count) ** 0.5) / 1.4))

        popup_html = f"""
        <div style="font-family:Inter,Arial,sans-serif;min-width:340px;max-width:440px">
          <div style="background:linear-gradient(135deg,{circle_color} 0%,#0f172a 100%);color:#fff;padding:14px 16px;border-radius:8px 8px 0 0">
            <div style="font-size:22px;font-weight:700;letter-spacing:.5px">{html.escape(country)}</div>
            <div style="opacity:.85;font-size:12px;margin-top:4px">Pays #{int(sorted_by_budget[sorted_by_budget['country']==country].index[0])+1 if country in country_budget_rank else '?'} par budget</div>
          </div>
          <div style="padding:14px 16px;background:#fff">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
              <div style="background:#eff6ff;border-radius:8px;padding:8px"><div style="font-size:11px;color:#64748b">Etablissements</div><div style="font-size:18px;font-weight:700;color:#1d4ed8">{int(row.org_count):,}</div></div>
              <div style="background:#fef3c7;border-radius:8px;padding:8px"><div style="font-size:11px;color:#64748b">Budget total</div><div style="font-size:18px;font-weight:700;color:#92400e">{safe_float(row.budget_total)/1e9:,.2f} G€</div></div>
              <div style="background:#dcfce7;border-radius:8px;padding:8px"><div style="font-size:11px;color:#64748b">Projets cumulés</div><div style="font-size:18px;font-weight:700;color:#166534">{int(row.project_total):,}</div></div>
              <div style="background:#fce7f3;border-radius:8px;padding:8px"><div style="font-size:11px;color:#64748b">Pays partenaires</div><div style="font-size:18px;font-weight:700;color:#9d174d">{partner_count}</div></div>
            </div>
            <div style="font-size:12px;color:#475569;margin-bottom:6px"><b>Partenaire principal</b> : {html.escape(str(top_partner[0]) or 'Aucun')} ({int(top_partner[1])} projets)</div>
            <div style="font-size:13px;font-weight:600;color:#0f172a;margin:8px 0 4px">Top établissements</div>
            <ul style="margin:0;padding-left:18px;list-style:none;font-size:12px;line-height:1.7">{top_orgs_html}</ul>
          </div>
        </div>
        """
        tooltip_html = f"<b>{html.escape(country)}</b> · {int(row.org_count)} orgs · {safe_float(row.budget_total)/1e6:,.0f} M€ · {partner_count} pays partenaires"
        folium.CircleMarker(
            location=[center[0], center[1]],
            radius=radius,
            color=circle_color,
            fill=True,
            fill_color=circle_color,
            fill_opacity=0.85,
            weight=2,
            popup=folium.Popup(popup_html, max_width=480),
            tooltip=folium.Tooltip(tooltip_html, sticky=True),
        ).add_to(marker_layer)
        heatmap_points.append([center[0], center[1], float(row.org_count)])

    if heatmap_points:
        plugins.HeatMap(heatmap_points, radius=22, blur=18, min_opacity=0.3).add_to(heatmap_layer)

    # Show country pairs with project_total >= 2 sorted by intensity. Cap to
    # the top 1000 pairs to keep the file size reasonable (~5-8 MB) and the
    # map readable; weaker pairs add visual noise without insight.
    MAX_PAIRS_DISPLAYED = 1000
    valid_pairs = [
        (key, entry)
        for key, entry in country_pair_summary.items()
        if int(entry["project_total"]) >= 2
    ]
    if valid_pairs:
        max_project_total = max(int(e["project_total"]) for _, e in valid_pairs)
    else:
        max_project_total = 1
    valid_pairs.sort(key=lambda item: int(item[1]["project_total"]), reverse=True)
    valid_pairs = valid_pairs[:MAX_PAIRS_DISPLAYED]

    for (country_a, country_b), entry in valid_pairs:
        center_a = country_centers.get(country_a)
        center_b = country_centers.get(country_b)
        if not center_a or not center_b:
            continue
        intensity = int(entry["project_total"]) / float(max_project_total)
        edge_color = _edge_color_for(intensity)
        width = max(1.2, min(7.0, 1 + (int(entry["project_total"]) ** 0.5) / 3.5))
        rows_html = "".join(
            "<tr>"
            f"<td>{html.escape(str(item['first_name'])[:55])}</td>"
            f"<td>{html.escape(str(item['second_name'])[:55])}</td>"
            f"<td style='text-align:right;font-weight:600;color:#1d4ed8'>{int(item['weight'])}</td>"
            f"<td style='text-align:right;color:#92400e'>{safe_float(item['pair_funding'])/1e6:,.2f} M€</td>"
            "</tr>"
            for item in entry["samples"][:8]
        ) or "<tr><td colspan='4'>Aucune collaboration détaillée.</td></tr>"
        edge_popup_html = (
            f'<div style="font-family:Inter,Arial,sans-serif;max-width:540px">'
            f'<div style="background:linear-gradient(135deg,{edge_color} 0%,#1e293b 100%);color:#fff;padding:10px 14px;border-radius:6px 6px 0 0">'
            f'<div style="font-size:17px;font-weight:700">{html.escape(country_a)} ↔ {html.escape(country_b)}</div>'
            f'<div style="opacity:.85;font-size:11px">Intensité {int(intensity*100)}%</div></div>'
            f'<div style="padding:10px 14px;background:#fff">'
            f'<div style="display:flex;gap:6px;margin-bottom:10px;font-size:12px">'
            f'<div style="flex:1;background:#eff6ff;border-radius:6px;padding:6px 8px"><b style="color:#1d4ed8">{int(entry["pair_count"]):,}</b> liens</div>'
            f'<div style="flex:1;background:#fef3c7;border-radius:6px;padding:6px 8px"><b style="color:#92400e">{int(entry["project_total"]):,}</b> projets</div>'
            f'<div style="flex:1;background:#dcfce7;border-radius:6px;padding:6px 8px"><b style="color:#166534">{safe_float(entry["funding_total"])/1e6:,.1f} M€</b></div>'
            f'</div>'
            f'<table style="width:100%;border-collapse:collapse;font-size:11px">'
            f'<thead style="background:#f1f5f9"><tr>'
            f'<th style="padding:6px;text-align:left">Etab. {html.escape(country_a)}</th>'
            f'<th style="padding:6px;text-align:left">Etab. {html.escape(country_b)}</th>'
            f'<th style="padding:6px;text-align:right">Proj.</th>'
            f'<th style="padding:6px;text-align:right">Montant</th>'
            f'</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table></div></div>'
        )
        edge_tooltip = (
            f"<b>{html.escape(country_a)} ↔ {html.escape(country_b)}</b><br>"
            f"{int(entry['pair_count'])} liens · {int(entry['project_total'])} projets · "
            f"{safe_float(entry['funding_total'])/1e6:,.1f} M€"
        )
        folium.PolyLine(
            locations=[[center_a[0], center_a[1]], [center_b[0], center_b[1]]],
            color=edge_color,
            weight=width,
            opacity=0.55 + 0.4 * intensity,
            popup=folium.Popup(edge_popup_html, max_width=820),
            tooltip=folium.Tooltip(edge_tooltip, sticky=True),
        ).add_to(edge_layer)

    plugins.Fullscreen(position="topright").add_to(fmap)
    folium.LayerControl(collapsed=False, position="topright").add_to(fmap)

    # ---------- Side overlay panel: KPIs, search, top countries, top pairs ----------
    total_orgs = int(country_summary["org_count"].sum())
    total_budget = float(country_summary["budget_total"].sum())
    total_pairs = len(country_pair_summary)
    total_active_pairs = len(valid_pairs)
    total_transnational_projects = int(sum(int(e["project_total"]) for e in country_pair_summary.values()))

    top_countries = country_summary.sort_values("budget_total", ascending=False).head(8)
    top_countries_html = "".join(
        f"""<li class="cco-item" data-fly="{c.country}" data-lat="{country_centers.get(c.country,(0,0))[0]}" data-lon="{country_centers.get(c.country,(0,0))[1]}">
          <span class="cco-flag" style="background:{_budget_color_for(country_budget_rank.get(c.country,0))}">{html.escape(c.country)}</span>
          <span class="cco-meta">{int(c.org_count):,} orgs · {safe_float(c.budget_total)/1e9:,.1f} G€</span>
        </li>"""
        for c in top_countries.itertuples(index=False)
    )

    top_pairs_sorted = sorted(valid_pairs, key=lambda item: int(item[1]["project_total"]), reverse=True)[:8]
    top_pairs_html = "".join(
        f"""<li class="cco-item" data-fly-pair="{a}|{b}"
              data-lat-a="{country_centers.get(a,(0,0))[0]}" data-lon-a="{country_centers.get(a,(0,0))[1]}"
              data-lat-b="{country_centers.get(b,(0,0))[0]}" data-lon-b="{country_centers.get(b,(0,0))[1]}">
          <span class="cco-pair">{html.escape(a)} ↔ {html.escape(b)}</span>
          <span class="cco-meta">{int(e['project_total']):,} proj · {safe_float(e['funding_total'])/1e6:,.0f} M€</span>
        </li>"""
        for (a, b), e in top_pairs_sorted
    )

    countries_options = "".join(
        f'<option value="{html.escape(c)}"></option>'
        for c in sorted(country_centers.keys())
    )
    countries_meta_js = json.dumps(
        {
            c: {"lat": float(country_centers[c][0]), "lon": float(country_centers[c][1])}
            for c in country_centers
        }
    )

    panel_html = f"""
<style>
  .cco-panel {{
    position:absolute; top:14px; left:14px; z-index:9999; width:320px;
    font-family:Inter,system-ui,Arial,sans-serif; color:#0f172a;
    background:rgba(255,255,255,.94); backdrop-filter:blur(8px);
    border:1px solid #e2e8f0; border-radius:14px;
    box-shadow:0 14px 40px rgba(15,23,42,.18);
    max-height: calc(100vh - 32px); overflow:auto;
  }}
  .cco-header {{
    background:linear-gradient(135deg,#1e3a8a 0%,#7c3aed 100%);
    color:#fff; padding:14px 16px 12px; border-radius:14px 14px 0 0;
  }}
  .cco-header h2 {{ margin:0; font-size:15px; font-weight:700; letter-spacing:.4px }}
  .cco-header p {{ margin:2px 0 0; font-size:11px; opacity:.85 }}
  .cco-body {{ padding:12px 14px 14px }}
  .cco-search {{ position:relative; margin-bottom:12px }}
  .cco-search input {{
    width:100%; padding:9px 12px; border:1px solid #cbd5e1; border-radius:8px;
    font-size:13px; outline:none; transition:border .15s;
  }}
  .cco-search input:focus {{ border-color:#7c3aed; box-shadow:0 0 0 3px rgba(124,58,237,.2) }}
  .cco-kpis {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:14px }}
  .cco-kpi {{ background:#f8fafc; border-radius:10px; padding:8px 10px; border:1px solid #e2e8f0 }}
  .cco-kpi-label {{ font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:.5px }}
  .cco-kpi-value {{ font-size:18px; font-weight:700; margin-top:2px }}
  .cco-section h3 {{ font-size:12px; margin:8px 0 6px; text-transform:uppercase; letter-spacing:.5px; color:#475569 }}
  .cco-list {{ list-style:none; padding:0; margin:0 0 8px }}
  .cco-item {{
    display:flex; justify-content:space-between; align-items:center;
    padding:7px 8px; border-radius:8px; cursor:pointer; gap:8px;
    font-size:12px; transition:background .12s;
  }}
  .cco-item:hover {{ background:#eef2ff }}
  .cco-flag {{
    display:inline-block; min-width:30px; padding:2px 6px; border-radius:6px;
    color:#fff; font-weight:700; text-align:center; font-size:11px;
  }}
  .cco-pair {{ font-weight:600; color:#1e293b }}
  .cco-meta {{ font-size:11px; color:#64748b; flex-shrink:0 }}
  .cco-legend {{
    position:absolute; bottom:14px; right:14px; z-index:9999;
    background:rgba(255,255,255,.94); backdrop-filter:blur(8px);
    border:1px solid #e2e8f0; border-radius:12px; padding:10px 12px;
    font-family:Inter,system-ui,Arial,sans-serif; font-size:11px;
    box-shadow:0 8px 24px rgba(15,23,42,.12); width:240px;
  }}
  .cco-legend h4 {{ margin:0 0 6px; font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:#475569 }}
  .cco-grad {{ height:8px; border-radius:4px; margin:4px 0 6px;
    background:linear-gradient(90deg,#fbbf24 0%,#f59e0b 25%,#ea580c 45%,#b91c1c 65%,#581c87 100%); }}
  .cco-row {{ display:flex; justify-content:space-between; color:#64748b; font-size:10px }}
  .cco-circle-row {{ display:flex; align-items:center; gap:6px; margin-top:6px }}
  .cco-dot {{ display:inline-block; width:10px; height:10px; border-radius:50% }}
</style>
<div class="cco-panel">
  <div class="cco-header">
    <h2>🌍 Collaborations transnationales</h2>
    <p>Carte interactive · {len(country_centers)} pays · {total_active_pairs} liens actifs</p>
  </div>
  <div class="cco-body">
    <div class="cco-search">
      <input id="ccoSearch" list="ccoCountries" placeholder="🔎 Rechercher un pays (FR, DE, IT...)" autocomplete="off"/>
      <datalist id="ccoCountries">{countries_options}</datalist>
    </div>
    <div class="cco-kpis">
      <div class="cco-kpi"><div class="cco-kpi-label">Pays</div><div class="cco-kpi-value">{len(country_centers)}</div></div>
      <div class="cco-kpi"><div class="cco-kpi-label">Liens actifs</div><div class="cco-kpi-value">{total_active_pairs}</div></div>
      <div class="cco-kpi"><div class="cco-kpi-label">Etablissements</div><div class="cco-kpi-value">{total_orgs:,}</div></div>
      <div class="cco-kpi"><div class="cco-kpi-label">Budget total</div><div class="cco-kpi-value">{total_budget/1e9:,.1f} G€</div></div>
      <div class="cco-kpi" style="grid-column:1/3"><div class="cco-kpi-label">Projets transnationaux</div><div class="cco-kpi-value">{total_transnational_projects:,}</div></div>
    </div>
    <div class="cco-section">
      <h3>🏆 Top pays par budget</h3>
      <ul class="cco-list">{top_countries_html}</ul>
    </div>
    <div class="cco-section">
      <h3>🤝 Top liaisons internationales</h3>
      <ul class="cco-list">{top_pairs_html}</ul>
    </div>
  </div>
</div>
<div class="cco-legend">
  <h4>Légende</h4>
  <div style="font-size:10px;color:#64748b">Intensité du lien (projets cumulés)</div>
  <div class="cco-grad"></div>
  <div class="cco-row"><span>Faible</span><span>Élevée</span></div>
  <div style="margin-top:8px;font-size:10px;color:#64748b">Couleur du pays = rang budgétaire</div>
  <div class="cco-circle-row"><span class="cco-dot" style="background:#93c5fd"></span><span>Bas</span>
    <span class="cco-dot" style="background:#3b82f6;margin-left:6px"></span><span>Moyen</span>
    <span class="cco-dot" style="background:#1e3a8a;margin-left:6px"></span><span>Haut</span></div>
  <div style="margin-top:8px;font-size:10px;color:#64748b">Taille du cercle = nombre d'établissements</div>
</div>
<script>
(function() {{
  const COUNTRIES = {countries_meta_js};
  function getMap() {{
    for (const k in window) {{
      if (k.startsWith('map_') && window[k] && typeof window[k].setView === 'function') {{
        return window[k];
      }}
    }}
    return null;
  }}
  function flyTo(lat, lon, zoom) {{
    const m = getMap();
    if (m && Number.isFinite(lat) && Number.isFinite(lon)) {{
      m.flyTo([lat, lon], zoom || 6, {{ duration: 0.9 }});
    }}
  }}
  function flyToBounds(coords) {{
    const m = getMap();
    if (m && coords.length >= 2 && typeof L !== 'undefined') {{
      m.flyToBounds(coords, {{ padding: [60, 60], duration: 0.9 }});
    }}
  }}
  document.addEventListener('click', (ev) => {{
    const item = ev.target.closest('.cco-item');
    if (!item) return;
    if (item.dataset.fly) {{
      flyTo(parseFloat(item.dataset.lat), parseFloat(item.dataset.lon), 6);
    }} else if (item.dataset.flyPair) {{
      flyToBounds([
        [parseFloat(item.dataset.latA), parseFloat(item.dataset.lonA)],
        [parseFloat(item.dataset.latB), parseFloat(item.dataset.lonB)]
      ]);
    }}
  }});
  const search = document.getElementById('ccoSearch');
  if (search) {{
    const handler = () => {{
      const value = (search.value || '').trim().toUpperCase();
      const meta = COUNTRIES[value];
      if (meta) {{ flyTo(meta.lat, meta.lon, 6); }}
    }};
    search.addEventListener('change', handler);
    search.addEventListener('keydown', (ev) => {{ if (ev.key === 'Enter') handler(); }});
  }}
}})();
</script>
"""
    fmap.get_root().html.add_child(folium.Element(panel_html))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    return output_path


def generate_demo_pair_graph(processed_dir: Path, output_path: Path) -> Path:
    organizations = load_csv(processed_dir / "organizations.csv")
    projects = load_csv(processed_dir / "projects.csv")
    edges_org_org = load_csv(processed_dir / "edges_org_org_explicit.csv")
    edges_org_project = load_csv(processed_dir / "edges_org_project.csv")

    org_lookup = organizations[
        ["org_id", "org_name", "country", "city", "budget_total_received", "nb_projects"]
    ].drop_duplicates().copy()
    org_lookup["org_id"] = org_lookup["org_id"].astype(str)
    org_lookup["budget_total_received"] = pd.to_numeric(
        org_lookup["budget_total_received"], errors="coerce"
    ).fillna(0.0)
    org_lookup["nb_projects"] = pd.to_numeric(org_lookup["nb_projects"], errors="coerce").fillna(0).astype(int)
    org_by_id = org_lookup.set_index("org_id").to_dict(orient="index")

    edges_org_org = edges_org_org.sort_values("weight_common_projects", ascending=False)
    example = None
    for row in edges_org_org.itertuples(index=False):
        a = str(row.org_a)
        b = str(row.org_b)
        if int(row.weight_common_projects or 0) <= 1:
            continue
        example = row
        break
    if example is None:
        raise ValueError("No multi-project collaboration found for demo.")

    a = str(example.org_a)
    b = str(example.org_b)
    a_meta = org_by_id.get(a, {"org_name": a, "country": "N/A", "city": "", "budget_total_received": 0.0, "nb_projects": 0})
    b_meta = org_by_id.get(b, {"org_name": b, "country": "N/A", "city": "", "budget_total_received": 0.0, "nb_projects": 0})

    edge_proj = edges_org_project.copy()
    edge_proj["source_org_id"] = edge_proj["source_org_id"].astype(str)
    edge_proj["target_project_id"] = edge_proj["target_project_id"].astype(str)
    edge_proj["weight_eur"] = pd.to_numeric(edge_proj["weight_eur"], errors="coerce").fillna(0.0)
    a_projects = edge_proj[edge_proj["source_org_id"] == a][["target_project_id", "weight_eur"]].rename(columns={"weight_eur": "a_funding"})
    b_projects = edge_proj[edge_proj["source_org_id"] == b][["target_project_id", "weight_eur"]].rename(columns={"weight_eur": "b_funding"})
    common = a_projects.merge(b_projects, on="target_project_id", how="inner")
    projects["project_id"] = projects["project_id"].astype(str)
    if "program" in projects.columns:
        projects["program"] = projects["program"].fillna("").astype(str)
    if "start_date" in projects.columns:
        projects["start_date"] = projects["start_date"].fillna("").astype(str)
    project_cols = [c for c in ["project_id", "project_title", "topic_label", "program", "start_date"] if c in projects.columns]
    common = common.merge(projects[project_cols], left_on="target_project_id", right_on="project_id", how="left")
    common["pair_total"] = common["a_funding"] + common["b_funding"]
    common = common.sort_values("pair_total", ascending=False)

    nb_common = int(len(common))
    a_total = float(common["a_funding"].sum())
    b_total = float(common["b_funding"].sum())
    total_pair_funding = float(common["pair_total"].sum())
    avg_per_project = total_pair_funding / max(nb_common, 1)

    # --- Charts data: programmes & topics ---
    if "program" in common.columns:
        program_series = common["program"].fillna("").replace("", "Non spécifié")
    else:
        program_series = pd.Series(["Non spécifié"] * nb_common)
    program_counts = program_series.value_counts().to_dict()
    program_chart_data = {
        "labels": list(program_counts.keys()),
        "values": [int(v) for v in program_counts.values()],
    }
    if "topic_label" in common.columns:
        topic_series = common["topic_label"].fillna("").astype(str)
        topic_series = topic_series[topic_series.str.len() > 0]
    else:
        topic_series = pd.Series(dtype=str)
    topic_counts = topic_series.value_counts().head(10).to_dict()
    topic_chart_data = {
        "labels": list(topic_counts.keys()),
        "values": [int(v) for v in topic_counts.values()],
    }

    # --- Network nodes/edges for vis-network ---
    network_nodes: list[dict[str, object]] = [
        {
            "id": "ORG_A",
            "label": str(a_meta.get("org_name", "A"))[:38],
            "title": (
                f"<b>{html.escape(str(a_meta.get('org_name','A')))}</b><br/>"
                f"{html.escape(str(a_meta.get('country','')))} · "
                f"{html.escape(str(a_meta.get('city','') or ''))}<br/>"
                f"Budget total: {safe_float(a_meta.get('budget_total_received', 0)):,.0f} €<br/>"
                f"Projets totaux: {int(a_meta.get('nb_projects', 0))}"
            ),
            "color": {"background": "#2563eb", "border": "#1e3a8a", "highlight": {"background": "#1d4ed8", "border": "#1e3a8a"}},
            "size": 70,
            "shape": "dot",
            "font": {"size": 18, "color": "#1e3a8a", "face": "Inter"},
            "borderWidth": 4,
            "fixed": {"x": True, "y": False},
            "x": -550,
            "y": 0,
        },
        {
            "id": "ORG_B",
            "label": str(b_meta.get("org_name", "B"))[:38],
            "title": (
                f"<b>{html.escape(str(b_meta.get('org_name','B')))}</b><br/>"
                f"{html.escape(str(b_meta.get('country','')))} · "
                f"{html.escape(str(b_meta.get('city','') or ''))}<br/>"
                f"Budget total: {safe_float(b_meta.get('budget_total_received', 0)):,.0f} €<br/>"
                f"Projets totaux: {int(b_meta.get('nb_projects', 0))}"
            ),
            "color": {"background": "#dc2626", "border": "#7f1d1d", "highlight": {"background": "#b91c1c", "border": "#7f1d1d"}},
            "size": 70,
            "shape": "dot",
            "font": {"size": 18, "color": "#7f1d1d", "face": "Inter"},
            "borderWidth": 4,
            "fixed": {"x": True, "y": False},
            "x": 550,
            "y": 0,
        },
    ]
    network_edges: list[dict[str, object]] = []
    max_pair_total = float(common["pair_total"].max()) if nb_common else 1.0
    if max_pair_total <= 0:
        max_pair_total = 1.0
    for i, row in enumerate(common.head(25).itertuples(index=False)):
        pid = f"P_{i}"
        title = str(row.project_title or row.target_project_id)
        topic = str(getattr(row, "topic_label", "") or "N/A")
        program = str(getattr(row, "program", "") or "N/A")
        funding = float(row.pair_total)
        node_size = 14 + (funding / max_pair_total) * 36
        network_nodes.append(
            {
                "id": pid,
                "label": (title[:32] + "...") if len(title) > 32 else title,
                "title": (
                    f"<b>{html.escape(title)}</b><br/>"
                    f"Sujet: {html.escape(topic)}<br/>"
                    f"Programme: {html.escape(program)}<br/>"
                    f"Financement A: {safe_float(row.a_funding):,.0f} €<br/>"
                    f"Financement B: {safe_float(row.b_funding):,.0f} €<br/>"
                    f"<b>Total A+B: {safe_float(row.pair_total):,.0f} €</b>"
                ),
                "color": {"background": "#a78bfa", "border": "#6d28d9", "highlight": {"background": "#7c3aed", "border": "#4c1d95"}},
                "size": node_size,
                "shape": "dot",
                "font": {"size": 11, "color": "#1f2937", "face": "Inter", "vadjust": -node_size - 12},
                "borderWidth": 2,
            }
        )
        a_w = max(1.0, min(7.0, 1 + (float(row.a_funding) / max_pair_total) * 5))
        b_w = max(1.0, min(7.0, 1 + (float(row.b_funding) / max_pair_total) * 5))
        network_edges.append({"from": "ORG_A", "to": pid, "color": {"color": "#93c5fd", "opacity": 0.7}, "width": a_w, "smooth": {"type": "curvedCW", "roundness": 0.05}})
        network_edges.append({"from": pid, "to": "ORG_B", "color": {"color": "#fca5a5", "opacity": 0.7}, "width": b_w, "smooth": {"type": "curvedCW", "roundness": 0.05}})

    # --- Sortable / searchable table ---
    table_rows = "".join(
        f"""<tr data-search="{html.escape(((str(row.project_title or row.target_project_id)) + ' ' + str(getattr(row, 'topic_label', '') or '') + ' ' + str(getattr(row, 'program', '') or '')).lower())}">
          <td>{html.escape(str(row.project_title or row.target_project_id))}</td>
          <td><span class="chip chip-topic">{html.escape(str(getattr(row, 'topic_label', '') or 'N/A'))}</span></td>
          <td><span class="chip chip-prog">{html.escape(str(getattr(row, 'program', '') or 'N/A'))}</span></td>
          <td data-num="{safe_float(row.a_funding)}" style="text-align:right">{safe_float(row.a_funding):,.0f}</td>
          <td data-num="{safe_float(row.b_funding)}" style="text-align:right">{safe_float(row.b_funding):,.0f}</td>
          <td data-num="{safe_float(row.pair_total)}" style="text-align:right;font-weight:700;color:#7c3aed">{safe_float(row.pair_total):,.0f}</td>
        </tr>"""
        for row in common.itertuples(index=False)
    )

    html_page = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Démo collaboration multi-projets</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://unpkg.com/vis-network@9.1.9/styles/vis-network.min.css">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: 'Inter', system-ui, Arial, sans-serif; margin: 0; color: #0f172a; background:#f1f5f9; }}
    .hero {{
      background: linear-gradient(135deg, #1e3a8a 0%, #7c3aed 50%, #db2777 100%);
      color: #fff; padding: 36px 28px 28px; box-shadow: 0 8px 30px rgba(15,23,42,.15);
    }}
    .hero h1 {{ margin:0; font-size: 28px; font-weight: 800; letter-spacing:-.4px }}
    .hero .sub {{ margin-top: 6px; opacity: .85; font-size: 14px }}
    .hero .actor-row {{ display:flex; gap: 16px; margin-top: 22px; flex-wrap:wrap }}
    .hero .actor {{ flex: 1 1 340px; background: rgba(255,255,255,.10); backdrop-filter: blur(8px);
      border:1px solid rgba(255,255,255,.18); border-radius: 14px; padding: 14px 18px; }}
    .hero .actor .lbl {{ text-transform: uppercase; font-size: 11px; opacity:.7; letter-spacing:.6px }}
    .hero .actor .name {{ font-size: 17px; font-weight: 700; margin-top:4px }}
    .hero .actor .meta {{ font-size: 12px; opacity:.85; margin-top: 4px }}
    .container {{ max-width: 1280px; margin: -18px auto 36px; padding: 0 24px; }}
    .kpis {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:14px; margin-bottom: 18px; }}
    .kpi {{ background:#fff; border:1px solid #e2e8f0; border-radius: 14px; padding: 14px 16px;
      box-shadow: 0 4px 16px rgba(15,23,42,.06); position: relative; overflow:hidden }}
    .kpi::after {{ content: ""; position: absolute; right:-30px; top:-30px; width: 80px; height: 80px;
      border-radius: 50%; opacity:.12 }}
    .kpi.k1::after {{ background:#7c3aed }} .kpi.k2::after {{ background:#db2777 }}
    .kpi.k3::after {{ background:#0ea5e9 }} .kpi.k4::after {{ background:#16a34a }}
    .kpi .icon {{ font-size: 22px; }}
    .kpi .lbl {{ font-size: 11px; color:#64748b; text-transform: uppercase; letter-spacing:.6px; margin-top:6px }}
    .kpi .val {{ font-size: 22px; font-weight: 800; color:#0f172a; margin-top: 3px }}
    .grid {{ display:grid; grid-template-columns: 2fr 1fr; gap:14px; margin-bottom: 18px }}
    .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:16px; box-shadow:0 4px 16px rgba(15,23,42,.06) }}
    .card h2 {{ margin: 0 0 12px; font-size: 15px; color:#1e293b; letter-spacing:.2px }}
    .card .desc {{ font-size: 12px; color:#64748b; margin-bottom: 10px }}
    #network {{ width: 100%; height: 540px; border-radius: 10px; background:
      radial-gradient(circle at 50% 50%, #f8fafc 0%, #e2e8f0 100%); }}
    .charts {{ display:grid; grid-template-columns: 1fr 1fr; gap:14px; margin-bottom: 18px }}
    .table-card {{ background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:16px; box-shadow:0 4px 16px rgba(15,23,42,.06) }}
    .table-toolbar {{ display:flex; gap:10px; align-items:center; margin-bottom: 12px; flex-wrap:wrap }}
    .search {{ flex:1; padding:10px 14px; border:1px solid #cbd5e1; border-radius:10px; font-size:13px; outline:none; min-width: 220px }}
    .search:focus {{ border-color:#7c3aed; box-shadow: 0 0 0 3px rgba(124,58,237,.18) }}
    .pill {{ padding: 6px 12px; border-radius: 999px; background:#f1f5f9; color:#475569; font-size:12px; font-weight:600 }}
    table {{ width:100%; border-collapse: collapse; font-size: 13px }}
    thead th {{ background:#f8fafc; color:#0f172a; text-align:left; padding:10px 12px; cursor:pointer; user-select:none;
      font-weight: 600; border-bottom: 1px solid #e2e8f0; position: sticky; top:0 }}
    thead th:hover {{ background:#eef2ff }}
    thead th::after {{ content: " ↕"; opacity:.4; font-size:10px }}
    thead th.sort-asc::after {{ content: " ▲"; opacity:.9 }}
    thead th.sort-desc::after {{ content: " ▼"; opacity:.9 }}
    tbody td {{ padding: 10px 12px; border-bottom: 1px dashed #e2e8f0 }}
    tbody tr:hover {{ background: #fafbff }}
    .chip {{ display:inline-block; padding: 3px 8px; border-radius:6px; font-size:11px; font-weight:600 }}
    .chip-topic {{ background: #f1f5f9; color:#1e293b }}
    .chip-prog {{ background: #ede9fe; color:#5b21b6 }}
    .legend {{ display:flex; gap: 16px; align-items:center; margin: 6px 0 14px; font-size:12px; color:#475569 }}
    .legend .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:middle }}
    @media (max-width: 980px) {{
      .grid {{ grid-template-columns: 1fr }}
      .charts {{ grid-template-columns: 1fr }}
      .kpis {{ grid-template-columns: repeat(2, 1fr) }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <h1>Démo : collaboration multi-projets entre deux organisations</h1>
    <div class="sub">Vue détaillée des projets communs et de leur financement · {nb_common} projet{'s' if nb_common>1 else ''} partagé{'s' if nb_common>1 else ''}</div>
    <div class="actor-row">
      <div class="actor">
        <div class="lbl">Organisation A</div>
        <div class="name">{html.escape(str(a_meta.get('org_name','A')))}</div>
        <div class="meta">{html.escape(str(a_meta.get('country','')))} · {html.escape(str(a_meta.get('city','') or ''))} · Budget global {safe_float(a_meta.get('budget_total_received',0))/1e6:,.1f} M€ · {int(a_meta.get('nb_projects',0))} projets</div>
      </div>
      <div class="actor">
        <div class="lbl">Organisation B</div>
        <div class="name">{html.escape(str(b_meta.get('org_name','B')))}</div>
        <div class="meta">{html.escape(str(b_meta.get('country','')))} · {html.escape(str(b_meta.get('city','') or ''))} · Budget global {safe_float(b_meta.get('budget_total_received',0))/1e6:,.1f} M€ · {int(b_meta.get('nb_projects',0))} projets</div>
      </div>
    </div>
  </header>
  <main class="container">
    <section class="kpis">
      <div class="kpi k1"><div class="icon">🔗</div><div class="lbl">Projets communs</div><div class="val">{nb_common:,}</div></div>
      <div class="kpi k2"><div class="icon">💶</div><div class="lbl">Financement total A+B</div><div class="val">{total_pair_funding/1e6:,.1f} M€</div></div>
      <div class="kpi k3"><div class="icon">📊</div><div class="lbl">Moyenne par projet</div><div class="val">{avg_per_project/1e3:,.0f} k€</div></div>
      <div class="kpi k4"><div class="icon">⚖️</div><div class="lbl">Part A / B</div><div class="val">{(a_total/total_pair_funding*100 if total_pair_funding else 0):.0f}% / {(b_total/total_pair_funding*100 if total_pair_funding else 0):.0f}%</div></div>
    </section>

    <section class="grid">
      <div class="card">
        <h2>🕸️ Graphe bipartite interactif A ↔ projets ↔ B</h2>
        <div class="desc">Survolez les nœuds pour le détail · cliquez et glissez pour explorer · molette pour zoomer.</div>
        <div class="legend">
          <span><span class="dot" style="background:#2563eb"></span>Organisation A</span>
          <span><span class="dot" style="background:#a78bfa"></span>Projet commun (taille = budget)</span>
          <span><span class="dot" style="background:#dc2626"></span>Organisation B</span>
        </div>
        <div id="network"></div>
      </div>
      <div class="card">
        <h2>🎯 Programmes</h2>
        <div class="desc">Répartition des projets communs par programme cadre.</div>
        <canvas id="chartProgram" height="220"></canvas>
      </div>
    </section>

    <section class="charts">
      <div class="card">
        <h2>📚 Top 10 des sujets</h2>
        <div class="desc">Sujets/topics les plus représentés dans les projets communs.</div>
        <canvas id="chartTopic" height="240"></canvas>
      </div>
      <div class="card">
        <h2>💸 Comparaison des financements (top 10)</h2>
        <div class="desc">Financement reçu par A et B sur chaque projet commun phare.</div>
        <canvas id="chartFunding" height="240"></canvas>
      </div>
    </section>

    <section class="table-card">
      <div class="table-toolbar">
        <h2 style="margin:0">📋 Détail des projets communs</h2>
        <span class="pill" id="projectCount">{nb_common} projets</span>
        <input class="search" id="searchInput" placeholder="🔎 Filtrer par titre, sujet ou programme..."/>
      </div>
      <div style="max-height:520px; overflow:auto; border:1px solid #e2e8f0; border-radius:10px">
        <table id="projectTable">
          <thead><tr>
            <th data-key="title">Projet</th>
            <th data-key="topic">Sujet</th>
            <th data-key="program">Programme</th>
            <th data-key="num" data-numeric="1">Financement A (€)</th>
            <th data-key="num" data-numeric="1">Financement B (€)</th>
            <th data-key="num" data-numeric="1" class="sort-desc">Total A+B (€)</th>
          </tr></thead>
          <tbody>{table_rows}</tbody>
        </table>
      </div>
    </section>
  </main>

  <script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script>
    const NET_NODES = {json.dumps(network_nodes, ensure_ascii=False)};
    const NET_EDGES = {json.dumps(network_edges, ensure_ascii=False)};
    const PROG = {json.dumps(program_chart_data, ensure_ascii=False)};
    const TOPIC = {json.dumps(topic_chart_data, ensure_ascii=False)};
    const TOP_FUND = {json.dumps([
        {"label": (str(r.project_title or r.target_project_id)[:30] + ("..." if len(str(r.project_title or r.target_project_id)) > 30 else "")),
         "a": float(r.a_funding), "b": float(r.b_funding)}
        for r in common.head(10).itertuples(index=False)
    ], ensure_ascii=False)};

    // ---- vis-network ----
    (function() {{
      const container = document.getElementById('network');
      const nodes = new vis.DataSet(NET_NODES);
      const edges = new vis.DataSet(NET_EDGES);
      const network = new vis.Network(container, {{ nodes, edges }}, {{
        physics: {{
          enabled: true,
          solver: 'forceAtlas2Based',
          forceAtlas2Based: {{ gravitationalConstant: -120, centralGravity: 0.005, springLength: 220, springConstant: 0.02, damping: 0.6 }},
          stabilization: {{ iterations: 250 }}
        }},
        interaction: {{ hover: true, tooltipDelay: 120, navigationButtons: false, keyboard: false }},
        nodes: {{ shadow: {{ enabled: true, color: 'rgba(0,0,0,.15)', size: 8, x: 0, y: 3 }} }},
        edges: {{ smooth: true }}
      }});
      network.once('stabilizationIterationsDone', () => network.setOptions({{ physics: false }}));
    }})();

    // ---- charts ----
    const palette = ['#7c3aed','#2563eb','#db2777','#16a34a','#f59e0b','#0ea5e9','#dc2626','#facc15','#10b981','#8b5cf6'];
    new Chart(document.getElementById('chartProgram'), {{
      type: 'doughnut',
      data: {{ labels: PROG.labels, datasets: [{{ data: PROG.values, backgroundColor: palette, borderWidth: 0 }}] }},
      options: {{ plugins: {{ legend: {{ position:'bottom', labels: {{ font: {{ family:'Inter', size:11 }} }} }} }} }}
    }});
    new Chart(document.getElementById('chartTopic'), {{
      type: 'bar',
      data: {{ labels: TOPIC.labels, datasets: [{{ data: TOPIC.values, backgroundColor: '#7c3aed', borderRadius: 6 }}] }},
      options: {{ indexAxis:'y', plugins: {{ legend: {{ display:false }} }},
        scales: {{ x: {{ grid: {{ color:'#e2e8f0' }} }}, y: {{ grid: {{ display:false }}, ticks: {{ font: {{ size:11 }} }} }} }} }}
    }});
    new Chart(document.getElementById('chartFunding'), {{
      type: 'bar',
      data: {{
        labels: TOP_FUND.map(r => r.label),
        datasets: [
          {{ label:'Org. A (€)', data: TOP_FUND.map(r=>r.a), backgroundColor:'#2563eb', borderRadius:5 }},
          {{ label:'Org. B (€)', data: TOP_FUND.map(r=>r.b), backgroundColor:'#dc2626', borderRadius:5 }}
        ]
      }},
      options: {{ indexAxis: 'y', plugins: {{ legend: {{ position:'bottom' }} }},
        scales: {{ x: {{ stacked: true, grid: {{ color:'#e2e8f0' }} }}, y: {{ stacked: true, grid: {{ display:false }}, ticks: {{ font: {{ size:11 }} }} }} }} }}
    }});

    // ---- search filter ----
    const search = document.getElementById('searchInput');
    const projectCount = document.getElementById('projectCount');
    const tbody = document.querySelector('#projectTable tbody');
    if (search && tbody) {{
      search.addEventListener('input', () => {{
        const q = search.value.toLowerCase().trim();
        let visible = 0;
        tbody.querySelectorAll('tr').forEach(tr => {{
          const match = !q || (tr.dataset.search || '').includes(q);
          tr.style.display = match ? '' : 'none';
          if (match) visible++;
        }});
        if (projectCount) projectCount.textContent = visible + ' projet' + (visible>1?'s':'');
      }});
    }}

    // ---- sortable columns ----
    const table = document.getElementById('projectTable');
    table.querySelectorAll('thead th').forEach((th, idx) => {{
      th.addEventListener('click', () => {{
        const numeric = th.dataset.numeric === '1';
        const isAsc = th.classList.contains('sort-asc');
        table.querySelectorAll('thead th').forEach(o => o.classList.remove('sort-asc','sort-desc'));
        th.classList.add(isAsc ? 'sort-desc' : 'sort-asc');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((r1, r2) => {{
          const c1 = r1.children[idx];
          const c2 = r2.children[idx];
          const v1 = numeric ? parseFloat(c1.dataset.num || '0') : (c1.textContent || '').trim().toLowerCase();
          const v2 = numeric ? parseFloat(c2.dataset.num || '0') : (c2.textContent || '').trim().toLowerCase();
          if (v1 < v2) return isAsc ? 1 : -1;
          if (v1 > v2) return isAsc ? -1 : 1;
          return 0;
        }});
        rows.forEach(r => tbody.appendChild(r));
      }});
    }});
  </script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_page, encoding="utf-8")
    return output_path


def main(processed_dir: Path, graphs_dir: Path) -> None:
    fr_es_path = graphs_dir / "country_collaborations_map.html"
    example_path = graphs_dir / "demo_multi_project_pair.html"
    generate_fr_es_map(processed_dir, fr_es_path)
    generate_demo_pair_graph(processed_dir, example_path)
    print("Generated demo graphs:")
    print(f"- fr_es_map: {fr_es_path}")
    print(f"- demo_pair: {example_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate France/Spain and demo collaboration graphs")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(processed_dir=args.processed_dir, graphs_dir=args.graphs_dir)
