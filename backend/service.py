"""Synchronous invoice processing used from FastAPI's worker thread pool."""

import os
from pathlib import Path

import pdfplumber

from .agent.workflow import build_graph, provider_and_model
from .schemas import InvoiceCheckResponse


class InvoiceServiceError(Exception):
    """Base class for errors that have a safe public API representation."""


class InvalidPDFError(InvoiceServiceError):
    pass


class UnreadablePDFError(InvoiceServiceError):
    pass


class ConfigurationError(InvoiceServiceError):
    pass


class AIProviderError(InvoiceServiceError):
    pass


def validate_configuration() -> None:
    """Fail before invoking the graph when the selected provider is not configured."""
    try:
        provider, _ = provider_and_model()
    except ValueError as exc:
        raise ConfigurationError(
            "The AI provider configuration is invalid. Check the backend environment settings."
        ) from exc

    key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
    if not (os.getenv(key_name) or "").strip():
        raise ConfigurationError(
            "The AI provider is not configured. Add the required API key to backend/.env."
        )


def validate_readable_pdf(pdf_path: Path) -> None:
    """Confirm that pdfplumber can parse the file and that it contains extractable text."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                raise InvalidPDFError("The PDF does not contain any pages.")
            has_text = any((page.extract_text() or "").strip() for page in pdf.pages)
    except InvalidPDFError:
        raise
    except Exception as exc:
        raise InvalidPDFError("The uploaded file is not a readable PDF.") from exc

    if not has_text:
        raise UnreadablePDFError(
            "No readable text was found. Scanned PDFs need OCR, which is not supported yet."
        )


def process_invoice(pdf_path: Path) -> InvoiceCheckResponse:
    """Validate and run one isolated PDF through the original LangGraph workflow."""
    validate_readable_pdf(pdf_path)
    validate_configuration()

    try:
        result = build_graph().invoke({"pdf_path": str(pdf_path)})
        return InvoiceCheckResponse(
            invoice=result["invoice"],
            status=result["status"],
            reasons=result.get("reasons") or [],
            attempts=result["attempts"],
        )
    except (InvalidPDFError, UnreadablePDFError, ConfigurationError):
        raise
    except Exception as exc:
        # Provider SDK exceptions vary between OpenAI/Gemini and versions. Keep their
        # potentially sensitive request details out of the browser response.
        raise AIProviderError(
            "The AI provider could not process this invoice. Try again later."
        ) from exc
