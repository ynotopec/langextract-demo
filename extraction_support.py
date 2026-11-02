"""Small compatibility helpers for PDF and model output handling."""

import io

import pdfplumber
from langextract.core.format_handler import FormatHandler


class NullSafeFormatHandler(FormatHandler):
    """Omit null entities without dropping valid entities in the same chunk.

    A null attribute dictionary is valid LangExtract output and is preserved.
    Other malformed output still raises through the normal resolver.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.omitted_entities = 0

    def parse_output(self, text, *, strict=None):
        groups = super().parse_output(text, strict=strict)
        cleaned = []
        for group in groups:
            omitted = {
                key for key, value in group.items()
                if value is None and not key.endswith(self.attribute_suffix)
            }
            self.omitted_entities += len(omitted)
            removed_keys = omitted | {name + self.attribute_suffix for name in omitted}
            cleaned.append({
                key: value for key, value in group.items()
                if key not in removed_keys
            })
        return cleaned


def pdf_to_text(file_data: bytes) -> tuple[str, list[int]]:
    """Return text and page numbers that could not be read (including scans)."""
    pages = []
    skipped_pages = []
    with pdfplumber.open(io.BytesIO(file_data)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text.strip():
                pages.append(f"[PAGE {index}]\n{text}")
            else:
                skipped_pages.append(index)
    return "\n\n".join(pages), skipped_pages
