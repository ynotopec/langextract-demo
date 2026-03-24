import io
import os
import tempfile
import textwrap

import langextract as lx
import pdfplumber
import streamlit as st

OPENAI_API_MODEL = os.getenv("OPENAI_API_MODEL", "mistral-small-vllm")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

try:
    from langextract import inference as lxi

    OPENAI_MODEL_TYPE = getattr(lxi, "OpenAILanguageModel", None)
except Exception:
    OPENAI_MODEL_TYPE = None

st.set_page_config(page_title="PDF → LangExtract", page_icon="📄", layout="wide")
st.title("📄 PDF → LangExtract")


def mask_secret(secret: str | None) -> str:
    if not secret:
        return "(missing)"
    return secret[:4] + "…" + secret[-4:] if len(secret) > 8 else "****"


with st.sidebar:
    st.header("Environment")
    st.write(f"**OPENAI_API_MODEL**: `{OPENAI_API_MODEL}`")
    st.write(f"**OPENAI_API_BASE**: `{OPENAI_API_BASE}`")
    st.write(f"**OPENAI_API_KEY**: `{mask_secret(OPENAI_API_KEY)}`")
    st.divider()
    extraction_passes = st.slider("Extraction passes", 1, 5, 2)
    max_workers = st.slider("Max workers", 1, 24, 8)
    max_char_buffer = st.slider("Max char buffer", 500, 4000, 1200, step=100)
    show_raw_text = st.checkbox("Show extracted text", value=False)

DEFAULT_PROMPT = textwrap.dedent(
    """\
    Task: extract business entities from a PDF (French/English).
    Rules:
    - Use exact text spans only.
    - No overlapping spans.
    - Useful attributes if present: date, amount, currency, email, IBAN, SIREN/SIRET, address, phone.
    - Classes: person, org, invoice, date, amount, email, iban, address, phone, ref.
    - Do not invent missing data.
    """
)

st.subheader("Extraction instructions")
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
pdf_file = st.file_uploader("Upload a PDF", type=["pdf"])


def pdf_to_text(file_data: bytes) -> str:
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(file_data)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(f"[PAGE {index}]\n{page_text}")
    return "\n\n".join(pages)


def missing_env() -> list[str]:
    checks = [
        ("OPENAI_API_MODEL", OPENAI_API_MODEL),
        ("OPENAI_API_BASE", OPENAI_API_BASE),
        ("OPENAI_API_KEY", OPENAI_API_KEY),
    ]
    return [name for name, value in checks if not value]


if st.button("🚀 Run extraction", disabled=pdf_file is None):
    missing = missing_env()
    if missing:
        st.error("Missing environment variables: " + ", ".join(missing))
        st.stop()

    with st.spinner("Reading PDF..."):
        content = pdf_file.read() if pdf_file else b""
        text = pdf_to_text(content) if content else ""
        if not text.strip():
            st.error("No text found. If this is a scanned PDF, run OCR first.")
            st.stop()

    if show_raw_text:
        with st.expander("Extracted text (preview)"):
            st.text(text[:50000])

    extract_kwargs = {
        "text_or_documents": text,
        "prompt_description": prompt,
        "examples": examples,
        "model_id": OPENAI_API_MODEL,
        "api_key": OPENAI_API_KEY,
        "fence_output": True,
        "use_schema_constraints": False,
        "language_model_params": {"base_url": OPENAI_API_BASE},
        "extraction_passes": extraction_passes,
        "max_workers": max_workers,
        "max_char_buffer": max_char_buffer,
    }
    if OPENAI_MODEL_TYPE is not None:
        extract_kwargs["language_model_type"] = OPENAI_MODEL_TYPE

    with st.spinner("Running extraction..."):
        try:
            result = lx.extract(**extract_kwargs)
        except Exception as exc:
            st.error(f"Inference failed: {exc}")
            st.stop()

    with tempfile.TemporaryDirectory() as temp_dir:
        jsonl_path = os.path.join(temp_dir, "extractions.jsonl")
        lx.io.save_annotated_documents([result], output_name="extractions.jsonl", output_dir=temp_dir)

        html = lx.visualize(jsonl_path)
        html_content = html.data if hasattr(html, "data") else html
        html_bytes = html_content.encode("utf-8")

        st.success("Extraction complete ✅")
        st.subheader("JSON summary")
        st.json(result.model_dump() if hasattr(result, "model_dump") else result)

        col1, col2 = st.columns(2)
        with col1:
            with open(jsonl_path, "rb") as handle:
                st.download_button(
                    "⬇️ Download JSONL",
                    data=handle.read(),
                    file_name="extractions.jsonl",
                    mime="application/jsonl",
                    use_container_width=True,
                )
        with col2:
            st.download_button(
                "⬇️ Download visualization (HTML)",
                data=html_bytes,
                file_name="visualization_langextract.html",
                mime="text/html",
                use_container_width=True,
            )

        st.subheader("Visualization preview")
        st.components.v1.html(html_content, height=520, scrolling=True)
