"""
STEP 1: Define WHAT you want to extract.

This Pydantic model is the "contract" we give to OpenAI.
With structured output, the LLM is forced to return JSON that matches
this exact shape, so we never have to parse messy free text.
The `description` fields are sent to the model as instructions, so write them carefully.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(description="Name or description of the product/service")
    quantity: Optional[float] = Field(default=None, description="Quantity ordered")
    unit_price: Optional[float] = Field(default=None, description="Price per unit, number only")
    amount: Optional[float] = Field(default=None, description="Line total (quantity x unit price), number only")


class Invoice(BaseModel):
    vendor_name: Optional[str] = Field(default=None, description="Company that issued the invoice (the seller)")
    invoice_number: Optional[str] = Field(default=None, description="Invoice number / ID")
    invoice_date: Optional[str] = Field(default=None, description="Invoice date in YYYY-MM-DD format")
    po_number: Optional[str] = Field(default=None, description="Purchase Order (PO) number, if present")
    currency: Optional[str] = Field(default=None, description="3-letter currency code, e.g. USD, INR, EUR")
    line_items: List[LineItem] = Field(default_factory=list, description="Every line item in the invoice table")
    subtotal: Optional[float] = Field(default=None, description="Subtotal before tax")
    # --- FIX 1 (schema): fields for the two things invoices show that used to have nowhere to go.
    # Without them the model had to bend the line items or the subtotal to make the maths work.
    discount: Optional[float] = Field(
        default=None,
        description=("Discount, rebate or credit deducted before tax, as a POSITIVE number: a line "
                     "reading 'Discount 10% -8,680.00' becomes 8680.0. Record this only if the "
                     "invoice actually shows a discount line. Otherwise leave it null. Never invent "
                     "or calculate a discount, and never put the discount in line_items."),
    )
    shipping: Optional[float] = Field(
        default=None,
        description=("Shipping, freight, delivery, handling or packing charge, as a POSITIVE number. "
                     "Record this only if the invoice actually shows such a charge. Otherwise leave "
                     "it null. Never invent or calculate it, and never put it in line_items."),
    )
    tax: Optional[float] = Field(default=None, description="Total tax amount (GST/VAT etc.)")
    total: Optional[float] = Field(default=None, description="Final amount due")


class PurchaseOrder(BaseModel):
    """Fields required to match supplier invoices to a purchase order."""

    vendor_name: Optional[str] = Field(default=None, description="Supplier named on the purchase order")
    po_number: Optional[str] = Field(default=None, description="Purchase order number / ID")
    order_date: Optional[str] = Field(default=None, description="Purchase order date in YYYY-MM-DD format")
    currency: Optional[str] = Field(default=None, description="3-letter currency code, e.g. USD, INR, EUR")
    line_items: List[LineItem] = Field(default_factory=list, description="Every ordered line item")
    subtotal: Optional[float] = Field(default=None, description="Subtotal before tax and shipping")
    shipping: Optional[float] = Field(default=None, description="Authorized shipping or freight amount")
    tax: Optional[float] = Field(default=None, description="Authorized tax amount")
    total: Optional[float] = Field(default=None, description="Total value authorized by the purchase order")
