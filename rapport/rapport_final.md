# Rapport final — Financement de la recherche europeenne

## 1. Contexte et problematique

Ce projet applique la theorie des graphes a des donnees open data de financement europeen.
L objectif est de comparer:

- le reseau explicite de collaborations (co-participation a des projets),
- et le reseau implicite de proximite thematique (similarite conceptuelle).

Question principale:

- Quelles organisations sont scientifiquement proches mais structurellement deconnectees?

## 2. Sources de donnees (liens)

- CORDIS: <https://cordis.europa.eu/data>
- OpenAlex: <https://api.openalex.org/works>
- OpenAIRE (optionnel): <https://api.openaire.eu/graph/v1>

Fichiers de provenance:

- `data/graphs/data_provenance_report.json`
- `rapport/inventaire_donnees.md`

### 2.1 Nature des donnees

- **CORDIS**: metadonnees projets et participants (financement, role, pays, geolocalisation, programme).
- **OpenAlex**: metadonnees publications (titre, DOI, annee, institutions, concepts/topics).
- **Donnees traitees**: tables normalisees de noeuds (`organizations`, `projects`, `publications`) et aretes (`edges_*`).

### 2.2 Volumetrie (etat courant)

- Brut principal CORDIS: `h2020_projects_raw.csv` ~69.6 MB, 178 783 lignes.
- Brut OpenAlex: `works_ec_funded.json` ~18.0 MB, 200 objets.
- Table la plus dense traitee: `edges_org_org_explicit.csv` 13 382 lignes.
- Artefacts graphe majeurs:
  - `collab_explicit.gexf` ~3.63 MB
  - `multiplex_full.graphml` ~2.91 MB

## 3. Environnement et dependances

- Python 3 + virtualenv (`env/`)
- librairies: `networkx`, `pandas`, `matplotlib`, `folium`, etc.
- dependances: `requirements.txt` et `requirements-core.txt`

## 4. Pipeline de traitement

1. Collecte (`src/fetch_*.py`)
2. Nettoyage/normalisation (`src/clean_normalize.py`)
3. Construction graphes (`src/build_graph.py`, `src/build_thematic_layer.py`)
4. Analyse (`src/algorithms.py`, `src/gap_analysis.py`, `src/temporal_analysis.py`)
5. Visualisation (`src/visualize.py`, `src/visualize_folium.py`)

## 5. Modele de graphe

- Noeuds: organisations, projets, publications
- Aretes explicites: organisation-projet, organisation-organisation
- Aretes implicites: organisation-organisation thematique

## 6. Resultats (echantillon courant)

- Organisations: 851
- Projets: 72
- Aretes explicites org-org: 13 382
- Aretes thematiques: 10
- Communautes explicites: 35
- Communautes thematiques: 3

## 7. Visualisations et exports

Graphes:

- `data/graphs/collab_explicit.gexf`
- `data/graphs/thematic_implicit.gexf`
- `data/graphs/gap_analysis.gexf`

Cartes:

- `data/graphs/research_network_map_folium.html`

## 8. Limites

- Disponibilite variable des endpoints CORDIS selon programme/fichier.
- Couverture publications dependante des filtres OpenAlex.
- Geolocalisation fine incomplete pour certaines organisations.

## 9. Perspectives

- Integrer HE complet + FP7 pour comparaisons temporelles robustes.
- Ajouter correlation financement vs productivite (publications/brevets).
- Ajouter alignement thematique EuroSciVoc / OpenAlex topics.

## 10. Annexes

- Commandes: `COMMANDES_GRAPHE.md`
- Cadrage objectifs: `OBJECTIFS_PROF.md`
- Contexte IA: `context/GEMINI_CONTEXT.md`
- Notes par seance: `rapport/seance_01.md`, `rapport/seance_XX.md`
