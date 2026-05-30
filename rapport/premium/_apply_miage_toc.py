#!/usr/bin/env python3
"""Restructure main.tex body to MIAGE harmonisation TOC."""
from pathlib import Path

main = Path(__file__).parent / "main.tex"
text = main.read_text(encoding="utf-8")
start = text.index("% Corps principal")
end = text.index("\\clearpage\n\\section{Bibliographie}")

# Keep all substantive blocks - reorganize headings only + add bridging paragraphs
body = r"""% Corps principal — plan MIAGE (harmonisation table des matières)
\section{Introduction}

\subsection{Contexte}
Les financements européens laissent des traces relationnelles exploitables~: co-participations, montants, rattachements institutionnels et, via des référentiels ouverts, des liens vers publications et concepts thématiques. Les portails \textbf{CORDIS} et \textbf{OpenAlex} rendent une partie de ces signaux \emph{reproductibles}~; le défi est de les normaliser, de les modéliser en graphe et d'en extraire des indicateurs interprétables sans sur-interpréter la causalité.

Du point de vue \textbf{système d'information}, on distingue le fonctionnel métier (qui finance quoi, qui collabore) du fonctionnel analytique (centralités, communautés, priorisation des écarts). Le prototype sépare ces niveaux en artefacts CSV/JSON et pages HTML pour faciliter l'audit.

\begin{defbox}[Graphe de collaboration explicite]
On note $G_{\mathrm{ex}}=(V,E)$ le graphe \textbf{sommets organismes}, avec une arête $\{u,v\}$ dès que $u$ et $v$ co-financent au moins un projet européen commun~; le poids entier compte les projets en commun (\path{edges_org_org_explicit.csv}).
\end{defbox}

\subsection{Problématique}
Deux lectures se complètent~: (i)~la \textbf{collaboration observée} (CORDIS)~; (ii)~la \textbf{proximité thématique} (OpenAlex/concepts). La question centrale~: \emph{qui pourrait collaborer} parmi des acteurs proches scientifiquement mais peu connectés contractuellement, sans transformer l'outil en décision automatique.

\subsection{Objectifs}
\begin{itemize}[nosep]
  \item construire une chaîne \textbf{open data $\rightarrow$ tables $\rightarrow$ graphes $\rightarrow$ métriques $\rightarrow$ visualisations} reproductible~;
  \item comparer $G_{\mathrm{ex}}$ et $G_{\mathrm{th}}$ (cosinus sur concepts)~;
  \item livrer des sorties \textbf{navigables} (\path{interactive_suite.html}, JSON, fiches organisation).
\end{itemize}

\begin{insightbox}
Fil conducteur~: pipeline \textbf{batch} Python, pages HTML statiques (pas de serveur Flask ni de SGBD obligatoire dans le périmètre livré).
\end{insightbox}

\section{Présentation du projet}

\subsection{Contexte général et origine du sujet}
Le travail s'inscrit dans le module \emph{Graphes et Open Data} (Université Paris Nanterre, MIAGE). Le périmètre métier est le \textbf{réseau institutionnel européen} (Horizon~2020, Horizon Europe) décrit par CORDIS, enrichi par des publications OpenAlex filtrées sur le financement Commission européenne. Le dépôt \githubproject{} matérialise une réponse technique complète au cahier des charges du module.

\subsection{Objectifs du projet}
Les objectifs opérationnels rejoignent la problématique de l'introduction~: produire des \textbf{faits relationnels versionnables}, calculer des \textbf{écarts thématiques/explicites}, prioriser des \textbf{pistes} via le score $\pi$, et permettre une \textbf{exploration interactive} sans dépendre d'une stack web lourde.

\subsection{Fonctionnalités principales}
\begin{itemize}[nosep]
  \item ingestion paramétrable (\texttt{--max-rows}, \texttt{--max-pages})~;
  \item huit tables CSV sous \path{data/processed/}, identifiant \texttt{org\_id}~;
  \item graphes \path{collab_explicit.gexf}, \path{thematic_implicit.gexf}~;
  \item métriques (PageRank, Louvain, betweenness échantillonnée, Burt) et \path{gap_analysis_top.json}~;
  \item hub \path{interactive_suite.html}, cartes Folium, démo biparti, vue concepts, \path{org_profiles/}.
\end{itemize}

\subsection{Place du projet dans une démarche MIAGE}
Synthèse \textbf{SI} (provenance, qualité), \textbf{modèle de données} (schéma relationnel plat), \textbf{algorithmique graphe}, \textbf{livrables utilisateur}. Les jeux sont publics~; le pipeline n'a pas vocation au profilage de personnes. Les classements $\pi$ restent des hypothèses à valider par un expert métier.

\section{Environnement de travail et technologies utilisées}

\subsection{Organisation générale de l'environnement}
Développement sur \textbf{macOS/Linux}, Python~3, environnement virtuel (\texttt{python3 -m venv env}). Orchestration par \path{src/run_pipeline.py}. Rédaction du rapport en \textbf{XeLaTeX} (polices TeX Gyre). Les livrables HTML s'ouvrent localement dans un navigateur~; \path{data/graphs/} doit rester la racine relative des iframes.

\subsection{Bibliothèques obligatoires du module}
Le cœur du module \emph{Graphes et Open Data} est couvert par les composants du tableau~\ref{tab:libs-core}.

\begin{table}[htbp]
\centering
\small
\caption{Bibliothèques au cœur du module (graphes et données).}
\label{tab:libs-core}
\begin{tabularx}{\textwidth}{@{}p{2.6cm} X@{}}
\toprule
\textbf{Composant} & \textbf{Rôle dans le projet} \\
\midrule
pandas / NumPy & ETL CSV/JSON, matrices creuses org$\times$concept. \\
NetworkX & GEXF, PageRank, betweenness, Burt, Louvain \cite{hagberg2008,blondel2008}. \\
requests / httpx & Téléchargement CORDIS et API OpenAlex. \\
\bottomrule
\end{tabularx}
\end{table}

\subsection{Technologies complémentaires ajoutées au projet}
\begin{table}[htbp]
\centering
\small
\caption{Technologies complémentaires (visualisation et extensions).}
\label{tab:libs-extra}
\begin{tabularx}{\textwidth}{@{}p{2.6cm} X@{}}
\toprule
\textbf{Composant} & \textbf{Rôle} \\
\midrule
Folium / Leaflet & Cartes européennes et macro pays. \\
Pyvis & Démo biparti et vue concepts (\path{map_concept_networkx_view.html}). \\
scikit-learn & TF-IDF (\path{dynamic_opportunities.json}). \\
\midrule
\multicolumn{2}{@{}l}{\footnotesize Optionnel dans \path{requirements.txt}~: \texttt{sentence-transformers}, \texttt{torch}, \texttt{faiss}, \texttt{leidenalg} (non requis au flux minimal).} \\
\bottomrule
\end{tabularx}
\end{table}

\paragraph{Assistance IA.}
\textbf{Gemini CLI} (\path{context/GEMINI_CONTEXT.md}) a aidé au développement et à la documentation. \textbf{Aucun LLM ne calcule} $\pi$, le cosinus ni les centralités.

\subsection{Structure fonctionnelle de l'application}
Le prototype suit une architecture \textbf{ETL batch} (figure~\ref{fig:chaine})~: pas d'application Flask ni de base PostgreSQL dans la livraison~; la «~structure applicative~» est la chaîne de scripts et les artefacts qu'elle régénère.

\begin{figure}[htbp]
\centering
\begin{tikzpicture}[
  node distance=0.85cm and 1.05cm,
  st/.style={draw=accent!55, rounded corners=6pt, minimum height=1.05cm, minimum width=2.75cm,
    align=center, font=\footnotesize\sffamily, fill=white, thick},
  src/.style={st, fill=accentsoft},
  arr/.style={-{Stealth}, thick, draw=accent!70},
]
  \node[src] (s) {Sources\\\scriptsize CORDIS · OpenAlex};
  \node[st, right=of s] (n) {Normalisation\\\scriptsize 8 CSV};
  \node[st, right=of n] (g) {Graphes\\\scriptsize GEXF / JSON};
  \node[src, right=of g] (v) {Vues HTML\\\scriptsize Folium};
  \draw[arr] (s) -- (n); \draw[arr] (n) -- (g); \draw[arr] (g) -- (v);
\end{tikzpicture}
\caption{Chaîne fonctionnelle (batch + livrables HTML).}
\label{fig:chaine}
\end{figure}

\subsection{Parcours utilisateur détaillé}
\begin{enumerate}[nosep,label=\textbf{\arabic*.}]
  \item Exécuter \path{run_pipeline.py} (ou les scripts étape par étape).
  \item Consulter \path{data/graphs/data_provenance_report.json} et les CSV \path{processed/}.
  \item Ouvrir \path{interactive_suite.html} depuis \path{data/graphs/}.
  \item Onglet \textbf{pays}~: asymétries transnationales.
  \item Onglet \textbf{réseau}~: zoom, filtres, couches collaboration / opportunités.
  \item Popup Folium $\rightarrow$ fiche \path{org_profiles/} si disponible.
  \item Onglet \textbf{biparti}~: cas CNRS/CEA (vis-network).
  \item Optionnel~: \path{map_concept_networkx_view.html} (concepts).
\end{enumerate}

\subsection{Organisation des fichiers et logique modulaire}
Le dépôt sépare \texttt{src/}, \texttt{data/raw}, \texttt{data/processed}, \texttt{data/graphs}. Chaque script est relançable isolément. Le tableau~\ref{tab:pipeline} résume l'ordonnancement~; \path{data_provenance_report.json} consolide la traçabilité.

\begin{table}[htbp]
\centering
\small
\caption{Ordonnancement des scripts (\texttt{src/}).}
\label{tab:pipeline}
\begin{tabularx}{\textwidth}{@{}p{2.35cm} X p{3.5cm}@{}}
\toprule
\textbf{Phase} & \textbf{Script} & \textbf{Artefacts} \\
\midrule
Acquisition & \path{fetch_cordis.py}, \path{fetch_openalex.py} & brut CORDIS, JSON OpenAlex \\
Normalisation & \path{clean_normalize.py} & 8 CSV \\
Multiplexe & \path{build_graph.py} & \path{collab_explicit.gexf} \\
Thème & \path{build_thematic_layer.py} & \path{thematic_implicit.gexf} \\
Écarts & \path{gap_analysis.py} & \path{gap_analysis_top.json} \\
Algos & \path{algorithms.py} & \path{organization_metrics.json} \\
Contrôles & \path{verify_data_sources.py}, \path{temporal_analysis.py} & provenance, temporel \\
Viz & \path{visualize_folium.py} & Folium, \path{interactive_suite.html} \\
Explor. & \path{build_map_concept_networkx.py} & \path{map_concept_networkx_view.html} \\
\bottomrule
\end{tabularx}
\end{table}

\section{Conception du projet}

\subsection{Architecture générale}
Schéma ETL~: sources ouvertes $\rightarrow$ schéma relationnel plat $\rightarrow$ graphes multiplexes $\rightarrow$ métriques $\rightarrow$ HTML. Les calculs lourds restent batch~; le navigateur ne fait qu'interpréter des fichiers pré-calculés.

\subsection{Conception des données}
"""

# Read middle chunks from original for tables we need - append from file
mid_start = text.index("\\subsection{Modèle de données relationnel}")
mid_end = text.index("\\section{Implémentation}")
body += text[mid_start:mid_end]

body += r"""
\subsection{Conception du modèle de graphe}
"""

graph_start = text.index("\\subsection{Modèle de graphe}")
graph_end = text.index("\\subsection{Architecture applicative}")
body += text[graph_start:graph_end]

body += r"""
\paragraph{Cadrage théorique.}
Le projet mobilise les réseaux complexes~\cite{newman2010}~: PageRank et betweenness sur $G_{\mathrm{ex}}$, Louvain~\cite{blondel2008}, Burt sur $G_{\mathrm{th}}$, lecture multiplexe~\cite{fortunato2010}.

\subsection{Conception de l'interface utilisateur}
"""

iface_start = text.index("\\subsection{Interfaces interactives")
iface_end = text.index("\\section{Tests et validation}")
# exclude implementation-only parts before interfaces - take from Interfaces
iface_start2 = text.index("\\subsection{Interfaces interactives")
body += text[iface_start2:iface_end]

body += r"""
\subsection{Scénarios d'usage retenus}
\begin{itemize}[nosep]
  \item \textbf{Analyste open data}~: vérifier volumes, provenance, cohérence des jointures.
  \item \textbf{Chargé de veille scientifique}~: parcourir le top $\pi$ et confronter à des stratégies d'établissement.
  \item \textbf{Soutenance / démonstration}~: suite interactive, cas biparti, lecture macro pays.
  \item \textbf{Reproductibilité}~: relancer le pipeline avec \texttt{--max-rows} réduit puis run complet.
\end{itemize}

\subsection{Présentation détaillée des écrans principaux}\label{sec:demo}
"""

demo_start = text.index("\\section{Démonstration graphique")
demo_end = text.index("\\section{Limites techniques")
body += text[demo_start:demo_end].replace(
    "\\section{Démonstration graphique (captures d'écran)}\\label{sec:demo}",
    ""
).replace("\\subsection{Protocole et conditions d'observation}", "\\paragraph{Protocole.}")

body += r"""
\subsection{Manuel d'utilisation synthétique}
\begin{enumerate}[nosep]
  \item \texttt{source env/bin/activate}
  \item \texttt{python src/run_pipeline.py --max-rows 40000 --max-pages 8}
  \item Ouvrir \path{data/graphs/interactive_suite.html} (dossier \path{graphs/} comme racine).
  \item Naviguer les onglets pays / réseau / biparti~; activer les couches sur la carte réseau.
  \item Exporter ou relire \path{gap_analysis_top.json} pour une liste priorisée hors navigateur.
\end{enumerate}

\subsection{Conception du stockage et persistance des artefacts}
Le projet \textbf{ne mobilise pas PostgreSQL} dans la livraison~: la persistance repose sur CSV (\path{processed/}), GEXF/GraphML (\path{graphs/}), JSON métier et HTML statiques. Cette conception facilite le versionnement Git, l'audit et la reprise sur incident, au prix d'absence de requêtage SQL temps réel.

\section{Implémentation et réalisation}

\subsection{Traitement et nettoyage des données}
"""

impl_start = text.index("\\subsection{Traitement et acquisition}")
impl_mid = text.index("\\subsection{Graphes et couche thématique}")
body += text[impl_start:impl_mid]

body += r"""
\subsection{Développement du pipeline Python orchestré}
\path{run_pipeline.py} enchaîne fetch, normalisation, graphes, écarts, métriques, contrôles et visualisation. \path{build_graph.py} matérialise le multiplexe et la projection $G_{\mathrm{ex}}$. Chaque étape reste exécutable seule pour le débogage.

\subsection{Visualisation cartographique avec Folium}
\path{visualize_folium.py} génère \path{research_network_map_folium.html}, \path{country_collaborations_map.html}, alimente \path{dynamic_opportunities.json} (TF-IDF) et régénère \path{interactive_suite.html}. Les filtres \texttt{--max-edges} préservent la fluidité du DOM.

\subsection{Calculs de métriques et priorisation des écarts}
"""

algo_start = text.index("\\subsection{Graphes et couche thématique}")
json_end = text.index("\\subsection{Interfaces interactives")
body += text[algo_start:json_end]

body += r"""
\subsection{Approche détaillée de l'enrichissement OpenAlex}
Les publications filtrées (financeur CE) sont appariées aux organisations CORDIS par nom normalisé. Les concepts et scores alimentent \path{edges_org_concept.csv}, puis la matrice creuse et le cosinus dans \path{build_thematic_layer.py}. La couverture reste partielle (200 œuvres sur l'exemplaire).

\subsection{Acquisition des jeux ouverts (API et téléchargements)}
\path{fetch_cordis.py} et \path{fetch_openalex.py} constituent la porte d'entrée (voir aussi \S\ref{sec:formules} pour les formules). OpenAIRE reste optionnel. Les paramètres \texttt{--max-rows} et \texttt{--max-pages} bornent les runs de développement.

\subsection{Exports graphes, JSON et vues complémentaires}
\path{algorithms.py} écrit les centralités et communautés. \path{build_map_concept_networkx.py} produit la vue concepts. Les principaux JSON sont listés tableau~\ref{tab:json}.

"""

json_start = text.index("\\subsection{Exports JSON métier}")
json_end2 = text.index("\\subsection{Interfaces interactives")
body += text[json_start:json_end2]

body += r"""
\section{Tests, validations et gestion des régressions}

\subsection{Logique générale de validation}
Pas de batterie PyTest systématique~: validation par \textbf{rejouabilité} du pipeline, contrôles de structure et recette manuelle des HTML.

\subsection{Tests sur les données}
"""

tests_start = text.index("\\subsection{Validation fonctionnelle}")
tests_mid = text.index("\\begin{table}[htbp]\n\\centering\n\\small\n\\caption{Contrôles rapides")
body += text[tests_start:tests_mid]

body += r"""
\subsection{Tests sur l'interface}
"""

tests_scen = text.index("\\subsection{Scénarios de recette manuelle}")
tests_end = text.index("\\section{Résultats et analyse quantitative}")
body += text[tests_scen:tests_end]

body += r"""
\subsection{Performance et stabilité}
"""

perf_start = text.index("\\subsection{Stabilité et performances}")
perf_end = text.index("\\subsection{Scénarios de recette manuelle}")
body += text[perf_start:perf_end]

body += r"""
\subsection{Tableau de validation fonctionnelle}
"""

body += text[tests_mid:tests_scen]

body += r"""
\section{Résultats obtenus}

\subsection{Un prototype complet d'analyse de réseaux européens}
"""

res_start = text.index("\\subsection{Synthèse indicative}")
res_mid = text.index("\\subsection{Lecture analytique}")
res_end = text.index("\\section{Démonstration graphique")
body += text[res_start:res_mid]

body += r"""
\subsection{Apports techniques}
Le dépôt démontre une chaîne industrielle plausible open data $\rightarrow$ graphes $\rightarrow$ métriques $\rightarrow$ HTML, avec séparation faits relationnels / couche de communication (audit, reprise).

\subsection{Bilan de la progression}
Le projet est passé d'une ingestion tabulaire à un multiplexe exploitable, puis à des vues interactives intégrées dans \path{interactive_suite.html}, en gardant un fil conducteur~: les opportunités de collaboration comme hypothèses, non comme décisions.

\subsection{Lecture analytique des résultats}
"""

body += text[res_mid:text.index("\\subsection{Interprétation pour l'analyste}")]

body += r"""
\subsection{Apport pour l'aide à la décision}
"""

body += text[text.index("\\subsection{Interprétation pour l'analyste}"):text.index("\\subsection{Apports pour le SI}")]

body += text[text.index("\\subsection{Apports pour le SI}"):res_end]

body += r"""
\section{Difficultés rencontrées et limites du projet}

\subsection{Difficultés liées aux données}
Hétérogénéité CORDIS, identifiants lacunaires, appariement lexical OpenAlex (homonymies). Montants agrégés indicatifs. Volume \path{edges_org_org_explicit.csv} (67\,Mo) contraignant en RAM.

\subsection{Difficultés liées à l'acquisition et à l'échelle}
Téléchargements CORDIS volumineux, pagination OpenAlex, temps de calcul de la betweenness et du rendu Folium sur graphes denses.

\subsection{Limites de la modélisation par graphe}
Cosinus thématique $\neq$ complémentarité métier. $\theta$ et \texttt{min-score} orientent l'espace exploré. Similarité $\neq$ collaboration garantie.

\subsection{Difficultés d'intégration entre les briques techniques}
Multiples formats (CSV, GEXF, JSON, HTML), chemins relatifs des iframes, synchronisation des paramètres de filtrage entre scripts et cartes.

\subsection{Limites techniques et statut du prototype}
Prototype de recherche/formation~: pas de SLA, pas de multi-utilisateurs, pas de moteur de recherche full-text sur les fiches. Les dépendances lourdes (torch, etc.) restent optionnelles.

\section{Perspectives d'amélioration}

\subsection{Amélioration de la qualité des données}
Identifiants ROR/PIC systématiques, enrichissement OpenAIRE, data card et journal de qualité par run.

\subsection{Amélioration des modèles et des paramètres}
Analyse de sensibilité sur $\theta$, $s_{\min}$ et les pondérations $\pi$~; validation avec experts métier~; complémentarité au-delà du cosinus.

\subsection{Amélioration technique et ergonomique}
API lecture seule sur JSON, intégration de la vue concepts dans le hub, tests utilisateurs, Leiden pour comparer les partitions.

\subsection{Mise en production et cadre juridique}
Hébergement statique des HTML, documentation RGPD renforcée, gouvernance des mises à jour CORDIS/OpenAlex.

\section{Conclusion}
"""

conc_start = text.index("\\section{Conclusion}")
conc_end = text.index("\\clearpage\n\\section{Bibliographie}")
body += text[conc_start:conc_end]

# Fix conclusion reference to captures - now in section 4.6
body = body.replace(
    "Les captures de la section précédente rappellent",
    "Les captures de la section~\ref{sec:demo} rappellent",
)

new_text = text[:start] + body + text[end:]

# Update annex numbering to match template 12.x
new_text = new_text.replace(
    "\\section*{Annexes (version condensée)}",
    "\\section{Annexes}",
)
new_text = new_text.replace("\\subsection*{A.", "\\subsection{Journal d'activité synthétique}")
new_text = new_text.replace(
    "Chaîne reproductible CORDIS/OpenAlex",
    "\\subsection{Flux technique simplifié}\nChaîne reproductible CORDIS/OpenAlex",
)
# Fix botched replace - read annex and fix manually
new_text = new_text.replace(
    "\\subsection{Journal d'activité synthétique} Synthèse des exigences de livraison}",
    "\\subsection{Journal d'activité synthétique}\nSynthèse des exigences de livraison.",
)
new_text = new_text.replace("\\subsection*{B.", "\\subsection{Annexe technique : commandes locales utiles}")
new_text = new_text.replace("\\subsection*{C.", "\\subsection{Ouverture des vues interactives}")
new_text = new_text.replace("\\subsection*{D.", "\\subsection{Paramètres fréquemment ajustés}")
new_text = new_text.replace("\\subsection*{E.", "\\subsection{Index des figures et tables}")
new_text = new_text.replace("\\subsection*{F.", "\\subsection{Arborescence du dépôt}")

# Remove duplicate Bibliographie numbering issue - addcontentsline for annex
if "\\addcontentsline{toc}{section}{Annexes}" not in new_text:
    new_text = new_text.replace(
        "\\section{Annexes}",
        "\\section{Annexes}\n\\addcontentsline{toc}{section}{Annexes}",
    )

# Update annex E reference
new_text = new_text.replace(
    "tab:libs}",
    "tab:libs-core}",
).replace("tab:libs-core}, tab:json", "tab:libs-core}, \\ref{tab:libs-extra}, \\ref{tab:json}")

main.write_text(new_text, encoding="utf-8")
print("Restructured", main)
