"""Authenticated API and same-origin Vue frontend."""

import asyncio
import json
import logging
import os
import secrets
import string
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from extraction_errors import PDFInputError, diagnose_extraction
from extraction_service import DEFAULT_PROMPT, extract_pdf

logger = logging.getLogger("langextract.api")


@dataclass(frozen=True)
class Settings:
    api_token: str
    model: str
    base_url: str
    model_key: str
    json_mode: bool = True
    max_upload_bytes: int = 20 * 1024 * 1024
    max_text_chars: int = 500_000

    @classmethod
    def from_env(cls):
        # Match the original run.sh: the project .env overrides inherited values.
        # Keep secrets literal rather than executing the file as shell code.
        load_dotenv(Path(__file__).with_name(".env"), interpolate=False, override=True)
        return cls(
            api_token=os.getenv("API_TOKEN", ""),
            model=os.getenv("OPENAI_API_MODEL", "mistral-small-vllm"),
            base_url=os.getenv("OPENAI_API_BASE", "http://127.0.0.1:8000/v1"),
            model_key=os.getenv("OPENAI_API_KEY", ""),
            json_mode=os.getenv("USE_OPENAI_JSON_MODE", "1").strip().lower()
            in {"1", "true", "yes"},
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))),
            max_text_chars=int(os.getenv("MAX_TEXT_CHARS", "500000")),
        )


class ExtractionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(default=DEFAULT_PROMPT, min_length=1, max_length=10000)
    extraction_passes: int = Field(default=2, ge=1, le=5)
    max_workers: int = Field(default=8, ge=1, le=24)
    max_char_buffer: int = Field(default=1200, ge=500, le=4000)
    include_text: bool = False


class ExtractionResponse(BaseModel):
    document: dict
    jsonl: str
    html: str
    warnings: list[str]
    skipped_pages: list[int]
    omitted_entities: int
    text: str | None


bearer = HTTPBearer(auto_error=False)


def create_app(settings: Settings | None = None, frontend_dir: Path | None = None):
    @asynccontextmanager
    async def lifespan(app):
        config = settings or Settings.from_env()
        token = config.api_token
        if (
            len(token) < 8
            or not any(char in string.ascii_uppercase for char in token)
            or not any(char in string.ascii_lowercase for char in token)
            or not any(char in string.digits for char in token)
            or not any(char in string.punctuation for char in token)
            or any(char.isspace() for char in token)
        ):
            raise RuntimeError(
                "API_TOKEN doit contenir au moins 8 caractères, une majuscule, "
                "une minuscule, un chiffre et un caractère spécial, sans espace."
            )
        if not config.model_key or not config.model or not config.base_url:
            raise RuntimeError(
                "OPENAI_API_KEY, OPENAI_API_MODEL et OPENAI_API_BASE sont requis."
            )
        if config.max_upload_bytes <= 0 or config.max_text_chars <= 0:
            raise RuntimeError("Les limites de taille doivent être positives.")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        app.state.settings = config
        app.state.extraction_lock = asyncio.Lock()
        yield

    api = FastAPI(title="LangExtract PDF", version="0.2.0", lifespan=lifespan)

    async def authenticate(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
    ):
        config = request.app.state.settings
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(), config.api_token.encode()
        ):
            raise HTTPException(
                401, "Token absent ou invalide.", headers={"WWW-Authenticate": "Bearer"}
            )
        return config

    @api.middleware("http")
    async def request_metadata(request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "font-src 'self' data:; img-src 'self' data:; frame-src 'self'; "
                "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
            )
            if request.url.path not in {"/docs", "/redoc"}
            else "frame-ancestors 'none'"
        )
        # No URL query, document content, exception message or Authorization in logs.
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - start) * 1000, 2),
                }
            )
        )
        return response

    @api.get("/healthz")
    async def health():
        return {"status": "ok"}

    @api.get("/api/v1/config")
    async def config(config: Annotated[Settings, Depends(authenticate)]):
        return {
            "defaults": ExtractionOptions().model_dump(),
            "max_upload_bytes": config.max_upload_bytes,
        }

    @api.post(
        "/api/v1/extractions",
        response_model=ExtractionResponse,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["file"],
                            "properties": {
                                "file": {"type": "string", "format": "binary"},
                                "options": {
                                    "type": "string",
                                    "description": "Objet JSON : prompt, extraction_passes, max_workers, max_char_buffer, include_text",
                                },
                            },
                        }
                    }
                },
            }
        },
    )
    async def extract(
        request: Request, config: Annotated[Settings, Depends(authenticate)]
    ):
        # Admission before upload/PDF parsing/inference. One running job per process.
        lock = request.app.state.extraction_lock
        if lock.locked():
            raise HTTPException(
                503,
                "Une extraction est déjà en cours. Réessayez plus tard.",
                headers={"Retry-After": "5"},
            )
        async with lock:
            max_body = config.max_upload_bytes + 64 * 1024
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                raise HTTPException(400, "Taille de requête invalide.") from None
            if length > max_body:
                raise HTTPException(413, "Le PDF dépasse la taille autorisée.")
            if not request.headers.get("content-type", "").startswith(
                "multipart/form-data"
            ):
                raise HTTPException(
                    415, "Un formulaire multipart/form-data avec un PDF est requis."
                )
            oversized = False

            async def limited_stream():
                nonlocal oversized
                total = 0
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > max_body:
                        oversized = True
                        # Multipart parser closes temporary files on this exception.
                        raise MultiPartException("Requête trop volumineuse.")
                    yield chunk

            try:
                form = await MultiPartParser(
                    request.headers,
                    limited_stream(),
                    max_files=1,
                    max_fields=1,
                    max_part_size=65536,
                ).parse()
            except MultiPartException:
                raise HTTPException(
                    413 if oversized else 400,
                    "Formulaire trop volumineux."
                    if oversized
                    else "Formulaire PDF invalide.",
                ) from None
            try:
                if set(form.keys()) - {"file", "options"}:
                    raise HTTPException(422, "Champs acceptés : file et options.")
                upload = form.get("file")
                if not isinstance(upload, UploadFile):
                    raise HTTPException(422, "Le champ file doit contenir un PDF.")
                if upload.size is not None and upload.size > config.max_upload_bytes:
                    raise HTTPException(413, "Le PDF dépasse la taille autorisée.")
                content = await upload.read(config.max_upload_bytes + 1)
                if len(content) > config.max_upload_bytes:
                    raise HTTPException(413, "Le PDF dépasse la taille autorisée.")
                if not content.startswith(b"%PDF-"):
                    raise HTTPException(422, "Le fichier doit être un PDF valide.")
                raw_options = form.get("options", "{}")
                if not isinstance(raw_options, str):
                    raise HTTPException(422, "options doit être un objet JSON.")
                try:
                    options = ExtractionOptions.model_validate_json(raw_options)
                except ValidationError:
                    raise HTTPException(
                        422,
                        "Paramètres invalides : prompt (1–10000 caractères), passes (1–5), workers (1–24), segment (500–4000).",
                    ) from None
                try:
                    return await run_in_threadpool(
                        extract_pdf, content, options, config
                    )
                except PDFInputError as exc:
                    raise HTTPException(422, str(exc)) from None
                except Exception as exc:  # noqa: BLE001 - classify provider/library errors without leaking their content
                    raise diagnose_extraction(exc, logger) from None

            finally:
                await form.close()

    dist = frontend_dir or Path(__file__).resolve().parent / "frontend" / "dist"
    if dist.is_dir():
        # No SPA fallback: unknown API paths must remain 404.
        api.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return api


app = create_app()
