"""Generate the decision brief from the archived results, without inference."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
s = json.loads((ROOT / "summary.json").read_text())
c = json.loads((ROOT / "corpus.json").read_text())
m = json.loads((ROOT / "measurements.json").read_text())
a = s["profiles"]["one-pass-pooled"]
b = s["profiles"]["two-passes"]
pct = lambda x: f"{100 * x:.1f} %"
case_rows = []
for case in c["cases"]:
    vals = []
    for profile in ["one-pass-A", "one-pass-B", "two-passes"]:
        r = next(
            r for r in m["rows"] if r["case"] == case["id"] and r["profile"] == profile
        )
        if r["expected_status"] == 422:
            val = "422 attendu"
        elif not case["gold"]:
            val = "0 faux positif"
        else:
            q = r["score"]
            val = f"{100 * 2 * q['tp'] / (2 * q['tp'] + q['fp'] + q['fn']):.1f} %"
        vals.append(val)
    case_rows.append([case["title"], *vals])
comparison = [
    ["Mesure", "1 passe (A+B)", "2 passes"],
    ["Précision exacte", pct(a["precision"]), pct(b["precision"])],
    ["Rappel exact", pct(a["recall"]), pct(b["recall"])],
    ["F1 micro", pct(a["f1"]), pct(b["f1"])],
    ["Temps médian", f"{a['median_seconds']:.2f} s", f"{b['median_seconds']:.2f} s"],
    ["Temps moyen", f"{a['mean_seconds']:.2f} s", f"{b['mean_seconds']:.2f} s"],
    [
        "TP / FP / FN",
        f"{a['tp']} / {a['fp']} / {a['fn']}",
        f"{b['tp']} / {b['fp']} / {b['fn']}",
    ],
    [
        "Documents exploitables",
        f"{a['successes']} / {a['requests']}",
        f"{b['successes']} / {b['requests']}",
    ],
]
readme = (
    f"""# LangExtract : valeur métier et limites observées

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
| Précision exacte | {pct(a["precision"])} | {pct(b["precision"])} |
| Rappel exact | {pct(a["recall"])} | {pct(b["recall"])} |
| F1 micro | {pct(a["f1"])} | {pct(b["f1"])} |
| Temps médian par PDF textuel | {a["median_seconds"]:.2f} s | {b["median_seconds"]:.2f} s |
| Temps moyen par PDF textuel | {a["mean_seconds"]:.2f} s | {b["mean_seconds"]:.2f} s |
| TP / FP / FN | {a["tp"]} / {a["fp"]} / {a["fn"]} | {b["tp"]} / {b["fp"]} / {b["fn"]} |

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

**Stabilité : {s["stable_documents"]}/{s["stability_documents"]} documents textuels ont exactement le même multiensemble
(classe, extrait, multiplicité) sur les deux exécutions à une passe.** Sur les seuls
8 cas positifs, 4/8 sont stables. Les attributs et les positions ne sont pas inclus
dans cette mesure de stabilité.

Deux passes améliorent ici le F1 groupé de {(b["f1"] - a["f1"]) * 100:.1f} points, avec un temps médian
multiplié par {b["median_seconds"] / a["median_seconds"]:.2f}. Ce bénéfice n’est pas uniforme : l’organisation
du tableau est retrouvée en une passe puis omise dans l’essai à deux passes.
Les deux répétitions à une passe donnent elles-mêmes des F1 différents
({pct(s["profiles"]["one-pass-A"]["f1"])} et {pct(s["profiles"]["one-pass-B"]["f1"])}). Le premier appel a pris
10,174 s ; il est conservé dans les mesures, sans présumer de la cause du délai.

## Résultats par cas - F1 exact

| Document | 1 passe A | 1 passe B | 2 passes |
| --- | --- | --- | --- |
"""
    + "\n".join("| " + " | ".join(row) + " |" for row in case_rows)
    + """

## Ce que cela apporte aux métiers

- **Factures / contrats** : candidats structurés pour préremplir un outil et vérifier
  la pièce justificative. Une validation humaine reste nécessaire sur les omissions.
- **Courriers / dossiers** : repérage des références et dates pour tri assisté,
  sans déduire de ce pilote une décision ou un classement automatique fiable.
- **Tableaux / documents longs** : segmentation et localisation observables dans
  les exports ; le test long ne prouve pas l’exhaustivité sur des contrats réels.
- **Contrôle et audit** : les extraits localisés permettent de relire la preuve.
  La justesse des offsets est distincte de la bonne interprétation métier.

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
"""
)
class_table = "## Résultats par classe (précision / rappel)\n\n| Classe | 1 passe groupée | 2 passes |\n| --- | --- | --- |\n"
for name in sorted(s["per_class"]["one-pass-pooled"]):
    vals = []
    for group in ["one-pass-pooled", "two-passes"]:
        q = s["per_class"][group].get(name, {})
        tp, fp, fn = q.get("tp", 0), q.get("fp", 0), q.get("fn", 0)
        vals.append(
            f"{pct(tp / (tp + fp)) if tp + fp else 'N/A'} / {pct(tp / (tp + fn)) if tp + fn else 'N/A'}"
        )
    class_table += "| " + name + " | " + " | ".join(vals) + " |\n"
readme = readme.replace(
    "## Échecs observés, avec preuves conservées",
    class_table + "\n## Échecs observés, avec preuves conservées",
)
(ROOT / "README.md").write_text(readme)
pdfmetrics.registerFont(
    TTFont("EvalFont", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
)
pdfmetrics.registerFont(
    TTFont("EvalBold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
)
styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="TitleEval",
        fontName="EvalBold",
        fontSize=25,
        leading=30,
        textColor=colors.HexColor("#132c48"),
        spaceAfter=18,
    )
)
styles.add(
    ParagraphStyle(
        name="SubEval",
        fontName="EvalBold",
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#096b70"),
        spaceBefore=14,
        spaceAfter=8,
    )
)
styles.add(
    ParagraphStyle(
        name="BodyEval", fontName="EvalFont", fontSize=9.5, leading=14, spaceAfter=9
    )
)
styles.add(
    ParagraphStyle(
        name="SmallEval", fontName="EvalFont", fontSize=8, leading=11, spaceAfter=6
    )
)
story = []


def para(text, style="BodyEval"):
    story.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[style]))


def table(rows, widths):
    data = [
        [Paragraph(escape(str(v)), styles["SmallEval"]) for v in row] for row in rows
    ]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6edf4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#132c48")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#132c48")),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#d5dee7")),
            ]
        )
    )
    story.append(t)


para("ÉVALUATION PILOTE | 3 NOVEMBRE 2026", "SmallEval")
para("LangExtract\nValeur métier et limites", "TitleEval")
para(
    "Pré-extraire des informations vérifiables, sans confondre traçabilité et exhaustivité.",
    "SubEval",
)
para(
    "10 PDF synthétiques · 12 pages · 41 références · 30 appels réels. Factures, contrats, courrier, tableau, anglais, corrections, document long, accents et contrôles négatifs."
)
table(comparison, [210, 140, 140])
para("Décision proposée", "SubEval")
para(
    "Poursuivre un pilote de préremplissage avec validation humaine. Les offsets et exports rendent la preuve consultable ; les omissions et la variabilité empêchent de conclure à une extraction autonome fiable."
)
para(
    "110/110 extraits sont présents dans la source et correctement localisés après normalisation des espaces/Unicode. Trois noms restent incomplets au regard du contrat malgré cette localisation valide."
)
para(
    "Limite décisive : aucune comparaison à un simple prompt du même modèle. Ni gain de temps humain ni coût fournisseur ne sont mesurés. Cette étude démontre un comportement du service, pas la supériorité du framework.",
    "SmallEval",
)
story.append(PageBreak())
para("Où la valeur se confirme\net où elle se dégrade", "TitleEval")
table(
    [["Document", "1 passe A", "1 passe B", "2 passes"], *case_rows], [235, 85, 85, 85]
)
para("Lecture des écarts", "SubEval")
para(
    "Stabilité : 5/9 documents textuels identiques entre A et B (4/8 positifs). La mesure compare classe, extrait et multiplicité, sans les attributs ni positions."
)
para(
    "Omissions d’organisations, noms tronqués et occurrence répétée manquante constituent les principaux écarts. Le tableau est complet dans les deux essais à une passe, puis perd une organisation dans l’essai à deux passes."
)
para(
    "Deux passes : +"
    + f"{(b['f1'] - a['f1']) * 100:.1f}"
    + " points de F1 groupé, mais un temps médian multiplié par "
    + f"{b['median_seconds'] / a['median_seconds']:.2f}"
    + ". Une seule exécution à deux passes ne permet pas de généraliser cet avantage."
)
para(
    "Contrôles négatifs : 3/3 listes vides correctes pour le texte neutre ; 3/3 rejets OCR attendus pour le PDF image. Les 27 appels textuels réussissent sans erreur HTTP inattendue.",
    "SmallEval",
)
story.append(PageBreak())
para("Méthode, portée\net décision suivante", "TitleEval")
for heading, body in [
    (
        "Mesure contrôlée",
        "Références écrites avant les appels et vérifiées contre le texte des PDF. Prompt métier fixe, un worker, segments de 1 200 caractères. Trois profils : une passe A, une passe B et deux passes. Ordre entrelacé avec graine 20261103. Aucune retouche du prompt après observation.",
    ),
    (
        "Qualité stricte",
        "TP = même classe et extrait complet. Comparaison de multiensembles, espaces et Unicode NFC normalisés uniquement. Un nom tronqué compte FP + FN. F1 = 2TP / (2TP + FP + FN). Attributs non notés. Scans exclus des scores textuels. Les négatifs n’ajoutent pas de vrais positifs.",
    ),
    (
        "Traçabilité et performance",
        "Offsets contrôlés contre document.text ; pas d’association référence-position pour les occurrences répétées. Durées HTTP complètes incluant PDF, inférence et exports. Premier appel de 10,174 s conservé. Pas de benchmark GPU ni de test de charge.",
    ),
    (
        "Limites à annoncer",
        "Corpus synthétique restreint, 41 occurrences, pas d’annotation indépendante. Noms artificiels susceptibles d’accentuer des ambiguïtés. Modèle exact, paramètres, tokens et coûts non exposés par cette API. Pas de comparaison directe LLM, de mesure du temps de correction ou de généralisation statistique.",
    ),
    (
        "Prochain jalon professionnel",
        "Comparer au même modèle via accès direct, sur un corpus métier autorisé annoté indépendamment. Geler le contrat et le jeu de test. Mesurer par champ : exactitude, omissions, attributs, preuve, coût et minutes de correction. Définir les seuils avec les métiers avant la décision de production.",
    ),
    (
        "Pièces auditables",
        "PDF du corpus, références, réponses synthétiques complètes, mesures, scripts de scoring et tests versionnés. README.md détaille le protocole et la reproduction. Token utilisé uniquement en mémoire ; aucun secret dans le dossier.",
    ),
]:
    para(heading, "SubEval")
    para(body)


def footer(canvas, doc):
    canvas.setFont("EvalFont", 8)
    canvas.setFillColor(colors.HexColor("#526277"))
    canvas.drawString(45, 25, "LangExtract | Étude pilote synthétique | 03/11/2026")
    canvas.drawRightString(550, 25, str(doc.page))


SimpleDocTemplate(
    str(ROOT / "report.pdf"),
    leftMargin=45,
    rightMargin=45,
    topMargin=42,
    bottomMargin=42,
    title="LangExtract - Évaluation pilote de valeur métier",
    author="Évaluation technique et métier",
).build(story, onFirstPage=footer, onLaterPages=footer)
print("README.md and report.pdf generated")
