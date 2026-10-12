from backend.app.agent.schema import Invoice, LineItem
from backend.app.services.invoice import build_configured_checks


def invoice_with_valid_amounts() -> Invoice:
    return Invoice(
        vendor_name="Example Vendor",
        invoice_date="2026-10-07",
        currency="USD",
        line_items=[LineItem(description="Service", amount=90)],
        subtotal=80,
        discount=10,
        shipping=5,
        tax=8,
        total=93,
    )


def statuses(invoice: Invoice, attempts: int = 1) -> dict[str, str]:
    return {check.id: check.status for check in build_configured_checks(invoice, attempts)}


def test_reports_every_configured_check_as_passed_for_consistent_invoice() -> None:
    result = statuses(invoice_with_valid_amounts())

    assert result == {
        "required_fields": "passed",
        "line_items": "passed",
        "currency": "passed",
        "subtotal_calculation": "passed",
        "total_calculation": "passed",
        "extraction_attempts": "passed",
    }


def test_reports_failed_calculations_and_retry_changes() -> None:
    invoice = invoice_with_valid_amounts().model_copy(update={"subtotal": 81, "total": 99})
    result = statuses(invoice, attempts=2)

    assert result["subtotal_calculation"] == "failed"
    assert result["total_calculation"] == "failed"
    assert result["extraction_attempts"] == "failed"


def test_reports_calculation_as_not_checked_when_values_are_missing() -> None:
    invoice = Invoice(
        vendor_name="Example Vendor",
        invoice_date="2026-10-07",
        currency=None,
        line_items=[],
        subtotal=None,
        tax=None,
        total=10,
    )
    result = statuses(invoice)

    assert result["line_items"] == "failed"
    assert result["currency"] == "failed"
    assert result["subtotal_calculation"] == "not_checked"
    assert result["total_calculation"] == "not_checked"
