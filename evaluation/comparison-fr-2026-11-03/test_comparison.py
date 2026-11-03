import json

import httpx
import pytest
from compare import PARAMETERS, Transport, align_direct, parse_direct


def test_baseline_aligns_repeated_unicode_entities_without_reusing_occurrence():
    text = "😀 Société Démo\nAster puis Société Démo Aster"
    entities = [
        {"extraction_class": "org", "extraction_text": "Société Démo Aster"}
        for _ in range(2)
    ]
    result = align_direct(text, entities)
    spans = [e["char_interval"] for e in result]
    assert spans[0] != spans[1]
    for span in spans:
        assert (
            " ".join(text[span["start_pos"] : span["end_pos"]].split())
            == "Société Démo Aster"
        )


def test_baseline_format_errors_are_not_converted_into_empty_successes():
    with pytest.raises(ValueError):
        parse_direct('{"org":"Aster"}', "Aster")
    with pytest.raises(ValueError):
        parse_direct('{"extractions":[{"org":[]}]}', "Aster")
    assert (
        parse_direct('{"extractions":[]}', "texte neutre")["document"]["extractions"]
        == []
    )


def test_baseline_null_values_match_null_safe_policy():
    result = parse_direct(
        '{"extractions":[{"org":null},{"amount":"50 EUR"}]}', "50 EUR"
    )
    assert len(result["document"]["extractions"]) == 1


def test_meter_redacts_token_even_if_upstream_echoes_it():
    token = "SYNTHETIC-TEST-ONLY-SECRET"
    transport = Transport("https://provider.invalid/v1", token)
    transport.client.close()

    def handle(request):
        assert request.headers["Authorization"] == "Bearer " + token
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"extractions":[]}'},
                        "finish_reason": "stop",
                    }
                ],
                "echo": token,
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 3,
                    "total_tokens": 15,
                },
            },
        )

    transport.client = httpx.Client(transport=httpx.MockTransport(handle))
    transport.request({"model": "ai-flash", **PARAMETERS, "messages": []})
    assert token not in json.dumps(transport.calls)
    assert transport.calls[0]["response"]["usage"]["total_tokens"] == 15
    transport.client.close()
