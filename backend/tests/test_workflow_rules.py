from backend.agent.schema import Invoice, LineItem
from backend.agent.workflow import (
    STATUS_AUTO_APPROVED,
    STATUS_NEEDS_REVIEW,
    decide,
    money_errors,
)


def invoice(**changes) -> Invoice:
    values = {
        "vendor_name": "Example Vendor",
        "invoice_number": "INV-1",
        "invoice_date": "2026-10-07",
        "po_number": None,
        "currency": "USD",
        "line_items": [LineItem(description="Service", quantity=1, unit_price=100, amount=100)],
        "subtotal": 90,
        "discount": 10,
        "shipping": 5,
        "tax": 9,
        "total": 104,
    }
    values.update(changes)
    return Invoice(**values)


def test_existing_discount_shipping_math_is_preserved() -> None:
    assert money_errors(invoice()) == []


def test_math_mismatch_requires_review() -> None:
    result = decide({"invoice": invoice(total=999), "attempts": 1, "errors": []})
    assert result["status"] == STATUS_NEEDS_REVIEW
    assert any("totals do not add up" in reason for reason in result["reasons"])


def test_clean_first_attempt_passes_configured_rules() -> None:
    result = decide({"invoice": invoice(), "attempts": 1, "errors": []})
    assert result == {"status": STATUS_AUTO_APPROVED, "reasons": []}


def test_changed_answer_after_retry_still_requires_review() -> None:
    result = decide({"invoice": invoice(), "attempts": 2, "errors": []})
    assert result["status"] == STATUS_NEEDS_REVIEW
    assert any("changed its answer after a retry" in reason for reason in result["reasons"])
