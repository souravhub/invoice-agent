"""Deterministic invoice-to-purchase-order matching rules."""

import re
from difflib import SequenceMatcher

from ..agent.schema import Invoice, LineItem, PurchaseOrder
from ..models.schemas import ConfiguredCheck, TwoWayMatchResponse

MONEY_TOLERANCE = 0.01
QUANTITY_TOLERANCE = 0.000001
DESCRIPTION_MATCH_THRESHOLD = 0.72


def normalize_identifier(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def normalize_text(value: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _description_score(left: str, right: str) -> float:
    a, b = normalize_text(left), normalize_text(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _line_problem(invoice_item: LineItem, po_item: LineItem) -> str | None:
    problems: list[str] = []
    if invoice_item.quantity is None or po_item.quantity is None:
        problems.append("quantity is missing")
    elif invoice_item.quantity - po_item.quantity > QUANTITY_TOLERANCE:
        problems.append(
            f"invoice quantity {invoice_item.quantity:g} exceeds ordered quantity {po_item.quantity:g}"
        )

    if invoice_item.unit_price is None or po_item.unit_price is None:
        problems.append("unit price is missing")
    elif abs(invoice_item.unit_price - po_item.unit_price) > MONEY_TOLERANCE:
        problems.append(
            f"invoice unit price {invoice_item.unit_price:.2f} differs from PO {po_item.unit_price:.2f}"
        )

    if (
        invoice_item.amount is not None
        and po_item.amount is not None
        and invoice_item.amount - po_item.amount > MONEY_TOLERANCE
    ):
        problems.append(
            f"invoice amount {invoice_item.amount:.2f} exceeds PO amount {po_item.amount:.2f}"
        )
    return "; ".join(problems) or None


def match_invoice_to_purchase_order(
    invoice: Invoice,
    purchase_order: PurchaseOrder,
    purchase_order_id: str | None = None,
    purchase_order_status: str = "open",
) -> TwoWayMatchResponse:
    checks: list[ConfiguredCheck] = []

    if purchase_order_status != "open":
        check = ConfiguredCheck(
            id="po_availability",
            label="Purchase order is available",
            status="failed",
            detail=f"The saved purchase order is {purchase_order_status}.",
        )
        return TwoWayMatchResponse(
            status="po_unavailable",
            purchase_order_id=purchase_order_id,
            po_number=purchase_order.po_number,
            checks=[check],
            reasons=[check.detail],
        )

    checks.append(ConfiguredCheck(
        id="po_availability", label="Purchase order is available", status="passed",
        detail="An open saved purchase order was found.",
    ))

    invoice_po = normalize_identifier(invoice.po_number)
    stored_po = normalize_identifier(purchase_order.po_number)
    po_ok = bool(invoice_po and stored_po and invoice_po == stored_po)
    checks.append(ConfiguredCheck(
        id="po_number_match", label="PO numbers agree",
        status="passed" if po_ok else "failed",
        detail=(f"Both documents reference {purchase_order.po_number}." if po_ok else
                f"Invoice PO number {invoice.po_number or 'missing'} does not match saved PO {purchase_order.po_number or 'missing'}."),
    ))

    invoice_vendor = normalize_text(invoice.vendor_name)
    po_vendor = normalize_text(purchase_order.vendor_name)
    vendor_ok = bool(invoice_vendor and po_vendor and invoice_vendor == po_vendor)
    checks.append(ConfiguredCheck(
        id="vendor_match", label="Vendors agree", status="passed" if vendor_ok else "failed",
        detail=(f"Both documents name {purchase_order.vendor_name}." if vendor_ok else
                f"Invoice vendor {invoice.vendor_name or 'missing'} does not match PO vendor {purchase_order.vendor_name or 'missing'}."),
    ))

    invoice_currency = (invoice.currency or "").strip().upper()
    po_currency = (purchase_order.currency or "").strip().upper()
    currency_ok = bool(invoice_currency and po_currency and invoice_currency == po_currency)
    checks.append(ConfiguredCheck(
        id="currency_match", label="Currencies agree", status="passed" if currency_ok else "failed",
        detail=(f"Both documents use {po_currency}." if currency_ok else
                f"Invoice currency {invoice.currency or 'missing'} does not match PO currency {purchase_order.currency or 'missing'}."),
    ))

    unmatched_po = set(range(len(purchase_order.line_items)))
    for invoice_index, invoice_item in enumerate(invoice.line_items, start=1):
        candidates = sorted(
            ((_description_score(invoice_item.description, purchase_order.line_items[index].description), index)
             for index in unmatched_po),
            reverse=True,
        )
        if not candidates or candidates[0][0] < DESCRIPTION_MATCH_THRESHOLD:
            checks.append(ConfiguredCheck(
                id=f"line_item_{invoice_index}", label=f"Line {invoice_index}: {invoice_item.description}",
                status="failed", detail="No matching line item was found on the purchase order.",
            ))
            continue
        _, po_index = candidates[0]
        unmatched_po.remove(po_index)
        po_item = purchase_order.line_items[po_index]
        problem = _line_problem(invoice_item, po_item)
        checks.append(ConfiguredCheck(
            id=f"line_item_{invoice_index}", label=f"Line {invoice_index}: {invoice_item.description}",
            status="failed" if problem else "passed",
            detail=problem or f"Matched PO line '{po_item.description}'; quantity and unit price are within tolerance.",
        ))

    if not invoice.line_items:
        checks.append(ConfiguredCheck(
            id="line_items_match", label="Invoice lines match the PO", status="not_checked",
            detail="No invoice line items were available to match.",
        ))

    total_ok = (
        invoice.total is not None
        and purchase_order.total is not None
        and invoice.total - purchase_order.total <= MONEY_TOLERANCE
    )
    checks.append(ConfiguredCheck(
        id="po_total_limit", label="Invoice is within the PO total",
        status="passed" if total_ok else ("not_checked" if invoice.total is None or purchase_order.total is None else "failed"),
        detail=(
            f"Invoice total {invoice.total:.2f} does not exceed PO total {purchase_order.total:.2f}."
            if total_ok else
            "Invoice and PO totals are both required for this check."
            if invoice.total is None or purchase_order.total is None else
            f"Invoice total {invoice.total:.2f} exceeds PO total {purchase_order.total:.2f}."
        ),
    ))

    problems = [check.detail for check in checks if check.status != "passed"]
    return TwoWayMatchResponse(
        status="matched" if not problems else "needs_review",
        purchase_order_id=purchase_order_id,
        po_number=purchase_order.po_number,
        checks=checks,
        reasons=problems,
    )
