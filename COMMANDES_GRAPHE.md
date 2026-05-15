# Commandes utiles pour generer et afficher les graphes

## 1) Preparation environnement

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements-core.txt
```

## 2) Pipeline complet

```bash
source env/bin/activate
python src/run_pipeline.py --max-rows 1000 --max-pages 1
```

## 3) Pipeline etape par etape

```bash
python src/fetch_cordis.py --max-rows 1000
python src/fetch_openalex.py --max-pages 1 --per-page 200
python src/clean_normalize.py
python src/build_graph.py
python src/build_thematic_layer.py --threshold 0.35
python src/gap_analysis.py --min-score 0.5
python src/algorithms.py
python src/temporal_analysis.py
python src/verify_data_sources.py
python src/visualize.py
python src/visualize_folium.py --max-edges 300
```

## 4) Sorties principales

- Graphes exportables Gephi:
  - `data/graphs/collab_explicit.gexf`
  - `data/graphs/thematic_implicit.gexf`
  - `data/graphs/gap_analysis.gexf`
- Cartes interactives:
  - `data/graphs/research_network_map_folium.html`

## 5) Ouvrir rapidement les cartes (macOS)

```bash
open data/graphs/research_network_map_folium.html
```
