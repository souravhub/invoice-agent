"""FastAPI entry point for the invoice checking web application."""

import logging
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

from .schemas import ErrorResponse, HealthResponse, InvoiceCheckResponse  # noqa: E402
from .service import (  # noqa: E402
    AIProviderError,
    ConfigurationError,
    InvalidPDFError,
    UnreadablePDFError,
    process_invoice,
)

LOGGER = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def configured_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="Invoice Agent API",
    version="1.0.0",
    description=(
        "Extracts one text-based invoice PDF and applies configured arithmetic and completeness "
        "checks. A passing result is not payment authorization or proof of authenticity."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse()


@app.post(
    "/api/invoices/check",
    response_model=InvoiceCheckResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid PDF"},
        413: {"model": ErrorResponse, "description": "Upload exceeds 20 MB"},
        415: {"model": ErrorResponse, "description": "File is not a PDF"},
        422: {"model": ErrorResponse, "description": "PDF contains no readable text"},
        502: {"model": ErrorResponse, "description": "AI provider failure"},
        503: {"model": ErrorResponse, "description": "Backend configuration is incomplete"},
    },
    tags=["invoices"],
)
async def check_invoice(file: UploadFile = File(..., description="One text-based PDF, at most 20 MB")):
    content_type = (file.content_type or "").lower()
    if content_type != "application/pdf":
        await file.close()
        return error_response(415, "pdf_required", "Choose a PDF file to continue.")

    try:
        with tempfile.TemporaryDirectory(prefix="invoice-agent-") as temp_dir:
            pdf_path = Path(temp_dir) / "invoice.pdf"
            total_bytes = 0
            header = bytearray()

            with pdf_path.open("wb") as destination:
                while chunk := await file.read(CHUNK_SIZE):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_BYTES:
                        return error_response(
                            413,
                            "file_too_large",
                            "The PDF is larger than the 20 MB upload limit.",
                        )
                    if len(header) < 1024:
                        header.extend(chunk[: 1024 - len(header)])
                    destination.write(chunk)

            if total_bytes == 0 or b"%PDF-" not in bytes(header):
                return error_response(400, "invalid_pdf", "The uploaded file is not a valid PDF.")

            try:
                return await run_in_threadpool(process_invoice, pdf_path)
            except InvalidPDFError as exc:
                return error_response(400, "invalid_pdf", str(exc))
            except UnreadablePDFError as exc:
                return error_response(422, "unreadable_pdf", str(exc))
            except ConfigurationError as exc:
                return error_response(503, "configuration_error", str(exc))
            except AIProviderError:
                LOGGER.warning("Invoice processing failed in the AI provider")
                return error_response(
                    502,
                    "ai_provider_error",
                    "The AI provider could not process this invoice. Try again later.",
                )
    finally:
        await file.close()
