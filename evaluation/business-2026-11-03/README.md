# LangExtract : valeur métier et limites observées

**Étude pilote du 3 novembre 2026 - corpus synthétique, service réellement appelé.**

## Décision proposée

Retenir LangExtract comme **brique de pré-extraction traçable avec contrôle humain**.
Les résultats justifient une expérimentation métier, pas une automatisation autonome
ni une affirmation de supériorité sur un simple prompt LLM. La valeur directement
observée est l’association des entités à des extraits et positions dans le texte,
avec des exports exploitables. La réduction de temps de travail humain reste à mesurer.

## Résultats chiffrés

10 PDF, 12 pages, 41 occurrences de référence, 30 requêtes séquentielles :
8 documents positifs, 1 négatif sans entité et 1 PDF image sans texte.
Les 27 demandes sur PDF textuels réussissent ; les 3 demandes sur PDF image sont
rejetées par 422 comme attendu. Aucun échec HTTP inattendu pendant cette campagne.

| Mesure | 1 passe, deux répétitions groupées | 2 passes, une exécution |
| --- | --- | --- |
| Précision exacte | 95.9 % | 100.0 % |
| Rappel exact | 85.4 % | 90.2 % |
| F1 micro | 90.3 % | 94.9 % |
| Temps médian par PDF textuel | 1.97 s | 3.66 s |
| Temps moyen par PDF textuel | 2.36 s | 3.21 s |
| TP / FP / FN | 70 / 3 / 12 | 37 / 0 / 4 |

Les dénominateurs diffèrent : 82 occurrences de référence sur 18 requêtes textuelles
pour le groupe 1 passe, 41 sur 9 requêtes textuelles pour le groupe 2 passes.
Les contrôles négatifs textuels contribuent aux temps et aux faux positifs, mais
n’ajoutent aucun vrai positif. Les scans sont exclus des scores d’entités et latences
textuelles, mais leur rejet est rapporté séparément.

**Traçabilité : 110/110 extraits renvoyés sont présents dans le texte et correctement
localisés par leurs offsets**, après normalisation des espaces et Unicode NFC.
Cela ne signifie pas que 110 entités sont correctes au sens du contrat : trois
extraits sont des noms tronqués, présents dans la source mais non conformes à la
référence complète. Les positions attendues des occurrences répétées ne sont pas
comparées une à une ; seule la validité locale de chaque offset est vérifiée.

**Stabilité : 5/9 documents textuels ont exactement le même multiensemble
(classe, extrait, multiplicité) sur les deux exécutions à une passe.** Sur les seuls
8 cas positifs, 4/8 sont stables. Les attributs et les positions ne sont pas inclus
dans cette mesure de stabilité.

Deux passes améliorent ici le F1 groupé de 4.5 points, avec un temps médian
multiplié par 1.86. Ce bénéfice n’est pas uniforme : l’organisation
du tableau est retrouvée en une passe puis omise dans l’essai à deux passes.
Les deux répétitions à une passe donnent elles-mêmes des F1 différents
(92.3 % et 88.3 %). Le premier appel a pris
10,174 s ; il est conservé dans les mesures, sans présumer de la cause du délai.

## Résultats par cas - F1 exact

| Document | 1 passe A | 1 passe B | 2 passes |
| --- | --- | --- | --- |
| Facture simple | 100.0 % | 88.9 % | 100.0 % |
| Contrat et parties | 100.0 % | 100.0 % | 100.0 % |
| Courrier administratif | 80.0 % | 100.0 % | 100.0 % |
| Tableau de commandes | 100.0 % | 100.0 % | 92.3 % |
| Document en anglais | 88.9 % | 66.7 % | 100.0 % |
| Valeurs annulées et applicables | 80.0 % | 80.0 % | 80.0 % |
| Document long avec entités dispersées | 85.7 % | 85.7 % | 85.7 % |
| Accents et répétitions | 88.9 % | 66.7 % | 88.9 % |
| Contrôle négatif sans entité | 0 faux positif | 0 faux positif | 0 faux positif |
| Contrôle négatif sans couche texte | 422 attendu | 422 attendu | 422 attendu |

## Ce que cela apporte aux métiers

- **Factures / contrats** : candidats structurés pour préremplir un outil et vérifier
  la pièce justificative. Une validation humaine reste nécessaire sur les omissions.
- **Courriers / dossiers** : repérage des références et dates pour tri assisté,
  sans déduire de ce pilote une décision ou un classement automatique fiable.
- **Tableaux / documents longs** : segmentation et localisation observables dans
  les exports ; le test long ne prouve pas l’exhaustivité sur des contrats réels.
- **Contrôle et audit** : les extraits localisés permettent de relire la preuve.
  La justesse des offsets est distincte de la bonne interprétation métier.

## Résultats par classe (précision / rappel)

| Classe | 1 passe groupée | 2 passes |
| --- | --- | --- |
| amount | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| date | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| email | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| invoice | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| org | 90.9 % / 50.0 % | 100.0 % / 60.0 % |
| person | 80.0 % / 80.0 % | 100.0 % / 100.0 % |
| ref | 100.0 % / 100.0 % | 100.0 % / 100.0 % |

## Échecs observés, avec preuves conservées

- Omission récurrente de certains noms d’organisation complets, notamment dans
  le document long. Références, montants et dates peuvent rester présents alors
  qu’une organisation manque : une réponse HTTP 200 n’est pas une preuve d’exhaustivité.
- Noms tronqués : `Personne Émeraude` devient `Émeraude`, `Personne Delta` devient
  `Delta`, et `Organisation Delta` devient `Delta` dans certains essais.
- Deux occurrences de `Organisation Été` attendues, une seule renvoyée. La mesure
  compte les occurrences ; une mesure limitée aux valeurs uniques masquerait ce manque.
- Les valeurs explicitement annulées n’ont pas été extraites dans le cas prévu.
  Le négatif sans entité donne une liste vide sur les trois essais, sans faux positif.
- Le scan n’est pas OCRisé. Le rejet clair est un comportement attendu de cette
  application, pas une évaluation d’un OCR ou une limite de tous les pipelines LangExtract.

## Protocole et formules

Corpus et références rédigés avant les appels, par l’auteur de cette évaluation,
sans adjudication humaine indépendante. Références vérifiées contre la couche
texte des PDF. Les noms et adresses sont fictifs ; `example.invalid` est utilisé.
Le même prompt métier et les mêmes exemples serveur sont conservés. Segments de
1 200 caractères, un worker, profils à 1 et 2 passes. Les 30 appels sont entrelacés
avec un ordre pseudo-aléatoire fixé (graine 20261103), sans concurrence ni reprise
silencieuse. Aucune adaptation du prompt aux résultats observés n’a été effectuée.

Un vrai positif exige la même classe et le même extrait complet, avec comparaison
de multiensembles. Seuls les espaces et Unicode NFC sont normalisés ; casse,
ponctuation, devise et accents ne sont pas effacés. Un nom tronqué produit un faux
positif et un faux négatif. Précision = TP/(TP+FP), rappel = TP/(TP+FN),
F1 = 2TP/(2TP+FP+FN). Les attributs ne sont pas notés.

Les durées mesurent l’aller-retour HTTP complet, parsing PDF, inférence et exports
compris, depuis cet environnement ; pas la seule inférence GPU ni le temps de
validation humaine. Les moyennes incluent le premier appel. Le PDF long fait
plusieurs pages et reste modeste : ni test de charge, ni stress test de grand contexte.

## Ce qui n’est pas démontré

Le service annonce l’application 0.2.0 mais n’expose pas l’identité/version du
modèle, sa quantification, température, seed, tokenizer, cache ou métriques de tokens.
La stabilité de ces paramètres pendant la campagne n’a pas pu être vérifiée.
L’URL testée est celle du service déjà autorisé ; son commit de déploiement est inconnu.
Le corpus n’est ni aléatoire ni représentatif d’une administration réelle, les noms
synthétiques peuvent accentuer l’ambiguïté des limites d’entités, et 41 références
sont trop peu pour généraliser. Pas d’intervalle de confiance ni de significativité
statistique revendiqués. Le niveau de difficulté des négatifs est limité.

**Comparaison avec un simple prompt LLM : non réalisée.** Le token fourni donne
accès à l’application, pas au fournisseur ni à son modèle exact. Présenter le profil
une passe comme un simple prompt serait incorrect : les deux profils utilisent
LangExtract. Aucun gain attribuable au seul framework, coût en tokens/euros,
gain de temps humain ou score RGAA n’est revendiqué.

## Suite recommandée avant décision de production

1. Fixer l’identité du modèle et ses paramètres, puis accéder au même endpoint
   pour un comparatif apparié LangExtract / simple extraction JSON.
2. Faire annoter un corpus métier autorisé par deux personnes indépendantes,
   en séparant jeu de réglage et jeu de test gelé. Couvrir montants ambigus,
   versions de clauses, mauvaise qualité PDF, tableaux et documents longs.
3. Répéter les deux méthodes sur les mêmes PDF, prompt métier et budget comparables.
   Déclarer les retries, erreurs, budget et contrats de sortie avant les essais.
4. Mesurer précision/rappel par champ, attributs, preuve exacte et temps de
   correction humaine, avec sessions chronométrées et coût fournisseur observé.
5. Fixer avec les métiers les seuils acceptables par risque : un montant erroné
   et une omission d’organisation n’ont pas nécessairement le même impact.

## Reproduction et livrables

- `report.pdf` : synthèse de trois pages prête à présenter.
- `corpus.py`, `corpus.json`, `pdfs/` : génération, références et PDF versionnés.
- `run_benchmark.py` : appels séquentiels, token lu dans `LANGEXTRACT_API_TOKEN`
  ou demandé sans affichage. Aucun secret dans les fichiers.
- `results/` : réponses complètes du corpus synthétique et mesures par appel.
- `measurements.json`, `summary.json`, `analyze.py` : mesures et agrégation sans modèle.
- `test_scoring.py` : tests du comptage, des doublons, des extraits partiels et Unicode.
- `present.py` : reconstruction de cette synthèse à partir des mesures gelées.

Depuis ce dossier, sur Linux avec les polices DejaVu et les dépendances
`reportlab`, `pdfplumber`, `Pillow`, `httpx[socks]`, `pytest` :

```bash
python analyze.py
python present.py
python -m pytest test_scoring.py -q
# Pour une NOUVELLE campagne : archiver results/ et measurements.json avant.
python run_benchmark.py  # demande le token sans l’enregistrer
```

`corpus.py` reconstruit les PDF et les références ; le générateur refuse de valider
une référence absente de la couche texte produite. L’analyse peut aussi être auditée
sans réexécuter la moindre requête authentifiée. Cette étude complète le contrôle
technique de `docs/audits/2026-11-03/` ; elle ne modifie pas le service déployé.
