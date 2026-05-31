# Données — cœur du projet OpenEUResearch-Graph

Ce dossier est le **résultat exploitable** du pipeline : sans `data/`, il n’y a ni graphes, ni cartes, ni rapport chiffré.

## Arborescence

| Chemin | Rôle |
|--------|------|
| `raw/` | Bruts téléchargés (CORDIS, OpenAlex, OpenAIRE optionnel). Régénérable avec `src/fetch_*.py`. |
| `processed/` | **8 CSV** normalisés — schéma relationnel du projet. |
| `graphs/` | GEXF/GraphML, JSON métier, cartes Folium, `interactive_suite.html`, fiches org. |

## Chaîne

```text
raw/  →  clean_normalize.py  →  processed/*.csv
                              →  build_graph.py, build_thematic_layer.py, gap_analysis.py, algorithms.py
                              →  graphs/ (GEXF, JSON, HTML)
```

## Ce qui est versionné sur GitHub (livraison « cœur »)

- `processed/` — les 8 tables CSV
- `graphs/` — JSON, CSV de synthèse, HTML interactifs, petits GEXF (`thematic_implicit.gexf`, etc.)

## Ce qui reste hors dépôt (trop lourd ou régénérable)

| Élément | Ordre de grandeur | Raison |
|---------|-------------------|--------|
| `graphs/collab_explicit.gexf` | ~312 Mo | Limite GitHub **100 Mo / fichier** |
| `graphs/org_profiles/` | ~84k HTML, ~842 Mo | Millions de fichiers, inadapté à Git |
| `graphs/fr_es_profiles/` | ~33 Mo | Sous-ensemble régional optionnel |
| `raw/` (exports complets) | ~350 Mo | Re-téléchargeable via le pipeline |

Pour une copie **complète** en local : exécuter `python src/run_pipeline.py` (voir README racine). Vous pouvez aussi publier une archive `.zip` en **Release GitHub** si l’enseignant exige tous les bruts.

## Fichiers indispensables pour la démo

- `graphs/interactive_suite.html` (ouvrir depuis `data/graphs/`)
- `graphs/gap_analysis_top.json`, `organization_metrics.json`, `metrics_summary.json`
- `processed/organizations.csv`, `edges_org_org_explicit.csv` (analyse tabulaire)
