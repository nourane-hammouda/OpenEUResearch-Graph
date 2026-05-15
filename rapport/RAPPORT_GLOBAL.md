# Rapport global — Réseau de financement de la recherche européenne

> Document de référence du projet : objectifs, architecture, données, pipeline, graphes, algorithmes, visualisations, résultats clés.

---

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture du projet](#2-architecture-du-projet)
3. [Sources de données](#3-sources-de-données)
4. [Données brutes (`data/raw/`)](#4-données-brutes-dataraw)
5. [Données nettoyées (`data/processed/`)](#5-données-nettoyées-dataprocessed)
6. [Pipeline de traitement (scripts `src/`)](#6-pipeline-de-traitement-scripts-src)
7. [Modèles de graphes construits](#7-modèles-de-graphes-construits)
8. [Algorithmes](#8-algorithmes)
9. [Visualisations & artefacts (`data/graphs/`)](#9-visualisations--artefacts-datagraphs)
10. [Résultats clés (chiffres réels)](#10-résultats-clés-chiffres-réels)
11. [Comment exécuter](#11-comment-exécuter)
12. [Outils & dépendances](#12-outils--dépendances)
13. [Fichiers cœur du projet](#13-fichiers-cœur-du-projet)
14. [Limites et perspectives](#14-limites-et-perspectives)

---

## 1. Vue d'ensemble

### Problématique

Identifier, à partir de données ouvertes, **comment se structure la recherche européenne** :

- Quels sont les acteurs centraux du financement européen (CORDIS / Horizon 2020 / Horizon Europe) ?
- Comment se forment les **réseaux de collaboration** entre institutions ?
- Quels sont les **acteurs relais** (brokers) qui ponctent des communautés thématiques distinctes ?
- Quelles sont les **opportunités de collaboration** non encore exploitées entre organisations ?

### Approche

Modélisation **multi-couches** (multiplex) :

| Couche | Nœuds | Arêtes | Source |
|---|---|---|---|
| Co-participation explicite | Organisations | Co-financement sur mêmes projets | CORDIS H2020 |
| Thématique implicite | Organisations | Similarité de concepts (TF-IDF) | OpenAlex |
| Bipartite financement | Org ↔ Projet | Montant `weight_eur` | CORDIS |
| Bipartite publications | Org ↔ Concept | Score OpenAlex | OpenAlex |

### Livrables principaux

- **Carte interactive principale** (Folium) avec 6 couches activables, panneau de contrôle dynamique, recherche multi-critères
- **Carte des collaborations entre pays** (1 000 paires les plus actives)
- **Démo bipartite interactive** (vis-network + Chart.js) pour deux organisations multi-collaboratrices
- **2 115 fiches HTML d'organisations** avec mini-cartes de partenaires et **opportunités calculées dynamiquement** (TF-IDF multi-critères sur 41 706 organisations)
- **Vue NetworkX/Pyvis** du graphe-concept complet (`map_concept_networkx_view.html`)

---

## 2. Architecture du projet

```
projet-graphe-recherche-eu/
├── data/
│   ├── raw/                  # Téléchargements bruts (CORDIS, OpenAlex)
│   ├── processed/            # 8 CSV normalisés (cf. §5)
│   └── graphs/               # Sorties (cartes HTML, JSON métriques, GEXF)
├── src/                      # 17 scripts Python (cf. §6)
├── rapport/                  # Documentation, journal, ce rapport
├── requirements.txt          # Dépendances complètes
├── requirements-core.txt     # Dépendances minimales pour la viz
└── README.md                 # Démarrage rapide
```

Le pipeline est **strictement linéaire** (sources → nettoyage → graphes → algorithmes → visualisations) et orchestré par `src/run_pipeline.py`.

---

## 3. Sources de données

### 3.1 CORDIS (Horizon 2020 / Horizon Europe)

- **Portail officiel** : https://cordis.europa.eu/data
- **Format** : archives `.zip` contenant des CSV (projets, organisations, fundings, etc.)
- **Couverture** : ~35 000 projets, ~1,1 M de relations org↔projet
- **Champs clés extraits** : `project_id`, `acronym`, `title`, `programme`, `start_date`, `end_date`, `topic`, `total_cost`, `org_pic`, `legal_name`, `country`, `city`, `nuts_code`, `org_role`, `ec_contribution`
- **Récupération** : script `src/fetch_cordis.py` télécharge les `.zip`, extrait les CSV vers `data/raw/cordis/` puis crée des versions allégées `_trimmed.csv`

### 3.2 OpenAlex

- **API** : https://api.openalex.org/works
- **Filtre utilisé** : `awards.funder_id=F4320332161` (Commission Européenne)
- **Volume** : ~200 publications EC-funded (échantillon paginé)
- **Champs clés** : `id`, `doi`, `title`, `publication_year`, `host_venue.display_name`, `concepts[]`, `authorships[].institutions[]`
- **Récupération** : `src/fetch_openalex.py` (pagination cursor, rate-limit respecté)

### 3.3 OpenAIRE (optionnel)

- **API** : https://api.openaire.eu/search/projects
- **Usage** : enrichissement complémentaire pour les programmes hors CORDIS
- **Récupération** : `src/fetch_openaire.py` (uniquement si flag `--include-openaire`)

### 3.4 Audit de provenance

`data/graphs/data_provenance_report.json` consigne pour chaque source :

- URL officielle
- chemins, tailles et dates des dumps locaux
- comptages d'intégrité (n_organizations, n_projects, couverture des arêtes, montants ≥ 0)

---

## 4. Données brutes (`data/raw/`)

| Fichier | Taille | Contenu | Origine |
|---|---:|---|---|
| `cordis/h2020_projects.zip` | 53 Mo | Archive originale CORDIS | Download CORDIS |
| `cordis/h2020_projects_raw.csv` | 75 Mo | Projets H2020 (extraction directe) | dézip de l'archive |
| `cordis/h2020_organizations_raw.csv` | 70 Mo | Organisations H2020 (extraction directe) | embed dans projets ou archive séparée |
| `cordis/h2020_projects_trimmed.csv` | 71 Mo | Projets, colonnes utiles uniquement | `clean_normalize.py` (étape intermédiaire) |
| `cordis/h2020_organizations_trimmed.csv` | 62 Mo | Organisations idem | idem |
| `openalex/works_ec_funded.json` | 18 Mo | Réponses API paginées (works EC) | `fetch_openalex.py` |

Les fichiers `_trimmed.csv` sont conservés car le ré-téléchargement CORDIS est lent (≥ 5 min).

---

## 5. Données nettoyées (`data/processed/`)

8 fichiers CSV produits par `src/clean_normalize.py`. Tous en UTF-8, séparateur virgule.

### 5.1 `organizations.csv` — **41 706 lignes** (5,6 Mo)

Une ligne = une organisation déduite de CORDIS.

| Colonne | Type | Description |
|---|---|---|
| `org_id` | str | Clé primaire `<COUNTRY>_<NORM_NAME>_<sha1[:10]>` (ex. `FR_FR40180089013_ba738b11f3`) |
| `org_name_norm` | str | Nom normalisé (uppercase, sans diacritiques) |
| `org_name` | str | Nom officiel (priorité au `legal_name` CORDIS) |
| `country` | str | Code ISO-2 |
| `city` | str | Ville |
| `org_type` | str | Type juridique (HES, REC, PRC, PUB, OTH…) |
| `budget_total_received` | float | Somme des `ec_contribution` reçus |
| `nb_projects` | int | Nombre de projets distincts |
| `latitude` / `longitude` | float | Géocodage (CORDIS NUTS + heuristiques) |

### 5.2 `projects.csv` — **34 135 lignes** (5,2 Mo)

| Colonne | Description |
|---|---|
| `project_id` | Clé CORDIS (ex. `889026`) |
| `project_title` | Titre officiel ou acronyme si manquant |
| `program` | `h2020_projects_trimmed`, `he_projects_trimmed`… (programme cadre dérivé) |
| `start_date` / `end_date` | Format ISO |
| `topic_label` | Code thématique CORDIS (ex. `EIC-SMEInst-2018-2020`) |
| `project_budget_eur` | Budget total du projet |

### 5.3 `edges_org_project.csv` — **178 558 lignes** (7,7 Mo)

Bipartite financement.

| Colonne | Description |
|---|---|
| `source_org_id` | FK vers `organizations.org_id` |
| `target_project_id` | FK vers `projects.project_id` |
| `weight_eur` | Contribution EC reçue par l'org sur ce projet |

### 5.4 `edges_org_org_explicit.csv` — **1 145 155 lignes** (67 Mo)

**Cœur** du graphe de collaboration. Une ligne = une paire d'organisations ayant participé à au moins 1 projet commun.

| Colonne | Description |
|---|---|
| `org_a`, `org_b` | FKs (paires non ordonnées) |
| `weight_common_projects` | Nombre de projets partagés |

Calculé en faisant le produit cartésien des participants par projet, dédupliqué.

### 5.5 `concepts.csv` — **2 843 lignes** (180 Ko)

| Colonne | Description |
|---|---|
| `publication_id` | URL OpenAlex (`https://openalex.org/W…`) |
| `concept_label` | Concept thématique (ex. `Biology`, `Genome biology`) |
| `concept_score` | Confiance OpenAlex (0–1) |

### 5.6 `edges_org_concept.csv` — **4 725 lignes** (317 Ko)

Bipartite implicite org ↔ concept.

| Colonne | Description |
|---|---|
| `source_org_id` | FK org |
| `concept_label` | concept OpenAlex |
| `weight` | Score moyen sur les publications de l'org |

### 5.7 `publications.csv` — **200 lignes** (36 Ko)

| Colonne | Description |
|---|---|
| `publication_id`, `doi`, `year`, `title`, `journal` | Méta-données OpenAlex |

### 5.8 `edges_org_publication.csv` — **424 lignes** (29 Ko)

Liens institution ↔ publication via `authorships[].institutions[]`.

---

## 6. Pipeline de traitement (scripts `src/`)

### Vue chronologique

```
fetch_cordis.py     ──► data/raw/cordis/*.csv
fetch_openalex.py   ──► data/raw/openalex/works_ec_funded.json
fetch_openaire.py   (optionnel)

         ▼
clean_normalize.py  ──► data/processed/*.csv (8 fichiers)
         ▼
build_graph.py             ──► collab_explicit.gexf
build_thematic_layer.py    ──► thematic_implicit.gexf
gap_analysis.py            ──► gap_analysis_top.json
algorithms.py              ──► organization_metrics.json + metrics_summary.json
temporal_analysis.py       ──► temporal_summary.csv
verify_data_sources.py     ──► data_provenance_report.json
         ▼
visualize_folium.py              ──► research_network_map_folium.html + 2 115 fiches
generate_country_demo_graphs.py  ──► country_collaborations_map.html + demo_multi_project_pair.html
build_map_concept_networkx.py    ──► map_concept_networkx.gexf (intermédiaire)
open_networkx_graph.py           ──► map_concept_networkx_view.html
```

Tout est orchestré par **`src/run_pipeline.py`** :

```bash
python src/run_pipeline.py --max-rows 40000 --max-pages 8
```

### Détail des scripts

#### `fetch_cordis.py`
- Télécharge les archives ZIP H2020/HE depuis cordis.europa.eu
- Dézippe vers `data/raw/cordis/`
- Tronque aux N premières lignes (`--max-rows`) si demandé

#### `fetch_openalex.py`
- Pagination cursor sur `/works?filter=awards.funder_id:F4320332161`
- 200 résultats par page (limite API)
- Sauve un JSON unique `data/raw/openalex/works_ec_funded.json`

#### `fetch_openaire.py`
- API OpenAIRE pour projets
- Optionnel (flag `--include-openaire`)

#### `clean_normalize.py` ★ **fichier clé**
- Hache + normalise les noms d'organisation pour générer `org_id` stable
- Géocode chaque organisation (NUTS CORDIS, fallback `COUNTRY_COORDS`)
- Calcule `budget_total_received`, `nb_projects` par agrégation
- Reconstruit `edges_org_org_explicit` par produit cartésien des participants par projet
- **Filtre** les noms invalides (`UNKNOWN`, `N/A`)
- **Déduplique** par `org_id`

#### `build_graph.py`
- Construit `nx.Graph` à partir de `edges_org_org_explicit.csv`
- Ajoute attributs nœud (`country`, `nb_projects`, `budget_total_received`, `pagerank_collab`…)
- Exporte `collab_explicit.gexf` (lu en aval par `algorithms.py` et `visualize.py`)

#### `build_thematic_layer.py`
- Pour chaque organisation : agrège ses concepts via `edges_org_concept.csv`
- Vectorise (one-hot pondéré par `weight`)
- Calcule **similarité cosinus** entre tous les couples (limité par seuil)
- Construit `thematic_implicit.gexf` (160 nœuds, 2 737 arêtes)

#### `gap_analysis.py`
- Compare la couche explicite et la couche thématique
- Identifie les paires **thematically close mais sans collaboration explicite**
- Score `priority_score = 0.55 × thematic + 0.18 × cross_country + 0.13 × cross_type + 0.14 × size_balance`
- Top-3 000 sauvegardés dans `gap_analysis_top.json`

#### `algorithms.py` ★ **fichier clé**
- Charge `collab_explicit.gexf` + `thematic_implicit.gexf`
- Calcule **6 métriques** par organisation :
  - PageRank (couche collab)
  - PageRank (couche thématique)
  - Betweenness centrality (approximée, k=500)
  - Communauté Louvain (collab)
  - Communauté Louvain (thématique)
  - Contrainte de Burt (sur la couche thématique)
- Sauve `organization_metrics.json` (9,7 Mo, 41 706 lignes) et `metrics_summary.json` (synthèse)

#### `temporal_analysis.py`
- Agrège budget/projets par année à partir de `start_date`
- Sauve `temporal_summary.csv`

#### `verify_data_sources.py`
- Vérifie l'existence et l'intégrité des dumps
- Produit `data_provenance_report.json`

#### `visualize_folium.py` ★ **fichier clé** (104 Ko, 2 400 lignes)
- Construction de la carte interactive principale
- 6 couches Folium activables (organisations, collaborations, opportunités, brokers, heatmap, périmètres pays)
- Panneau dynamique avec :
  - Filtre top-N par PageRank
  - Recherche multi-mode (org, pays, ville, région, type, global)
  - KPIs, top-8 orgs cliquables, top-8 pays cliquables
- **Moteur d'opportunités dynamique** (TF-IDF + multi-critères) sur les 41 706 organisations
- Génération de **2 115 fiches HTML** (top-2 000 PageRank + 115 issues du gap analysis)

#### `generate_country_demo_graphs.py`
- Carte des collaborations entre pays (top 1 000 paires actives)
- Démo bipartite interactive (vis-network + Chart.js)

#### `build_map_concept_networkx.py`
- Construit un NetworkX complet reproduisant le concept de la carte Folium (intermédiaire)

#### `open_networkx_graph.py`
- Lit le `.gexf` et produit une vue Pyvis interactive HTML

---

## 7. Modèles de graphes construits

### 7.1 Couche explicite (co-participation projets)

- **Nœuds** : 41 706 organisations
- **Arêtes** : 1 145 155 collaborations (paires non ordonnées)
- **Pondération** : `weight_common_projects` ∈ ℕ
- **Densité** : ~0,13 % (sparse)
- **Composante connexe principale** : ≥ 95 % des nœuds

### 7.2 Couche thématique implicite

- **Nœuds** : 160 organisations (filtrées sur disponibilité OpenAlex)
- **Arêtes** : 2 737 (similarité cosinus ≥ seuil)
- **Pondération** : score cosinus ∈ [0,1]
- **9 communautés** Louvain détectées

### 7.3 Couche bipartite organisation ↔ projet

- 41 706 + 34 135 nœuds
- 178 558 arêtes pondérées en €

### 7.4 Multiplex (les trois superposés)

Représentation conceptuelle utilisée pour l'analyse de gap et la carte concept NetworkX (pyvis).

---

## 8. Algorithmes

| Algorithme | Sur quelle couche | Bibliothèque | Coût | Sortie |
|---|---|---|---:|---|
| **PageRank** (collab) | Explicite | `networkx.pagerank` | O(E·k) | Score d'influence par org |
| **PageRank** (thématique) | Implicite | idem | O(E·k) | Influence dans la sphère sujet |
| **Louvain** | Explicite + thématique | `python-louvain` | O(N log N) | ID de communauté par org |
| **Betweenness centrality** | Explicite | `nx.betweenness_centrality(k=500)` (approximée) | O(N×k) | Score de pont |
| **Burt constraint** | Thématique | implémentation interne | O(N·d²) | Faible = pont structurel |
| **TF-IDF + cosinus** | corpus titres + topics | `sklearn.feature_extraction.text` | O(N×T) | Similarité thématique |
| **Gap analysis** | combinaison | logique custom | O(P) | Top opportunités |
| **Moteur dynamique d'opportunités** | tous les 41 706 orgs | TF-IDF (1-2-grams, 2 500 features) + scoring multi-critères | ~100 s | Top-10 partenaires par org cible |

### 8.1 Score multi-critères du moteur d'opportunités

Pour chaque organisation cible, on score chaque candidat (non-collaborateur) :

```
priority = 0.55 × thematic       (cosinus TF-IDF sur titres + topics)
         + 0.18 × cross_country  (1.0 si pays différents, 0.4 sinon)
         + 0.13 × cross_type     (1.0 si types différents, 0.5 sinon)
         + 0.14 × size_balance   (ratio min/max des budgets)
```

Le candidat est conservé si sa similarité thématique > 0 et qu'il n'est pas déjà collaborateur.

### 8.2 Détection des acteurs relais (brokers)

Un broker = nœud avec **forte centralité d'intermédiarité** ET **faible contrainte de Burt** (peu de redondance dans son voisinage thématique). Implémenté dans `visualize_folium.py` via un seuil quantile sur la contrainte de Burt × `betweenness_collab > 0`.

---

## 9. Visualisations & artefacts (`data/graphs/`)

### 9.1 Cartes HTML interactives

| Fichier | Taille | Description | Tech |
|---|---:|---|---|
| `research_network_map_folium.html` | 8,1 Mo | **Carte principale** : 6 couches activables (orgs, collabs, opportunités, brokers, heatmap, périmètres), panneau de contrôle dynamique avec recherche & top-listes cliquables, légende fixe | Folium + Leaflet + JS custom |
| `country_collaborations_map.html` | 4,8 Mo | Top 1 000 paires de pays, dégradé de couleur par intensité, panneau overlay avec KPIs et top-8 cliquables | Folium + Leaflet |
| `demo_multi_project_pair.html` | 154 Ko | Démo bipartite **interactive** A ↔ projets ↔ B, 3 charts (programmes / sujets / financement), tableau triable | vis-network 9.1.9 + Chart.js 4.4.1 |
| `map_concept_networkx_view.html` | 2,6 Mo | Vue interactive du graphe-concept complet | Pyvis |
| `org_profiles/*.html` | ~2,5 Mo total | **2 115 fiches d'organisations** : KPIs, projets, partenaires explicites, **top 10 opportunités dynamiques** sur mini-carte Leaflet | HTML/JS custom |

### 9.2 Données graphes (intermédiaires lus par le pipeline)

| Fichier | Taille | Description |
|---|---:|---|
| `collab_explicit.gexf` | 312 Mo | Graphe explicite complet (lu par `algorithms.py`) |
| `thematic_implicit.gexf` | 825 Ko | Graphe thématique (lu par `algorithms.py`, `gap_analysis.py`, `visualize_folium.py`) |

### 9.3 JSON résultats

| Fichier | Taille | Description |
|---|---:|---|
| `organization_metrics.json` | 9,7 Mo | Métriques par organisation (PageRank, Louvain, Burt, Betweenness) — **lu par la viz** |
| `metrics_summary.json` | 3 Ko | Synthèse globale (n_nodes, n_edges, n_communities, top-30 PageRank) |
| `gap_analysis_top.json` | 925 Ko | Top 3 000 opportunités selon l'algo gap (fallback) |
| `dynamic_opportunities.json` | 6,9 Mo | Sortie du moteur dynamique : top-10 par org pour 2 115 orgs profilées |
| `display_filter_report.json` | 494 o | Diagnostic du filtre top-N de la viz |
| `data_provenance_report.json` | 2,8 Ko | Audit des sources et intégrité |

### 9.4 Le moteur d'opportunités dynamique en chiffres

- TF-IDF sur **41 706 corpus** (titres + topics agrégés par organisation)
- 2 500 features max, n-grammes 1-2, sublinear TF
- Couverture : **2 115 / 2 115 orgs** profilées ont ≥ 1 opportunité (100 %)
- Temps de calcul : ~30 s sur MBP M1

---

## 10. Résultats clés (chiffres réels)

### Volumétrie

| Indicateur | Valeur |
|---|---:|
| Organisations distinctes | **41 706** |
| Projets distincts | **34 135** |
| Pays distincts | **165** (incluant non-EU) |
| Liens de collaboration explicites | **1 145 155** |
| Liens financement org↔projet | **178 558** |
| Communautés Louvain (collab) | **4 391** |
| Communautés Louvain (thématique) | **9** |
| Budget cumulé EC (échantillon traité) | ~140 G€ |

### Top 5 organisations par PageRank (couche collab)

| Rang | Org ID | Score |
|---:|---|---:|
| 1 | `DE_DE129515865_…` (Fraunhofer) | 0,00528 |
| 2 | `FR_FR40180089013_…` (CNRS) | 0,00437 |
| 3 | `IT_IT02118311006_…` (CNR Italie) | 0,00338 |
| 4 | `FR_FR43775685019_…` (CEA) | 0,00333 |
| 5 | `ES_ESQ2818002D_…` (CSIC) | 0,00302 |

### Filtre d'affichage de la carte principale

```json
{
  "orgs_before_any_filter": 41706,
  "orgs_after_top_n_filter": 2000,
  "edges_org_org_after": 244799,
  "gaps_after_relaxed_filter": 685,
  "context_only_orgs_added": 110
}
```

→ La carte affiche les **2 000 orgs les plus centrales** + 110 orgs contextuelles (présentes seulement comme cible d'opportunités).

---

## 11. Comment exécuter

### Installation

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
```

### Pipeline complet

```bash
python src/run_pipeline.py --max-rows 40000 --max-pages 8
```

### Exécutions ciblées

```bash
# Régénérer uniquement les visualisations
python -m src.visualize_folium --processed-dir data/processed \
    --graphs-dir data/graphs --max-edges 800 --programme ALL --max-orgs 2000

# Régénérer les démos pays/bipartite
python -m src.generate_country_demo_graphs

# Régénérer la vue NetworkX/Pyvis
python -m src.build_map_concept_networkx
python -m src.open_networkx_graph
```

### Options notables

- `--programme ALL|H2020|HE` : filtre les organisations selon le programme cadre
- `--max-orgs N` : top-N PageRank pour l'affichage (défaut 2 000)
- `--max-edges M` : limite d'arêtes affichées par couche

---

## 12. Outils & dépendances

### Stack Python

| Bibliothèque | Version | Usage |
|---|---|---|
| `pandas` | 2.x | Manipulation tabulaire |
| `numpy` | 1.x | Vectorisation |
| `networkx` | 3.x | Graphes (PageRank, Louvain, Betweenness) |
| `python-louvain` | 0.16 | Détection de communautés |
| `scikit-learn` | 1.8 | TF-IDF, normalisation |
| `folium` | 0.x | Cartes Leaflet via Python |
| `pyvis` | 0.3 | Vue interactive NetworkX |
| `matplotlib` | 3.x | Backups statiques (rarement utilisé) |
| `requests` | 2.x | API OpenAlex / OpenAIRE |

### Stack Web (CDN)

- **Leaflet 1.9.4** — moteur cartographique
- **vis-network 9.1.9** — graphe bipartite interactif (démo)
- **Chart.js 4.4.1** — donut, bar charts (démo)
- **Inter** (Google Fonts) — typographie

---

## 13. Fichiers cœur du projet

### 13.1 Scripts critiques (dans l'ordre de complexité)

1. **`src/visualize_folium.py`** — 104 Ko, 2 400 lignes — la couche présentation et le moteur d'opportunités dynamique. **Le plus gros fichier, le plus stratégique**.
2. **`src/clean_normalize.py`** — 14 Ko — fondation de toutes les données aval (génération `org_id`, dédup, géocodage).
3. **`src/algorithms.py`** — calcul des métriques de centralité.
4. **`src/generate_country_demo_graphs.py`** — 55 Ko — les deux visualisations annexes.
5. **`src/build_thematic_layer.py`** + **`src/gap_analysis.py`** — la chaîne d'analyse thématique.

### 13.2 Données critiques

1. **`data/processed/edges_org_org_explicit.csv`** — 67 Mo, 1,1 M de lignes — **structure du graphe**.
2. **`data/processed/organizations.csv`** — 5,6 Mo — métadonnées de tous les nœuds.
3. **`data/graphs/organization_metrics.json`** — 9,7 Mo — toutes les métriques calculées (entrée de la viz).
4. **`data/graphs/dynamic_opportunities.json`** — 6,9 Mo — recommandations multi-critères.

### 13.3 Sorties utilisateur final

1. **`data/graphs/research_network_map_folium.html`** — la carte principale.
2. **`data/graphs/country_collaborations_map.html`** — carte pays.
3. **`data/graphs/demo_multi_project_pair.html`** — démo bipartite.
4. **`data/graphs/org_profiles/*.html`** — fiches détaillées.

---

## 14. Limites et perspectives

### Limites actuelles

- **Couche thématique réduite** : seulement 160 organisations (limitée par la disponibilité OpenAlex sur ce sous-ensemble)
- **PageRank approximé** sur betweenness (`k=500`) pour des raisons de performance
- **Géocodage** : ~5 % d'organisations sans coordonnées précises (fallback sur centre du pays)
- **Données Horizon Europe** absentes (pipeline préparé mais flux CORDIS HE non encore intégré)
- **`org_type`** parfois manquant pour anciens dumps CORDIS

### Pistes d'amélioration

- **Enrichir la couche thématique** : remplacer OpenAlex concepts par les `topic_label` CORDIS (déjà disponibles pour 100 % des projets)
- **Ajouter une dimension temporelle** : détecter les évolutions de communautés entre 2014–2027
- **Algorithme de recommandation supervisé** : entraîner un modèle sur les collaborations passées pour prédire les futures
- **API REST** : exposer les métriques via FastAPI pour intégration dans un dashboard externe
- **Comparaison HE vs H2020** : identifier les nouveaux entrants et les acteurs en décrue
- **Embedding GNN** (GraphSAGE) sur la couche multiplex pour des opportunités plus fines

---

*Dernière mise à jour : avril 2026 · pipeline v3 (moteur d'opportunités dynamique + visualisations modernes)*
