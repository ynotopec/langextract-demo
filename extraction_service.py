"""PDF extraction and exports, independent of the HTTP interface."""

import json
import os
import tempfile
import textwrap

import langextract as lx
from langextract import factory as lxf

from extraction_errors import PDFInputError, extraction_stage
from extraction_support import NullSafeFormatHandler, pdf_to_text

DEFAULT_PROMPT = textwrap.dedent(
    """\
    Tâche : extraire des entités métier depuis un PDF (français/anglais).
    Règles :
    - Utiliser uniquement des extraits exacts du texte.
    - Ne pas faire chevaucher les extraits.
    - Attributs utiles si présents : date, montant, devise, email, IBAN, SIREN/SIRET, adresse, téléphone.
    - Classes : person, org, invoice, date, amount, email, iban, address, phone, ref.
    - Ne pas inventer de données absentes.
    - Omettre les entités absentes : ne jamais produire de valeur null ou vide.
    - Si aucune entité n’est présente, retourner une liste extractions vide.
    """
)

EXAMPLES = [
    lx.data.ExampleData(
        text="FACTURE n° 2024-0915 — Client: ACME SAS — Montant: 1 250,00 EUR — Contact: billing@acme.fr — IBAN: FR76 3000 6000 0112 3456 7890 189",
        extractions=[
            lx.data.Extraction(
                extraction_class="invoice",
                extraction_text="FACTURE n° 2024-0915",
                attributes={"number": "2024-0915"},
            ),
            lx.data.Extraction(extraction_class="org", extraction_text="ACME SAS"),
            lx.data.Extraction(
                extraction_class="amount",
                extraction_text="1 250,00 EUR",
                attributes={"value": "1250.00", "currency": "EUR"},
            ),
            lx.data.Extraction(
                extraction_class="email", extraction_text="billing@acme.fr"
            ),
            lx.data.Extraction(
                extraction_class="iban",
                extraction_text="FR76 3000 6000 0112 3456 7890 189",
            ),
        ],
    )
]


def extract_pdf(content: bytes, options, settings) -> dict:
    try:
        text, skipped_pages = pdf_to_text(content)
    except Exception as exc:
        raise PDFInputError(
            "Impossible de lire ce PDF : fichier invalide, chiffré ou endommagé."
        ) from exc
    if not text.strip():
        raise PDFInputError("Aucun texte trouvé. Un OCR peut être nécessaire en amont.")
    if len(text) > settings.max_text_chars:
        raise PDFInputError(
            "Le texte du PDF dépasse la limite de caractères autorisée."
        )
    output_format = (
        lx.data.FormatType.JSON if settings.json_mode else lx.data.FormatType.YAML
    )
    handler = NullSafeFormatHandler(format_type=output_format, use_fences=True)
    with extraction_stage("inference"):
        result = lx.extract(
            text_or_documents=text,
            prompt_description=options.prompt,
            examples=EXAMPLES,
            format_type=output_format,
            resolver_params={"format_handler": handler, "suppress_parse_errors": False},
            config=lxf.ModelConfig(
                model_id=settings.model,
                provider="openai",
                provider_kwargs={
                    "base_url": settings.base_url,
                    "api_key": settings.model_key,
                    "format_type": output_format,
                    "max_workers": options.max_workers,
                },
            ),
            fence_output=True,
            use_schema_constraints=False,
            extraction_passes=options.extraction_passes,
            max_workers=options.max_workers,
            max_char_buffer=options.max_char_buffer,
            show_progress=False,
        )
    with extraction_stage("export"), tempfile.TemporaryDirectory() as temp_dir:
        path = os.path.join(temp_dir, "extractions.jsonl")
        lx.io.save_annotated_documents(
            [result], output_name="extractions.jsonl", output_dir=temp_dir
        )
        with open(path, encoding="utf-8") as handle:
            jsonl = handle.read()
        with extraction_stage("visualization"):
            html = lx.visualize(path)
        html = html.data if hasattr(html, "data") else html
        document = json.loads(jsonl)
    warnings = []
    if skipped_pages:
        warnings.append(
            "Pages sans texte ou illisibles ignorées : "
            + ", ".join(map(str, skipped_pages))
            + ". Un OCR peut être nécessaire."
        )
    if handler.omitted_entities:
        warnings.append(
            f"{handler.omitted_entities} entité(s) nulles ignorées ; vérifiez le résultat."
        )
    return {
        "document": document,
        "jsonl": jsonl,
        "html": html,
        "warnings": warnings,
        "skipped_pages": skipped_pages,
        "omitted_entities": handler.omitted_entities,
        "text": text if options.include_text else None,
    }
