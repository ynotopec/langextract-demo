import json
from types import SimpleNamespace
from unittest.mock import patch

import langextract as lx
import pytest
from langextract import factory
from langextract.resolver import Resolver, ResolverParsingError

from extraction_support import NullSafeFormatHandler, pdf_to_text


@pytest.mark.parametrize(
    "format_type", [lx.data.FormatType.JSON, lx.data.FormatType.YAML]
)
def test_real_provider_keeps_valid_entities_and_export(endpoint, tmp_path, format_type):
    url, requests = endpoint
    handler = NullSafeFormatHandler(format_type=format_type, use_fences=True)
    result = lx.extract(
        text_or_documents="ACME paid 42.",
        prompt_description="Extract present entities; omit null values.",
        examples=[
            lx.data.ExampleData(
                text="ACME",
                extractions=[
                    lx.data.Extraction(extraction_class="org", extraction_text="ACME")
                ],
            )
        ],
        config=factory.ModelConfig(
            model_id="ai-flash",
            provider="openai",
            provider_kwargs={
                "api_key": "test",
                "base_url": url,
                "format_type": format_type,
            },
        ),
        format_type=format_type,
        fence_output=True,
        use_schema_constraints=False,
        resolver_params={"format_handler": handler, "suppress_parse_errors": False},
        extraction_passes=2,
        show_progress=False,
    )
    assert [(e.extraction_class, e.extraction_text) for e in result.extractions] == [
        ("org", "ACME"),
        ("amount", "42"),
    ]
    assert handler.omitted_entities == 2
    assert len(requests) == 2
    assert ("response_format" in requests[0]) == (
        format_type == lx.data.FormatType.JSON
    )
    lx.io.save_annotated_documents(
        [result], output_name="result.jsonl", output_dir=str(tmp_path)
    )
    exported = json.loads((tmp_path / "result.jsonl").read_text())
    assert len(exported["extractions"]) == 2
    assert lx.visualize(str(tmp_path / "result.jsonl"))


def test_normal_resolver_reproduces_null_failure():
    with pytest.raises((ResolverParsingError, ValueError)):
        Resolver().resolve('{"extractions": [{"org": "ACME"}, {"email": null}]}')


@pytest.mark.parametrize("value", ["[]", "{}"])
def test_other_invalid_entity_types_still_fail(value):
    handler = NullSafeFormatHandler()
    with pytest.raises((ResolverParsingError, ValueError)):
        Resolver(format_handler=handler).resolve(
            '{"extractions": [{"org": "ACME"}, {"email": ' + value + "}]}"
        )


def test_null_attributes_are_not_counted_or_removed():
    handler = NullSafeFormatHandler()
    assert handler.parse_output(
        '{"extractions": [{"org": "ACME", "org_attributes": null}]}'
    ) == [{"org": "ACME", "org_attributes": None}]
    assert handler.omitted_entities == 0
    assert handler.parse_output('{"extractions": [{"email": null}]}') == [{}]


def test_pdf_skips_bad_and_empty_pages_with_original_page_numbers():
    good = SimpleNamespace(extract_text=lambda: "ACME")
    blank = SimpleNamespace(extract_text=lambda: "")

    def broken():
        raise ValueError("bad page")

    pdf = SimpleNamespace(
        pages=[good, SimpleNamespace(extract_text=broken), blank, good]
    )
    with patch("extraction_support.pdfplumber.open") as opened:
        opened.return_value.__enter__.return_value = pdf
        text, skipped = pdf_to_text(b"pdf")
    assert text == "[PAGE 1]\nACME\n\n[PAGE 4]\nACME"
    assert skipped == [2, 3]
