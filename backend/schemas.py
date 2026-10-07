"""Documented API contracts returned to the browser."""

from typing import Literal

from pydantic import BaseModel, Field

from .agent.schema import Invoice


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


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
