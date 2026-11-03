"""Build a four-page French decision brief from frozen measurements."""

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
LABELS = {
    "direct": "Prompt direct",
    "langextract-1": "LangExtract 1 passe",
    "langextract-2": "LangExtract 2 passes",
}
ORDER = list(LABELS)
pct = lambda v: "N/A" if v is None else f"{100 * v:.1f} %"


def main():
    s = json.loads((ROOT / "summary.json").read_text())
    o = s["overview"]
    d = o["direct"]
    names = [LABELS[k] for k in ORDER]
    delta = (o["langextract-1"]["f1"] - d["f1"]) * 100
    verdict = f"Écart F1 LangExtract une passe / prompt direct : {delta:+.2f} points."
    if delta > 0:
        verdict += " LangExtract obtient un meilleur score descriptif sur ce corpus ; ce constat ne prouve pas un avantage général."
    elif delta < 0:
        verdict += " Le prompt direct obtient le meilleur score des deux sur ce corpus ; aucun gain global de qualité de LangExtract une passe n’est démontré ici."
    else:
        verdict += (
            " Aucune différence globale de F1 n’est observée entre ces deux méthodes."
        )
    quality = [
        ["Mesure", *names],
        ["Précision", *[pct(o[k]["precision"]) for k in ORDER]],
        ["Rappel", *[pct(o[k]["recall"]) for k in ORDER]],
        ["F1 micro", *[pct(o[k]["f1"]) for k in ORDER]],
        [
            "Succès / traitements",
            *[f"{o[k]['successes']}/{o[k]['jobs']}" for k in ORDER],
        ],
        ["TP / FP / FN", *[f"{o[k]['tp']}/{o[k]['fp']}/{o[k]['fn']}" for k in ORDER]],
    ]
    resources = [
        ["Mesure", *names],
        ["Temps médian", *[f"{o[k]['median_seconds']:.2f} s" for k in ORDER]],
        ["Temps moyen", *[f"{o[k]['mean_seconds']:.2f} s" for k in ORDER]],
        ["Appels HTTP LLM", *[str(o[k]["http_calls"]) for k in ORDER]],
        [
            "Tokens entrée",
            *[f"{o[k]['tokens']['prompt_tokens']:,}".replace(",", " ") for k in ORDER],
        ],
        [
            "Tokens sortie",
            *[
                f"{o[k]['tokens']['completion_tokens']:,}".replace(",", " ")
                for k in ORDER
            ],
        ],
        [
            "Tokens totaux",
            *[f"{o[k]['tokens']['total_tokens']:,}".replace(",", " ") for k in ORDER],
        ],
        [
            "Multiplicateur tokens",
            *[
                f"{o[k]['tokens']['total_tokens'] / d['tokens']['total_tokens']:.2f} x"
                for k in ORDER
            ],
        ],
    ]
    classes = sorted(set().union(*(set(s["by_class"][k]) for k in ORDER)))
    class_rows = [["Classe - P / R", *names]]
    french_classes = {
        "amount": "Montant",
        "date": "Date",
        "email": "E-mail",
        "invoice": "Facture",
        "org": "Organisation",
        "person": "Personne",
        "ref": "Référence",
    }
    for name in classes:
        values = []
        for method in ORDER:
            q = s["by_class"][method].get(name, {})
            tp, fp, fn = q.get("tp", 0), q.get("fp", 0), q.get("fn", 0)
            values.append(
                f"{pct(tp / (tp + fp) if tp + fp else None)} / {pct(tp / (tp + fn) if tp + fn else None)}"
            )
        class_rows.append([f"{french_classes.get(name, name)} ({name})", *values])
    stability = [
        ["Contrôle", *names],
        [
            "Entités identiques A/B",
            *[f"{s['stability'][k]['identical_entity_multisets']}/40" for k in ORDER],
        ],
        [
            "Négatifs sans entité",
            *[f"{s['stability'][k]['negative_successes']}/8" for k in ORDER],
        ],
        [
            "Offsets valides",
            *[f"{o[k]['offset_valid']}/{o[k]['predicted']}" for k in ORDER],
        ],
        [
            "Extraits dans la source",
            *[f"{o[k]['source_grounded']}/{o[k]['predicted']}" for k in ORDER],
        ],
    ]
    long_rows = [
        ["Documents longs", *names],
        ["F1 micro", *[pct(s["long_documents"][k]["f1"]) for k in ORDER]],
        [
            "Temps médian",
            *[f"{s['long_documents'][k]['median_seconds']:.2f} s" for k in ORDER],
        ],
    ]

    def markdown_table(rows):
        return "\n".join(
            [
                "| " + " | ".join(row) + " |"
                for row in [rows[0], ["---"] * len(rows[0]), *rows[1:]]
            ]
        )

    cases_table = [["Cas français", "Direct F1", "LX 1 F1", "LX 2 F1"]]
    for case in s["by_case"]:
        cases_table.append(
            [
                case["case"] + " - " + case["title"],
                *[
                    pct(case["methods"][method]["f1"])
                    if not case["negative"]
                    else f"{case['methods'][method]['fp']} FP"
                    for method in ORDER
                ],
            ]
        )
    readme = f"""# Comparatif français : prompt direct et LangExtract

Étude contrôlée du 3 novembre 2026. **40 PDF entièrement en français, 44 pages,
158 occurrences de référence, 240 traitements** (40 documents × 3 stratégies ×
2 exécutions). Tous les appels ont été réalisés sur le même endpoint authentifié :
`https://api-llm-custom.ailab.infocepo.com/v1`, alias `ai-flash`.

## Décision et portée

{verdict}

F1 arrondis (direct, une passe, deux passes) : {pct(d["f1"])}, {pct(o["langextract-1"]["f1"])}, {pct(o["langextract-2"]["f1"])}. Deux passes
augmentent le F1 de seulement {(o["langextract-2"]["f1"] - d["f1"]) * 100:.3f} point par rapport au direct,
avec {o["langextract-2"]["tokens"]["total_tokens"] / d["tokens"]["total_tokens"]:.2f} fois les tokens.
Cette différence minime ne justifie pas à elle seule deux passes. À une passe,
le volume de tokens augmente de {(o["langextract-1"]["tokens"]["total_tokens"] / d["tokens"]["total_tokens"] - 1) * 100:.1f} %.
La stabilité descriptive est de {s["stability"]["direct"]["identical_entity_multisets"]}/40 documents pour le direct,
{s["stability"]["langextract-1"]["identical_entity_multisets"]}/40 pour LangExtract une passe et
{s["stability"]["langextract-2"]["identical_entity_multisets"]}/40 à deux passes. Sur les quatre documents longs,
LangExtract une passe retrouve {s["long_documents"]["langextract-1"]["tp"]}/40 occurrences cumulées
contre {s["long_documents"]["direct"]["tp"]}/40 pour le direct.
Ce sont des indices d'intérêt opérationnel à confirmer, sans test de significativité.

Le résultat mesure cette configuration locale de LangExtract 1.7.1 et ce modèle,
pas toutes les possibilités du framework ni le frontend déployé. Les documents
sont synthétiques et rédigés pour cette étude, sans annotation humaine indépendante.
Ils sont plus nombreux et diversifiés que le pilote précédent, mais ne constituent
pas un échantillon représentatif d’une administration.

## Résultats de qualité

{markdown_table(quality)}

Chaque stratégie est évaluée sur 316 occurrences attendues (158 × 2). Les 4 négatifs
sont inclus dans les faux positifs et les temps, mais n’ajoutent aucun vrai positif.
Un échec de traitement compte toutes les occurrences de référence comme manquantes.
Il n’y a pas de suppression silencieuse des cas échoués.

## Ressources mesurées

{markdown_table(resources)}

Les tokens sont ceux renvoyés dans `usage` par le serveur. Données de consommation
complètes pour tous les appels : **{all(o[k]["usage_complete"] for k in ORDER)}**.
Il s’agit d’un indicateur de volume, pas d’un prix en euros ni d’une mesure d’énergie.
Caches, facturation, débit GPU et temps humain de validation ne sont pas mesurés.
Les temps couvrent l’extraction depuis le texte déjà lu, y compris parsing et
alignement, sans upload HTTP de PDF ni rendu/export HTML. Ils ne sont pas directement
comparables aux durées end-to-end du pilote via FastAPI.

## Qualité par classe - précision / rappel

{markdown_table(class_rows)}

## Répétabilité, contrôles et localisation

{markdown_table(stability)}

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

{markdown_table(long_rows)}

Le texte complet tient dans la fenêtre de contexte annoncée du modèle pour ces
quatre documents. Le prompt direct peut donc le lire en un seul appel ; LangExtract
utilise des segments de 1 200 caractères. Ce choix, proche de l’application testée,
n’est pas nécessairement optimal pour ce modèle à grand contexte. Un autre réglage
de segmentation peut modifier le compromis ; il n’a pas été recherché après coup.

## Résultats par document

{markdown_table(cases_table)}

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
**{s["alias_unchanged"]}**. Le nom annoncé ne précise pas le checkpoint exact,
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
"""
    (ROOT / "README.md").write_text(readme)
    pdfmetrics.registerFont(
        TTFont("FrReport", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    )
    pdfmetrics.registerFont(
        TTFont("FrBold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleR",
            fontName="FrBold",
            fontSize=24,
            leading=29,
            textColor=colors.HexColor("#132c48"),
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="HeadR",
            fontName="FrBold",
            fontSize=12,
            leading=17,
            textColor=colors.HexColor("#096b70"),
            spaceBefore=13,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyR", fontName="FrReport", fontSize=9.2, leading=13.5, spaceAfter=9
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallR", fontName="FrReport", fontSize=8.2, leading=11.5, spaceAfter=5
        )
    )
    story = []

    def p(text, style="BodyR"):
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[style]))

    def table(rows, widths):
        data = [
            [Paragraph(escape(str(value)), styles["SmallR"]) for value in row]
            for row in rows
        ]
        t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6edf4")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#132c48")),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#d5dee7")),
                ]
            )
        )
        story.append(t)

    widths = [160, 110, 110, 110]
    p("ÉTUDE CONTRÔLÉE | 3 NOVEMBRE 2026", "SmallR")
    p("Extraction en français\nPrompt direct ou LangExtract ?", "TitleR")
    p("40 documents français - 158 références - 240 traitements", "HeadR")
    p(
        "Corpus synthétique de 44 pages : 36 documents positifs, 4 négatifs. Deux exécutions par méthode ; même endpoint ai-flash, modèle amont annoncé qwen3.6."
    )
    table(quality, widths)
    p("Ce que les mesures permettent de décider", "HeadR")
    p(verdict)
    p(
        f"F1 à deux passes : écart de {(o['langextract-2']['f1'] - d['f1']) * 100:+.3f} point face au direct, pour {o['langextract-2']['tokens']['total_tokens'] / d['tokens']['total_tokens']:.2f} fois les tokens. Répétabilité observée (direct / une passe / deux passes) : {s['stability']['direct']['identical_entity_multisets']}/40, {s['stability']['langextract-1']['identical_entity_multisets']}/40 et {s['stability']['langextract-2']['identical_entity_multisets']}/40. Ces écarts descriptifs ne sont pas une preuve statistique de supériorité.",
        "SmallR",
    )
    p("Comparer une brique de framework à une requête complète", "HeadR")
    p(
        "Le prompt direct lit le document entier. LangExtract est mesuré à 1 puis 2 passes, avec segments de 1 200 caractères. La baseline reçoit les mêmes exemples et un alignement textuel simple : la présence d’offsets ne lui est pas refusée artificiellement."
    )
    p(
        "Portée : 40 cas rédigés pour cette étude, sans validation indépendante. Les résultats décrivent cette configuration et ne prouvent pas une supériorité universelle. Ni temps humain ni coût en euros ne sont mesurés.",
        "SmallR",
    )
    story.append(PageBreak())
    p("Le français :\nqualité par champ et cas difficiles", "TitleR")
    table(class_rows, widths)
    p("Focus sur les quatre documents longs", "HeadR")
    table(long_rows, widths)
    p("Interprétation métier", "HeadR")
    p(
        "Le bon critère est la couverture des informations applicables, pas seulement une réponse JSON valide. Le corpus inclut des montants annulés, des dates remplacées, des tableaux, des noms accentués, des répétitions et des informations éloignées dans le texte."
    )
    p(
        "Les textes longs restent petits par rapport au contexte annoncé de 262 144 tokens. Le prompt direct peut donc lire ces textes d’un seul tenant. La segmentation testée n’est pas un réglage optimisé pour ce modèle."
    )
    p(
        "La synthèse détaillée README.md donne les 40 scores par document. Les références, réponses et prompts sont archivés pour vérifier chaque faux positif ou omission.",
        "SmallR",
    )
    story.append(PageBreak())
    p("Ressources, preuves\net répétabilité", "TitleR")
    table(resources, widths)
    p("Contrôles de sortie", "HeadR")
    table(stability, widths)
    p("Comment lire ces chiffres", "HeadR")
    p(
        "Les tokens proviennent du champ usage renvoyé par le serveur ; leur volume n’est pas une facture. Le budget total n’est pas égalisé : LangExtract peut demander plusieurs appels. La durée couvre le texte vers les entités annotées, pas l’upload PDF ni les exports de l’application."
    )
    p(
        "Les offsets de la baseline sont construits par recherche textuelle tolérant les espaces ; ceux de LangExtract viennent de son resolver. Le contrôle local des offsets ne garantit pas l’identité de l’occurrence attendue lorsque des textes se répètent. La stabilité ignore attributs et positions.",
        "SmallR",
    )
    story.append(PageBreak())
    p("Méthode auditable\net conditions de généralisation", "TitleR")
    for heading, body in [
        (
            "Comparaison appariée",
            "Mêmes 40 PDF et couche texte pour les trois méthodes. Même prompt métier français, même exemple, même alias et endpoint. Température 0, seed 42, JSON mode et plafond de 4 096 tokens par appel vérifiés systématiquement. Un worker, ordre entrelacé fixé ; pas de retries ni de tuning après observation.",
        ),
        (
            "Scoring strict",
            "Classe et extrait complet doivent correspondre. Comparaison de multiensembles ; espaces et NFC normalisés uniquement. Un nom tronqué compte FP + FN. Précision = TP/(TP+FP), rappel = TP/(TP+FN), F1 = 2TP/(2TP+FP+FN). Les cas échoués ne sont pas retirés du bilan.",
        ),
        (
            "Modèle observé",
            "ai-flash annonce qwen3.6, raisonnement désactivé. Alias avant/après inchangé : "
            + str(s["alias_unchanged"])
            + ". LangExtract 1.7.1 est exécuté localement et instrumenté. Checkpoint, quantification, matériel, cache et tarif exacts ne sont pas exposés.",
        ),
        (
            "Limites du corpus",
            "Français intégral mais synthétique : situations choisies, noms fictifs, références rédigées par l’auteur sans double annotation. Pas d’échantillonnage représentatif ni de test statistique de population. Attributs, relations, OCR et temps de correction humaine non mesurés.",
        ),
        (
            "Suite de décision",
            "Valider sur documents métier autorisés annotés indépendamment. Séparer réglage et test, choisir les métriques par risque et chronométrer les corrections. Tester le réglage de segmentation sur le jeu de réglage, puis geler le protocole avant la validation finale.",
        ),
        (
            "Dossier livré",
            "Synthèse PDF, protocole, corpus et références, PDF originaux, 240 réponses instrumentées, snapshots modèles, mesures de tokens et scripts de reproduction. L’ancien pilote reste archivé ; ses scores ne sont pas directement comparables à cette nouvelle campagne.",
        ),
    ]:
        p(heading, "HeadR")
        p(body)

    def footer(canvas, doc):
        canvas.setFont("FrReport", 8)
        canvas.setFillColor(colors.HexColor("#526277"))
        canvas.drawString(
            45, 24, "Comparatif français | Corpus synthétique | 03/11/2026"
        )
        canvas.drawRightString(550, 24, str(doc.page))

    SimpleDocTemplate(
        str(ROOT / "report.pdf"),
        leftMargin=45,
        rightMargin=45,
        topMargin=40,
        bottomMargin=40,
        title="Extraction en français - Prompt direct et LangExtract",
        author="Évaluation contrôlée",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    print("Report and protocol generated")


if __name__ == "__main__":
    main()
