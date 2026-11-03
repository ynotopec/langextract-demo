"""Deterministic synthetic corpus. References authored before model calls."""

import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

import pdfplumber
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent
PROMPT = """Extraire uniquement les entités présentes et applicables dans le document.
Classes : org (nom complet d'organisation), person (nom complet de personne),
invoice (libellé FACTURE n° suivi du numéro), date (date complète, jamais une année seule),
amount (montant avec sa devise), ref (référence de contrat, marché ou dossier), email (adresse complète).
Utiliser des extraits exacts et non chevauchants. Ne pas extraire les valeurs barrées,
annulées ou explicitement inapplicables. Ne pas extraire les en-têtes génériques.
Extraire chaque occurrence applicable, sans inventer ni calculer de total.
Omettre les classes absentes. Conserver accents, casse et ponctuation.
Attributs facultatifs ; ils ne remplacent jamais l'extrait exact."""


def ent(cls, value):
    return {"class": cls, "text": value}


CASES = [
    {
        "id": "01-invoice",
        "title": "Facture simple",
        "paragraphs": [
            "FACTURE n° DEMO-001",
            "Fournisseur : Organisation Alpha. Date : 12 janvier 2026.",
            "Montant hors taxes : 100,00 EUR. Montant toutes taxes comprises : 120,00 EUR.",
        ],
        "gold": [
            ent("invoice", "FACTURE n° DEMO-001"),
            ent("org", "Organisation Alpha"),
            ent("date", "12 janvier 2026"),
            ent("amount", "100,00 EUR"),
            ent("amount", "120,00 EUR"),
        ],
    },
    {
        "id": "02-contract",
        "title": "Contrat et parties",
        "paragraphs": [
            "Contrat CONTRAT-DEMO-042 entre Organisation Beta et Organisation Gamma.",
            "Les représentants sont Personne Alpha et Personne Beta.",
            "Signature : 3 février 2026. Valeur du contrat : 9 500,00 EUR.",
        ],
        "gold": [
            ent("ref", "CONTRAT-DEMO-042"),
            ent("org", "Organisation Beta"),
            ent("org", "Organisation Gamma"),
            ent("person", "Personne Alpha"),
            ent("person", "Personne Beta"),
            ent("date", "3 février 2026"),
            ent("amount", "9 500,00 EUR"),
        ],
    },
    {
        "id": "03-letter",
        "title": "Courrier administratif",
        "paragraphs": [
            "Dossier DOSSIER-DEMO-007. Le 8 mars 2026.",
            "Organisation Delta confirme la réception de la demande de Personne Gamma.",
            "Pour toute question : contact@example.invalid. Aucun paiement demandé.",
        ],
        "gold": [
            ent("ref", "DOSSIER-DEMO-007"),
            ent("date", "8 mars 2026"),
            ent("org", "Organisation Delta"),
            ent("person", "Personne Gamma"),
            ent("email", "contact@example.invalid"),
        ],
    },
    {
        "id": "04-table",
        "title": "Tableau de commandes",
        "paragraphs": ["Commandes de Organisation Epsilon."],
        "table": [
            ["Référence", "Échéance", "Montant"],
            ["CMD-DEMO-101", "4 avril 2026", "250,00 EUR"],
            ["CMD-DEMO-102", "5 avril 2026", "375,00 EUR"],
        ],
        "gold": [
            ent("org", "Organisation Epsilon"),
            ent("ref", "CMD-DEMO-101"),
            ent("date", "4 avril 2026"),
            ent("amount", "250,00 EUR"),
            ent("ref", "CMD-DEMO-102"),
            ent("date", "5 avril 2026"),
            ent("amount", "375,00 EUR"),
        ],
    },
    {
        "id": "05-english",
        "title": "Document en anglais",
        "paragraphs": [
            "Agreement AGREEMENT-DEMO-008. Organisation Zeta appoints Personne Delta.",
            "Effective date: 15 May 2026. Contract value: 800.00 USD.",
        ],
        "gold": [
            ent("ref", "AGREEMENT-DEMO-008"),
            ent("org", "Organisation Zeta"),
            ent("person", "Personne Delta"),
            ent("date", "15 May 2026"),
            ent("amount", "800.00 USD"),
        ],
    },
    {
        "id": "06-superseded",
        "title": "Valeurs annulées et applicables",
        "paragraphs": [
            "Organisation Eta : avis rectificatif.",
            "Ancienne proposition annulée et inapplicable : 300,00 EUR, échéance 1 juin 2026.",
            "Seule décision applicable : 450,00 EUR, échéance 2 juin 2026.",
        ],
        "gold": [
            ent("org", "Organisation Eta"),
            ent("amount", "450,00 EUR"),
            ent("date", "2 juin 2026"),
        ],
    },
    {
        "id": "07-long",
        "title": "Document long avec entités dispersées",
        "paragraphs": ["Organisation Theta présente le dossier."]
        + [
            "Le présent paragraphe décrit une procédure technique générique. Les vérifications sont effectuées sans donnée nominative ni valeur financière."
        ]
        * 22
        + ["Référence du marché : MARCHE-DEMO-203."]
        + [
            "La documentation détaille les étapes de contrôle et les conditions de réalisation. Chaque étape doit faire l’objet d’une vérification."
        ]
        * 22
        + ["La décision finale engage 1 750,00 EUR au 9 juillet 2026."],
        "gold": [
            ent("org", "Organisation Theta"),
            ent("ref", "MARCHE-DEMO-203"),
            ent("amount", "1 750,00 EUR"),
            ent("date", "9 juillet 2026"),
        ],
    },
    {
        "id": "08-accents",
        "title": "Accents et répétitions",
        "paragraphs": [
            "Organisation Été désigne Personne Émeraude pour le dossier DOSSIER-DEMO-ÉTÉ.",
            "Organisation Été confirme la décision du 6 août 2026.",
        ],
        "gold": [
            ent("org", "Organisation Été"),
            ent("person", "Personne Émeraude"),
            ent("ref", "DOSSIER-DEMO-ÉTÉ"),
            ent("org", "Organisation Été"),
            ent("date", "6 août 2026"),
        ],
    },
    {
        "id": "09-no-entities",
        "title": "Contrôle négatif sans entité",
        "paragraphs": [
            "Ce texte décrit une méthode générique. Il ne contient aucune organisation nommée, aucune personne identifiée et aucune donnée chiffrée."
        ],
        "gold": [],
    },
    {
        "id": "10-image-only",
        "title": "Contrôle négatif sans couche texte",
        "paragraphs": [],
        "gold": [],
        "expected_status": 422,
    },
]


def build():
    pdfmetrics.registerFont(
        TTFont("EvalFont", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    )
    styles = getSampleStyleSheet()
    for name in ["Normal", "Heading1"]:
        styles[name].fontName = "EvalFont"
    styles["Normal"].fontSize = 10
    styles["Normal"].leading = 15
    (ROOT / "pdfs").mkdir(exist_ok=True)
    manifest = []
    for case in CASES:
        path = ROOT / "pdfs" / f"{case['id']}.pdf"
        if case.get("expected_status") == 422:
            from PIL import Image, ImageDraw
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfgen import canvas

            image = Image.new("RGB", (800, 180), "white")
            ImageDraw.Draw(image).text(
                (30, 60),
                "Organisation Image - document scanne synthetique",
                fill="black",
            )
            c = canvas.Canvas(str(path), invariant=1)
            c.drawImage(ImageReader(image), 40, 600, width=500, height=112)
            c.save()
        else:
            story = [
                Paragraph(
                    "Corpus synthétique - " + escape(case["title"]), styles["Heading1"]
                ),
                Spacer(1, 14),
            ]
            for paragraph in case["paragraphs"]:
                story.extend(
                    [Paragraph(escape(paragraph), styles["Normal"]), Spacer(1, 8)]
                )
            if case.get("table"):
                t = Table(case["table"], colWidths=[180, 160, 140])
                t.setStyle(
                    TableStyle(
                        [
                            ("FONTNAME", (0, 0), (-1, -1), "EvalFont"),
                            ("FONTSIZE", (0, 0), (-1, -1), 10),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf4")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                            ("TOPPADDING", (0, 0), (-1, -1), 12),
                        ]
                    )
                )
                story.append(t)
            SimpleDocTemplate(
                str(path),
                leftMargin=45,
                rightMargin=45,
                topMargin=40,
                bottomMargin=40,
                invariant=1,
            ).build(story)
        with pdfplumber.open(path) as pdf:
            text = "\n\n".join(
                f"[PAGE {i}]\n{p.extract_text()}"
                for i, p in enumerate(pdf.pages, 1)
                if (p.extract_text() or "").strip()
            )
            pages = len(pdf.pages)
        # Validate the authored references against the actual PDF text layer.
        import re

        normalized = lambda x: re.sub(r"\s+", " ", x).strip()
        for expected in case["gold"]:
            assert normalized(expected["text"]) in normalized(text), (
                case["id"],
                expected,
            )
        manifest.append(
            {
                **case,
                "pdf": str(path.relative_to(ROOT)),
                "pages": pages,
                "text_characters": len(text),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (ROOT / "corpus.json").write_text(
        json.dumps({"prompt": PROMPT, "cases": manifest}, ensure_ascii=False, indent=2)
        + "\n"
    )
    print(
        json.dumps(
            {
                "cases": len(manifest),
                "reference_entities": sum(len(c["gold"]) for c in manifest),
                "pages": sum(c["pages"] for c in manifest),
            }
        )
    )


if __name__ == "__main__":
    build()
