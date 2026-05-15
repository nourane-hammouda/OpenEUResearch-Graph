# Contexte Gemini CLI / IA generative

Ce fichier sert de contexte de travail pour une IA generative (Gemini CLI ou autre assistant).

## Contexte du cours

Ce cours porte sur la realisation d un projet complet manipulant diverses notions de theorie des graphes.
Les donnees proviennent de depots open data. Elles doivent etre recuperees, nettoyees, normalisees, puis
transformees en un ou plusieurs graphes. Des algorithmes de theorie des graphes sont ensuite appliques
pour resoudre un probleme non trivial, avec visualisation finale (Gephi, Graphviz, cartes web).

## Projet cible

Theme:

- financement de la recherche europeenne
- reseau explicite de collaborations vs proximite thematique implicite

Objectif:

- identifier des opportunites de collaboration non exploitees

## Contraintes de reponse pour l IA

- Repondre en francais.
- Etre direct, technique, sans marketing.
- Proposer des commandes executables.
- Justifier les choix d algorithmes.
- Signaler les limites des donnees et les biais.
- Ajouter des commentaires de code en anglais uniquement si necessaire.

## Commandes de base a connaitre

```bash
source env/bin/activate
python src/run_pipeline.py --max-rows 20000 --max-pages 5
python src/visualize_folium.py --max-edges 400
```

## Fichiers pivots du projet

- `src/fetch_cordis.py`
- `src/fetch_openalex.py`
- `src/clean_normalize.py`
- `src/build_graph.py`
- `src/algorithms.py`
- `src/gap_analysis.py`
- `src/visualize_folium.py`
- `data/graphs/data_provenance_report.json`
