# OpenEUResearch-Graph

Pipeline **open data** pour analyser les financements européens (CORDIS, OpenAlex) : réseaux multi-couches, métriques de graphe, opportunités de collaboration et visualisations interactives.

**Projet MIAGE** — Université Paris Nanterre · module *Graphes et Open Data* · encadré par Valentin Bouquet.

## Idée centrale

Le dossier **`data/`** est le **cœur du dépôt** : le code dans `src/` produit des tables, graphes et pages HTML que le rapport et la démo exploitent directement. Voir [`data/README.md`](data/README.md) pour la politique de versionnement (ce qui est sur GitHub vs régénérable localement).

| Couche | Rôle |
|--------|------|
| $G_{\mathrm{ex}}$ | Collaborations **observées** (co-projets CORDIS) |
| $G_{\mathrm{th}}$ | Proximité **thématique** (concepts OpenAlex, cosinus) |
| Écarts | Paires fortes en thème mais absentes du graphe explicite → score **π** (`gap_analysis_top.json`) |

## Sources ouvertes

| Source | Accès | Script |
|--------|--------|--------|
| [CORDIS](https://cordis.europa.eu/data) | Export CSV/ZIP H2020 & Horizon Europe | `src/fetch_cordis.py` |
| [OpenAlex](https://api.openalex.org/works) | API (filtre CE : `awards.funder_id:F4320332161`) | `src/fetch_openalex.py` |
| [OpenAIRE](https://api.openaire.eu/graph/v1) | Optionnel | `src/fetch_openaire.py` |

Après chaque run : `data/graphs/data_provenance_report.json` (fichiers sources, tailles, contrôles).

## Structure du dépôt

```text
projet-graphe-recherche-eu/
├── src/                    # Pipeline Python (fetch → graphes → viz)
├── data/
│   ├── raw/                # Bruts (non versionnés ; .gitkeep)
│   ├── processed/          # 8 CSV normalisés (versionnés)
│   └── graphs/             # JSON, HTML, GEXF légers (voir data/README.md)
├── rapport/
│   ├── premium/            # Rapport PDF (main.tex → XeLaTeX)
│   └── presentation/       # Slides HTML + captures
├── context/                # Contexte projet / Gemini CLI
├── OBJECTIFS_PROF.md
└── COMMANDES_GRAPHE.md
```

## Installation

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

Python 3.13+ : si des dépendances lourdes échouent :

```bash
pip install -r requirements-core.txt
```

## Pipeline complet

Depuis la racine du projet :

```bash
source env/bin/activate
python src/run_pipeline.py --max-rows 40000 --max-pages 8
```

Run léger (test) :

```bash
python src/run_pipeline.py --max-rows 20000 --max-pages 5
```

Avec OpenAIRE :

```bash
python src/run_pipeline.py --max-rows 20000 --max-pages 5 --include-openaire
```

## Étapes manuelles (débogage)

```bash
python src/fetch_cordis.py --max-rows 40000
python src/fetch_openalex.py --max-pages 8 --per-page 200
python src/clean_normalize.py
python src/build_graph.py
python src/build_thematic_layer.py --threshold 0.30
python src/gap_analysis.py --min-score 0.40
python src/algorithms.py
python src/temporal_analysis.py
python src/verify_data_sources.py
python src/visualize_folium.py --max-edges 400
```

Paramètres fréquents : `build_thematic_layer.py --threshold` (θ, défaut 0,30), `gap_analysis.py --min-score` (défaut 0,40).

## Livrables principaux (`data/`)

### Tables (`data/processed/`)

- `organizations.csv`, `projects.csv`, `publications.csv`, `concepts.csv`
- `edges_org_project.csv`, `edges_org_org_explicit.csv`, `edges_org_publication.csv`, `edges_org_concept.csv`

### Graphes & métriques (`data/graphs/`)

- `collab_explicit.gexf` (gros fichier — **hors Git**, généré localement)
- `thematic_implicit.gexf`, `metrics_summary.json`, `organization_metrics.json`
- `gap_analysis_top.json`, `dynamic_opportunities.json`, `temporal_summary.csv`

### Interface

Ouvrir **`data/graphs/interactive_suite.html`** en gardant `data/graphs/` comme racine du navigateur :

1. Collaborations par pays  
2. Réseau européen (collaboration + opportunités)  
3. Démo bipartite (ex. CNRS / CEA)

Compléments : `research_network_map_folium.html`, `map_concept_networkx_view.html`, fiches `org_profiles/*.html` (générées localement, non versionnées en masse).

## Rapport et présentation

| Document | Chemin |
|----------|--------|
| Rapport (source LaTeX) | `rapport/premium/main.tex` |
| PDF | `rapport/premium/main.pdf` |
| Compilation | `cd rapport/premium && latexmk -xelatex -interaction=nonstopmode main.tex` |
| Présentation HTML | `rapport/presentation/présentation.html` |

## Données personnalisées

Placer vos fichiers dans :

- `data/raw/cordis/` — `h2020_*`, `he_*` (projets / organisations)
- `data/raw/openalex/works_ec_funded.json`

Puis relancer `clean_normalize.py` ou le pipeline complet.

## Documentation complémentaire

- [`data/README.md`](data/README.md) — cœur data, exclusions Git  
- [`OBJECTIFS_PROF.md`](OBJECTIFS_PROF.md) — cadrage module  
- [`COMMANDES_GRAPHE.md`](COMMANDES_GRAPHE.md) — commandes utiles  
- [`context/GEMINI_CONTEXT.md`](context/GEMINI_CONTEXT.md) — assistance IA (développement ; les métriques π ne sont pas calculées par un LLM)

## Auteur

**Nourane Hammouda** — n° 43017567 · [Dépôt GitHub](https://github.com/nourane-hammouda/OpenEUResearch-Graph)
