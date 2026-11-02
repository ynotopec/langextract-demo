"""Safe diagnostics: never return/log provider messages or document contents."""

import json
import logging
import secrets
import traceback
from contextlib import contextmanager
from pathlib import Path

import openai
from fastapi import HTTPException
from langextract.core.exceptions import FormatError
from langextract.resolver import ResolverParsingError


class PDFInputError(ValueError):
    """A fixed, user-facing PDF validation error."""


class ExtractionFailure(Exception):
    def __init__(self, stage):
        super().__init__(stage)
        self.stage = stage


@contextmanager
def extraction_stage(stage):
    try:
        yield
    except ExtractionFailure:
        raise
    except Exception as exc:
        raise ExtractionFailure(stage) from exc


def diagnose_extraction(exc: Exception, logger: logging.Logger) -> HTTPException:
    chain = []
    pending = [exc]
    seen = set()
    while pending and len(chain) < 16:
        error = pending.pop(0)
        if id(error) in seen:
            continue
        seen.add(id(error))
        chain.append(error)
        for nested in (
            error.__cause__,
            error.__context__,
            getattr(error, "original", None),
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
    stage = exc.stage if isinstance(exc, ExtractionFailure) else "inference"
    upstream = next(
        (e.status_code for e in chain if isinstance(e, openai.APIStatusError)), None
    )
    status, category = 502, "inference_error"
    message = "Échec de l’extraction. Consultez le diagnostic dans les logs serveur."
    if stage in {"export", "visualization"}:
        status, category = 500, stage
        message = "L’inférence a terminé, mais la génération des exports a échoué. Consultez le diagnostic serveur."
    elif any(isinstance(e, (openai.APITimeoutError, TimeoutError)) for e in chain):
        status, category = 504, "provider_timeout"
        message = "Le fournisseur n’a pas répondu dans le délai imparti. Vérifiez sa charge et sa disponibilité."
    elif any(
        isinstance(e, (openai.APIConnectionError, ConnectionError)) for e in chain
    ):
        category = "provider_connection"
        message = "Connexion au fournisseur impossible. Vérifiez OPENAI_API_BASE, le réseau, le proxy et TLS côté serveur."
    elif upstream in {401, 403}:
        category = "provider_auth"
        message = "Le fournisseur refuse l’accès. Vérifiez OPENAI_API_KEY et les droits du modèle côté serveur (ce n’est pas le token de connexion à l’application)."
    elif upstream == 404:
        category = "provider_not_found"
        message = "Endpoint ou modèle introuvable. Vérifiez OPENAI_API_BASE (suffixe /v1) et OPENAI_API_MODEL côté serveur."
    elif upstream == 429:
        status, category = 503, "provider_rate_limit"
        message = "Le fournisseur limite les requêtes ou son quota est épuisé. Réduisez les requêtes parallèles ou vérifiez le quota."
    elif upstream == 400:
        # Inspect only for fixed signatures; never echo/log the provider's text.
        messages = " ".join(str(e).lower() for e in chain)
        if "src property must be a valid json object" in messages or (
            any(
                word in messages
                for word in ("response_format", "json mode", "json_object")
            )
            and any(
                word in messages
                for word in ("unsupported", "not supported", "invalid", "rejected")
            )
        ):
            category = "provider_json_mode"
            message = "Le fournisseur refuse le mode JSON. Définissez USE_OPENAI_JSON_MODE=0 dans .env puis redémarrez le service."
        elif any(
            word in messages
            for word in (
                "context length",
                "context_length",
                "maximum context",
                "too many tokens",
            )
        ):
            category = "provider_context"
            message = "Le contexte du modèle est dépassé. Réduisez les caractères par segment ou augmentez le contexte côté fournisseur."
        else:
            category = "provider_bad_request"
            message = "Le fournisseur rejette la requête (HTTP 400). Vérifiez le modèle et les paramètres pris en charge côté serveur."
    elif upstream is not None:
        category = "provider_http"
        message = f"Le fournisseur renvoie HTTP {upstream}. Vérifiez ses logs et sa disponibilité."
    elif any(isinstance(e, (FormatError, ResolverParsingError)) for e in chain):
        category = "model_output_format"
        message = "La réponse du modèle ne respecte pas le format d’extraction attendu. Vérifiez la compatibilité du modèle et le mode JSON/YAML."
    elif any(isinstance(e, ImportError) for e in chain):
        status, category = 500, "dependency_error"
        message = "Une dépendance serveur manque ou est incompatible. Relancez install.sh puis redémarrez le service."
    reference = secrets.token_hex(6)
    logger.error(
        json.dumps(
            {
                "event": "extraction_failed",
                "reference": reference,
                "stage": stage,
                "category": category,
                "upstream_status": upstream,
                "exception_types": [type(e).__name__ for e in chain],
                "frames": [
                    {
                        "file": Path(frame.filename).name,
                        "function": frame.name,
                        "line": frame.lineno,
                    }
                    for e in chain
                    for frame in traceback.extract_tb(e.__traceback__)
                ][-20:],
            }
        )
    )
    return HTTPException(
        status,
        f"{message} Référence diagnostic : {reference}.",
        headers={"Retry-After": "5"} if status == 503 else None,
    )
