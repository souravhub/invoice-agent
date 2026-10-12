from backend.app.agent.schema import Invoice, LineItem, PurchaseOrder
from backend.app.services.matching import match_invoice_to_purchase_order, normalize_identifier


def documents() -> tuple[Invoice, PurchaseOrder]:
    invoice = Invoice(
        vendor_name="Example Supplies Ltd.",
        invoice_number="INV-10",
        invoice_date="2026-10-08",
        po_number="PO-0010",
        currency="USD",
        line_items=[LineItem(description="Blue office chairs", quantity=2, unit_price=50, amount=100)],
        subtotal=100,
        tax=10,
        total=110,
    )
    purchase_order = PurchaseOrder(
        vendor_name="Example Supplies Ltd.",
        po_number="PO 0010",
        order_date="2026-10-01",
        currency="USD",
        line_items=[LineItem(description="Blue office chair", quantity=4, unit_price=50, amount=200)],
        subtotal=200,
        tax=20,
        total=220,
    )
    return invoice, purchase_order


def test_normalizes_po_numbers_for_lookup_and_comparison() -> None:
    assert normalize_identifier(" po-0010 ") == "PO0010"


def test_matching_invoice_passes_two_way_match() -> None:
    invoice, purchase_order = documents()
    result = match_invoice_to_purchase_order(invoice, purchase_order, "saved-po")

    assert result.status == "matched"
    assert result.purchase_order_id == "saved-po"
    assert all(check.status == "passed" for check in result.checks)


def test_overbilling_requires_review() -> None:
    invoice, purchase_order = documents()
    invoice.line_items[0].quantity = 5
    invoice.line_items[0].amount = 250
    invoice.total = 275
    result = match_invoice_to_purchase_order(invoice, purchase_order)

    assert result.status == "needs_review"
    assert any("exceeds ordered quantity" in reason for reason in result.reasons)
    assert any("exceeds PO total" in reason for reason in result.reasons)


def test_missing_line_values_are_not_silently_approved() -> None:
    invoice, purchase_order = documents()
    invoice.line_items[0].quantity = None
    result = match_invoice_to_purchase_order(invoice, purchase_order)

    assert result.status == "needs_review"
    assert any("quantity is missing" in reason for reason in result.reasons)


def test_closed_purchase_order_is_unavailable() -> None:
    invoice, purchase_order = documents()
    result = match_invoice_to_purchase_order(
        invoice, purchase_order, purchase_order_status="closed"
    )

    assert result.status == "po_unavailable"
    assert result.checks[0].status == "failed"
