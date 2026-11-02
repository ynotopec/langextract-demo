import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import langextract as lx
import pytest
from langextract import factory
from langextract.resolver import Resolver, ResolverParsingError
from streamlit.testing.v1 import AppTest

from extraction_support import NullSafeFormatHandler, pdf_to_text


@pytest.fixture
def endpoint(monkeypatch):
    # Only the loopback test server bypasses a configured outbound proxy.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            output = (
                '{"extractions": [{"org": "ACME", "org_attributes": null}, '
                '{"email": null, "email_attributes": {"type": "work"}}, '
                '{"amount": 42}]}'
                if 'response_format' in body else
                'extractions:\n- org: ACME\n  org_attributes: null\n- email: null\n- amount: 42\n'
            )
            response = json.dumps({
                'id': 'test', 'object': 'chat.completion', 'created': 0,
                'model': body['model'],
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': output},
                             'finish_reason': 'stop'}],
            }).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.mark.parametrize('format_type', [lx.data.FormatType.JSON, lx.data.FormatType.YAML])
def test_real_provider_keeps_valid_entities_and_export(endpoint, tmp_path, format_type):
    url, requests = endpoint
    handler = NullSafeFormatHandler(format_type=format_type, use_fences=True)
    result = lx.extract(
        text_or_documents='ACME paid 42.',
        prompt_description='Extract present entities; omit null values.',
        examples=[lx.data.ExampleData(text='ACME', extractions=[
            lx.data.Extraction(extraction_class='org', extraction_text='ACME')])],
        config=factory.ModelConfig(model_id='ai-flash', provider='openai', provider_kwargs={
            'api_key': 'test', 'base_url': url, 'format_type': format_type,
        }),
        format_type=format_type, fence_output=True, use_schema_constraints=False,
        resolver_params={'format_handler': handler, 'suppress_parse_errors': False},
        extraction_passes=2, show_progress=False,
    )
    assert [(e.extraction_class, e.extraction_text) for e in result.extractions] == [
        ('org', 'ACME'), ('amount', '42')]
    assert handler.omitted_entities == 2
    assert len(requests) == 2
    assert ('response_format' in requests[0]) == (format_type == lx.data.FormatType.JSON)
    lx.io.save_annotated_documents([result], output_name='result.jsonl', output_dir=str(tmp_path))
    exported = json.loads((tmp_path / 'result.jsonl').read_text())
    assert len(exported['extractions']) == 2
    assert lx.visualize(str(tmp_path / 'result.jsonl'))


def test_normal_resolver_reproduces_null_failure():
    with pytest.raises((ResolverParsingError, ValueError)):
        Resolver().resolve('{"extractions": [{"org": "ACME"}, {"email": null}]}')


@pytest.mark.parametrize('value', ['[]', '{}'])
def test_other_invalid_entity_types_still_fail(value):
    handler = NullSafeFormatHandler()
    with pytest.raises((ResolverParsingError, ValueError)):
        Resolver(format_handler=handler).resolve(
            '{"extractions": [{"org": "ACME"}, {"email": ' + value + '}]}')


def test_null_attributes_are_not_counted_or_removed():
    handler = NullSafeFormatHandler()
    assert handler.parse_output('{"extractions": [{"org": "ACME", "org_attributes": null}]}') == [
        {'org': 'ACME', 'org_attributes': None}]
    assert handler.omitted_entities == 0
    assert handler.parse_output('{"extractions": [{"email": null}]}') == [{}]


def test_pdf_skips_bad_and_empty_pages_with_original_page_numbers():
    good = SimpleNamespace(extract_text=lambda: 'ACME')
    blank = SimpleNamespace(extract_text=lambda: '')

    def broken():
        raise ValueError('bad page')

    pdf = SimpleNamespace(pages=[good, SimpleNamespace(extract_text=broken), blank, good])
    with patch('extraction_support.pdfplumber.open') as opened:
        opened.return_value.__enter__.return_value = pdf
        text, skipped = pdf_to_text(b'pdf')
    assert text == '[PAGE 1]\nACME\n\n[PAGE 4]\nACME'
    assert skipped == [2, 3]


def test_french_ui_extraction_warns_and_renders_json(endpoint, monkeypatch):
    url, _ = endpoint
    monkeypatch.setenv('OPENAI_API_MODEL', 'ai-flash')
    monkeypatch.setenv('OPENAI_API_BASE', url)
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.delenv('USE_OPENAI_JSON_MODE', raising=False)
    with patch('streamlit.file_uploader', return_value=io.BytesIO(b'pdf')), patch(
        'extraction_support.pdf_to_text', return_value=('ACME paid 42.', [2])
    ):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
        app.button[0].click().run(timeout=20)
    assert not app.exception
    assert not app.error
    assert len(app.warning) == 2
    assert 'Pages' in app.warning[0].value
    assert 'nulles' in app.warning[1].value
    assert app.success
    assert app.json


def test_missing_key_shows_error_instead_of_exception(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with patch('streamlit.file_uploader', return_value=io.BytesIO(b'pdf')):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
        app.button[0].click().run()
    assert not app.exception
    assert 'OPENAI_API_KEY' in app.error[0].value
