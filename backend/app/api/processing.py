"""Invoice and purchase-order processing endpoints."""

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..core.config import (
    MAX_UPLOAD_BYTES,
    UPLOAD_CHUNK_SIZE,
    ZIP_CONTENT_TYPES,
    ZIP_SIGNATURES,
)

from ..models.schemas import (
    ErrorResponse,
    HealthResponse,
    InvoiceBatchResponse,
    InvoiceCheckResponse,
    InvoiceRecheckRequest,
    PurchaseOrderExtractionResponse,
    TwoWayMatchRequest,
    TwoWayMatchResponse,
)
from ..services.invoice import (
    AIProviderError,
    ConfigurationError,
    InvalidPDFError,
    UnreadablePDFError,
    extract_purchase_order,
    process_invoice,
    recheck_invoice,
)
from ..services.matching import match_invoice_to_purchase_order
from ..services.archives import InvalidZIPError, process_zip

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse()


@router.post(
    "/invoices/check",
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
                while chunk := await file.read(UPLOAD_CHUNK_SIZE):
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


@router.post(
    "/purchase-orders/extract",
    response_model=PurchaseOrderExtractionResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid PDF"},
        413: {"model": ErrorResponse, "description": "Upload exceeds 20 MB"},
        415: {"model": ErrorResponse, "description": "File is not a PDF"},
        422: {"model": ErrorResponse, "description": "PDF contains no readable text"},
        502: {"model": ErrorResponse, "description": "AI provider failure"},
        503: {"model": ErrorResponse, "description": "Backend configuration is incomplete"},
    },
    tags=["purchase orders"],
)
async def extract_purchase_order_pdf(
    file: UploadFile = File(..., description="One text-based purchase-order PDF, at most 20 MB"),
):
    if (file.content_type or "").lower() != "application/pdf":
        await file.close()
        return error_response(415, "pdf_required", "Choose a PDF file to continue.")

    try:
        with tempfile.TemporaryDirectory(prefix="invoice-agent-po-") as temp_dir:
            pdf_path = Path(temp_dir) / "purchase-order.pdf"
            total_bytes = 0
            header = bytearray()
            with pdf_path.open("wb") as destination:
                while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_BYTES:
                        return error_response(
                            413, "file_too_large", "The PDF is larger than the 20 MB upload limit."
                        )
                    if len(header) < 1024:
                        header.extend(chunk[: 1024 - len(header)])
                    destination.write(chunk)

            if total_bytes == 0 or b"%PDF-" not in bytes(header):
                return error_response(400, "invalid_pdf", "The uploaded file is not a valid PDF.")
            try:
                return await run_in_threadpool(extract_purchase_order, pdf_path)
            except InvalidPDFError as exc:
                return error_response(400, "invalid_pdf", str(exc))
            except UnreadablePDFError as exc:
                return error_response(422, "unreadable_pdf", str(exc))
            except ConfigurationError as exc:
                return error_response(503, "configuration_error", str(exc))
            except AIProviderError:
                LOGGER.warning("Purchase-order processing failed in the AI provider")
                return error_response(
                    502, "ai_provider_error",
                    "The AI provider could not process this purchase order. Try again later.",
                )
    finally:
        await file.close()


@router.post(
    "/invoices/two-way-match",
    response_model=TwoWayMatchResponse,
    tags=["invoices"],
)
def two_way_match(payload: TwoWayMatchRequest) -> TwoWayMatchResponse:
    """Compare already extracted invoice data with one saved purchase order."""
    return match_invoice_to_purchase_order(
        payload.invoice,
        payload.purchase_order,
        payload.purchase_order_id,
        payload.purchase_order_status,
    )


@router.post(
    "/invoices/recheck",
    response_model=InvoiceCheckResponse,
    tags=["invoices"],
)
def recheck_invoice_validation(payload: InvoiceRecheckRequest) -> InvoiceCheckResponse:
    """Re-run deterministic checks on an existing extraction without making an AI request."""
    return recheck_invoice(payload.invoice, payload.attempts, payload.two_way_match)


@router.post(
    "/invoices/check-batch",
    response_model=InvoiceBatchResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or unsafe ZIP archive"},
        413: {"model": ErrorResponse, "description": "Compressed upload exceeds 20 MB"},
        415: {"model": ErrorResponse, "description": "File is not a ZIP archive"},
        503: {"model": ErrorResponse, "description": "Backend configuration is incomplete"},
    },
    description=(
        "Checks up to 10 text-based invoice PDFs from one ZIP sequentially. The compressed ZIP "
        "may be at most 20 MB and its PDFs may total at most 100 MB uncompressed. Unsafe paths, "
        "encrypted entries, nested ZIPs, non-PDF files, and suspicious compression ratios are "
        "rejected. Valid archives return independent success or error details for every PDF."
    ),
    tags=["invoices"],
)
async def check_invoice_batch(
    file: UploadFile = File(..., description="One ZIP containing 1 to 10 text-based invoice PDFs"),
):
    content_type = (file.content_type or "").lower()
    is_octet_stream_zip = (
        content_type == "application/octet-stream" and (file.filename or "").lower().endswith(".zip")
    )
    if content_type not in ZIP_CONTENT_TYPES and not is_octet_stream_zip:
        await file.close()
        return error_response(415, "zip_required", "Choose a ZIP file to continue.")

    try:
        with tempfile.TemporaryDirectory(prefix="invoice-agent-batch-") as temp_dir:
            zip_path = Path(temp_dir) / "invoices.zip"
            total_bytes = 0
            header = bytearray()

            with zip_path.open("wb") as destination:
                while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_BYTES:
                        return error_response(
                            413,
                            "file_too_large",
                            "The ZIP is larger than the 20 MB compressed upload limit.",
                        )
                    if len(header) < 4:
                        header.extend(chunk[: 4 - len(header)])
                    destination.write(chunk)

            if total_bytes == 0 or not any(bytes(header).startswith(sig) for sig in ZIP_SIGNATURES):
                return error_response(400, "invalid_zip", "The uploaded file is not a valid ZIP.")

            try:
                return await run_in_threadpool(process_zip, zip_path)
            except InvalidZIPError as exc:
                return error_response(400, "invalid_zip", str(exc))
            except ConfigurationError as exc:
                return error_response(503, "configuration_error", str(exc))
    finally:
        await file.close()
