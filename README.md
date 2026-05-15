# Financement de la recherche europeenne

Pipeline open data pour construire un reseau multi-couches entre organisations, projets et publications europeennes.

## Donnees reelles et provenance

Ce projet utilise des sources publiques reelles:

- CORDIS: `https://cordis.europa.eu/data`
- OpenAlex API: `https://api.openalex.org/works` (filtre CE: `awards.funder_id:F4320332161`)
- OpenAIRE (optionnel): `https://api.openaire.eu/graph/v1`

Apres execution du pipeline, un rapport de provenance est genere:

- `data/graphs/data_provenance_report.json`

Ce rapport inclut:

- les fichiers telecharges et leur taille/date,
- des controles d integrite sur les tables processees,
- des metriques de couverture entre noeuds et aretes.

## Structure

- `data/raw/cordis`: extractions CORDIS (projets + organisations)
- `data/raw/openalex`: publications financees par la Commission europeenne
- `data/raw/openaire`: extraction OpenAIRE (optionnel)
- `data/processed`: tables normalisees
- `data/graphs`: graphes exports (`gexf`, `graphml`, `json`) + rapports

## Installation

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

Si tu es en Python 3.13+ et que certaines dependances lourdes ne compilent pas, utilise:

```bash
pip install -r requirements-core.txt
```

## Execution rapide (pipeline complet)

Depuis `projet-graphe-recherche-eu/`:

```bash
source env/bin/activate
python src/run_pipeline.py --max-rows 20000 --max-pages 5
```

Avec OpenAIRE en plus:

```bash
python src/run_pipeline.py --max-rows 20000 --max-pages 5 --include-openaire
```

## Execution etape par etape

```bash
python src/fetch_cordis.py --max-rows 40000
python src/fetch_openalex.py --max-pages 8 --per-page 200
python src/fetch_openaire.py --size 500
python src/clean_normalize.py
python src/build_graph.py
python src/build_thematic_layer.py --threshold 0.35
python src/gap_analysis.py --min-score 0.5
python src/algorithms.py
python src/temporal_analysis.py
python src/verify_data_sources.py
python src/visualize.py
python src/visualize_folium.py --max-edges 400
```

## Fichiers principaux generes

- `data/processed/organizations.csv`
- `data/processed/projects.csv`
- `data/processed/publications.csv`
- `data/processed/edges_org_project.csv`
- `data/graphs/collab_explicit.gexf`
- `data/graphs/thematic_implicit.gexf`
- `data/graphs/multiplex_full.graphml`
- `data/graphs/gap_analysis.gexf`
- `data/graphs/metrics_summary.json`
- `data/graphs/temporal_summary.csv`
- `data/graphs/data_provenance_report.json`
- `data/graphs/research_network_map_folium.html`
- `data/graphs/org_profiles/*.html` (fiches detaillees par organisation)

## Si tu veux fournir tes propres donnees

Tu peux injecter directement tes fichiers ici:

- CORDIS: `data/raw/cordis/`
  - `h2020_projects_trimmed.csv`
  - `h2020_organizations_trimmed.csv`
  - `he_projects_trimmed.csv`
  - `he_organizations_trimmed.csv`
- OpenAlex: `data/raw/openalex/works_ec_funded.json`

Si tes schemas colonnes sont proches des exports CORDIS/OpenAlex, le pipeline fonctionne sans changement.

## Documents de cadrage et rapport

- Objectifs du cours et correspondance projet: `OBJECTIFS_PROF.md`
- Commandes prêtes a executer: `COMMANDES_GRAPHE.md`
- Contexte IA (Gemini CLI): `context/GEMINI_CONTEXT.md`
- Rapport final (modele): `rapport/rapport_final.md`
- Journal de seances: `rapport/seance_01.md`, `rapport/seance_XX.md`
- Journal quotidien date: `rapport/JOURNAL.md` + `rapport/journal/YYYY-MM-DD.md`
- Inventaire data (nature + volumes): `rapport/inventaire_donnees.md`

## Navigation detaillee (carte -> fiche organisation)

Dans la carte `data/graphs/research_network_map_folium.html`, chaque popup organisation contient un lien
`Voir fiche detaillee` qui ouvre une page dediee:

- `data/graphs/org_profiles/<organisation>.html`

La fiche contient:

- financements recus et nombre de projets,
- liste des projets (top 20),
- collaborations explicites (top 25),
- opportunites de collaboration (top 25),
- statut broker + metriques (PageRank, Betweenness, Burt).
