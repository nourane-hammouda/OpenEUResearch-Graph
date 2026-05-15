# Cadrage projet selon objectifs du cours

Ce document mappe explicitement le projet avec les exigences du professeur.

## 1) Recuperer les donnees (open data + API)

Sources en place:

- CORDIS (`src/fetch_cordis.py`)
- OpenAlex (`src/fetch_openalex.py`)
- OpenAIRE optionnel (`src/fetch_openaire.py`)

Sorties:

- `data/raw/cordis/*`
- `data/raw/openalex/*`
- `data/raw/openaire/*`

## 2) Traiter et normaliser

Pipeline:

- `src/clean_normalize.py` (nettoyage, harmonisation, dedup de noms)
- `src/verify_data_sources.py` (controle de provenance et integrite)

Sorties:

- `data/processed/organizations.csv`
- `data/processed/projects.csv`
- `data/processed/publications.csv`
- `data/processed/edges_*.csv`

## 3) Problematique graphe non triviale

Problematique retenue:

- comparer le reseau de collaborations explicites (financement/co-participation)
- au reseau de proximite thematique implicite
- pour detecter les opportunites de collaboration non exploitees (gap analysis)

## 4) Construire et analyser un ou plusieurs graphes

Construction:

- `src/build_graph.py` (graphe explicite)
- `src/build_thematic_layer.py` (graphe implicite)

Analyse:

- `src/algorithms.py` (PageRank, Louvain, betweenness, Burt)
- `src/gap_analysis.py` (aretes thematiques fortes sans collab explicite)
- `src/temporal_analysis.py` (snapshots temporels)

## 5) Visualiser / exporter

Exports Gephi/GraphML/JSON:

- `data/graphs/collab_explicit.gexf`
- `data/graphs/thematic_implicit.gexf`
- `data/graphs/multiplex_full.graphml`

Visualisations:

- `src/visualize.py` (vue statique)
- `src/visualize_folium.py` (cartes interactives)

## 6) Environnement technique

Conforme:

- Python 3 + virtualenv (`env/`)
- `requirements.txt` et `requirements-core.txt`
- dossier `data/` complet
- dossier `context/` pour contexte IA
- dossier `rapport/` pour comptes rendus par seance

## 7) Livrables rapport

Modele de rapport:

- `rapport/rapport_final.md`
- `rapport/seance_XX.md`

Contenu attendu:

- contexte + problematique
- sources + liens
- methodologie de nettoyage
- modelisation graphe
- algorithmes + resultats
- captures/exports graphes
- limites et perspectives
