# app.py — Streamlit PDF → LangExtract (OpenAI-only via env + base_url)
# Lancer : python -m streamlit run app.py

import os
import io
import textwrap
import tempfile
import streamlit as st
import pdfplumber

# ==== Variables d'environnement requises ====
OPENAI_API_MODEL = os.getenv("OPENAI_API_MODEL", "mistral-small-vllm")
OPENAI_API_BASE  = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")

# ==== Importer LangExtract après avoir lu l'env ====
import langextract as lx

# Optionnel mais utile pour VRAIMENT forcer OpenAI :
# (présent depuis les versions 1.0.3+)
try:
    from langextract import inference as lxi
    OpenAILM = getattr(lxi, "OpenAILanguageModel", None)
except Exception:
    OpenAILM = None  # on restera sur l'auto-résolution + api_key + base_url

# ==== UI Streamlit ====
st.set_page_config(page_title="PDF → LangExtract (OpenAI-only)", page_icon="📄", layout="wide")
st.title("📄 PDF → LangExtract — OpenAI (endpoint compatible)")

def _mask(s: str | None) -> str:
    if not s: return "(absent)"
    return s[:4] + "…" + s[-4:] if len(s) > 8 else "****"

with st.sidebar:
    st.header("Environnement")
    st.write(f"**OPENAI_API_MODEL** = `{OPENAI_API_MODEL}`")
    st.write(f"**OPENAI_API_BASE**  = `{OPENAI_API_BASE}`")
    st.write(f"**OPENAI_API_KEY**   = `{_mask(OPENAI_API_KEY)}`")
    st.divider()
    passes = st.slider("Extraction passes", 1, 5, 2)
    max_workers = st.slider("Max workers", 1, 24, 8)
    max_char_buffer = st.slider("Max char buffer", 500, 4000, 1200, step=100)
    show_raw_text = st.checkbox("Afficher le texte extrait", value=False)
    st.caption("Si le PDF est scanné, faites un OCR en amont (ex: ocrmypdf).")

# ==== Prompt & few-shot par défaut ====
default_prompt = textwrap.dedent("""\
    Tâche: extraire des entités business d'un PDF (français/anglais).
    RÈGLES:
    - Utiliser le texte exact (pas de paraphrase).
    - Pas de chevauchement de spans.
    - Attributs utiles si présents: date, montant, devise, email, IBAN, SIREN/SIRET, adresse, téléphone.
    - Classes possibles: person, org, invoice, date, amount, email, iban, address, phone, ref.
    - Ne rien inventer si absent.
""")
st.subheader("Instructions d’extraction")
prompt = st.text_area("Prompt", value=default_prompt, height=200)

examples = [
    lx.data.ExampleData(
        text="FACTURE n° 2024-0915 — Client: ACME SAS — Montant: 1 250,00 EUR — Contact: billing@acme.fr — IBAN: FR76 3000 6000 0112 3456 7890 189",
        extractions=[
            lx.data.Extraction(extraction_class="invoice", extraction_text="FACTURE n° 2024-0915", attributes={"number": "2024-0915"}),
            lx.data.Extraction(extraction_class="org", extraction_text="ACME SAS"),
            lx.data.Extraction(extraction_class="amount", extraction_text="1 250,00 EUR", attributes={"value": "1250.00", "currency": "EUR"}),
            lx.data.Extraction(extraction_class="email", extraction_text="billing@acme.fr"),
            lx.data.Extraction(extraction_class="iban", extraction_text="FR76 3000 6000 0112 3456 7890 189"),
        ],
    )
]

# ==== Upload PDF ====
st.subheader("PDF")
pdf_file = st.file_uploader("Déposez un PDF", type=["pdf"])

def pdf_to_text(fp: io.BytesIO) -> str:
    chunks = []
    with pdfplumber.open(fp) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                chunks.append(f"[PAGE {i}]\n{t}")
    return "\n\n".join(chunks)

def missing_env() -> list[str]:
    return [n for n, v in [
        ("OPENAI_API_MODEL", OPENAI_API_MODEL),
        ("OPENAI_API_BASE",  OPENAI_API_BASE),
        ("OPENAI_API_KEY",   OPENAI_API_KEY),
    ] if not v]

# ==== Action ====
if st.button("🚀 Lancer l’extraction", disabled=pdf_file is None):
    miss = missing_env()
    if miss:
        st.error("Variables manquantes: " + ", ".join(miss))
        st.stop()

    with st.spinner("Lecture du PDF…"):
        raw = pdf_file.read() if pdf_file else b""
        text = pdf_to_text(io.BytesIO(raw)) if raw else ""
        if not text.strip():
            st.error("Aucun texte détecté (PDF scanné ? faites un OCR d’abord).")
            st.stop()

    if show_raw_text:
        with st.expander("Texte extrait (aperçu)"):
            st.text(text[:50_000] if len(text) > 50_000 else text)

    # ==== Appel LangExtract (OpenAI seulement) ====
    # - On force le backend OpenAI via language_model_type quand dispo
    # - On passe base_url pour cibler un endpoint OpenAI-compatible (vLLM, etc.)
    extract_kwargs = dict(
        text_or_documents=text,
        prompt_description=prompt,
        examples=examples,
        model_id=OPENAI_API_MODEL,
        api_key=OPENAI_API_KEY,          # clé OpenAI (ou proxy compatible)
        fence_output=True,               # requis pour OpenAI
        use_schema_constraints=False,    # recommandé pour OpenAI
        language_model_params={"base_url": OPENAI_API_BASE},
        extraction_passes=passes,
        max_workers=max_workers,
        max_char_buffer=max_char_buffer,
    )
    if OpenAILM is not None:
        extract_kwargs["language_model_type"] = OpenAILM  # forcer le provider

    with st.spinner("Extraction (OpenAI)…"):
        try:
            result = lx.extract(**extract_kwargs)
        except Exception as e:
            st.error(f"Échec d'inférence: {e}")
            st.stop()

    # ==== Sorties ====
    with tempfile.TemporaryDirectory() as tmpd:
        jsonl_path = os.path.join(tmpd, "extractions.jsonl")
        lx.io.save_annotated_documents([result], output_name="extractions.jsonl", output_dir=tmpd)
        html = lx.visualize(jsonl_path)
        html_bytes = (html.data if hasattr(html, "data") else html).encode("utf-8")

        st.success("Extraction terminée ✅")
        st.subheader("Résumé JSON")
        try:
            st.json(result.model_dump() if hasattr(result, "model_dump") else result)
        except Exception:
            st.write(result)

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ Télécharger JSONL",
                data=open(jsonl_path, "rb").read(),
                file_name="extractions.jsonl",
                mime="application/jsonl",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "⬇️ Télécharger la visualisation (HTML)",
                data=html_bytes,
                file_name="visualisation_langextract.html",
                mime="text/html",
                use_container_width=True,
            )

        st.subheader("Aperçu de la visualisation")
        st.components.v1.html(html_bytes.decode("utf-8"), height=520, scrolling=True)
