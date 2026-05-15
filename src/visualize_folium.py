from __future__ import annotations

import argparse
import json
import re
from html import escape
from pathlib import Path

import folium
import networkx as nx
import pandas as pd
from folium import plugins


# Country centroids (lat, lon) by ISO2.
COUNTRY_COORDS: dict[str, tuple[float, float]] = {
    "AT": (47.5162, 14.5501),
    "BE": (50.5039, 4.4699),
    "BG": (42.7339, 25.4858),
    "CH": (46.8182, 8.2275),
    "CY": (35.1264, 33.4299),
    "CZ": (49.8175, 15.4730),
    "DE": (51.1657, 10.4515),
    "DK": (56.2639, 9.5018),
    "EE": (58.5953, 25.0136),
    "EL": (39.0742, 21.8243),
    "ES": (40.4637, -3.7492),
    "FI": (61.9241, 25.7482),
    "FR": (46.2276, 2.2137),
    "HR": (45.1000, 15.2000),
    "HU": (47.1625, 19.5033),
    "IE": (53.1424, -7.6921),
    "IL": (31.0461, 34.8516),
    "IS": (64.9631, -19.0208),
    "IT": (41.8719, 12.5674),
    "LT": (55.1694, 23.8813),
    "LU": (49.8153, 6.1296),
    "LV": (56.8796, 24.6032),
    "MT": (35.9375, 14.3754),
    "NL": (52.1326, 5.2913),
    "NO": (60.4720, 8.4689),
    "PL": (51.9194, 19.1451),
    "PT": (39.3999, -8.2245),
    "RO": (45.9432, 24.9668),
    "SE": (60.1282, 18.6435),
    "SI": (46.1512, 14.9955),
    "SK": (48.6690, 19.6990),
    "TR": (38.9637, 35.2433),
    "UK": (55.3781, -3.4360),
    "US": (39.8283, -98.5795),
}

DISPLAY_ORG_LIMIT = 3_000
DISPLAY_GAP_LIMIT = 2_000

def circle_radius_from_budget(budget: float) -> float:
    scaled = max(3.0, min(25.0, (budget / 1_000_000.0) ** 0.5 * 2.5))
    return float(scaled)


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8", low_memory=False)


def safe_float(value: object) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return 0.0


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull_lon_lat(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique_points = sorted(set(points))
    if len(unique_points) <= 1:
        return unique_points

    lower: list[tuple[float, float]] = []
    for point in unique_points:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique_points):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def resolve_org_coordinates(organizations: pd.DataFrame) -> pd.DataFrame:
    organizations = organizations.copy()
    organizations["country"] = organizations["country"].astype(str).str.upper()
    organizations["lat_country"] = organizations["country"].map(lambda c: COUNTRY_COORDS.get(c, (None, None))[0])
    organizations["lon_country"] = organizations["country"].map(lambda c: COUNTRY_COORDS.get(c, (None, None))[1])
    organizations["latitude"] = pd.to_numeric(organizations.get("latitude"), errors="coerce")
    organizations["longitude"] = pd.to_numeric(organizations.get("longitude"), errors="coerce")
    organizations["lat"] = organizations["latitude"].fillna(organizations["lat_country"])
    organizations["lon"] = organizations["longitude"].fillna(organizations["lon_country"])
    return organizations.dropna(subset=["lat", "lon"]).copy()


def apply_display_filter(
    organizations: pd.DataFrame,
    edges_org_project: pd.DataFrame,
    edges_org_org: pd.DataFrame,
    projects: pd.DataFrame,
    gaps: list[dict[str, object]],
    graphs_dir: Path,
    programme: str = "ALL",
    max_orgs: int = 2000,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    list[dict[str, object]],
    pd.DataFrame,
    dict[str, object],
]:
    """Filter organizations + edges before rendering.

    1. Programme filter (H2020 / HE / ALL).
    2. Top-N PageRank from organization_metrics.json.
       Fallback: nb_projects (if metrics file is missing/unreadable).
    3. Edge filtering rules:
       - Collaborations (edges_org_project, edges_org_org) STRICT:
         both endpoints must be in the top-N display set.
       - Opportunities (gaps) RELAXED:
         keep a gap if AT LEAST ONE endpoint is in the top-N display set.
         Endpoints outside top-N are returned as ``context_orgs`` so the
         caller can render lightweight context markers without inflating
         the display count.
    """
    organizations_full = organizations.copy()
    summary: dict[str, object] = {
        "orgs_before_any_filter": int(len(organizations)),
        "programme_filter": (programme or "ALL").upper(),
        "max_orgs": int(max_orgs),
        "edges_org_project_before": int(len(edges_org_project)),
        "edges_org_org_before": int(len(edges_org_org)),
        "gaps_before_filter": int(len(gaps)),
        "ranked_by": "pagerank_collab",
        "fallback_used": False,
    }

    programme_normalized = (programme or "ALL").upper()
    if programme_normalized in {"H2020", "HE"} and not projects.empty and not edges_org_project.empty:
        prog_frame = projects.copy()
        prog_col_series = prog_frame.get("programme", "")
        prog_frame["programme_norm"] = prog_col_series.astype(str).str.upper()
        keep_projects = set(
            prog_frame.loc[
                prog_frame["programme_norm"] == programme_normalized, "project_id"
            ].astype(str).tolist()
        )
        if keep_projects:
            mask = edges_org_project["target_project_id"].astype(str).isin(keep_projects)
            programme_orgs = set(edges_org_project.loc[mask, "source_org_id"].astype(str).tolist())
        else:
            programme_orgs = set()
        organizations = organizations[organizations["org_id"].astype(str).isin(programme_orgs)].copy()
    summary["orgs_after_programme_filter"] = int(len(organizations))

    metrics_path = graphs_dir / "organization_metrics.json"
    pagerank_map: dict[str, float] = {}
    if metrics_path.exists():
        try:
            metrics_records = json.loads(metrics_path.read_text(encoding="utf-8"))
            if isinstance(metrics_records, list):
                for row in metrics_records:
                    oid = str(row.get("org_id", ""))
                    if not oid:
                        continue
                    try:
                        pagerank_map[oid] = float(row.get("pagerank_collab", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        pagerank_map[oid] = 0.0
        except Exception:
            pagerank_map = {}

    if pagerank_map:
        organizations = organizations.assign(
            _pr=organizations["org_id"].astype(str).map(pagerank_map).fillna(0.0)
        )
        organizations = (
            organizations.sort_values("_pr", ascending=False)
            .head(int(max_orgs))
            .drop(columns=["_pr"])
            .copy()
        )
    else:
        summary["ranked_by"] = "nb_projects (fallback - organization_metrics.json missing)"
        summary["fallback_used"] = True
        nb_projects_series = pd.to_numeric(organizations.get("nb_projects"), errors="coerce").fillna(0)
        organizations = organizations.assign(_nbp=nb_projects_series)
        organizations = (
            organizations.sort_values("_nbp", ascending=False)
            .head(int(max_orgs))
            .drop(columns=["_nbp"])
            .copy()
        )

    summary["orgs_after_top_n_filter"] = int(len(organizations))

    keep_org_ids = set(organizations["org_id"].astype(str).tolist())

    # Collaborations: STRICT filter (both endpoints must be in top-N).
    if not edges_org_project.empty:
        edges_org_project = edges_org_project[
            edges_org_project["source_org_id"].astype(str).isin(keep_org_ids)
        ].copy()

    if not edges_org_org.empty:
        edges_org_org = edges_org_org[
            edges_org_org["org_a"].astype(str).isin(keep_org_ids)
            & edges_org_org["org_b"].astype(str).isin(keep_org_ids)
        ].copy()

    # Opportunities: RELAXED filter (at least one endpoint in top-N).
    filtered_gaps: list[dict[str, object]] = []
    context_org_ids: set[str] = set()
    for gap in gaps:
        a = str(gap.get("org_a", ""))
        b = str(gap.get("org_b", ""))
        a_in = a in keep_org_ids
        b_in = b in keep_org_ids
        if a_in or b_in:
            filtered_gaps.append(gap)
            if a and not a_in:
                context_org_ids.add(a)
            if b and not b_in:
                context_org_ids.add(b)

    if context_org_ids:
        context_orgs = (
            organizations_full[
                organizations_full["org_id"].astype(str).isin(context_org_ids)
            ]
            .drop_duplicates(subset=["org_id"], keep="first")
            .copy()
        )
    else:
        context_orgs = organizations_full.iloc[0:0].copy()

    summary["edges_org_project_after"] = int(len(edges_org_project))
    summary["edges_org_org_after"] = int(len(edges_org_org))
    summary["gaps_after_relaxed_filter"] = int(len(filtered_gaps))
    summary["context_only_orgs_added"] = int(len(context_orgs))

    return organizations, edges_org_project, edges_org_org, filtered_gaps, context_orgs, summary


def add_filter_banner(
    fmap: folium.Map,
    summary: dict[str, object],
    original_org_count: int,
    context_org_count: int = 0,
) -> None:
    shown = int(summary.get("orgs_after_top_n_filter", 0))
    programme_label = str(summary.get("programme_filter", "ALL"))
    rank_label = str(summary.get("ranked_by", "pagerank_collab"))
    context_part = (
        f" (+ <b>{int(context_org_count):,}</b> context orgs via opportunities)"
        if context_org_count > 0
        else ""
    )
    banner_html = f"""
<style>
#filter-banner {{
  position: fixed;
  top: 14px;
  left: 14px;
  z-index: 99998;
  background: rgba(17, 24, 39, 0.92);
  color: #ffffff;
  padding: 8px 12px;
  border-radius: 10px;
  font-family: Inter, -apple-system, "Segoe UI", sans-serif;
  font-size: 12px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.25);
  max-width: min(560px, calc(100vw - 32px));
}}
#filter-banner b {{ color: #fde68a; }}
</style>
<div id="filter-banner">
  Displaying <b>{shown:,}</b> orgs{context_part}
  / <b>{int(original_org_count):,}</b> organizations
  | Filter: <b>{escape(programme_label)}</b>
  | Ranked by <b>{escape(rank_label)}</b>
</div>
"""
    fmap.get_root().html.add_child(folium.Element(banner_html))


def add_common_controls(fmap: folium.Map) -> None:
    plugins.Fullscreen(position="topright").add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)


def add_base_tiles(fmap: folium.Map) -> None:
    folium.TileLayer("OpenStreetMap", name="Fond OSM", control=True, show=True).add_to(fmap)
    folium.TileLayer("cartodbpositron", name="Fond clair", control=True, show=False).add_to(fmap)
    folium.TileLayer("cartodbdark_matter", name="Fond sombre", control=True, show=False).add_to(fmap)


def add_dynamic_ui_panel(
    fmap: folium.Map,
    layer_config: list[dict[str, str]],
    search_records: list[dict[str, object]],
    kpis: dict[str, object] | None = None,
    top_orgs: list[dict[str, object]] | None = None,
    top_countries: list[dict[str, object]] | None = None,
) -> None:
    kpis = kpis or {}
    top_orgs = top_orgs or []
    top_countries = top_countries or []

    buttons_html = "".join(
        (
            f"<button class='viz-toggle' data-layer-id='{escape(item['id'])}' "
            f"data-color='{escape(item['color'])}' "
            f"style='background:{escape(item['color'])};border-color:{escape(item['color'])};color:#ffffff'>"
            f"{escape(item['label'])}</button>"
        )
        for item in layer_config
    )

    kpi_blocks = [
        ("Organisations", str(kpis.get("orgs", "—")), "k1"),
        ("Budget total", str(kpis.get("budget", "—")), "k2"),
        ("Pays distincts", str(kpis.get("countries", "—")), "k3"),
        ("Acteurs relais", str(kpis.get("brokers", "—")), "k4"),
    ]
    kpis_html = "".join(
        f'<div class="vp-kpi {cls}"><div class="lbl">{escape(label)}</div><div class="val">{escape(val)}</div></div>'
        for (label, val, cls) in kpi_blocks
    )

    top_orgs_html = "".join(
        f'<li class="vp-item" data-fly-lat="{safe_float(it.get("lat"))}" data-fly-lon="{safe_float(it.get("lon"))}" data-fly-zoom="9">'
        f'<span class="vp-rank">{idx+1}</span>'
        f'<span class="vp-name">{escape(str(it.get("name","") or "")[:42])}</span>'
        f'<span class="vp-meta">{escape(str(it.get("country","") or ""))}</span>'
        '</li>'
        for idx, it in enumerate(top_orgs[:8])
    ) or '<li class="vp-empty">Aucune donnée</li>'

    top_countries_html = "".join(
        f'<li class="vp-item" data-fly-lat="{safe_float(it.get("lat"))}" data-fly-lon="{safe_float(it.get("lon"))}" data-fly-zoom="5">'
        f'<span class="vp-flag">{escape(str(it.get("country","")))}</span>'
        f'<span class="vp-name">{int(it.get("count", 0)):,} orgs</span>'
        f'<span class="vp-meta">{escape(str(it.get("budget","")))}</span>'
        '</li>'
        for it in top_countries[:8]
    ) or '<li class="vp-empty">Aucune donnée</li>'

    sub_text = str(kpis.get("subtitle", "Carte interactive multi-couches"))

    panel_html = f"""
<style>
#viz-panel {{
  position: fixed;
  top: 14px;
  right: 14px;
  z-index: 99999;
  width: min(360px, calc(100vw - 32px));
  max-height: calc(100vh - 110px);
  background: rgba(255,255,255,.96);
  backdrop-filter: blur(10px);
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(15,23,42,.22);
  font-family: Inter, -apple-system, "Segoe UI", sans-serif;
  color: #0f172a;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}}
#viz-panel .vp-header {{
  background: linear-gradient(135deg,#1e3a8a 0%,#7c3aed 60%,#db2777 100%);
  color:#fff; padding: 14px 16px;
}}
#viz-panel .vp-header h2 {{
  margin:0; font-size:15px; font-weight:700; letter-spacing:.3px;
}}
#viz-panel .vp-header p {{
  margin:3px 0 0; font-size:11px; opacity:.85;
}}
#viz-panel .vp-body {{
  padding: 12px 14px 14px;
  overflow: auto;
  flex: 1;
}}
#viz-panel h3 {{
  margin: 12px 0 6px;
  font-size: 11px; text-transform: uppercase;
  letter-spacing:.6px; color:#64748b; font-weight:700;
}}
#viz-panel h3:first-child {{ margin-top: 0; }}
#viz-panel .vp-kpis {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 4px;
}}
#viz-panel .vp-kpi {{
  background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px;
  padding:8px 10px; position:relative; overflow:hidden;
}}
#viz-panel .vp-kpi::after {{
  content:""; position:absolute; right:-22px; top:-22px;
  width:60px; height:60px; border-radius:50%; opacity:.12;
}}
#viz-panel .vp-kpi.k1::after {{ background:#1e3a8a }}
#viz-panel .vp-kpi.k2::after {{ background:#0ea5e9 }}
#viz-panel .vp-kpi.k3::after {{ background:#16a34a }}
#viz-panel .vp-kpi.k4::after {{ background:#f59e0b }}
#viz-panel .vp-kpi .lbl {{ font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:.5px }}
#viz-panel .vp-kpi .val {{ font-size:16px; font-weight:800; margin-top:2px }}
#viz-panel .btn-grid {{
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px; margin-bottom: 6px;
}}
#viz-panel .viz-toggle {{
  border: 1px solid transparent; border-radius: 8px;
  background: #1f2937; color: #ffffff;
  padding: 7px 9px; cursor: pointer; font-size: 12px;
  text-align: left; transition: all .2s ease;
  display: flex; align-items: center; gap: 6px;
}}
#viz-panel .viz-toggle::before {{
  content: "●"; font-size: 9px; opacity:.95;
}}
#viz-panel .viz-toggle.active {{
  font-weight: 600;
  box-shadow: 0 0 0 3px rgba(15,23,42,.12), 0 4px 12px rgba(15,23,42,.18);
}}
#viz-panel .viz-toggle:hover {{
  transform: translateY(-1px);
}}
#viz-panel .filter-grid {{
  display: grid; grid-template-columns: 110px 1fr; gap: 6px;
}}
#viz-panel select, #viz-panel input {{
  border: 1px solid #cbd5e1; border-radius: 8px;
  padding: 7px 9px; font-size: 12px;
  width: 100%; box-sizing: border-box;
  font-family: inherit;
}}
#viz-panel input:focus, #viz-panel select:focus {{
  outline: none; border-color:#7c3aed;
  box-shadow: 0 0 0 3px rgba(124,58,237,.18);
}}
#viz-panel .actions {{
  display: flex; gap: 6px; margin-top: 8px;
}}
#viz-panel .actions button {{
  flex: 1; border: none; border-radius: 8px;
  padding: 9px 10px; cursor: pointer; font-size: 12px; font-weight: 600;
  transition: transform .12s, box-shadow .12s;
}}
#viz-panel .actions button.primary {{
  background: linear-gradient(135deg,#7c3aed,#db2777); color:#fff;
}}
#viz-panel .actions button.secondary {{
  background: #f1f5f9; color: #0f172a;
}}
#viz-panel .actions button:hover {{ transform: translateY(-1px); box-shadow: 0 6px 14px rgba(124,58,237,.25) }}
#viz-results {{
  margin-top: 8px; max-height: 120px; overflow: auto;
  border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 6px 8px; font-size: 12px;
  color: #0f172a; background: #fff;
}}
#viz-results .item {{ padding: 3px 0; border-bottom: 1px dashed #e2e8f0; }}
#viz-results .item:last-child {{ border-bottom: none; }}
#viz-panel .vp-list {{
  list-style:none; padding:0; margin:0;
}}
#viz-panel .vp-item {{
  display:flex; align-items:center; gap:8px;
  padding:6px 8px; border-radius:8px;
  cursor:pointer; font-size:12px; transition: background .12s;
}}
#viz-panel .vp-item:hover {{ background:#eef2ff; }}
#viz-panel .vp-rank {{
  display:inline-flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:50%;
  background: linear-gradient(135deg,#7c3aed,#db2777); color:#fff;
  font-weight:700; font-size:11px; flex-shrink:0;
}}
#viz-panel .vp-flag {{
  display:inline-block; min-width:32px; padding:3px 7px;
  border-radius:6px; background:#1e3a8a; color:#fff;
  font-weight:700; text-align:center; font-size:11px; flex-shrink:0;
}}
#viz-panel .vp-name {{
  flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  color:#0f172a; font-weight:500;
}}
#viz-panel .vp-meta {{
  font-size:10px; color:#64748b; flex-shrink:0;
}}
#viz-panel .vp-empty {{ color:#94a3b8; font-size:12px; padding:8px; }}
#viz-legend {{
  position: fixed; bottom: 14px; left: 14px;
  z-index: 99998; width: 240px;
  background: rgba(255,255,255,.96); backdrop-filter: blur(8px);
  border: 1px solid #e2e8f0; border-radius:12px;
  box-shadow: 0 8px 24px rgba(15,23,42,.14);
  padding: 10px 12px;
  font-family: Inter, sans-serif; font-size: 11px; color:#0f172a;
}}
#viz-legend h4 {{
  margin:0 0 6px; font-size:11px;
  text-transform:uppercase; letter-spacing:.5px; color:#475569;
}}
#viz-legend .row {{ display:flex; align-items:center; gap:6px; margin: 3px 0 }}
#viz-legend .dot {{ display:inline-block; width:10px; height:10px; border-radius:50% }}
#viz-legend .pill {{ display:inline-block; height:6px; border-radius:3px; flex:1; max-width:60px }}
</style>

<div id="viz-panel">
  <div class="vp-header">
    <h2>🌐 Réseau de recherche européen</h2>
    <p>{escape(sub_text)}</p>
  </div>
  <div class="vp-body">
    <div class="vp-kpis">{kpis_html}</div>
    <h3>📍 Couches affichables</h3>
    <div class="btn-grid">{buttons_html}</div>
    <h3>🔎 Recherche & filtre</h3>
    <div class="filter-grid">
      <select id="viz-mode">
        <option value="org_name">Org.</option>
        <option value="country">Pays</option>
        <option value="city">Ville</option>
        <option value="region">Région</option>
        <option value="org_type">Type</option>
        <option value="all">Global</option>
      </select>
      <input id="viz-query" type="text" placeholder="🔍 Ex: CNRS, FR, Paris…" list="viz-suggest"/>
    </div>
    <datalist id="viz-suggest"></datalist>
    <div class="actions">
      <button id="viz-apply" class="primary">Filtrer & zoomer</button>
      <button id="viz-clear" class="secondary">Reset</button>
    </div>
    <div id="viz-results">Aucun filtre appliqué.</div>
    <h3>🏆 Top organisations (PageRank)</h3>
    <ul class="vp-list">{top_orgs_html}</ul>
    <h3>🌍 Top pays</h3>
    <ul class="vp-list">{top_countries_html}</ul>
  </div>
</div>
<div id="viz-legend">
  <h4>Légende des couches</h4>
  <div class="row"><span class="dot" style="background:#0f766e"></span> Organisations (cluster)</div>
  <div class="row"><span class="dot" style="background:#dc2626"></span> Collaborations (poids)</div>
  <div class="row"><span class="dot" style="background:#7c3aed"></span> Opportunités (score)</div>
  <div class="row"><span class="dot" style="background:#f59e0b"></span> Acteurs relais (Burt)</div>
  <div class="row"><span class="dot" style="background:#888"></span> Orgs hors top-N</div>
  <div style="margin-top:8px;color:#64748b">Taille des cercles = budget reçu</div>
  <div class="row" style="margin-top:6px"><span class="pill" style="background:linear-gradient(90deg,#dbeafe,#7c3aed)"></span><span style="color:#64748b">Faible → Fort</span></div>
</div>

<script>
(function() {{
  const layerConfig = {json.dumps(layer_config, ensure_ascii=False)};
  const searchData = {json.dumps(search_records, ensure_ascii=False)};

  function findMap() {{
    if (typeof L === "undefined") return null;
    for (const key of Object.keys(window)) {{
      if (!key.startsWith("map_")) continue;
      const candidate = window[key];
      if (candidate && candidate instanceof L.Map) return candidate;
    }}
    return null;
  }}

  function findLayer(cfg) {{
    const byVar = window[cfg.var_name];
    if (byVar && (byVar.addTo || byVar._leaflet_id)) return byVar;
    const mapRef = window.__vizMapRef;
    if (mapRef) {{
      let found = null;
      mapRef.eachLayer(layer => {{
        if (layer && layer.options && layer.options.name === cfg.layer_name) found = layer;
      }});
      if (found) return found;
    }}
    for (const key of Object.keys(window)) {{
      if (!key.startsWith("feature_group_") && !key.startsWith("marker_cluster_") && !key.startsWith("heat_map_")) continue;
      const cand = window[key];
      if (cand && cand.options && cand.options.name === cfg.layer_name) return cand;
    }}
    return null;
  }}

  function styleButton(btn, cfg, active) {{
    btn.classList.toggle("active", !!active);
    btn.style.background = cfg.color;
    btn.style.borderColor = cfg.color;
    btn.style.color = "#ffffff";
    btn.style.opacity = active ? "1" : "0.45";
  }}

  function syncAllButtons() {{
    const mapRef = window.__vizMapRef;
    if (!mapRef) return;
    layerConfig.forEach(cfg => {{
      const btn = document.querySelector('button[data-layer-id="' + cfg.id + '"]');
      if (!btn) return;
      const layer = findLayer(cfg);
      const active = !!(layer && mapRef.hasLayer(layer));
      styleButton(btn, cfg, active);
    }});
  }}

  function bindButtons() {{
    layerConfig.forEach(cfg => {{
      const btn = document.querySelector('button[data-layer-id="' + cfg.id + '"]');
      if (!btn || btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function () {{
        const mapRef = window.__vizMapRef;
        if (!mapRef) return;
        const layer = findLayer(cfg);
        if (!layer) {{
          btn.style.outline = "2px solid #ef4444";
          setTimeout(() => {{ btn.style.outline = "none"; }}, 800);
          return;
        }}
        if (mapRef.hasLayer(layer)) mapRef.removeLayer(layer);
        else mapRef.addLayer(layer);
        syncAllButtons();
      }});
    }});
  }}

  function bindFilterUI() {{
    if (window.__vizFilterBound) return;
    const mapRef = window.__vizMapRef;
    if (!mapRef) return;
    const resultsBox = document.getElementById("viz-results");
    const modeInput = document.getElementById("viz-mode");
    const queryInput = document.getElementById("viz-query");
    const suggestBox = document.getElementById("viz-suggest");
    const applyBtn = document.getElementById("viz-apply");
    const clearBtn = document.getElementById("viz-clear");
    if (!resultsBox || !modeInput || !queryInput || !suggestBox || !applyBtn || !clearBtn) return;
    window.__vizFilterBound = true;

    const filterLayer = L.layerGroup().addTo(mapRef);

    function updateSuggestions() {{
      const mode = modeInput.value;
      const seen = new Set();
      const values = [];
      for (const row of searchData) {{
        const raw = mode === "all"
          ? (row.org_name + " | " + row.city + " | " + row.region + " | " + row.country + " | " + row.org_type)
          : String(row[mode] || "");
        const cleaned = String(raw || "").trim();
        if (!cleaned || seen.has(cleaned.toLowerCase())) continue;
        seen.add(cleaned.toLowerCase());
        values.push(cleaned);
        if (values.length >= 300) break;
      }}
      suggestBox.innerHTML = values.map(v => '<option value="' + v.split('"').join('&quot;') + '"></option>').join("");
    }}

    function renderMatches(matches) {{
      if (!matches.length) {{ resultsBox.innerHTML = "Aucun resultat pour ce filtre."; return; }}
      const sample = matches.slice(0, 12).map(row => (
        '<div class="item"><b>' + row.org_name + '</b> - ' + (row.city || "N/A") + ', ' + (row.country || "N/A") + '</div>'
      )).join("");
      const hidden = matches.length > 12 ? '<div class="item">... +' + (matches.length - 12) + ' autres resultats</div>' : "";
      resultsBox.innerHTML = '<div class="item"><b>' + matches.length + '</b> resultats</div>' + sample + hidden;
    }}

    function applyFilter() {{
      const mode = modeInput.value;
      const query = queryInput.value.trim().toLowerCase();
      let matches = searchData;
      if (query) {{
        matches = searchData.filter(row => {{
          if (mode === "all") {{
            const payload = (row.org_name + " " + row.city + " " + row.region + " " + row.country + " " + row.org_type).toLowerCase();
            return payload.includes(query);
          }}
          return String(row[mode] || "").toLowerCase().includes(query);
        }});
      }}
      filterLayer.clearLayers();
      const bounds = [];
      matches.slice(0, 300).forEach(row => {{
        const lat = Number(row.lat || 0);
        const lon = Number(row.lon || 0);
        if (!lat || !lon) return;
        bounds.push([lat, lon]);
        L.circleMarker([lat, lon], {{
          radius: 6, color: "#10b981", fillColor: "#34d399", fillOpacity: 0.85, weight: 1
        }})
        .bindPopup('<b>' + row.org_name + '</b><br>Pays: ' + (row.country || "N/A") + '<br>Ville: ' + (row.city || "N/A") + '<br>Type: ' + (row.org_type || "N/A"))
        .addTo(filterLayer);
      }});
      renderMatches(matches);
      if (bounds.length === 1) mapRef.setView(bounds[0], 8);
      else if (bounds.length > 1) mapRef.fitBounds(bounds, {{ padding: [24, 24] }});
    }}

    applyBtn.addEventListener("click", applyFilter);
    clearBtn.addEventListener("click", function () {{
      queryInput.value = "";
      filterLayer.clearLayers();
      resultsBox.innerHTML = "Aucun filtre applique.";
    }});
    queryInput.addEventListener("keydown", function (event) {{
      if (event.key === "Enter") {{ event.preventDefault(); applyFilter(); }}
    }});
    modeInput.addEventListener("change", updateSuggestions);
    updateSuggestions();
  }}

  function bindTopLists() {{
    if (window.__vizTopBound) return;
    const mapRef = window.__vizMapRef;
    if (!mapRef) return;
    window.__vizTopBound = true;
    document.querySelectorAll('#viz-panel .vp-item').forEach(li => {{
      li.addEventListener('click', () => {{
        const lat = parseFloat(li.dataset.flyLat || '0');
        const lon = parseFloat(li.dataset.flyLon || '0');
        const z = parseInt(li.dataset.flyZoom || '7', 10);
        if (Number.isFinite(lat) && Number.isFinite(lon) && lat !== 0) {{
          mapRef.flyTo([lat, lon], z, {{ duration: 0.9 }});
        }}
      }});
    }});
  }}

  function tryInit(attempt) {{
    const mapRef = findMap();
    if (!mapRef) {{
      if (attempt < 100) setTimeout(function () {{ tryInit(attempt + 1); }}, 150);
      return;
    }}
    window.__vizMapRef = mapRef;
    bindButtons();
    bindFilterUI();
    bindTopLists();
    syncAllButtons();
    setTimeout(syncAllButtons, 500);
    setTimeout(syncAllButtons, 1500);
  }}

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", function () {{ tryInit(0); }});
  }} else {{
    tryInit(0);
  }}
  window.addEventListener("load", function () {{ tryInit(0); }});
}})();
</script>
"""
    fmap.get_root().html.add_child(folium.Element(panel_html))


def compute_dynamic_opportunities(
    organizations: pd.DataFrame,
    projects: pd.DataFrame,
    edges_org_project: pd.DataFrame,
    edges_org_org_explicit: pd.DataFrame,
    target_org_ids: list[str],
    top_k: int = 10,
    max_candidates: int = 60,
) -> dict[str, list[dict[str, object]]]:
    """Compute multi-criteria collaboration opportunities for target orgs.

    Signals used:
    - Thematic: TF-IDF on aggregated project titles + topic_labels per org.
    - Cross-country bonus (transnational).
    - Cross-type bonus (HES/REC/PRC complementarity).
    - Size balance (budget magnitude proximity).
    - Excludes existing collaborators (edges_org_org_explicit).

    Returns dict {org_id: [opportunity dicts sorted by priority_score desc]}.
    """
    if organizations.empty or not target_org_ids:
        return {}

    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
    except ImportError:
        print("[opportunity engine] scikit-learn/numpy unavailable; skipping dynamic computation")
        return {}

    title_col = "project_title" if "project_title" in projects.columns else "title"
    topic_col = "topic_label" if "topic_label" in projects.columns else None

    project_text_map: dict[str, str] = {}
    if not projects.empty:
        title_series = projects[title_col].fillna("").astype(str) if title_col in projects.columns else None
        topic_series = projects[topic_col].fillna("").astype(str) if topic_col else None
        ids_series = projects["project_id"].astype(str)
        for idx in range(len(projects)):
            pid = ids_series.iloc[idx]
            parts = []
            if title_series is not None:
                parts.append(title_series.iloc[idx])
            if topic_series is not None:
                parts.append(topic_series.iloc[idx])
            project_text_map[pid] = " ".join(p for p in parts if p)

    org_corpus_parts: dict[str, list[str]] = {}
    if not edges_org_project.empty:
        for row in edges_org_project.itertuples(index=False):
            oid = str(getattr(row, "source_org_id", ""))
            pid = str(getattr(row, "target_project_id", ""))
            text = project_text_map.get(pid, "")
            if oid and text:
                org_corpus_parts.setdefault(oid, []).append(text)

    organizations = organizations.drop_duplicates(subset=["org_id"], keep="first").copy()
    org_meta_records = organizations.set_index("org_id").to_dict(orient="index")
    org_ids_ordered = list(org_meta_records.keys())

    corpus_texts: list[str] = []
    for oid in org_ids_ordered:
        title_text = " ".join(org_corpus_parts.get(oid, []))
        meta = org_meta_records[oid]
        fallback = " ".join(
            [
                str(meta.get("org_name", "") or ""),
                str(meta.get("org_type", "") or ""),
                str(meta.get("country", "") or ""),
                str(meta.get("city", "") or ""),
            ]
        ).strip()
        combined = (title_text + " " + fallback).strip() if title_text else fallback
        corpus_texts.append(combined if combined else "unknown")

    print(
        f"[opportunity engine] building TF-IDF over {len(corpus_texts):,} orgs "
        f"(targets={len(target_org_ids):,})..."
    )

    tfidf = TfidfVectorizer(
        max_features=2500,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.7,
        sublinear_tf=True,
    )
    try:
        tfidf_matrix = tfidf.fit_transform(corpus_texts)
    except ValueError as exc:
        print(f"[opportunity engine] TF-IDF failed: {exc}")
        return {}
    tfidf_matrix = normalize(tfidf_matrix, norm="l2", axis=1)
    org_index = {oid: i for i, oid in enumerate(org_ids_ordered)}

    existing_collabs: dict[str, set[str]] = {}
    if not edges_org_org_explicit.empty:
        for row in edges_org_org_explicit.itertuples(index=False):
            a = str(getattr(row, "org_a", ""))
            b = str(getattr(row, "org_b", ""))
            if a and b:
                existing_collabs.setdefault(a, set()).add(b)
                existing_collabs.setdefault(b, set()).add(a)

    results: dict[str, list[dict[str, object]]] = {}
    for target_oid in target_org_ids:
        target_idx = org_index.get(str(target_oid))
        if target_idx is None:
            results[str(target_oid)] = []
            continue

        target_meta = org_meta_records.get(target_oid, {})
        target_country = str(target_meta.get("country", "") or "").upper()
        target_type = str(target_meta.get("org_type", "") or "").upper()
        try:
            target_budget = float(target_meta.get("budget_total_received", 0.0) or 0.0)
        except (TypeError, ValueError):
            target_budget = 0.0
        target_existing = existing_collabs.get(str(target_oid), set())

        target_vec = tfidf_matrix[target_idx]
        sims_row = tfidf_matrix.dot(target_vec.T).toarray().flatten()
        sims_row[target_idx] = -1.0

        # Walk all orgs by descending similarity and skip existing collaborators
        # until we have max_candidates. This guarantees that even highly-connected
        # top-PageRank orgs (whose top-K nearest are all current collaborators)
        # surface real opportunities.
        sorted_desc = np.argsort(-sims_row)

        candidates: list[dict[str, object]] = []
        for cand_idx in sorted_desc:
            thematic = float(sims_row[cand_idx])
            if thematic <= 0:
                break
            cand_oid = org_ids_ordered[cand_idx]
            if cand_oid in target_existing:
                continue
            cand_meta = org_meta_records.get(cand_oid, {})
            other_country = str(cand_meta.get("country", "") or "").upper()
            other_type = str(cand_meta.get("org_type", "") or "").upper()
            try:
                other_budget = float(cand_meta.get("budget_total_received", 0.0) or 0.0)
            except (TypeError, ValueError):
                other_budget = 0.0

            cross_country = bool(target_country and other_country and target_country != other_country)
            cross_type = bool(target_type and other_type and target_type != other_type)
            if target_budget > 0 and other_budget > 0:
                size_balance = min(target_budget, other_budget) / max(target_budget, other_budget)
            else:
                size_balance = 0.4

            priority = (
                0.55 * thematic
                + 0.18 * (1.0 if cross_country else 0.4)
                + 0.13 * (1.0 if cross_type else 0.5)
                + 0.14 * float(size_balance)
            )

            candidates.append(
                {
                    "partner_id": cand_oid,
                    "partner_name": str(cand_meta.get("org_name", "") or cand_oid),
                    "partner_country": other_country,
                    "partner_type": other_type,
                    "thematic_score": round(thematic, 4),
                    "priority_score": round(priority, 4),
                    "cross_country": cross_country,
                    "cross_type": cross_type,
                    "size_balance_score": round(float(size_balance), 4),
                }
            )
            if len(candidates) >= max_candidates:
                break

        candidates.sort(key=lambda entry: float(entry.get("priority_score", 0.0)), reverse=True)
        results[str(target_oid)] = candidates[:top_k]

    print(
        f"[opportunity engine] done. orgs with >=1 opportunity: "
        f"{sum(1 for v in results.values() if v):,} / {len(results):,}"
    )
    return results


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:80] if slug else "organisation"


def build_org_context(
    organizations: pd.DataFrame,
    projects: pd.DataFrame,
    edges_org_project: pd.DataFrame,
    edges_org_org: pd.DataFrame,
    metrics: pd.DataFrame,
    gaps: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    organizations = organizations.copy()
    organizations["country"] = organizations["country"].astype(str).str.upper()
    if "lat" not in organizations.columns:
        lat_src = pd.to_numeric(organizations.get("latitude"), errors="coerce")
        fallback_lat = organizations["country"].map(lambda c: COUNTRY_COORDS.get(c, (None, None))[0])
        organizations["lat"] = lat_src.fillna(fallback_lat)
    if "lon" not in organizations.columns:
        lon_src = pd.to_numeric(organizations.get("longitude"), errors="coerce")
        fallback_lon = organizations["country"].map(lambda c: COUNTRY_COORDS.get(c, (None, None))[1])
        organizations["lon"] = lon_src.fillna(fallback_lon)

    project_title = dict(zip(projects["project_id"].astype(str), projects["project_title"].astype(str), strict=False))
    project_program = dict(zip(projects["project_id"].astype(str), projects["program"].astype(str), strict=False))
    org_name = dict(zip(organizations["org_id"].astype(str), organizations["org_name"].astype(str), strict=False))
    org_lat = dict(zip(organizations["org_id"].astype(str), pd.to_numeric(organizations["lat"], errors="coerce"), strict=False))
    org_lon = dict(zip(organizations["org_id"].astype(str), pd.to_numeric(organizations["lon"], errors="coerce"), strict=False))

    summary = (
        edges_org_project.groupby("source_org_id", as_index=False)
        .agg(total_funding=("weight_eur", "sum"), n_projects=("target_project_id", "nunique"))
    )
    summary_map = {
        str(row["source_org_id"]): {
            "total_funding": float(row["total_funding"]),
            "n_projects": int(row["n_projects"]),
        }
        for row in summary.to_dict(orient="records")
    }

    project_rows: dict[str, list[dict[str, object]]] = {}
    for row in edges_org_project.sort_values("weight_eur", ascending=False).itertuples(index=False):
        oid = str(getattr(row, "source_org_id"))
        pid = str(getattr(row, "target_project_id"))
        project_rows.setdefault(oid, [])
        if len(project_rows[oid]) >= 20:
            continue
        project_rows[oid].append(
            {
                "project_id": pid,
                "title": project_title.get(pid, pid),
                "program": project_program.get(pid, "N/A"),
                "funding_eur": float(getattr(row, "weight_eur", 0.0) or 0.0),
            }
        )

    collab_rows: dict[str, list[dict[str, object]]] = {}
    for row in edges_org_org.sort_values("weight_common_projects", ascending=False).itertuples(index=False):
        a = str(getattr(row, "org_a"))
        b = str(getattr(row, "org_b"))
        w = float(getattr(row, "weight_common_projects", 0.0) or 0.0)
        collab_rows.setdefault(a, []).append(
            {
                "org_id": b,
                "org_name": org_name.get(b, b),
                "weight": w,
                "lat": safe_float(org_lat.get(b)),
                "lon": safe_float(org_lon.get(b)),
            }
        )
        collab_rows.setdefault(b, []).append(
            {
                "org_id": a,
                "org_name": org_name.get(a, a),
                "weight": w,
                "lat": safe_float(org_lat.get(a)),
                "lon": safe_float(org_lon.get(a)),
            }
        )
    for key in list(collab_rows.keys()):
        collab_rows[key] = collab_rows[key][:25]

    metric_map: dict[str, dict[str, object]] = {}
    if not metrics.empty and "org_id" in metrics.columns:
        metric_map = {str(row["org_id"]): row for row in metrics.to_dict(orient="records")}

    burt_rank: dict[str, int] = {}
    if metric_map:
        rows_sorted = sorted(
            (
                (oid, safe_float(row.get("burt_constraint_thematic", 0.0)))
                for oid, row in metric_map.items()
                if safe_float(row.get("burt_constraint_thematic", 0.0)) > 0
            ),
            key=lambda item: item[1],
        )
        for idx, (oid, _) in enumerate(rows_sorted, start=1):
            burt_rank[oid] = idx
    max_rank_broker = max(5, int(len(burt_rank) * 0.30)) if burt_rank else 0

    gap_rows: dict[str, list[dict[str, object]]] = {}
    for row in gaps:
        a = str(row.get("org_a", ""))
        b = str(row.get("org_b", ""))
        s = safe_float(row.get("thematic_score"))
        if not a or not b:
            continue
        gap_rows.setdefault(a, []).append(
            {
                "org_id": b,
                "org_name": org_name.get(b, b),
                "score": s,
                "lat": safe_float(org_lat.get(b)),
                "lon": safe_float(org_lon.get(b)),
            }
        )
        gap_rows.setdefault(b, []).append(
            {
                "org_id": a,
                "org_name": org_name.get(a, a),
                "score": s,
                "lat": safe_float(org_lat.get(a)),
                "lon": safe_float(org_lon.get(a)),
            }
        )
    for key in list(gap_rows.keys()):
        gap_rows[key] = sorted(gap_rows[key], key=lambda item: safe_float(item["score"]), reverse=True)[:25]

    out: dict[str, dict[str, object]] = {}
    for row in organizations.to_dict(orient="records"):
        oid = str(row.get("org_id", ""))
        metric = metric_map.get(oid, {})
        burt = safe_float(metric.get("burt_constraint_thematic", 0.0))
        has_thematic_signal = burt > 0.0
        out[oid] = {
            "org": row,
            "summary": summary_map.get(oid, {"total_funding": 0.0, "n_projects": 0}),
            "projects": project_rows.get(oid, []),
            "collabs": collab_rows.get(oid, []),
            "gaps": gap_rows.get(oid, []),
            "metric": metric,
            "is_broker": bool(metric) and has_thematic_signal and burt_rank.get(oid, 999999) <= max_rank_broker,
        }
    return out


def write_org_profile_pages(
    context: dict[str, dict[str, object]],
    output_dir: Path,
    full_gaps: list[dict[str, object]] | None = None,
    org_name_full: dict[str, str] | None = None,
    org_country_full: dict[str, str] | None = None,
    org_coords_full: dict[str, tuple[float, float]] | None = None,
    dynamic_opportunities: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    full_gaps = list(full_gaps or [])
    org_name_full = org_name_full or {}
    org_country_full = org_country_full or {}
    org_coords_full = org_coords_full or {}
    dynamic_opportunities = dynamic_opportunities or {}

    if dynamic_opportunities:
        non_empty = sum(1 for v in dynamic_opportunities.values() if v)
        print(
            f"[opportunity diagnostic] using dynamic opportunities engine: "
            f"{non_empty:,} / {len(dynamic_opportunities):,} orgs have >=1 opportunity"
        )
    elif full_gaps:
        sample_a = [str(g.get("org_a", "")) for g in full_gaps[:3]]
        sample_b = [str(g.get("org_b", "")) for g in full_gaps[:3]]
        print(f"[opportunity diagnostic] fallback to gap_analysis_top.json: size={len(full_gaps)}")
        print(f"[opportunity diagnostic] sample org_a values: {sample_a}")
        print(f"[opportunity diagnostic] sample org_b values: {sample_b}")
    else:
        print("[opportunity diagnostic] no opportunity source available")

    diagnostic_count = 0
    links: dict[str, str] = {}
    index_rows: list[tuple[str, str]] = []
    for org_id, item in context.items():
        org = item["org"]
        summary = item["summary"]
        projects = item["projects"]
        collabs = item["collabs"]
        metric = item["metric"] or {}
        name = str(org.get("org_name", org_id))
        country = str(org.get("country", "N/A"))
        city = str(org.get("city", "N/A"))
        is_broker = "Oui" if bool(item.get("is_broker")) else "Non"
        pagerank = safe_float(metric.get("pagerank_collab", 0.0))
        betweenness = safe_float(metric.get("betweenness_collab", 0.0))
        burt = safe_float(metric.get("burt_constraint_thematic", 0.0))

        project_html = "".join(
            "<tr>"
            f"<td>{escape(str(row.get('project_id', '')))}</td>"
            f"<td>{escape(str(row.get('title', '')))}</td>"
            f"<td>{escape(str(row.get('program', '')))}</td>"
            f"<td style='text-align:right'>{safe_float(row.get('funding_eur', 0.0)):,.0f}</td>"
            "</tr>"
            for row in projects
        ) or "<tr><td colspan='4'>Aucun projet disponible.</td></tr>"
        collab_list_html = "".join(
            "<li>"
            f"<span>{escape(str(row.get('org_name', 'N/A')))}</span>"
            f"<b>{safe_float(row.get('weight', 0.0)):.1f}</b>"
            "</li>"
            for row in collabs[:12]
        ) or "<li><span>Aucune collaboration explicite</span><b>-</b></li>"

        org_id_str = str(org_id)
        if dynamic_opportunities and org_id_str in dynamic_opportunities:
            org_opportunities: list[dict[str, object]] = list(dynamic_opportunities[org_id_str])
            opportunity_source = "dynamic"
        else:
            org_opportunities = []
            for gap in full_gaps:
                a = str(gap.get("org_a", ""))
                b = str(gap.get("org_b", ""))
                if a == org_id_str:
                    partner_id = b
                    partner_country = str(gap.get("org_b_country", "") or "")
                elif b == org_id_str:
                    partner_id = a
                    partner_country = str(gap.get("org_a_country", "") or "")
                else:
                    continue
                org_opportunities.append(
                    {
                        "partner_id": partner_id,
                        "partner_name": org_name_full.get(partner_id, partner_id),
                        "partner_country": partner_country or org_country_full.get(partner_id, ""),
                        "priority_score": safe_float(gap.get("priority_score")),
                        "thematic_score": safe_float(gap.get("thematic_score")),
                    }
                )
            org_opportunities.sort(
                key=lambda r: safe_float(r.get("priority_score", 0.0)), reverse=True
            )
            opportunity_source = "legacy_json"

        top_opportunities = org_opportunities[:10]

        if diagnostic_count < 5:
            preview_partner = (
                top_opportunities[0].get("partner_id") if top_opportunities else None
            )
            print(
                f"[opportunity diagnostic] org={org_id_str} "
                f"source={opportunity_source} "
                f"matches={len(org_opportunities)} "
                f"top_partner={preview_partner}"
            )
            diagnostic_count += 1

        if top_opportunities:
            gap_list_html = "".join(
                "<li>"
                f"<span>{escape(str(entry.get('partner_name') or org_name_full.get(str(entry.get('partner_id', '')), str(entry.get('partner_id', '')))))}"
                f" <small>({escape(str(entry.get('partner_country') or 'N/A'))})</small></span>"
                f"<b>P&nbsp;{safe_float(entry.get('priority_score', 0.0)):.3f}"
                f" | T&nbsp;{safe_float(entry.get('thematic_score', 0.0)):.3f}</b>"
                "</li>"
                for entry in top_opportunities
            )
        else:
            gap_list_html = "<li><span>Aucune opportunite detectee pour cette organisation</span><b>-</b></li>"

        center_lat = safe_float(org.get("lat"))
        center_lon = safe_float(org.get("lon"))
        collab_graph_data = [
            {
                "name": str(row.get("org_name", "")),
                "value": safe_float(row.get("weight", 0.0)),
                "lat": safe_float(row.get("lat", 0.0)),
                "lon": safe_float(row.get("lon", 0.0)),
            }
            for row in collabs[:15]
        ]
        gap_graph_data: list[dict[str, object]] = []
        for entry in top_opportunities:
            partner_id = str(entry.get("partner_id", ""))
            partner_name = entry.get("partner_name") or org_name_full.get(partner_id, partner_id)
            coords = org_coords_full.get(partner_id, (0.0, 0.0))
            gap_graph_data.append(
                {
                    "name": str(partner_name),
                    "value": safe_float(entry.get("priority_score", 0.0)),
                    "lat": safe_float(coords[0]),
                    "lon": safe_float(coords[1]),
                }
            )

        html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(name)} — Fiche detaillee</title>
<style>
body {{
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  margin: 0;
  color: #1f2937;
  background: radial-gradient(circle at top left, #eef2ff 0%, #f8fafc 40%, #ffffff 100%);
}}
.container {{ max-width: 1220px; margin: 0 auto; padding: 20px; }}
.hero {{
  border-radius: 16px;
  background: linear-gradient(135deg, #1d4ed8 0%, #7c3aed 100%);
  color: #ffffff;
  padding: 18px 20px;
  box-shadow: 0 10px 30px rgba(79, 70, 229, 0.25);
}}
.hero h1 {{ margin: 0 0 6px 0; font-size: 28px; line-height: 1.2; }}
.hero-meta {{ font-size: 14px; opacity: 0.95; display: flex; gap: 10px; flex-wrap: wrap; }}
.chip {{
  display: inline-block;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.28);
}}
.cards {{ margin-top: 14px; display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 10px; }}
.card {{
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 3px 12px rgba(15, 23, 42, 0.06);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.card:hover {{ transform: translateY(-1px); box-shadow: 0 8px 20px rgba(15, 23, 42, 0.1); }}
.kpi-title {{ font-size: 12px; color: #6b7280; margin-bottom: 6px; }}
.kpi-value {{ font-size: 22px; font-weight: 700; color: #111827; }}
.section {{
  margin-top: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #ffffff;
  padding: 12px;
  box-shadow: 0 3px 10px rgba(15, 23, 42, 0.05);
}}
.section h2 {{ margin: 0 0 10px 0; font-size: 18px; }}
.toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }}
.tab-btn {{
  border: 1px solid #d1d5db;
  background: #f9fafb;
  color: #111827;
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13px;
  cursor: pointer;
}}
.tab-btn.active {{ background: #111827; color: #ffffff; border-color: #111827; }}
.panel {{ display: none; }}
.panel.active {{ display: block; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ border: 1px solid #e5e7eb; padding: 7px 8px; font-size: 13px; }}
th {{ background: #f3f4f6; text-align: left; }}
.filter-row {{ display: flex; gap: 8px; margin-bottom: 10px; }}
.filter-row input {{
  width: 100%;
  max-width: 380px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
}}
.split {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 10px; align-items: start; }}
.list-card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px; background: #fcfcff; align-self: start; }}
.list-card h3 {{ margin: 0 0 8px 0; font-size: 14px; }}
.list-card ul {{ list-style: none; padding: 0; margin: 0; max-height: 420px; overflow: auto; }}
.list-card li {{
  display: flex;
  justify-content: space-between;
  gap: 8px;
  border-bottom: 1px dashed #e5e7eb;
  padding: 6px 0;
  font-size: 13px;
}}
.list-card li:last-child {{ border-bottom: none; }}
.map-box {{ width: 100%; height: 420px; border-radius: 8px; border: 1px solid #e5e7eb; }}
.graph-caption {{ color: #4b5563; font-size: 12px; margin-top: 6px; }}
</style></head><body>
<div class="container">
<div class="hero">
  <h1>{escape(name)}</h1>
  <div class="hero-meta">
    <span class="chip">ID: {escape(org_id)}</span>
    <span class="chip">Pays: {escape(country)}</span>
    <span class="chip">Ville: {escape(city)}</span>
    <span class="chip">Acteur relais: {is_broker}</span>
  </div>
</div>
<div class="cards">
<div class="card"><div class="kpi-title">Budget total recu</div><div class="kpi-value">{safe_float(summary.get('total_funding', 0.0)):,.0f} EUR</div></div>
<div class="card"><div class="kpi-title">Nombre de projets</div><div class="kpi-value">{int(summary.get('n_projects', 0))}</div></div>
<div class="card"><div class="kpi-title">PageRank / Betweenness / Burt</div><div class="kpi-value">{pagerank:.5f} | {betweenness:.5f} | {burt:.3f}</div></div>
</div>

<div class="section">
  <h2>Projets et financements</h2>
  <div class="filter-row">
    <input id="projectFilter" type="text" placeholder="Filtrer un projet (id, titre, programme)..." />
  </div>
  <table id="projectTable"><thead><tr><th>ID projet</th><th>Titre</th><th>Programme</th><th>Financement EUR</th></tr></thead><tbody>{project_html}</tbody></table>
</div>

<div class="section">
<h2>Reseau local dynamique</h2>
<div class="toolbar">
  <button class="tab-btn active" data-panel="panel-collab">Collaborations explicites</button>
  <button class="tab-btn" data-panel="panel-gap">Opportunites de collaboration</button>
</div>
<div id="panel-collab" class="panel active">
<div class="split">
<div><div id="collabMap" class="map-box"></div></div>
<div class="list-card"><h3>Top partenaires (poids)</h3><ul>{collab_list_html}</ul></div>
</div>
<div class="graph-caption">Noeud central = organisation courante. Les liens montrent les partenaires explicites et le poids (projets communs).</div>
</div>
<div id="panel-gap" class="panel">
<div class="split">
<div><div id="gapMap" class="map-box"></div></div>
<div class="list-card"><h3>Top opportunites (score)</h3><ul>{gap_list_html}</ul></div>
</div>
<div class="graph-caption">Noeud central = organisation courante. Les liens montrent les partenaires potentiels avec score thematique.</div>
</div>
</div>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="anonymous"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin="anonymous"></script>
<script>
const collabData = {json.dumps(collab_graph_data, ensure_ascii=False)};
const gapData = {json.dumps(gap_graph_data, ensure_ascii=False)};
const centerLabel = {json.dumps(name, ensure_ascii=False)};
const centerLat = {center_lat};
const centerLon = {center_lon};

const mapRegistry = {{}};
const mapBoundsRegistry = {{}};

function drawLocalMap(divId, nodes, edgeColor, metricLabel) {{
  const box = document.getElementById(divId);
  if (!box) return;
  if (!Number.isFinite(centerLat) || !Number.isFinite(centerLon) || centerLat === 0 || centerLon === 0) {{
    box.innerHTML = "<div style='padding:12px;color:#6b7280'>Coordonnees indisponibles pour cette organisation.</div>";
    return;
  }}

  const map = L.map(divId, {{ zoomControl: true, preferCanvas: true }}).setView([centerLat, centerLon], 4);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap'
  }}).addTo(map);

  const centerMarker = L.circleMarker([centerLat, centerLon], {{
    radius: 9, color: '#1f77b4', weight: 2, fillOpacity: 0.9
  }}).addTo(map);
  centerMarker.bindPopup(`<b>${{centerLabel}}</b><br>Organisation centrale`);

  const bounds = [[centerLat, centerLon]];
  const valid = (nodes || []).filter(n => Number.isFinite(n.lat) && Number.isFinite(n.lon) && n.lat !== 0 && n.lon !== 0);
  const maxValue = Math.max(...valid.map(n => Number(n.value || 0)), 1);
  valid.forEach(node => {{
    const lat = Number(node.lat), lon = Number(node.lon), value = Number(node.value || 0);
    const width = 1 + (value / maxValue) * 5;
    L.polyline([[centerLat, centerLon], [lat, lon]], {{
      color: edgeColor, weight: width, opacity: 0.65
    }}).addTo(map).bindPopup(`Type arete: ${{metricLabel}}<br>Poids/score: ${{value.toFixed(3)}}`);
    L.circleMarker([lat, lon], {{
      radius: 6, color: '#374151', weight: 1, fillOpacity: 0.85
    }}).addTo(map).bindPopup(`<b>${{node.name}}</b><br>${{metricLabel}}: ${{value.toFixed(3)}}`);
    bounds.push([lat, lon]);
  }});

  if (bounds.length > 1) {{
    map.fitBounds(bounds, {{ padding: [25, 25] }});
  }}
  mapRegistry[divId] = map;
  mapBoundsRegistry[divId] = bounds;
  return map;
}}

drawLocalMap("collabMap", collabData, "#dc2626", "Poids");
drawLocalMap("gapMap", gapData, "#7c3aed", "Score");

// Re-trigger Leaflet sizing when a hidden panel becomes visible.
// Hidden containers have 0x0 size at init time and tiles never load
// without an explicit invalidateSize() once the panel is shown.
function refreshMapForPanel(panelId) {{
  let mapId = null;
  if (panelId === "panel-collab") mapId = "collabMap";
  else if (panelId === "panel-gap") mapId = "gapMap";
  if (!mapId) return;
  const map = mapRegistry[mapId];
  if (!map) return;
  requestAnimationFrame(() => {{
    map.invalidateSize(true);
    const b = mapBoundsRegistry[mapId];
    if (b && b.length > 1) {{
      map.fitBounds(b, {{ padding: [25, 25] }});
    }}
  }});
}}

const tabButtons = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll(".panel");
tabButtons.forEach(btn => {{
  btn.addEventListener("click", () => {{
    const panelId = btn.getAttribute("data-panel");
    tabButtons.forEach(item => item.classList.remove("active"));
    panels.forEach(item => item.classList.remove("active"));
    btn.classList.add("active");
    const panel = document.getElementById(panelId);
    if (panel) panel.classList.add("active");
    refreshMapForPanel(panelId);
  }});
}});

window.addEventListener("load", () => {{
  // Ensure the initially-visible map (collab) re-measures after fonts/layout settle.
  refreshMapForPanel("panel-collab");
}});

const projectFilter = document.getElementById("projectFilter");
if (projectFilter) {{
  projectFilter.addEventListener("input", () => {{
    const q = projectFilter.value.toLowerCase().trim();
    document.querySelectorAll("#projectTable tbody tr").forEach(row => {{
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(q) ? "" : "none";
    }});
  }});
}}
</script>
</div>
</body></html>"""
        filename = f"{slugify(name)}-{slugify(org_id)}.html"
        (output_dir / filename).write_text(html, encoding="utf-8")
        links[org_id] = f"org_profiles/{filename}"
        index_rows.append((name, filename))
    index_rows = sorted(index_rows, key=lambda item: item[0].lower())
    list_items = "".join(
        f"<li><a href='{escape(filename)}'>{escape(name)}</a></li>"
        for name, filename in index_rows
    )
    index_html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Index des fiches organisations</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
input {{ width: 100%; max-width: 560px; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; }}
li {{ margin: 4px 0; }}
</style></head><body>
<h1>Index des fiches organisations</h1>
<p>Filtrer par nom :</p>
<input id="q" type="text" placeholder="Ex: Université, CNRS, Fraunhofer..." oninput="f()"/>
<ul id="list">{list_items}</ul>
<script>
function f() {{
  const q = document.getElementById('q').value.toLowerCase();
  const items = document.querySelectorAll('#list li');
  items.forEach(li => {{
    li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</body></html>"""
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")
    return links


def build_funding_map(organizations: pd.DataFrame, output_path: Path) -> Path:
    fmap = folium.Map(location=[50.5, 9.5], zoom_start=4, tiles="cartodbpositron", control_scale=True)
    organizations = resolve_org_coordinates(organizations)

    marker_cluster = plugins.MarkerCluster(name="Organisations (cluster)", show=True).add_to(fmap)
    funding_layer = folium.FeatureGroup(name="Bulles de financement", show=True).add_to(fmap)
    heat_layer_points: list[list[float]] = []

    for row in organizations.itertuples(index=False):
        coords = [float(getattr(row, "lat")), float(getattr(row, "lon"))]
        country = str(getattr(row, "country", "")).upper()
        city = str(getattr(row, "city", "") or "")
        budget = float(getattr(row, "budget_total_received", 0.0) or 0.0)
        nb_projects = int(getattr(row, "nb_projects", 0) or 0)
        org_name = str(getattr(row, "org_name", "Unknown"))
        popup_html = (
            f"<b>{org_name}</b><br>"
            f"Pays: {country}<br>"
            f"Ville: {city or 'N/A'}<br>"
            f"Budget: {budget:,.0f} EUR<br>"
            f"Projets: {nb_projects}"
        )

        folium.Marker(
            location=coords,
            popup=folium.Popup(popup_html, max_width=350),
            icon=folium.Icon(color="blue", icon="university", prefix="fa"),
        ).add_to(marker_cluster)

        folium.CircleMarker(
            location=coords,
            radius=circle_radius_from_budget(budget),
            color="#0057b8",
            fill=True,
            fill_opacity=0.45,
            weight=1,
            popup=folium.Popup(popup_html, max_width=350),
        ).add_to(funding_layer)
        heat_layer_points.append([coords[0], coords[1], max(0.1, budget / 5_000_000)])

    if heat_layer_points:
        plugins.HeatMap(heat_layer_points, name="Carte de chaleur du financement", radius=25, blur=20, show=False).add_to(fmap)

    add_common_controls(fmap)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    return output_path


def build_collaboration_map(
    organizations: pd.DataFrame,
    edges_org_org: pd.DataFrame,
    output_path: Path,
    max_edges: int = 400,
) -> Path:
    fmap = folium.Map(location=[50.5, 9.5], zoom_start=4, tiles="cartodbpositron", control_scale=True)
    organizations = resolve_org_coordinates(organizations)

    org_lookup = organizations[["org_id", "org_name", "country", "city", "lat", "lon"]].copy()
    org_lookup["coords"] = org_lookup.apply(lambda row: (float(row["lat"]), float(row["lon"])), axis=1)
    org_by_id = org_lookup.set_index("org_id").to_dict(orient="index")

    # Search index: organization + city + country (+ extra tokens if present)
    search_features: list[dict[str, object]] = []
    for row in organizations_display.itertuples(index=False):
        lat = safe_float(getattr(row, "lat", 0.0))
        lon = safe_float(getattr(row, "lon", 0.0))
        if not (lat and lon):
            continue
        org_name = str(getattr(row, "org_name", "") or "")
        city = str(getattr(row, "city", "") or "")
        country = str(getattr(row, "country", "") or "")
        org_type = str(getattr(row, "org_type", "") or "")
        region = str(getattr(row, "region", "") or "")
        search_text = " | ".join(part for part in [org_name, city, region, country, org_type] if part).strip()
        search_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "search_text": search_text,
                    "org_name": org_name,
                    "city": city or "N/A",
                    "region": region or "N/A",
                    "country": country or "N/A",
                },
            }
        )

    search_geojson = folium.GeoJson(
        {"type": "FeatureCollection", "features": search_features},
        name="Index recherche",
        show=False,
        tooltip=folium.GeoJsonTooltip(
            fields=["org_name", "city", "region", "country"],
            aliases=["Organisation", "Ville", "Region", "Pays"],
            localize=True,
            sticky=False,
        ),
        popup=folium.GeoJsonPopup(
            fields=["org_name", "city", "region", "country"],
            aliases=["Organisation", "Ville", "Region", "Pays"],
            localize=True,
        ),
    ).add_to(fmap)
    plugins.Search(
        layer=search_geojson,
        search_label="search_text",
        placeholder="Rechercher organisation, ville, region, pays...",
        collapsed=False,
        search_zoom=8,
        position="topleft",
    ).add_to(fmap)

    if not edges_org_org.empty:
        edges_org_org = edges_org_org.sort_values("weight_common_projects", ascending=False).head(max_edges)

    line_layer = folium.FeatureGroup(name="Liens de collaboration (top)", show=True).add_to(fmap)
    node_layer = plugins.MarkerCluster(name="Organisations", show=True).add_to(fmap)

    for row in edges_org_org.itertuples(index=False):
        left = str(getattr(row, "org_a"))
        right = str(getattr(row, "org_b"))
        weight = float(getattr(row, "weight_common_projects", 0.0) or 0.0)
        left_meta = org_by_id.get(left)
        right_meta = org_by_id.get(right)
        if not left_meta or not right_meta:
            continue
        left_coords = left_meta["coords"]
        right_coords = right_meta["coords"]
        folium.PolyLine(
            locations=[left_coords, right_coords],
            color="#d62728",
            weight=max(1.0, min(6.0, weight / 2.0)),
            opacity=0.35,
            popup=folium.Popup(
                f"<b>{left_meta['org_name']}</b> ↔ <b>{right_meta['org_name']}</b><br>"
                f"Common projects: {int(weight)}",
                max_width=420,
            ),
        ).add_to(line_layer)

    for row in org_lookup.itertuples(index=False):
        folium.Marker(
            location=row.coords,
            popup=folium.Popup(
                f"<b>{row.org_name}</b><br>Country: {row.country}<br>City: {row.city or 'N/A'}",
                max_width=320,
            ),
            icon=folium.Icon(color="cadetblue", icon="circle", prefix="fa"),
        ).add_to(node_layer)

    add_common_controls(fmap)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    return output_path


def build_gap_map(organizations: pd.DataFrame, graphs_dir: Path, output_path: Path, max_edges: int = 250) -> Path:
    fmap = folium.Map(location=[50.5, 9.5], zoom_start=4, tiles="cartodbpositron", control_scale=True)
    organizations = resolve_org_coordinates(organizations)
    org_by_id = organizations.set_index("org_id").to_dict(orient="index")

    gap_json = graphs_dir / "gap_analysis_top.json"
    if gap_json.exists():
        gaps = json.loads(gap_json.read_text(encoding="utf-8"))
    else:
        gaps = []
        thematic_path = graphs_dir / "thematic_implicit.gexf"
        if thematic_path.exists():
            thematic = nx.read_gexf(thematic_path)
            for left, right, data in thematic.edges(data=True):
                if data.get("explicit_collab"):
                    continue
                gaps.append({"org_a": left, "org_b": right, "thematic_score": safe_float(data.get("weight"))})
        gaps = sorted(gaps, key=lambda item: safe_float(item.get("thematic_score")), reverse=True)

    link_layer = folium.FeatureGroup(name="Opportunites de collaboration", show=True).add_to(fmap)
    marker_layer = plugins.MarkerCluster(name="Organisations (gaps)", show=True).add_to(fmap)

    for gap in gaps[: max(max_edges, DISPLAY_GAP_LIMIT)]:
        left = str(gap.get("org_a", ""))
        right = str(gap.get("org_b", ""))
        score = safe_float(gap.get("thematic_score"))
        left_meta = org_by_id.get(left)
        right_meta = org_by_id.get(right)
        if not left_meta or not right_meta:
            continue
        left_coords = [float(left_meta["lat"]), float(left_meta["lon"])]
        right_coords = [float(right_meta["lat"]), float(right_meta["lon"])]
        folium.PolyLine(
            locations=[left_coords, right_coords],
            color="#6a0dad",
            weight=max(1.0, min(6.0, 1 + score * 4)),
            opacity=0.55,
            popup=folium.Popup(
                f"<b>Gap opportunity</b><br>{left_meta['org_name']} ↔ {right_meta['org_name']}<br>"
                f"Thematic score: {score:.3f}",
                max_width=420,
            ),
        ).add_to(link_layer)

    for row in organizations.itertuples(index=False):
        folium.Marker(
            location=[float(row.lat), float(row.lon)],
            popup=folium.Popup(f"<b>{row.org_name}</b><br>Country: {row.country}", max_width=300),
            icon=folium.Icon(color="purple", icon="lightbulb", prefix="fa"),
        ).add_to(marker_layer)

    add_common_controls(fmap)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    return output_path


def build_broker_map(organizations: pd.DataFrame, graphs_dir: Path, output_path: Path, top_n: int = 120) -> Path:
    fmap = folium.Map(location=[50.5, 9.5], zoom_start=4, tiles="cartodbpositron", control_scale=True)
    organizations = resolve_org_coordinates(organizations)

    metrics_path = graphs_dir / "organization_metrics.json"
    if not metrics_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fmap.save(str(output_path))
        return output_path

    metrics = pd.DataFrame(json.loads(metrics_path.read_text(encoding="utf-8")))
    if metrics.empty or "org_id" not in metrics.columns:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fmap.save(str(output_path))
        return output_path

    merged = organizations.merge(metrics, left_on="org_id", right_on="org_id", how="inner")
    merged = merged.sort_values("burt_constraint_thematic", ascending=True).head(top_n)

    layer = plugins.MarkerCluster(name="Acteurs brokers (top)", show=True).add_to(fmap)
    for row in merged.itertuples(index=False):
        constraint = safe_float(getattr(row, "burt_constraint_thematic", 0.0))
        pagerank = safe_float(getattr(row, "pagerank_collab", 0.0))
        folium.CircleMarker(
            location=[float(row.lat), float(row.lon)],
            radius=max(5.0, min(18.0, 6 + pagerank * 3000)),
            color="#ff8c00",
            fill=True,
            fill_opacity=0.65,
            popup=folium.Popup(
                f"<b>{row.org_name}</b><br>"
                f"Country: {row.country}<br>"
                f"Burt constraint: {constraint:.4f}<br>"
                f"PageRank: {pagerank:.6f}",
                max_width=360,
            ),
        ).add_to(layer)

    add_common_controls(fmap)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    return output_path


def run(
    processed_dir: Path,
    graphs_dir: Path,
    max_edges: int,
    programme: str = "ALL",
    max_orgs: int = 2000,
) -> dict[str, str]:
    organizations = load_csv(processed_dir / "organizations.csv")
    projects = load_csv(processed_dir / "projects.csv")
    edges_org_project = load_csv(processed_dir / "edges_org_project.csv")
    edges_org_org = load_csv(processed_dir / "edges_org_org_explicit.csv")
    if organizations.empty:
        raise FileNotFoundError("Missing organizations.csv. Run clean_normalize.py first.")
    metrics_path = graphs_dir / "organization_metrics.json"
    metrics = pd.DataFrame(json.loads(metrics_path.read_text(encoding="utf-8"))) if metrics_path.exists() else pd.DataFrame()
    gap_json = graphs_dir / "gap_analysis_top.json"
    gaps: list[dict[str, object]] = json.loads(gap_json.read_text(encoding="utf-8")) if gap_json.exists() else []

    original_org_count = int(len(organizations))

    full_gaps_for_profiles: list[dict[str, object]] = list(gaps)
    organizations_pre_filter = organizations.copy()
    edges_org_project_pre_filter = edges_org_project.copy()
    edges_org_org_pre_filter = edges_org_org.copy()
    full_orgs_resolved = (
        resolve_org_coordinates(organizations_pre_filter)
        if not organizations_pre_filter.empty
        else organizations_pre_filter
    )
    org_name_full: dict[str, str] = {}
    org_country_full: dict[str, str] = {}
    org_coords_full: dict[str, tuple[float, float]] = {}
    if not full_orgs_resolved.empty:
        for record in full_orgs_resolved.to_dict(orient="records"):
            oid_full = str(record.get("org_id", ""))
            if not oid_full:
                continue
            org_name_full[oid_full] = str(record.get("org_name", "") or "")
            org_country_full[oid_full] = str(record.get("country", "") or "").upper()
            try:
                org_coords_full[oid_full] = (
                    float(record.get("lat")),
                    float(record.get("lon")),
                )
            except (TypeError, ValueError):
                continue

    (
        organizations,
        edges_org_project,
        edges_org_org,
        gaps,
        context_orgs,
        filter_summary,
    ) = apply_display_filter(
        organizations=organizations,
        edges_org_project=edges_org_project,
        edges_org_org=edges_org_org,
        projects=projects,
        gaps=gaps,
        graphs_dir=graphs_dir,
        programme=programme,
        max_orgs=max_orgs,
    )
    print("Display filter:")
    print(f"- orgs before filter: {filter_summary['orgs_before_any_filter']:,}")
    print(
        f"- orgs after programme filter ({filter_summary['programme_filter']}): "
        f"{filter_summary['orgs_after_programme_filter']:,}"
    )
    print(
        f"- orgs after top-{filter_summary['max_orgs']} filter "
        f"(ranked by {filter_summary['ranked_by']}): "
        f"{filter_summary['orgs_after_top_n_filter']:,}"
    )
    print(
        f"- edges_org_project: {filter_summary['edges_org_project_before']:,} -> "
        f"{filter_summary['edges_org_project_after']:,}"
    )
    print(
        f"- edges_org_org (strict): {filter_summary['edges_org_org_before']:,} -> "
        f"{filter_summary['edges_org_org_after']:,}"
    )
    print(f"- gaps before: {filter_summary['gaps_before_filter']:,}")
    print(
        f"- gaps after relaxed filter: {filter_summary['gaps_after_relaxed_filter']:,}"
    )
    print(
        f"- context-only orgs added to map: {filter_summary['context_only_orgs_added']:,}"
    )
    report_path = graphs_dir / "display_filter_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_payload = dict(filter_summary)
    report_payload["original_org_count"] = original_org_count
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    gap_org_ids: set[str] = set()
    for gap in full_gaps_for_profiles:
        a = str(gap.get("org_a", ""))
        b = str(gap.get("org_b", ""))
        if a:
            gap_org_ids.add(a)
        if b:
            gap_org_ids.add(b)
    displayed_org_ids = set(organizations["org_id"].astype(str).tolist())
    extra_gap_only_ids = gap_org_ids - displayed_org_ids
    if extra_gap_only_ids and not organizations_pre_filter.empty:
        extra_orgs_df = organizations_pre_filter[
            organizations_pre_filter["org_id"].astype(str).isin(extra_gap_only_ids)
        ].copy()
        organizations_for_profiles = pd.concat([organizations, extra_orgs_df], ignore_index=True)
        organizations_for_profiles = organizations_for_profiles.drop_duplicates(
            subset=["org_id"], keep="first"
        )
    else:
        organizations_for_profiles = organizations
    print(
        f"[opportunity diagnostic] profiles to generate: "
        f"top-N={len(displayed_org_ids):,} + extra_from_gaps={len(extra_gap_only_ids):,} "
        f"= total={len(organizations_for_profiles):,}"
    )

    org_context = build_org_context(
        organizations=organizations_for_profiles,
        projects=projects,
        edges_org_project=edges_org_project,
        edges_org_org=edges_org_org,
        metrics=metrics,
        gaps=gaps,
    )

    # Compute opportunities dynamically for every org getting a profile, using
    # the *full* base of organizations / projects / collaborations (not the
    # display-filtered subset). This guarantees that even high-PageRank orgs
    # like Helsinki Univ. have meaningful, multi-criteria opportunities.
    profile_target_ids = list(
        organizations_for_profiles["org_id"].astype(str).drop_duplicates().tolist()
    )
    dynamic_opportunities = compute_dynamic_opportunities(
        organizations=organizations_pre_filter,
        projects=projects,
        edges_org_project=edges_org_project_pre_filter,
        edges_org_org_explicit=edges_org_org_pre_filter,
        target_org_ids=profile_target_ids,
        top_k=10,
        max_candidates=60,
    )
    dynamic_payload_path = graphs_dir / "dynamic_opportunities.json"
    try:
        dynamic_payload_path.write_text(
            json.dumps(dynamic_opportunities, indent=2, default=str), encoding="utf-8"
        )
    except Exception as exc:
        print(f"[opportunity engine] could not persist dynamic_opportunities.json: {exc}")

    profile_links = write_org_profile_pages(
        org_context,
        graphs_dir / "org_profiles",
        full_gaps=full_gaps_for_profiles,
        org_name_full=org_name_full,
        org_country_full=org_country_full,
        org_coords_full=org_coords_full,
        dynamic_opportunities=dynamic_opportunities,
    )

    fmap = folium.Map(location=[50.5, 9.5], zoom_start=4, tiles=None, control_scale=True)
    add_base_tiles(fmap)
    organizations = resolve_org_coordinates(organizations)
    if "region" not in organizations.columns:
        organizations["region"] = ""
    if "org_type" not in organizations.columns:
        organizations["org_type"] = ""
    organizations["budget_total_received"] = pd.to_numeric(
        organizations.get("budget_total_received"), errors="coerce"
    ).fillna(0.0)
    organizations["nb_projects"] = pd.to_numeric(organizations.get("nb_projects"), errors="coerce").fillna(0).astype(int)
    organizations_display = (
        organizations.sort_values(["budget_total_received", "nb_projects"], ascending=False)
        .head(DISPLAY_ORG_LIMIT)
        .copy()
    )
    org_lookup = organizations[["org_id", "org_name", "country", "city", "org_type", "region", "lat", "lon"]].copy()
    org_lookup = org_lookup.drop_duplicates(subset=["org_id"], keep="first")
    org_lookup["coords"] = org_lookup.apply(lambda row: (float(row["lat"]), float(row["lon"])), axis=1)
    org_by_id = org_lookup.set_index("org_id").to_dict(orient="index")

    # Resolve coordinates for context orgs (gap endpoints outside the top-N).
    if not context_orgs.empty:
        if "region" not in context_orgs.columns:
            context_orgs["region"] = ""
        if "org_type" not in context_orgs.columns:
            context_orgs["org_type"] = ""
        context_orgs_resolved = resolve_org_coordinates(context_orgs)
    else:
        context_orgs_resolved = context_orgs

    if not context_orgs_resolved.empty:
        for row in context_orgs_resolved.itertuples(index=False):
            oid = str(getattr(row, "org_id", ""))
            if not oid or oid in org_by_id:
                continue
            try:
                lat_val = float(getattr(row, "lat"))
                lon_val = float(getattr(row, "lon"))
            except (TypeError, ValueError):
                continue
            org_by_id[oid] = {
                "org_id": oid,
                "org_name": str(getattr(row, "org_name", "") or ""),
                "country": str(getattr(row, "country", "") or ""),
                "city": str(getattr(row, "city", "") or ""),
                "org_type": str(getattr(row, "org_type", "") or ""),
                "region": str(getattr(row, "region", "") or ""),
                "lat": lat_val,
                "lon": lon_val,
                "coords": (lat_val, lon_val),
            }
    search_records: list[dict[str, object]] = []
    for row in organizations_display.itertuples(index=False):
        lat = safe_float(getattr(row, "lat", 0.0))
        lon = safe_float(getattr(row, "lon", 0.0))
        if not (lat and lon):
            continue
        search_records.append(
            {
                "org_name": str(getattr(row, "org_name", "") or ""),
                "country": str(getattr(row, "country", "") or ""),
                "city": str(getattr(row, "city", "") or ""),
                "region": str(getattr(row, "region", "") or ""),
                "org_type": str(getattr(row, "org_type", "") or ""),
                "lat": lat,
                "lon": lon,
            }
        )
    org_projects = edges_org_project.groupby("source_org_id")
    org_project_funding: dict[str, dict[str, float]] = {}
    for org_id, frame in org_projects:
        org_project_funding[str(org_id)] = {
            str(pid): safe_float(val)
            for pid, val in zip(frame["target_project_id"].astype(str), frame["weight_eur"], strict=False)
        }
    org_funding_line_count = (
        edges_org_project.groupby("source_org_id").size().astype(int).to_dict() if not edges_org_project.empty else {}
    )
    project_title_by_id = dict(zip(projects["project_id"].astype(str), projects["project_title"].astype(str), strict=False))

    # Layer 1: funding bubbles + heatmap
    funding_layer = folium.FeatureGroup(name="Bulles de financement", show=True).add_to(fmap)
    heat_layer_points: list[list[float]] = []
    for row in organizations_display.itertuples(index=False):
        coords = [float(getattr(row, "lat")), float(getattr(row, "lon"))]
        org_id = str(getattr(row, "org_id", ""))
        country = str(getattr(row, "country", "")).upper()
        city = str(getattr(row, "city", "") or "")
        budget = float(getattr(row, "budget_total_received", 0.0) or 0.0)
        nb_projects = int(getattr(row, "nb_projects", 0) or 0)
        nb_financing_rows = int(org_funding_line_count.get(org_id, 0))
        org_name = str(getattr(row, "org_name", "Unknown"))
        popup_html = (
            f"<b>{org_name}</b><br>"
            f"Pays: {country}<br>"
            f"Ville: {city or 'N/A'}<br>"
            f"Budget: {budget:,.0f} EUR<br>"
            f"Projets: {nb_projects}<br>"
            f"Lignes de financement: {nb_financing_rows}<br>"
            f"<a href='{escape(profile_links.get(org_id, '#'))}' target='_blank'>Voir fiche detaillee</a>"
        )
        folium.CircleMarker(
            location=coords,
            radius=circle_radius_from_budget(budget),
            color="#0057b8",
            fill=True,
            fill_opacity=0.45,
            weight=1,
            popup=folium.Popup(popup_html, max_width=350),
        ).add_to(funding_layer)
        heat_layer_points.append([coords[0], coords[1], max(0.1, budget / 5_000_000)])

    heat_layer = None
    if heat_layer_points:
        heat_layer = plugins.HeatMap(
            heat_layer_points,
            name="Carte de chaleur du financement",
            radius=25,
            blur=20,
            show=False,
        ).add_to(fmap)

    # Layer 1bis: country grouping with approximate perimeters from organization positions.
    country_layer = folium.FeatureGroup(name="Groupage par pays (perimetres)", show=False).add_to(fmap)
    country_points = organizations.copy()
    country_points["country"] = country_points["country"].astype(str).str.upper()
    country_points["city"] = country_points.get("city", "").astype(str)
    country_points["budget_total_received"] = pd.to_numeric(
        country_points.get("budget_total_received"), errors="coerce"
    ).fillna(0.0)
    country_points["nb_projects"] = pd.to_numeric(country_points.get("nb_projects"), errors="coerce").fillna(0).astype(int)

    for country, frame in country_points.groupby("country"):
        if not country or country == "NAN":
            continue
        coords = [
            (safe_float(getattr(row, "lon")), safe_float(getattr(row, "lat")))
            for row in frame.itertuples(index=False)
            if safe_float(getattr(row, "lat")) and safe_float(getattr(row, "lon"))
        ]
        if not coords:
            continue

        cities = sorted({str(city).strip() for city in frame["city"].tolist() if str(city).strip() and str(city).strip() != "nan"})[:6]
        popup_html = (
            f"<b>Pays:</b> {escape(country)}<br>"
            f"<b>Organisations:</b> {int(frame['org_id'].astype(str).nunique())}<br>"
            f"<b>Budget total:</b> {float(frame['budget_total_received'].sum()):,.0f} EUR<br>"
            f"<b>Projets cumules:</b> {int(frame['nb_projects'].sum())}<br>"
            f"<b>Exemples de villes:</b> {escape(', '.join(cities) if cities else 'N/A')}"
        )

        lons = [point[0] for point in coords]
        lats = [point[1] for point in coords]
        center = [sum(lats) / len(lats), sum(lons) / len(lons)]

        unique_coords = sorted(set(coords))
        if len(unique_coords) >= 3:
            hull = convex_hull_lon_lat(unique_coords)
            hull_lat_lon = [[lat, lon] for lon, lat in hull]
            folium.Polygon(
                locations=hull_lat_lon,
                color="#2563eb",
                weight=2,
                fill=True,
                fill_opacity=0.08,
                popup=folium.Popup(popup_html, max_width=360),
            ).add_to(country_layer)
        elif len(unique_coords) == 2:
            lon_min, lon_max = min(lons), max(lons)
            lat_min, lat_max = min(lats), max(lats)
            pad_lon = max(0.2, (lon_max - lon_min) * 0.25)
            pad_lat = max(0.2, (lat_max - lat_min) * 0.25)
            rectangle = [
                [lat_min - pad_lat, lon_min - pad_lon],
                [lat_min - pad_lat, lon_max + pad_lon],
                [lat_max + pad_lat, lon_max + pad_lon],
                [lat_max + pad_lat, lon_min - pad_lon],
            ]
            folium.Polygon(
                locations=rectangle,
                color="#2563eb",
                weight=2,
                fill=True,
                fill_opacity=0.08,
                popup=folium.Popup(popup_html, max_width=360),
            ).add_to(country_layer)
        else:
            folium.Circle(
                location=center,
                radius=45000,
                color="#2563eb",
                weight=2,
                fill=True,
                fill_opacity=0.08,
                popup=folium.Popup(popup_html, max_width=360),
            ).add_to(country_layer)

        folium.CircleMarker(
            location=center,
            radius=max(4.0, min(12.0, 3 + frame["org_id"].astype(str).nunique() ** 0.5 / 2)),
            color="#1d4ed8",
            fill=True,
            fill_opacity=0.85,
            weight=1,
            popup=folium.Popup(popup_html, max_width=360),
        ).add_to(country_layer)

    # Layer 2: explicit collaboration links
    collab_layer = folium.FeatureGroup(name="Liens de collaboration (top)", show=False).add_to(fmap)
    if not edges_org_org.empty:
        edges_org_org = edges_org_org.sort_values("weight_common_projects", ascending=False).head(max_edges)
        for row in edges_org_org.itertuples(index=False):
            left = str(getattr(row, "org_a"))
            right = str(getattr(row, "org_b"))
            weight = float(getattr(row, "weight_common_projects", 0.0) or 0.0)
            left_meta = org_by_id.get(left)
            right_meta = org_by_id.get(right)
            if not left_meta or not right_meta:
                continue
            left_projects = org_project_funding.get(left, {})
            right_projects = org_project_funding.get(right, {})
            common_projects = sorted(set(left_projects.keys()).intersection(right_projects.keys()))
            top_common = common_projects[:5]
            common_titles = [project_title_by_id.get(pid, pid) for pid in top_common]
            pair_funding = sum(left_projects.get(pid, 0.0) + right_projects.get(pid, 0.0) for pid in common_projects)
            top_common_text = "<br>".join(escape(title) for title in common_titles) if common_titles else "N/A"
            folium.PolyLine(
                locations=[left_meta["coords"], right_meta["coords"]],
                color="#d62728",
                weight=max(1.0, min(6.0, weight / 2.0)),
                opacity=0.35,
                popup=folium.Popup(
                    f"<b>{left_meta['org_name']}</b> ↔ <b>{right_meta['org_name']}</b><br>"
                    f"<b>Type arete:</b> Collaboration explicite<br>"
                    f"<b>Poids:</b> {int(weight)} projets communs<br>"
                    f"<b>Montant cumule (A+B) sur projets communs:</b> {pair_funding:,.0f} EUR<br>"
                    f"<b>Exemples de projets communs:</b><br>{top_common_text}",
                    max_width=420,
                ),
            ).add_to(collab_layer)

    # Layer 3: gap opportunities (reuses already-filtered gaps)
    gap_layer = folium.FeatureGroup(name="Opportunites de collaboration", show=False).add_to(fmap)
    for gap in gaps[:max_edges]:
        left = str(gap.get("org_a", ""))
        right = str(gap.get("org_b", ""))
        score = safe_float(gap.get("thematic_score"))
        priority_score = safe_float(gap.get("priority_score"))
        priority_label = str(gap.get("priority_label", "") or "N/A")
        left_meta = org_by_id.get(left)
        right_meta = org_by_id.get(right)
        if not left_meta or not right_meta:
            continue
        left_broker = bool(org_context.get(left, {}).get("is_broker", False))
        right_broker = bool(org_context.get(right, {}).get("is_broker", False))
        left_country = str(gap.get("org_a_country", "") or left_meta.get("country", "N/A"))
        right_country = str(gap.get("org_b_country", "") or right_meta.get("country", "N/A"))
        left_type = str(gap.get("org_a_type", "") or "N/A")
        right_type = str(gap.get("org_b_type", "") or "N/A")
        left_projects_count = int(safe_float(gap.get("org_a_projects", 0)))
        right_projects_count = int(safe_float(gap.get("org_b_projects", 0)))
        left_budget = safe_float(gap.get("org_a_budget", 0.0))
        right_budget = safe_float(gap.get("org_b_budget", 0.0))
        cross_country = bool(gap.get("cross_country", False))
        cross_type = bool(gap.get("cross_type", False))
        size_balance = safe_float(gap.get("size_balance_score", 0.0))
        folium.PolyLine(
            locations=[left_meta["coords"], right_meta["coords"]],
            color="#6a0dad",
            weight=max(1.0, min(6.0, 1 + priority_score * 4)),
            opacity=0.55,
            popup=folium.Popup(
                f"<b>Opportunite (gap)</b><br>{left_meta['org_name']} ↔ {right_meta['org_name']}<br>"
                f"<b>Type arete:</b> Proximite thematique implicite<br>"
                f"<b>Score thematique (poids):</b> {score:.3f}<br>"
                f"<b>Priorite recommandee:</b> {priority_label} ({priority_score:.3f})<br>"
                f"<b>Broker (gauche/droite):</b> {'Oui' if left_broker else 'Non'} / {'Oui' if right_broker else 'Non'}<br>"
                f"<b>Pays (gauche/droite):</b> {left_country} / {right_country}<br>"
                f"<b>Types (gauche/droite):</b> {left_type} / {right_type}<br>"
                f"<b>Effet transnational:</b> {'Oui' if cross_country else 'Non'}<br>"
                f"<b>Complementarite de types:</b> {'Oui' if cross_type else 'Non'}<br>"
                f"<b>Volume projets (gauche/droite):</b> {left_projects_count} / {right_projects_count}<br>"
                f"<b>Budget total recu (gauche/droite):</b> {left_budget:,.0f} / {right_budget:,.0f} EUR<br>"
                f"<b>Equilibre de taille:</b> {size_balance:.3f}",
                max_width=420,
            ),
        ).add_to(gap_layer)

    # Layer 3bis: context-only orgs (endpoints of opportunities outside top-N).
    context_layer = folium.FeatureGroup(
        name="Context orgs (via opportunities)", show=False
    ).add_to(fmap)
    if not context_orgs_resolved.empty:
        for row in context_orgs_resolved.itertuples(index=False):
            try:
                lat_val = float(getattr(row, "lat"))
                lon_val = float(getattr(row, "lon"))
            except (TypeError, ValueError):
                continue
            if not (lat_val and lon_val):
                continue
            org_name_ctx = str(getattr(row, "org_name", "") or "")
            country_ctx = str(getattr(row, "country", "") or "N/A")
            folium.CircleMarker(
                location=[lat_val, lon_val],
                radius=4,
                color="#888888",
                fill=True,
                fill_opacity=0.65,
                weight=1,
                popup=folium.Popup(
                    f"<b>{escape(org_name_ctx)}</b><br>"
                    f"Pays: {escape(country_ctx)}<br>"
                    f"<i>Contexte opportunite (hors top-{int(filter_summary.get('max_orgs', 0))})</i>",
                    max_width=260,
                ),
            ).add_to(context_layer)

    # Layer 4: brokers
    broker_layer = folium.FeatureGroup(name="Acteurs relais (ponts) (top)", show=False).add_to(fmap)
    metrics_path = graphs_dir / "organization_metrics.json"
    if metrics_path.exists():
        if not metrics.empty and "org_id" in metrics.columns:
            merged = organizations.merge(metrics, left_on="org_id", right_on="org_id", how="inner")
            merged["burt_constraint_thematic"] = pd.to_numeric(merged["burt_constraint_thematic"], errors="coerce").fillna(0.0)
            merged = merged[merged["burt_constraint_thematic"] > 0].sort_values("burt_constraint_thematic", ascending=True)
            top_n = max(5, int(len(merged) * 0.30))
            merged = merged.head(top_n)
            for row in merged.itertuples(index=False):
                constraint = safe_float(getattr(row, "burt_constraint_thematic", 0.0))
                pagerank = safe_float(getattr(row, "pagerank_collab", 0.0))
                folium.CircleMarker(
                    location=[float(row.lat), float(row.lon)],
                    radius=max(5.0, min(18.0, 6 + pagerank * 3000)),
                    color="#ff8c00",
                    fill=True,
                    fill_opacity=0.65,
                    popup=folium.Popup(
                        f"<b>{row.org_name}</b><br>"
                        f"Pays: {row.country}<br>"
                        f"Contrainte de Burt: {constraint:.4f}<br>"
                        f"PageRank: {pagerank:.6f}",
                        max_width=360,
                    ),
                ).add_to(broker_layer)

    # Base markers
    org_cluster = plugins.MarkerCluster(name="Organisations", show=True).add_to(fmap)
    display_org_ids = set(organizations_display["org_id"].astype(str).tolist())
    org_lookup_display = org_lookup[org_lookup["org_id"].astype(str).isin(display_org_ids)].copy()
    for row in org_lookup_display.itertuples(index=False):
        folium.Marker(
            location=row.coords,
            popup=folium.Popup(
                f"<b>{row.org_name}</b><br>Pays: {row.country}<br>Ville: {row.city or 'N/A'}<br>"
                f"<a href='{escape(profile_links.get(str(row.org_id), '#'))}' target='_blank'>Voir fiche detaillee</a>",
                max_width=320,
            ),
            icon=folium.Icon(color="cadetblue", icon="circle", prefix="fa"),
        ).add_to(org_cluster)

    ui_layers = [
        {
            "id": "funding",
            "label": "Bulles de financement",
            "color": "#2563eb",
            "var_name": funding_layer.get_name(),
            "layer_name": "Bulles de financement",
        },
        {
            "id": "countries",
            "label": "Perimetres pays",
            "color": "#1d4ed8",
            "var_name": country_layer.get_name(),
            "layer_name": "Groupage par pays (perimetres)",
        },
        {
            "id": "collabs",
            "label": "Liens de collaboration",
            "color": "#dc2626",
            "var_name": collab_layer.get_name(),
            "layer_name": "Liens de collaboration (top)",
        },
        {
            "id": "gaps",
            "label": "Opportunites de collaboration",
            "color": "#7c3aed",
            "var_name": gap_layer.get_name(),
            "layer_name": "Opportunites de collaboration",
        },
        {
            "id": "brokers",
            "label": "Acteurs relais",
            "color": "#f59e0b",
            "var_name": broker_layer.get_name(),
            "layer_name": "Acteurs relais (ponts) (top)",
        },
        {
            "id": "orgs",
            "label": "Organisations",
            "color": "#0f766e",
            "var_name": org_cluster.get_name(),
            "layer_name": "Organisations",
        },
    ]
    if heat_layer is not None:
        ui_layers.append(
            {
                "id": "heat",
                "label": "Heatmap financement",
                "color": "#ec4899",
                "var_name": heat_layer.get_name(),
                "layer_name": "Carte de chaleur du financement",
            }
        )
    # Compute KPIs and top performers for the panel.
    panel_orgs_count = int(len(organizations_display))
    panel_budget_total = float(organizations_display["budget_total_received"].sum())
    panel_countries_count = int(
        organizations_display["country"].astype(str).str.upper().replace("", pd.NA).dropna().nunique()
    )
    brokers_count = 0
    metrics_for_panel = metrics if "metrics" in dir() else pd.DataFrame()
    try:
        if not metrics.empty and "burt_constraint_thematic" in metrics.columns:
            mvals = pd.to_numeric(metrics["burt_constraint_thematic"], errors="coerce").fillna(0.0)
            brokers_count = int((mvals > 0).sum() * 0.30)
    except Exception:
        brokers_count = 0

    def _fmt_eur(value: float) -> str:
        if value >= 1e9:
            return f"{value/1e9:,.1f} G€"
        if value >= 1e6:
            return f"{value/1e6:,.1f} M€"
        if value >= 1e3:
            return f"{value/1e3:,.0f} k€"
        return f"{value:,.0f} €"

    # Top organizations by PageRank (or budget fallback)
    top_orgs_panel: list[dict[str, object]] = []
    if not metrics.empty and "org_id" in metrics.columns:
        ranked = organizations_display.merge(
            metrics[["org_id", "pagerank_collab"]], on="org_id", how="left"
        )
        ranked["pagerank_collab"] = pd.to_numeric(ranked["pagerank_collab"], errors="coerce").fillna(0.0)
        ranked = ranked.sort_values(
            ["pagerank_collab", "budget_total_received"], ascending=[False, False]
        ).head(8)
    else:
        ranked = organizations_display.sort_values("budget_total_received", ascending=False).head(8)
    for row in ranked.itertuples(index=False):
        try:
            top_orgs_panel.append(
                {
                    "name": str(getattr(row, "org_name", "") or ""),
                    "country": str(getattr(row, "country", "") or ""),
                    "lat": float(getattr(row, "lat", 0.0) or 0.0),
                    "lon": float(getattr(row, "lon", 0.0) or 0.0),
                    "budget": _fmt_eur(safe_float(getattr(row, "budget_total_received", 0.0))),
                }
            )
        except (TypeError, ValueError):
            continue

    # Top countries by org count
    top_countries_panel: list[dict[str, object]] = []
    if "country" in organizations_display.columns:
        country_agg = (
            organizations_display.assign(country=organizations_display["country"].astype(str).str.upper())
            .groupby("country", as_index=False)
            .agg(
                count=("org_id", "nunique"),
                lat=("lat", "mean"),
                lon=("lon", "mean"),
                budget=("budget_total_received", "sum"),
            )
        )
        country_agg = country_agg[country_agg["country"].astype(str).str.len() > 0]
        country_agg = country_agg.sort_values("count", ascending=False).head(8)
        for row in country_agg.itertuples(index=False):
            try:
                top_countries_panel.append(
                    {
                        "country": str(row.country),
                        "count": int(row.count),
                        "lat": float(row.lat),
                        "lon": float(row.lon),
                        "budget": _fmt_eur(safe_float(row.budget)),
                    }
                )
            except (TypeError, ValueError):
                continue

    panel_kpis = {
        "orgs": f"{panel_orgs_count:,}",
        "budget": _fmt_eur(panel_budget_total),
        "countries": f"{panel_countries_count}",
        "brokers": f"{brokers_count:,}" if brokers_count else "—",
        "subtitle": (
            f"Top {panel_orgs_count:,} orgs · {panel_countries_count} pays · "
            f"~{int(filter_summary.get('edges_org_org_after', 0)):,} liens"
        ),
    }

    add_dynamic_ui_panel(
        fmap=fmap,
        layer_config=ui_layers,
        search_records=search_records,
        kpis=panel_kpis,
        top_orgs=top_orgs_panel,
        top_countries=top_countries_panel,
    )
    add_filter_banner(
        fmap=fmap,
        summary=filter_summary,
        original_org_count=original_org_count,
        context_org_count=int(filter_summary.get("context_only_orgs_added", 0)),
    )

    add_common_controls(fmap)
    map_path = graphs_dir / "research_network_map_folium.html"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(map_path))

    # Cleanup legacy separate maps
    for old_name in [
        "funding_map_folium.html",
        "collaboration_map_folium.html",
        "gap_map_folium.html",
        "broker_map_folium.html",
    ]:
        old_path = graphs_dir / old_name
        if old_path.exists():
            old_path.unlink()

    return {
        "research_network_map": str(map_path),
        "org_profiles_dir": str(graphs_dir / "org_profiles"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Folium maps for organizations and collaborations")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--graphs-dir", type=Path, default=Path("data/graphs"))
    parser.add_argument("--max-edges", type=int, default=400, help="Maximum collaboration edges drawn on map")
    parser.add_argument(
        "--programme",
        type=str,
        default="ALL",
        choices=["ALL", "H2020", "HE", "all", "h2020", "he"],
        help="Filter organizations by programme (H2020, HE, or ALL).",
    )
    parser.add_argument(
        "--max-orgs",
        type=int,
        default=2000,
        help="Maximum organizations rendered on the map (top-N by PageRank).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    outputs = run(
        processed_dir=args.processed_dir,
        graphs_dir=args.graphs_dir,
        max_edges=args.max_edges,
        programme=str(args.programme).upper(),
        max_orgs=args.max_orgs,
    )
    print("Generated Folium maps:")
    for key, value in outputs.items():
        print(f"- {key}: {value}")
