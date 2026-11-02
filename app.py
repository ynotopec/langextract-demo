import json
import os
import tempfile
import textwrap

import langextract as lx
from langextract import factory as lxf
import streamlit as st

from extraction_support import NullSafeFormatHandler, pdf_to_text

OPENAI_API_MODEL = os.getenv("OPENAI_API_MODEL", "mistral-small-vllm")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USE_OPENAI_JSON_MODE = os.getenv("USE_OPENAI_JSON_MODE", "1").strip().lower() in {"1", "true", "yes"}

st.set_page_config(page_title="PDF → LangExtract", page_icon="📄", layout="wide")
st.title("📄 PDF → LangExtract")


def mask_secret(secret: str | None) -> str:
    if not secret:
        return "(absent)"
    return secret[:4] + "…" + secret[-4:] if len(secret) > 8 else "****"


with st.sidebar:
    st.header("Environnement")
    st.write("**Provider** : `openai` (endpoint compatible)")
    st.write(f"**OPENAI_API_MODEL**: `{OPENAI_API_MODEL}`")
    st.write(f"**OPENAI_API_BASE**: `{OPENAI_API_BASE}`")
    st.write(f"**OPENAI_API_KEY**: `{mask_secret(OPENAI_API_KEY)}`")
    st.divider()
    extraction_passes = st.slider("Passes d’extraction", 1, 5, 2)
    max_workers = st.slider("Requêtes parallèles", 1, 24, 8)
    max_char_buffer = st.slider("Caractères par segment", 500, 4000, 1200, step=100)
    show_raw_text = st.checkbox("Afficher le texte extrait", value=False)

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

st.subheader("Instructions d’extraction")
prompt = st.text_area("Prompt", value=DEFAULT_PROMPT, height=200)

examples = [
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
            lx.data.Extraction(extraction_class="email", extraction_text="billing@acme.fr"),
            lx.data.Extraction(
                extraction_class="iban", extraction_text="FR76 3000 6000 0112 3456 7890 189"
            ),
        ],
    )
]

st.subheader("PDF")
pdf_file = st.file_uploader("Déposez un PDF", type=["pdf"])


def missing_env() -> list[str]:
    checks = [
        ("OPENAI_API_MODEL", OPENAI_API_MODEL),
        ("OPENAI_API_BASE", OPENAI_API_BASE),
        ("OPENAI_API_KEY", OPENAI_API_KEY),
    ]
    return [name for name, value in checks if not value]


def format_inference_error(exc: Exception) -> str:
    """Return a clearer, actionable inference error message for known providers."""
    message = str(exc)
    lowered = message.lower()
    if "src property must be a valid json object" in lowered:
        return (
            f"{message}\n\n"
            "L’endpoint a rejeté le mode JSON. Essayez USE_OPENAI_JSON_MODE=0 "
            "dans .env pour demander une sortie YAML."
        )
    return message


if st.button("🚀 Lancer l’extraction", disabled=pdf_file is None):
    missing = missing_env()
    if missing:
        st.error("Variables d’environnement manquantes : " + ", ".join(missing))
        st.stop()

    with st.spinner("Lecture du PDF…"):
        content = pdf_file.read() if pdf_file else b""
        try:
            text, skipped_pages = pdf_to_text(content) if content else ("", [])
        except Exception:
            st.error("Impossible de lire ce PDF : fichier invalide, chiffré ou endommagé.")
            st.stop()
        if skipped_pages:
            st.warning(
                "Pages sans texte exploitable ou illisibles, ignorées : "
                + ", ".join(map(str, skipped_pages))
                + ". Un OCR peut être nécessaire."
            )
        if not text.strip():
            st.error("Aucun texte trouvé. Si le PDF est scanné, effectuer un OCR au préalable.")
            st.stop()

    if show_raw_text:
        with st.expander("Texte extrait (aperçu)"):
            st.text(text[:50000])

    output_format = lx.data.FormatType.JSON if USE_OPENAI_JSON_MODE else lx.data.FormatType.YAML
    handler = NullSafeFormatHandler(format_type=output_format, use_fences=True)
    extract_kwargs = {
        "text_or_documents": text,
        "prompt_description": prompt,
        "examples": examples,
        "format_type": output_format,
        "resolver_params": {"format_handler": handler, "suppress_parse_errors": False},
        "config": lxf.ModelConfig(
            model_id=OPENAI_API_MODEL,
            provider="openai",
            provider_kwargs={
                "base_url": OPENAI_API_BASE,
                "api_key": OPENAI_API_KEY,
                "format_type": output_format,
                "max_workers": max_workers,
            },
        ),
        "fence_output": True,
        "use_schema_constraints": False,
        "extraction_passes": extraction_passes,
        "max_workers": max_workers,
        "max_char_buffer": max_char_buffer,
    }

    with st.spinner("Extraction…"):
        try:
            result = lx.extract(**extract_kwargs)
        except Exception as exc:
            st.error(f"Échec de l’inférence : {format_inference_error(exc)}")
            st.stop()

    if handler.omitted_entities:
        st.warning(
            f"Le modèle a produit {handler.omitted_entities} entité(s) nulles, ignorées. "
            "Les entités valides ont été conservées ; vérifiez le résultat."
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        jsonl_path = os.path.join(temp_dir, "extractions.jsonl")
        lx.io.save_annotated_documents([result], output_name="extractions.jsonl", output_dir=temp_dir)

        html = lx.visualize(jsonl_path)
        html_content = html.data if hasattr(html, "data") else html
        html_bytes = html_content.encode("utf-8")

        st.success("Extraction terminée ✅")
        st.subheader("Résumé JSON")
        with open(jsonl_path, encoding="utf-8") as handle:
            st.json(json.loads(handle.readline()))

        col1, col2 = st.columns(2)
        with col1:
            with open(jsonl_path, "rb") as handle:
                st.download_button(
                    "⬇️ Télécharger JSONL",
                    data=handle.read(),
                    file_name="extractions.jsonl",
                    mime="application/jsonl",
                    use_container_width=True,
                )
        with col2:
            st.download_button(
                "⬇️ Télécharger la visualisation (HTML)",
                data=html_bytes,
                file_name="visualization_langextract.html",
                mime="text/html",
                use_container_width=True,
            )

        st.subheader("Aperçu de la visualisation")
        st.components.v1.html(html_content, height=520, scrolling=True)
