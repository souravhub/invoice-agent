"""Documented API contracts returned to the browser."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..agent.schema import Invoice, PurchaseOrder


class ConfiguredCheck(BaseModel):
    """One transparent outcome from the configured invoice rules."""

    id: str = Field(description="Stable identifier for the configured check.")
    label: str = Field(description="Human-readable name shown in the frontend.")
    status: Literal["passed", "failed", "not_checked"] = Field(
        description=(
            "passed means the extracted values satisfy this rule; failed needs review; "
            "not_checked means the extracted invoice lacked enough data to run the rule."
        )
    )
    detail: str = Field(description="A safe explanation of what was compared or found.")


class PurchaseOrderExtractionResponse(BaseModel):
    purchase_order: PurchaseOrder
    attempts: int = Field(default=1, ge=1)
    checks: list[ConfiguredCheck] = Field(default_factory=list)


class TwoWayMatchRequest(BaseModel):
    invoice: Invoice
    purchase_order: PurchaseOrder
    purchase_order_id: str | None = None
    purchase_order_status: Literal["open", "closed", "cancelled"] = "open"


class TwoWayMatchResponse(BaseModel):
    status: Literal["matched", "needs_review", "po_not_found", "po_unavailable", "ambiguous_po"]
    purchase_order_id: str | None = None
    po_number: str | None = None
    checks: list[ConfiguredCheck] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class InvoiceRecheckRequest(BaseModel):
    """Already extracted values to run through deterministic validation again."""

    invoice: Invoice
    attempts: int = Field(default=1, ge=1)
    two_way_match: TwoWayMatchResponse | None = None


class InvoiceCheckResponse(BaseModel):
    """The extracted invoice and the existing workflow's review decision."""

    invoice: Invoice
    status: Literal["auto_approved", "needs_review"] = Field(
        description=(
            "auto_approved means the extraction passed the configured checks; it is not "
            "payment authorization or proof that the invoice is authentic."
        )
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Configured-check failures explaining why human review is required.",
    )
    attempts: int = Field(ge=1, description="Number of AI extraction attempts used.")
    checks: list[ConfiguredCheck] = Field(
        default_factory=list,
        description="Individual configured check outcomes for display in the frontend.",
    )
    two_way_match: TwoWayMatchResponse | None = Field(
        default=None,
        description="PO matching result when a saved purchase order was available.",
    )


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class BatchFileResult(BaseModel):
    """Result or safe error for one PDF inside an accepted ZIP archive."""

    filename: str = Field(description="Validated relative filename from the ZIP archive.")
    result: InvoiceCheckResponse | None = None
    error: ErrorDetail | None = None


class BatchSummary(BaseModel):
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)


class InvoiceBatchResponse(BaseModel):
    """Results for every PDF in a ZIP, including independent per-file failures."""

    summary: BatchSummary
    files: list[BatchFileResult]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class UserProfileRequest(BaseModel):
    displayName: str | None = None
    email: str | None = None
    photoURL: str | None = None


class InvoiceRecordCreate(BaseModel):
    fileName: str
    fileType: Literal["pdf", "zip"]
    fileSizeBytes: int = Field(ge=0)
    status: Literal["auto_approved", "needs_review", "batch_complete"]
    result: InvoiceCheckResponse | InvoiceBatchResponse


class InvoiceRecordUpdate(BaseModel):
    status: Literal["auto_approved", "needs_review", "batch_complete"]
    result: InvoiceCheckResponse | InvoiceBatchResponse


class InvoiceRecord(InvoiceRecordCreate):
    id: str
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    recheckedAt: datetime | None = None


class PurchaseOrderRecordCreate(BaseModel):
    fileName: str
    fileSizeBytes: int = Field(ge=0)
    normalizedPoNumber: str
    status: Literal["open", "closed", "cancelled"] = "open"
    purchaseOrder: PurchaseOrder
    extraction: PurchaseOrderExtractionResponse


class PurchaseOrderRecord(PurchaseOrderRecordCreate):
    id: str
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class PurchaseOrderStatusUpdate(BaseModel):
    status: Literal["open", "closed", "cancelled"]


class MatchSavedPurchaseOrderRequest(BaseModel):
    invoice: Invoice


class AnalysisRecordCreate(BaseModel):
    fileName: str
    fileType: Literal["pdf"] = "pdf"
    fileSizeBytes: int | None = Field(default=None, ge=0)
    archiveName: str | None = None
    status: Literal["auto_approved", "needs_review"]
    result: InvoiceCheckResponse


class AnalysisBatchCreate(BaseModel):
    analyses: list[AnalysisRecordCreate] = Field(min_length=1, max_length=10)


class AnalysisRecord(AnalysisRecordCreate):
    id: str
    createdAt: datetime | None = None
