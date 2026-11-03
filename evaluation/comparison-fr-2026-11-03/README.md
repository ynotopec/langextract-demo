# Comparatif français : prompt direct et LangExtract

Étude contrôlée du 3 novembre 2026. **40 PDF entièrement en français, 44 pages,
158 occurrences de référence, 240 traitements** (40 documents × 3 stratégies ×
2 exécutions). Tous les appels ont été réalisés sur le même endpoint authentifié :
`https://api-llm-custom.ailab.infocepo.com/v1`, alias `ai-flash`.

## Décision et portée

Écart F1 LangExtract une passe / prompt direct : +0.00 points. Aucune différence globale de F1 n’est observée entre ces deux méthodes.

F1 arrondis (direct, une passe, deux passes) : 97.8 %, 97.8 %, 97.8 %. Deux passes
augmentent le F1 de seulement 0.014 point par rapport au direct,
avec 2.27 fois les tokens.
Cette différence minime ne justifie pas à elle seule deux passes. À une passe,
le volume de tokens augmente de 13.6 %.
La stabilité descriptive est de 34/40 documents pour le direct,
38/40 pour LangExtract une passe et
40/40 à deux passes. Sur les quatre documents longs,
LangExtract une passe retrouve 40/40 occurrences cumulées
contre 39/40 pour le direct.
Ce sont des indices d'intérêt opérationnel à confirmer, sans test de significativité.

Le résultat mesure cette configuration locale de LangExtract 1.7.1 et ce modèle,
pas toutes les possibilités du framework ni le frontend déployé. Les documents
sont synthétiques et rédigés pour cette étude, sans annotation humaine indépendante.
Ils sont plus nombreux et diversifiés que le pilote précédent, mais ne constituent
pas un échantillon représentatif d’une administration.

## Résultats de qualité

| Mesure | Prompt direct | LangExtract 1 passe | LangExtract 2 passes |
| --- | --- | --- | --- |
| Précision | 98.7 % | 98.7 % | 98.1 % |
| Rappel | 96.8 % | 96.8 % | 97.5 % |
| F1 micro | 97.8 % | 97.8 % | 97.8 % |
| Succès / traitements | 80/80 | 80/80 | 80/80 |
| TP / FP / FN | 306/4/10 | 306/4/10 | 308/6/8 |

Chaque stratégie est évaluée sur 316 occurrences attendues (158 × 2). Les 4 négatifs
sont inclus dans les faux positifs et les temps, mais n’ajoutent aucun vrai positif.
Un échec de traitement compte toutes les occurrences de référence comme manquantes.
Il n’y a pas de suppression silencieuse des cas échoués.

## Ressources mesurées

| Mesure | Prompt direct | LangExtract 1 passe | LangExtract 2 passes |
| --- | --- | --- | --- |
| Temps médian | 1.28 s | 1.28 s | 2.53 s |
| Temps moyen | 1.55 s | 1.53 s | 3.10 s |
| Appels HTTP LLM | 80 | 96 | 192 |
| Tokens entrée | 45 998 | 53 318 | 106 636 |
| Tokens sortie | 9 402 | 9 614 | 19 329 |
| Tokens totaux | 55 400 | 62 932 | 125 965 |
| Multiplicateur tokens | 1.00 x | 1.14 x | 2.27 x |

Les tokens sont ceux renvoyés dans `usage` par le serveur. Données de consommation
complètes pour tous les appels : **True**.
Il s’agit d’un indicateur de volume, pas d’un prix en euros ni d’une mesure d’énergie.
Caches, facturation, débit GPU et temps humain de validation ne sont pas mesurés.
Les temps couvrent l’extraction depuis le texte déjà lu, y compris parsing et
alignement, sans upload HTTP de PDF ni rendu/export HTML. Ils ne sont pas directement
comparables aux durées end-to-end du pilote via FastAPI.

## Qualité par classe - précision / rappel

| Classe - P / R | Prompt direct | LangExtract 1 passe | LangExtract 2 passes |
| --- | --- | --- | --- |
| Montant (amount) | 100.0 % / 97.8 % | 100.0 % / 97.8 % | 100.0 % / 100.0 % |
| Date (date) | 100.0 % / 100.0 % | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| E-mail (email) | 100.0 % / 100.0 % | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| Facture (invoice) | 100.0 % / 100.0 % | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| Organisation (org) | 95.4 % / 94.3 % | 95.5 % / 96.6 % | 93.5 % / 97.7 % |
| Personne (person) | 100.0 % / 94.1 % | 100.0 % / 94.1 % | 100.0 % / 88.2 % |
| Référence (ref) | 100.0 % / 96.9 % | 100.0 % / 93.8 % | 100.0 % / 96.9 % |

## Répétabilité, contrôles et localisation

| Contrôle | Prompt direct | LangExtract 1 passe | LangExtract 2 passes |
| --- | --- | --- | --- |
| Entités identiques A/B | 34/40 | 38/40 | 40/40 |
| Négatifs sans entité | 8/8 | 8/8 | 8/8 |
| Offsets valides | 310/310 | 310/310 | 314/314 |
| Extraits dans la source | 310/310 | 310/310 | 314/314 |

Deux sorties sont dites identiques si leur multiensemble (classe, extrait complet,
multiplicité) est identique. Les attributs et positions ne font pas partie de cette
mesure de stabilité. Les offsets sont vérifiés contre le texte après normalisation
des espaces et Unicode NFC ; ce contrôle ne valide pas l’identité de l’occurrence
de référence lorsque le même texte apparaît plusieurs fois.

Le prompt direct reçoit un alignement déterministe par recherche textuelle, tolérant
les espaces et sans réutiliser la même occurrence. LangExtract emploie son propre
alignement. Ainsi, la présence de positions dans la réponse n’est pas réservée au
framework par construction. Le contrôle « extrait dans la source » reste distinct
de l’exactitude métier d’un nom complet ou de sa classe.

## Sous-ensemble long : quatre PDF de deux pages

| Documents longs | Prompt direct | LangExtract 1 passe | LangExtract 2 passes |
| --- | --- | --- | --- |
| F1 micro | 98.7 % | 100.0 % | 100.0 % |
| Temps médian | 1.72 s | 2.16 s | 5.15 s |

Le texte complet tient dans la fenêtre de contexte annoncée du modèle pour ces
quatre documents. Le prompt direct peut donc le lire en un seul appel ; LangExtract
utilise des segments de 1 200 caractères. Ce choix, proche de l’application testée,
n’est pas nécessairement optimal pour ce modèle à grand contexte. Un autre réglage
de segmentation peut modifier le compromis ; il n’a pas été recherché après coup.

## Résultats par document

| Cas français | Direct F1 | LX 1 F1 | LX 2 F1 |
| --- | --- | --- | --- |
| fr-01 - Facture avec taxes | 100.0 % | 100.0 % | 100.0 % |
| fr-02 - Bon de commande | 100.0 % | 100.0 % | 100.0 % |
| fr-03 - Contrat entre deux parties | 100.0 % | 100.0 % | 100.0 % |
| fr-04 - Avenant avec montant annulé | 100.0 % | 100.0 % | 100.0 % |
| fr-05 - Courrier de réception | 90.0 % | 100.0 % | 80.0 % |
| fr-06 - Décision attributive | 94.7 % | 100.0 % | 100.0 % |
| fr-07 - Procès-verbal de réception | 100.0 % | 100.0 % | 100.0 % |
| fr-08 - Rapport d’incident | 88.9 % | 88.9 % | 88.9 % |
| fr-09 - Note de nomination | 83.3 % | 66.7 % | 66.7 % |
| fr-10 - Convention de subvention | 100.0 % | 100.0 % | 100.0 % |
| fr-11 - Attestation sans montant | 100.0 % | 100.0 % | 100.0 % |
| fr-12 - Notification avec date remplacée | 100.0 % | 100.0 % | 100.0 % |
| fr-13 - Demande de remboursement | 100.0 % | 100.0 % | 100.0 % |
| fr-14 - Bordereau de transmission | 100.0 % | 100.0 % | 100.0 % |
| fr-15 - Compte rendu sans références | 100.0 % | 100.0 % | 100.0 % |
| fr-16 - Deux devis et décision finale | 100.0 % | 100.0 % | 100.0 % |
| fr-17 - Tableau de paiements | 100.0 % | 100.0 % | 100.0 % |
| fr-18 - Tableau avec case vide | 100.0 % | 100.0 % | 100.0 % |
| fr-19 - Nom avec accents | 75.0 % | 75.0 % | 75.0 % |
| fr-20 - Noms répétés | 100.0 % | 100.0 % | 100.0 % |
| fr-21 - Pluridevises sans conversion | 100.0 % | 100.0 % | 100.0 % |
| fr-22 - Année et nombres distracteurs | 100.0 % | 100.0 % | 100.0 % |
| fr-23 - Référence coupée du libellé | 90.9 % | 90.9 % | 100.0 % |
| fr-24 - Référence entre parenthèses | 100.0 % | 100.0 % | 100.0 % |
| fr-25 - Deux contacts distincts | 100.0 % | 100.0 % | 100.0 % |
| fr-26 - Montant écrit en lettres | 93.3 % | 93.3 % | 100.0 % |
| fr-27 - Négation sans annulation de parties | 100.0 % | 100.0 % | 100.0 % |
| fr-28 - Pièces jointes et instruction documentaire | 100.0 % | 100.0 % | 100.0 % |
| fr-29 - Facture et avoir sans calcul | 100.0 % | 100.0 % | 100.0 % |
| fr-30 - Dates de période | 100.0 % | 100.0 % | 100.0 % |
| fr-31 - Bloc de signature | 100.0 % | 85.7 % | 100.0 % |
| fr-32 - Dates numériques françaises | 100.0 % | 100.0 % | 100.0 % |
| fr-33 - Long - entités dispersées | 93.3 % | 100.0 % | 100.0 % |
| fr-34 - Long - répétitions des parties | 100.0 % | 100.0 % | 100.0 % |
| fr-35 - Long - rectification finale | 100.0 % | 100.0 % | 100.0 % |
| fr-36 - Long - tableau en fin de dossier | 100.0 % | 100.0 % | 100.0 % |
| fr-37 - Négatif - texte générique | 0 FP | 0 FP | 0 FP |
| fr-38 - Négatif - valeurs toutes annulées | 0 FP | 0 FP | 0 FP |
| fr-39 - Négatif - formulaire non rempli | 0 FP | 0 FP | 0 FP |
| fr-40 - Négatif - exemples de formats | 0 FP | 0 FP | 0 FP |

## Protocole gelé avant les appels

- Corpus : 32 documents courts de structures distinctes, 4 documents longs,
  4 négatifs ; 36 positifs au total. Facture, commande, contrat, avenant, courrier,
  décision, procès-verbal, incident, nomination, convention, attestation,
  notification, remboursement, transmission, compte rendu, devis, tableaux,
  accents, répétitions, devises, montants en lettres, dates, références et négations.
- Références rédigées avant la génération et vérifiées contre la couche texte des
  PDF. Noms fictifs et adresses `example.invalid`. Aucune donnée métier réelle.
  Pas d’ajustement de référence ou de prompt après observation des résultats.
- Même texte extrait par `pdfplumber`, mêmes instructions métier, même exemple
  français et même format JSON. La baseline utilise uniquement le renderer
  de prompt pour partager exactement les exemples : elle n’exécute ni segmentation,
  ni resolver, ni annotation, ni passes LangExtract.
- Paramètres par appel identiques et vérifiés par assertion : température 0, seed 42,
  plafond 4 096 tokens de sortie, `response_format=json_object`, `n=1`, alias `ai-flash`.
  Une requête complète pour le prompt direct ; LangExtract 1 ou 2 passes, un worker,
  segments de 1 200 caractères. **Le budget total d’appels/tokens n’est pas égalisé :
  il est mesuré.** La différence de nombre d’appels fait partie du compromis étudié.
- 240 traitements entrelacés avec graine d’ordre 20261104. Pas de concurrence,
  de retries automatiques, de tuning adaptatif ni de sélection du meilleur essai.
  Le plafond de sécurité de 650 appels LLM n’a pas été utilisé pour sélectionner
  des résultats ; vérifier le nombre effectif dans `summary.json`.
- Le transport LangExtract est instrumenté pour compter tous les appels sans retries
  cachés du SDK. Le framework conserve ses prompts, segmentation, résolution,
  alignement et fusion des passes. Ce transport renvoie le contenu du premier choix
  au format `ScoredOutput`, sans modifier la réponse du modèle.

## Modèle et provenance

L’alias `ai-flash` annonce `qwen3.6` comme modèle amont avec raisonnement désactivé.
Les snapshots `/models` avant/après sont conservés. Identité de l’alias inchangée :
**True**. Le nom annoncé ne précise pas le checkpoint exact,
la quantification ou le matériel. Les réponses complètes permettent de vérifier
le modèle effectivement déclaré et les tokens de chaque appel.

Les chiffres du premier pilote ne doivent pas être comparés directement à ceux-ci :
corpus, prompt, contrôle des paramètres et chemin d’exécution ont changé. Le pilote
historique est conservé sans réécriture. Cette étude porte sur l’extraction en
français, pas sur la qualité générale de la langue française du modèle.

## Scoring et limites

Vrai positif = classe identique et extrait complet identique, avec comparaison
de multiensembles. Seuls espaces et NFC sont normalisés ; pas de tolérance sur
casse, accents, devise ou ponctuation. Précision = TP/(TP+FP), rappel = TP/(TP+FN),
F1 = 2TP/(2TP+FP+FN). Un nom tronqué provoque un faux positif et un faux négatif.
Les tableaux par classe et par cas rendent ces pénalités explicites.

Les attributs et relations métier ne sont pas évalués. Les noms artificiels,
les phrases souvent explicites et les négatifs contrôlés limitent la validité
externe. Les 40 documents ne sont pas un tirage aléatoire ; les deux répétitions
ne créent pas 80 documents indépendants. Aucun test de significativité ni intervalle
de confiance de population n’est revendiqué. Ni OCR, ni qualité image, ni stress
test de grand contexte ne sont évalués dans cette campagne.

Avant une décision de production : corpus réel autorisé, double annotation
indépendante, jeu de réglage séparé du test, scoring d’attributs/relations,
mesure chronométrée des corrections humaines et seuils convenus avec les métiers.

## Fichiers et reproduction

- `report.pdf` : synthèse de décision de quatre pages.
- `corpus.py` et `corpus.json` : textes, références et génération des 40 PDF.
- `pdfs.tar.gz` : PDF réellement utilisés, avec leurs empreintes dans le corpus.
- `compare.py` : protocole et instrumentation, token lu en mémoire uniquement.
- `responses.jsonl.gz` : 240 preuves complètes, une ligne JSON par traitement :
  paramètres et prompts, réponses du modèle, usage, sortie annotée et mesure.
- `measurements.json`, `summary.json`, `models-before.json`, `models-after.json` :
  mesures et métadonnées sans secret.
- `analyze.py`, `present.py`, `pack.py` : agrégation, restitution et empaquetage.
- `test_comparison.py` : vérifications de l’alignement, des rejets et de l’exclusion des secrets.

Lancer depuis ce dossier avec Python, les dépendances du projet et ReportLab/Pillow/
pdfplumber pour les PDF ; les polices DejaVu sont requises par le générateur.

```bash
python analyze.py
python present.py
python -m pytest test_comparison.py -q
# Consulter toutes les réponses sans requête réseau :
gzip -dc responses.jsonl.gz
# Extraire les PDF sous pdfs/ :
tar -xzf pdfs.tar.gz
# Nouvelle campagne seulement, après archivage de results/ et measurements.json :
python compare.py  # demande le token sans l'enregistrer
```

Le scorer commun reste celui de `../business-2026-11-03/run_benchmark.py`.
Les sorties brutes et PDF sont disponibles dans les archives pour limiter le poids
du dépôt ; aucun token, en-tête Authorization ou donnée réelle n’est versionné.
