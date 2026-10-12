"""Synchronous invoice processing used from FastAPI's worker thread pool."""

import os
from pathlib import Path

import pdfplumber

from ..agent.schema import Invoice, PurchaseOrder
from ..agent.workflow import (
    MONEY_TOLERANCE,
    REQUIRED_FIELDS,
    build_graph,
    decide,
    is_blank,
    provider_and_model,
    get_llm,
)
from ..models.schemas import (
    ConfiguredCheck,
    InvoiceCheckResponse,
    PurchaseOrderExtractionResponse,
    TwoWayMatchResponse,
)


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


def build_configured_checks(invoice: Invoice, attempts: int) -> list[ConfiguredCheck]:
    """Describe the existing workflow rules without changing their decisions."""
    checks: list[ConfiguredCheck] = []
    field_labels = {
        "vendor_name": "vendor",
        "invoice_date": "invoice date",
        "total": "total",
    }
    missing = [field_labels[name] for name in REQUIRED_FIELDS if is_blank(getattr(invoice, name))]
    checks.append(
        ConfiguredCheck(
            id="required_fields",
            label="Required fields present",
            status="failed" if missing else "passed",
            detail=(
                f"Missing: {', '.join(missing)}."
                if missing
                else "Vendor, invoice date, and total were extracted."
            ),
        )
    )

    item_count = len(invoice.line_items)
    checks.append(
        ConfiguredCheck(
            id="line_items",
            label="Line items extracted",
            status="passed" if item_count else "failed",
            detail=(
                f"{item_count} line item{'s' if item_count != 1 else ''} were extracted."
                if item_count
                else "No line items were extracted."
            ),
        )
    )

    checks.append(
        ConfiguredCheck(
            id="currency",
            label="Currency present",
            status="failed" if is_blank(invoice.currency) else "passed",
            detail=(
                "No currency was extracted."
                if is_blank(invoice.currency)
                else f"Currency: {invoice.currency}."
            ),
        )
    )

    if invoice.subtotal is None or not invoice.line_items:
        subtotal_check = ConfiguredCheck(
            id="subtotal_calculation",
            label="Line items and subtotal agree",
            status="not_checked",
            detail="A subtotal and at least one line item are required for this check.",
        )
    else:
        items_sum = sum(item.amount or 0 for item in invoice.line_items)
        discount = abs(invoice.discount) if invoice.discount else 0.0
        expected_subtotal = items_sum - discount
        subtotal_matches = abs(expected_subtotal - invoice.subtotal) <= MONEY_TOLERANCE
        subtotal_check = ConfiguredCheck(
            id="subtotal_calculation",
            label="Line items and subtotal agree",
            status="passed" if subtotal_matches else "failed",
            detail=(
                f"Line items ({items_sum:.2f}) minus discount ({discount:.2f}) = "
                f"{expected_subtotal:.2f}; extracted subtotal = {invoice.subtotal:.2f}."
            ),
        )
    checks.append(subtotal_check)

    if None in (invoice.subtotal, invoice.tax, invoice.total):
        total_check = ConfiguredCheck(
            id="total_calculation",
            label="Subtotal, tax, shipping, and total agree",
            status="not_checked",
            detail="Subtotal, tax, and total are required for this check.",
        )
    else:
        shipping = abs(invoice.shipping) if invoice.shipping else 0.0
        expected_total = invoice.subtotal + invoice.tax + shipping
        total_matches = abs(expected_total - invoice.total) <= MONEY_TOLERANCE
        total_check = ConfiguredCheck(
            id="total_calculation",
            label="Subtotal, tax, shipping, and total agree",
            status="passed" if total_matches else "failed",
            detail=(
                f"Subtotal ({invoice.subtotal:.2f}) + tax ({invoice.tax:.2f}) + "
                f"shipping ({shipping:.2f}) = {expected_total:.2f}; "
                f"extracted total = {invoice.total:.2f}."
            ),
        )
    checks.append(total_check)

    checks.append(
        ConfiguredCheck(
            id="extraction_attempts",
            label="Extracted without retry changes",
            status="passed" if attempts == 1 else "failed",
            detail=(
                "The first extraction passed validation."
                if attempts == 1
                else f"The extraction changed during {attempts} attempts; confirm it manually."
            ),
        )
    )
    return checks


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
            checks=build_configured_checks(result["invoice"], result["attempts"]),
        )
    except (InvalidPDFError, UnreadablePDFError, ConfigurationError):
        raise
    except Exception as exc:
        # Provider SDK exceptions vary between OpenAI/Gemini and versions. Keep their
        # potentially sensitive request details out of the browser response.
        raise AIProviderError(
            "The AI provider could not process this invoice. Try again later."
        ) from exc


def recheck_invoice(
    invoice: Invoice,
    attempts: int,
    two_way_match: TwoWayMatchResponse | None = None,
) -> InvoiceCheckResponse:
    """Reapply code-based validation without reading the PDF or invoking an AI provider."""
    decision = decide({"invoice": invoice, "attempts": attempts, "errors": []})
    reasons = decision["reasons"]
    status = decision["status"]
    if two_way_match and two_way_match.status != "matched":
        status = "needs_review"
        reasons = [*reasons, *two_way_match.reasons]
    return InvoiceCheckResponse(
        invoice=invoice,
        status=status,
        reasons=list(dict.fromkeys(reasons)),
        attempts=attempts,
        checks=build_configured_checks(invoice, attempts),
        two_way_match=two_way_match,
    )


def extract_purchase_order(pdf_path: Path) -> PurchaseOrderExtractionResponse:
    """Extract a saved purchase order using the same provider and PDF safeguards."""
    validate_readable_pdf(pdf_path)
    validate_configuration()
    try:
        with pdfplumber.open(pdf_path) as pdf:
            raw_text = "\n\n--- PAGE BREAK ---\n\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
        structured_llm = get_llm().with_structured_output(PurchaseOrder)
        purchase_order = structured_llm.invoke(
            "You are a purchase order data extraction assistant. Extract the fields from the "
            "purchase order below. Use null for absent values and never invent values. Amounts "
            "must be plain numbers without currency symbols or commas. Extract every ordered line."
            f"\n\nPURCHASE ORDER TEXT:\n{raw_text}"
        )
        checks = [
            ConfiguredCheck(
                id="po_number_present", label="PO number present",
                status="passed" if not is_blank(purchase_order.po_number) else "failed",
                detail=(f"PO number: {purchase_order.po_number}." if purchase_order.po_number else "No PO number was extracted."),
            ),
            ConfiguredCheck(
                id="po_vendor_present", label="Vendor present",
                status="passed" if not is_blank(purchase_order.vendor_name) else "failed",
                detail=(f"Vendor: {purchase_order.vendor_name}." if purchase_order.vendor_name else "No vendor was extracted."),
            ),
            ConfiguredCheck(
                id="po_line_items", label="PO line items extracted",
                status="passed" if purchase_order.line_items else "failed",
                detail=f"{len(purchase_order.line_items)} line item(s) were extracted.",
            ),
            ConfiguredCheck(
                id="po_total_present", label="PO total present",
                status="passed" if purchase_order.total is not None else "failed",
                detail=(f"PO total: {purchase_order.total:.2f}." if purchase_order.total is not None else "No PO total was extracted."),
            ),
        ]
        return PurchaseOrderExtractionResponse(purchase_order=purchase_order, checks=checks)
    except (InvalidPDFError, UnreadablePDFError, ConfigurationError):
        raise
    except Exception as exc:
        raise AIProviderError(
            "The AI provider could not process this purchase order. Try again later."
        ) from exc
