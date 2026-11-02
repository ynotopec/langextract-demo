import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import ExtractionOptions, Settings, create_app
from extraction_service import extract_pdf

TOKEN = "Synthetic-api-test-token-000000000000"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
CONFIG = Settings(
    api_token=TOKEN,
    model="ai-flash",
    base_url="http://127.0.0.1:1/v1",
    model_key="synthetic-model-key",
)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(CONFIG, tmp_path)) as client:
        yield client


def upload(client, **kwargs):
    return client.post(
        "/api/v1/extractions",
        headers=HEADERS,
        files={"file": ("test.pdf", b"%PDF-test", "application/pdf")},
        **kwargs,
    )


@pytest.mark.parametrize(
    "path,method", [("/api/v1/config", "get"), ("/api/v1/extractions", "post")]
)
def test_token_required_before_processing(client, path, method):
    for headers in [
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Basic wrong"},
    ]:
        response = (
            getattr(client, method)(path, headers=headers, content=b"not multipart")
            if method == "post"
            else client.get(path, headers=headers)
        )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_config_has_no_secrets_or_endpoint(client):
    response = client.get("/api/v1/config", headers=HEADERS)
    assert response.status_code == 200
    assert CONFIG.api_token not in response.text
    assert CONFIG.model_key not in response.text
    assert CONFIG.base_url not in response.text
    assert response.json()["defaults"]["extraction_passes"] == 2
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/healthz").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/v1/extractions"]["post"]["security"] == [
        {"HTTPBearer": []}
    ]


@pytest.mark.parametrize(
    "token",
    [
        "",
        "Aa1!aaa",
        "aa1!aaaa",
        "AA1!AAAA",
        "Aaa!aaaa",
        "Aa12aaaa",
        "Aa1! aaab",
        "Aa1!aaa\t",
        "replace-with-a-random-token-at-least-32-characters",
    ],
)
def test_startup_fails_without_configured_token(token):
    with (
        pytest.raises(RuntimeError, match="API_TOKEN"),
        TestClient(create_app(replace(CONFIG, api_token=token))),
    ):
        pass


def test_startup_fails_without_provider_key():
    with (
        pytest.raises(RuntimeError, match="OPENAI_API_KEY"),
        TestClient(create_app(replace(CONFIG, model_key=""))),
    ):
        pass


def test_bad_pdf_and_options_do_not_invoke_model(client):
    with patch("app.extract_pdf") as extract:
        assert (
            client.post(
                "/api/v1/extractions",
                headers=HEADERS,
                files={"file": ("fake.pdf", b"no pdf")},
            ).status_code
            == 422
        )
        for options in [
            "not-json",
            '{"max_workers":25}',
            '{"extraction_passes":0}',
            '{"prompt":""}',
            '{"max_char_buffer":499}',
        ]:
            assert upload(client, data={"options": options}).status_code == 422
        assert (
            client.post(
                "/api/v1/extractions", headers=HEADERS, data={"options": "{}"}
            ).status_code
            == 415
        )
        assert (
            client.post(
                "/api/v1/extractions",
                headers=HEADERS,
                files={"other": ("a.pdf", b"%PDF-test")},
            ).status_code
            == 422
        )
        extract.assert_not_called()


def test_oversized_file_and_chunked_body(tmp_path):
    with TestClient(
        create_app(replace(CONFIG, max_upload_bytes=10), tmp_path)
    ) as client:
        assert (
            client.post(
                "/api/v1/extractions",
                headers=HEADERS,
                files={"file": ("a.pdf", b"%PDF-" + b"x" * 12)},
            ).status_code
            == 413
        )

        # No Content-Length: stream enforcement must also reject large requests.
        def chunks():
            yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n%PDF-'
            for _ in range(20):
                yield b"x" * 4096
            yield b"\r\n--boundary--\r\n"

        response = client.post(
            "/api/v1/extractions",
            headers={
                **HEADERS,
                "Content-Type": "multipart/form-data; boundary=boundary",
            },
            content=chunks(),
        )
        assert response.status_code == 413


def test_provider_error_does_not_leak_credentials(client):
    with patch(
        "app.extract_pdf",
        side_effect=RuntimeError(f"provider leaked {CONFIG.model_key}"),
    ):
        response = upload(client)
    assert response.status_code == 502
    assert CONFIG.model_key not in response.text
    assert client.get("/healthz").status_code == 200


def test_concurrency_rejects_second_job_and_releases_slot(client):
    started, release = threading.Event(), threading.Event()
    result = {
        "document": {},
        "jsonl": "{}\n",
        "html": "<p>ok</p>",
        "warnings": [],
        "skipped_pages": [],
        "omitted_entities": 0,
        "text": None,
    }

    def slow(*args):
        started.set()
        assert release.wait(10)
        return result

    with patch("app.extract_pdf", side_effect=slow), ThreadPoolExecutor() as executor:
        first = executor.submit(upload, client)
        try:
            assert started.wait(5)
            assert client.get("/healthz").status_code == 200
            rejected = upload(client)
            assert rejected.status_code == 503
            assert rejected.headers["retry-after"] == "5"
        finally:
            release.set()
        assert first.result().status_code == 200
        assert upload(client).status_code == 200


def test_real_extraction_pipeline_through_api(endpoint, tmp_path):
    url, requests = endpoint
    with (
        TestClient(create_app(replace(CONFIG, base_url=url), tmp_path)) as client,
        patch("extraction_service.pdf_to_text", return_value=("ACME paid 42.", [2])),
    ):
        response = upload(client, data={"options": json.dumps({"include_text": True})})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(requests) == 2
    assert result["omitted_entities"] == 2
    assert result["skipped_pages"] == [2]
    assert len(result["warnings"]) == 2
    assert result["text"] == "ACME paid 42."
    assert len(json.loads(result["jsonl"])["extractions"]) == 2
    assert "ACME" in result["html"]


def test_scanned_or_invalid_pdf_is_actionable(client):
    with patch("extraction_service.pdf_to_text", return_value=("", [1])):
        response = upload(client)
    assert response.status_code == 422
    assert "OCR" in response.text
    with patch("extraction_service.pdf_to_text", side_effect=ValueError("invalid")):
        assert upload(client).status_code == 422


def test_text_size_limit_prevents_inference():
    with (
        patch("extraction_service.pdf_to_text", return_value=("x" * 11, [])),
        patch("extraction_service.lx.extract") as extract,
    ):
        with pytest.raises(ValueError, match="limite"):
            extract_pdf(
                b"%PDF-", ExtractionOptions(), replace(CONFIG, max_text_chars=10)
            )
        extract.assert_not_called()


def test_static_frontend_and_api_not_found(tmp_path):
    (tmp_path / "index.html").write_text('<html lang="fr">Frontend</html>')
    with TestClient(create_app(CONFIG, tmp_path)) as client:
        assert "Frontend" in client.get("/").text
        assert client.get("/api/v1/missing", headers=HEADERS).status_code == 404


@pytest.mark.parametrize(
    "token", ["Aa1!aaaa", "Aa1$aaaa", "Aa1#aaaa", "Aa1~aaaa", "Aa1${aa}"]
)
def test_eight_character_tokens_with_each_required_category_are_accepted(
    token, tmp_path
):
    with TestClient(create_app(replace(CONFIG, api_token=token), tmp_path)) as client:
        assert (
            client.get(
                "/api/v1/config", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/v1/config", headers={"Authorization": f"Bearer {token}wrong"}
            ).status_code
            == 401
        )
