"""
Generates the test invoices (invoices/invoice_02.pdf .. invoice_15.pdf) plus a
matching answer key for each (answer_keys/invoice_02.json .. invoice_15.json).

Each invoice's data is defined once, and BOTH the PDF and the answer key are built
from it, so the two can never disagree.

Easy set (clean, computer-generated, everything adds up):
    invoice_02  Northwind Catering (EUR)    - no PO number
    invoice_03  Blue Ridge Software (USD)   - US date format 09/03/2026
    invoice_04  Sharma Electricals (INR)    - 10 line items, tax split into CGST + SGST
    invoice_05  Brightline Design (GBP)     - final amount labeled "Amount Due"

Hard set (each one breaks an assumption):
    invoice_06  Continental Paper (USD)     - 3 pages, items span pages, totals only on page 3
    invoice_07  Lakeview Furniture (INR)    - discount line: items do NOT sum to the subtotal
    invoice_08  Riverside Tools (USD)       - freight added after the subtotal: subtotal + tax != total
    invoice_09  Acme credit note (INR)      - negative amounts and a negative total
    invoice_10  Hoffmann Burotechnik (EUR)  - German labels, 15.09.2026 date, 1.997,00 number format
    invoice_11  Verma Pustak Bhandar (INR)  - Hindi (Devanagari) mixed with English
    invoice_12  Two invoices in one PDF     - answer key covers the FIRST invoice only
    invoice_13  Ravi Electric Works (INR)   - informal bill, no invoice number, no PO, no tax line
    invoice_14  Meridian Fasteners (USD)    - four similar-looking reference numbers
    invoice_15  Cloudline Hosting (USD)     - ambiguous date 04/05/2026

Where the "correct" answer is genuinely debatable, the answer key carries a
"notes" field explaining the judgment call. evaluate.py ignores that field.
"""
import json
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

os.makedirs("invoices", exist_ok=True)
os.makedirs("answer_keys", exist_ok=True)
styles = getSampleStyleSheet()


def money(x):
    return f"{x:,.2f}"


def qty(x):
    return f"{x:g}"  # 20.0 -> "20"


def money_de(x):
    """German number format: 1997.0 -> '1.997,00'"""
    return f"{x:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


AUTO = object()  # "work this out from the line items"


def build_key(vendor, number, date_iso, po, currency, rows, tax_rates,
              subtotal=AUTO, tax=AUTO, total=AUTO, notes=None, discount=None, shipping=None):
    """
    rows: (description, quantity, unit_price). Returns a dict in the same format as main.py's output.

    subtotal / tax / total are worked out from the line items unless passed in. Pass them
    (including None) for invoices where the printed figures deliberately do not follow from
    the items, such as a discount, a freight charge, or a bill with no tax line at all.

    discount / shipping are null on most invoices and are only filled in where the invoice
    prints such a line. Both are positive amounts, matching the schema.
    """
    items = [
        {"description": d, "quantity": float(q), "unit_price": float(p), "amount": round(q * p, 2)}
        for d, q, p in rows
    ]
    if subtotal is AUTO:
        subtotal = round(sum(li["amount"] for li in items), 2)
    if tax is AUTO:
        tax = round(sum(round(subtotal * r, 2) for r in tax_rates), 2)
    if total is AUTO:
        total = round(subtotal + tax, 2)

    key = {
        "vendor_name": vendor,
        "invoice_number": number,
        "invoice_date": date_iso,
        "po_number": po,
        "currency": currency,
        "line_items": items,
        "subtotal": subtotal,
        "discount": discount,
        "shipping": shipping,
        "tax": tax,
        "total": total,
    }
    if notes:
        key["notes"] = notes  # a judgment call, explained. evaluate.py ignores this field.
    return key


def save_key(name, key):
    with open(f"answer_keys/{name}.json", "w") as f:
        json.dump(key, f, indent=2)


def draw_cells(c, y, cells, xs, first_right=1):
    """Draw one row on a canvas. Columns from index `first_right` on are right-aligned at their x."""
    for i, (text, x) in enumerate(zip(cells, xs)):
        if i >= first_right:
            c.drawRightString(x, y, text)
        else:
            c.drawString(x, y, text)


# ---------- invoice_02: two-column header, striped table, NO PO number ----------
def invoice_02():
    key = build_key(
        "Northwind Catering GmbH", "NWC-7781", "2026-08-22", None, "EUR",
        [
            ("Conference lunch buffet (per person)", 45, 18.00),
            ("Coffee & pastry service (per person)", 45, 6.00),
            ("Service staff (hours)", 6, 32.00),
        ],
        [0.19],
    )
    doc = SimpleDocTemplate("invoices/invoice_02.pdf", pagesize=A4)
    header = Table([[
        Paragraph("<font size=16><b>Northwind Catering GmbH</b></font><br/><br/>"
                  "Friedrichstrasse 118<br/>10117 Berlin, Germany<br/>VAT ID: DE298765432", styles["Normal"]),
        Paragraph("<font size=14><b>INVOICE</b></font><br/><br/>Invoice #: NWC-7781<br/>"
                  "Date: August 22, 2026<br/>Customer: Helios Consulting AG", styles["Normal"]),
    ]], colWidths=[280, 200])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    rows = [["Item", "Qty", "Price (€)", "Total (€)"]]
    rows += [[li["description"], qty(li["quantity"]), money(li["unit_price"]), money(li["amount"])]
             for li in key["line_items"]]
    n = len(rows)
    rows += [
        ["", "", "Net amount", money(key["subtotal"])],
        ["", "", "VAT 19%", money(key["tax"])],
        ["", "", "Total (EUR)", "€ " + money(key["total"])],
    ]
    t = Table(rows, colWidths=[230, 50, 100, 100])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e7d32")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, n - 1), [colors.white, colors.HexColor("#e8f5e9")]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (2, n), (-1, n), 0.5, colors.grey),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    doc.build([
        header, Spacer(1, 24), t, Spacer(1, 24),
        Paragraph("Please transfer the amount within 14 days to IBAN DE44 1001 0010 0123 4567 89.", styles["Normal"]),
    ])
    save_key("invoice_02", key)


# ---------- invoice_03: hand-drawn US Letter layout, USD, US date format ----------
def invoice_03():
    key = build_key(
        "Blue Ridge Software LLC", "BRS-10293", "2026-09-03", "PO-5521-A", "USD",
        [
            ("Annual license - Team plan", 1, 4800.00),
            ("Additional user seats", 12, 120.00),
            ("Onboarding & training (hours)", 8, 150.00),
        ],
        [0.0825],
    )
    c = canvas.Canvas("invoices/invoice_03.pdf", pagesize=LETTER)
    w, h = LETTER

    c.setFillColor(colors.HexColor("#0d47a1"))
    c.rect(0, h - 90, w, 90, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, h - 50, "Blue Ridge Software LLC")
    c.setFont("Helvetica", 9)
    c.drawString(40, h - 68, "401 Congress Ave, Suite 1500, Austin, TX 78701  |  (512) 555-0147")
    c.setFont("Helvetica-Bold", 26)
    c.drawRightString(w - 40, h - 58, "INVOICE")

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    info = [("Invoice #:", "BRS-10293"), ("Invoice Date:", "09/03/2026"),
            ("Due Date:", "10/03/2026"), ("PO Number:", "PO-5521-A")]
    y = h - 125
    for label, value in info:
        c.drawRightString(w - 140, y, label)
        c.drawRightString(w - 40, y, value)
        y -= 15

    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, h - 125, "BILL TO")
    c.setFont("Helvetica", 10)
    for i, line in enumerate(["Cascade Health Partners", "2200 Westlake Ave N", "Seattle, WA 98109"]):
        c.drawString(40, h - 140 - i * 14, line)

    xs = [40, 360, 460, w - 40]
    y = h - 225
    c.setFillColor(colors.HexColor("#e3f2fd"))
    c.rect(35, y - 6, w - 70, 20, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    draw_cells(c, y, ["DESCRIPTION", "QTY", "RATE", "AMOUNT"], xs)
    c.setFont("Helvetica", 10)
    for li in key["line_items"]:
        y -= 22
        draw_cells(c, y, [li["description"], qty(li["quantity"]), "$" + money(li["unit_price"]),
                          "$" + money(li["amount"])], xs)
    y -= 12
    c.line(300, y, w - 40, y)

    for label, value, bold in [("Subtotal", key["subtotal"], False),
                               ("Sales Tax (8.25%)", key["tax"], False),
                               ("Total (USD)", key["total"], True)]:
        y -= 18
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(460, y, label)
        c.drawRightString(w - 40, y, "$" + money(value))

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(40, 60, "Payment terms: Net 30. Make checks payable to Blue Ridge Software LLC.")
    c.save()
    save_key("invoice_03", key)


# ---------- invoice_04: dense GST invoice with 10 line items, HSN codes, CGST + SGST ----------
def invoice_04():
    rows_data = [
        ("LED Panel Light 18W", "9405", 24, 650.00),
        ("Copper Wire 2.5 sq mm (90 m coil)", "8544", 6, 2350.00),
        ("Modular Switch 6A", "8536", 40, 85.00),
        ("MCB 32A Double Pole", "8536", 8, 780.00),
        ("Extension Board 4-Socket", "8536", 15, 420.00),
        ("PVC Conduit Pipe 25mm (3 m)", "3917", 50, 95.00),
        ("Ceiling Fan 1200mm", "8414", 6, 2850.00),
        ("Exhaust Fan 250mm", "8414", 4, 1450.00),
        ("Insulation Tape (Pack of 10)", "3919", 12, 180.00),
        ("Distribution Board 8-Way", "8537", 2, 3200.00),
    ]
    key = build_key(
        "Sharma Electricals & Hardware", "SEH/26-27/0192", "2026-09-05", "PO/ENG/4471", "INR",
        [(d, q, p) for d, _, q, p in rows_data],
        [0.09, 0.09],  # CGST 9% + SGST 9%
    )
    cgst = round(key["subtotal"] * 0.09, 2)
    small = styles["Normal"].clone("small", fontSize=9, leading=11)

    doc = SimpleDocTemplate("invoices/invoice_04.pdf", pagesize=A4, topMargin=36, bottomMargin=36)
    story = [
        Paragraph("<para align=center><b>TAX INVOICE</b></para>", styles["Heading3"]),
        Paragraph("<b>Sharma Electricals &amp; Hardware</b>", styles["Heading2"]),
        Paragraph("Shop No. 14, Laxmi Road, Pune, Maharashtra 411002 | GSTIN: 27AAKFS5678L1Z2 | Ph: 020-2445 6789", small),
        Spacer(1, 10),
    ]
    details = Table([
        ["Invoice No:", "SEH/26-27/0192", "Buyer:", "Kulkarni Constructions Pvt. Ltd."],
        ["Invoice Date:", "05-Sep-2026", "Site:", "Baner, Pune 411045"],
        ["Buyer's Order No:", "PO/ENG/4471", "Buyer GSTIN:", "27AABCK4321M1Z9"],
    ], colWidths=[95, 120, 75, 190])
    details.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                                 ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                                 ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold")]))
    story += [details, Spacer(1, 10)]

    rows = [["S.No", "Description of Goods", "HSN", "Qty", "Rate", "Amount"]]
    for i, ((desc, hsn, _, _), li) in enumerate(zip(rows_data, key["line_items"]), start=1):
        rows.append([str(i), desc, hsn, qty(li["quantity"]), money(li["unit_price"]), money(li["amount"])])
    rows += [
        ["", "", "", "", "Taxable Value", money(key["subtotal"])],
        ["", "", "", "", "CGST @ 9%", money(cgst)],
        ["", "", "", "", "SGST @ 9%", money(cgst)],
        ["", "", "", "", "Grand Total", money(key["total"])],
    ]
    t = Table(rows, colWidths=[35, 190, 45, 40, 80, 90])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff3e0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (4, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story += [
        t, Spacer(1, 8),
        Paragraph("<b>Amount in words:</b> Rupees Ninety-Six Thousand Five Hundred Eighty-Three Only", small),
        Spacer(1, 30),
        Paragraph("<para align=right>For Sharma Electricals &amp; Hardware<br/><br/><br/>Authorised Signatory</para>", small),
    ]
    doc.build(story)
    save_key("invoice_04", key)


# ---------- invoice_05: minimal, no grid lines, GBP, final line labeled "Amount Due" ----------
def invoice_05():
    key = build_key(
        "Brightline Design Studio Ltd", "BDS-0042", "2026-09-12", "BL-PO-2231", "GBP",
        [
            ("Brand identity design", 1, 2400.00),
            ("Website mockups (per page)", 5, 180.00),
            ("Revision rounds", 3, 75.00),
        ],
        [0.20],
    )
    c = canvas.Canvas("invoices/invoice_05.pdf", pagesize=A4)
    w, h = A4

    c.setFillColor(colors.HexColor("#6a1b9a"))
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, h - 70, "brightline")
    c.setFillColor(colors.grey)
    c.setFont("Helvetica", 9)
    c.drawString(50, h - 86, "Brightline Design Studio Ltd  ·  27 Ancoats Street, Manchester M4 5AA  ·  VAT No. GB 312 4567 89")

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    y = h - 130
    for label, value in [("Invoice", "BDS-0042"), ("Issued", "12 Sep 2026"),
                         ("Your reference", "BL-PO-2231"), ("Client", "Harbour & Finch Coffee Co.")]:
        c.setFillColor(colors.grey)
        c.drawString(50, y, label)
        c.setFillColor(colors.black)
        c.drawString(160, y, value)
        y -= 16

    y -= 30
    for li in key["line_items"]:
        c.setFont("Helvetica", 11)
        c.drawString(50, y, li["description"])
        c.drawRightString(w - 50, y, "£" + money(li["amount"]))
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.grey)
        c.drawString(50, y - 13, f"{qty(li['quantity'])} x £{money(li['unit_price'])}")
        c.setFillColor(colors.black)
        y -= 40

    for label, value in [("Subtotal", key["subtotal"]), ("VAT (20%)", key["tax"])]:
        c.setFont("Helvetica", 10)
        c.drawRightString(w - 160, y, label)
        c.drawRightString(w - 50, y, "£" + money(value))
        y -= 18
    y -= 10
    c.setFillColor(colors.HexColor("#6a1b9a"))
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(w - 160, y, "Amount Due")
    c.drawRightString(w - 50, y, "£" + money(key["total"]))

    c.setFillColor(colors.grey)
    c.setFont("Helvetica", 9)
    c.drawString(50, 60, "Payable within 21 days by bank transfer. Sort code 20-45-77, Account 43917265.")
    c.save()
    save_key("invoice_05", key)


# =============================================================================
# HARD SET: invoice_06 to invoice_15
# =============================================================================

# ---------- invoice_06: 3 pages, items span pages, totals only on the last page ----------
def invoice_06():
    key = build_key(
        "Continental Paper & Packaging Co.", "PKG-2026-3341", "2026-09-08", "PO-CP-7788", "USD",
        [
            ("Corrugated Box 12x12x12 (Bundle of 25)", 40, 22.50),
            ("Corrugated Box 18x18x18 (Bundle of 25)", 20, 38.00),
            ("Kraft Paper Roll 900mm", 12, 54.00),
            ("Bubble Wrap Roll 1m x 50m", 15, 41.00),
            ("Stretch Film 500mm", 30, 18.75),
            ("Packing Tape 48mm (Pack of 6)", 25, 14.40),
            ("Void Fill Paper (Carton)", 10, 62.00),
            ("Edge Protector 50mm (Pack of 50)", 8, 33.50),
            ("Pallet Wrap Dispenser", 4, 47.25),
            ("Shipping Label Roll 4x6 (1000 ct)", 18, 21.00),
            ("Poly Mailer 10x13 (Pack of 500)", 14, 29.50),
            ("Foam Sheet 12x12 (Pack of 100)", 9, 36.00),
            ("Strapping Band 12mm Roll", 6, 58.00),
            ("Desiccant Pack 50g (Box of 200)", 5, 44.00),
        ],
        [0.06],
    )
    small = styles["Normal"].clone("small06", fontSize=9, leading=11)
    doc = SimpleDocTemplate("invoices/invoice_06.pdf", pagesize=LETTER, topMargin=40)
    items = key["line_items"]
    pages = [items[:6], items[6:11], items[11:]]

    story = []
    for page_no, chunk in enumerate(pages, start=1):
        story += [
            Paragraph("<b>Continental Paper &amp; Packaging Co.</b>", styles["Heading2"]),
            Paragraph("2400 Industrial Parkway, Columbus, OH 43228 | (614) 555-0188", small),
            Paragraph("Invoice PKG-2026-3341 &nbsp; | &nbsp; Date: 08 September 2026 &nbsp; | &nbsp; "
                      f"PO: PO-CP-7788 &nbsp; | &nbsp; <b>Page {page_no} of 3</b>", small),
            Spacer(1, 12),
        ]
        data = [["Description", "Qty", "Rate", "Amount"]]
        data += [[li["description"], qty(li["quantity"]), money(li["unit_price"]), money(li["amount"])]
                 for li in chunk]
        t = Table(data, colWidths=[260, 50, 80, 90])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(t)
        if page_no < 3:
            story += [Spacer(1, 10), Paragraph("<i>Continued on next page ...</i>", small), PageBreak()]

    totals = Table([
        ["Subtotal", money(key["subtotal"])],
        ["Sales Tax (6%)", money(key["tax"])],
        ["Total (USD)", money(key["total"])],
    ], colWidths=[130, 90], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.grey),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story += [Spacer(1, 16), totals, Spacer(1, 16),
              Paragraph("Totals apply to all 14 items across pages 1 to 3. Net 30.", small)]
    doc.build(story)
    save_key("invoice_06", key)


# ---------- invoice_07: a discount line, so items do NOT sum to the subtotal ----------
def invoice_07():
    items_sum = 86800.00
    discount = -8680.00                      # "Festive discount 10%", printed as its own line
    subtotal_after_discount = 78120.00       # what the invoice prints as Subtotal
    key = build_key(
        "Lakeview Furniture Works", "LFW-2026-118", "2026-09-10", "PO-LV-0031", "INR",
        [
            ("Study Table (Oak finish)", 6, 7450.00),
            ("Bookshelf 5-Tier", 4, 3900.00),
            ("Office Chair (Mesh Back)", 10, 2650.00),
        ],
        [0.18],
        subtotal=subtotal_after_discount,
        discount=8680.00,
        notes=("The invoice prints a 10% festive discount (-8,680.00) between the items and the "
               "subtotal. It is recorded in the discount field as a POSITIVE 8,680.00, and the "
               "subtotal is the discounted figure printed on the invoice, so line items "
               "(86,800.00) minus discount equals the subtotal (78,120.00). The discount must NOT "
               "appear as a line item. A client may instead want it captured as a negative line "
               "item, in which case the line_items count would be 4 rather than 3."),
    )
    assert round(sum(li["amount"] for li in key["line_items"]), 2) == items_sum

    doc = SimpleDocTemplate("invoices/invoice_07.pdf", pagesize=A4)
    small = styles["Normal"].clone("small07", fontSize=9, leading=11)
    rows = [["Description", "Qty", "Rate (INR)", "Amount (INR)"]]
    rows += [[li["description"], qty(li["quantity"]), money(li["unit_price"]), money(li["amount"])]
             for li in key["line_items"]]
    n = len(rows)
    rows += [
        ["", "", "Gross amount", money(items_sum)],
        ["", "", "Festive discount 10%", money(discount)],
        ["", "", "Subtotal", money(key["subtotal"])],
        ["", "", "GST 18%", money(key["tax"])],
        ["", "", "Total Payable", money(key["total"])],
    ]
    t = Table(rows, colWidths=[210, 50, 120, 110])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4e342e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, n - 1), 0.4, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TEXTCOLOR", (2, n + 1), (-1, n + 1), colors.HexColor("#b71c1c")),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    doc.build([
        Paragraph("Lakeview Furniture Works", styles["Title"]),
        Paragraph("Plot 22, Furniture Cluster, Jodhpur 342001 | GSTIN: 08AACFL9911K1ZP", small),
        Spacer(1, 14),
        Paragraph("<b>INVOICE</b> LFW-2026-118", styles["Heading3"]),
        Paragraph("Date: 10 September 2026 | PO: PO-LV-0031 | Buyer: Nimbus Coworking LLP", small),
        Spacer(1, 14), t, Spacer(1, 18),
        Paragraph("Discount applied under the festive scheme. Goods once sold are not returnable.", small),
    ])
    save_key("invoice_07", key)


# ---------- invoice_08: freight added AFTER the subtotal, so subtotal + tax != total ----------
def invoice_08():
    freight = 185.00
    key = build_key(
        "Riverside Tools & Machinery", "RTM-88214", "2026-09-11", "PO-RS-9912", "USD",
        [
            ("Cordless Drill 18V", 8, 129.00),
            ("Angle Grinder 5in", 5, 89.50),
            ("Tool Chest 5-Drawer", 2, 415.00),
            ("Socket Set 120-Piece", 6, 74.25),
        ],
        [0.07],
        total=3132.85,  # 2755.00 items + 185.00 freight + 192.85 tax
        shipping=185.00,
        notes=("A freight charge of 185.00 is added after the subtotal. It is recorded in the "
               "shipping field, so subtotal (2,755.00) + tax (192.85) + shipping equals the total "
               "(3,132.85). Tax is charged on the subtotal only, not on the freight. The freight "
               "must NOT appear as a line item. A client may instead want it captured as a line "
               "item, in which case the line_items count would be 5 rather than 4."),
    )
    c = canvas.Canvas("invoices/invoice_08.pdf", pagesize=A4)
    w, h = A4

    c.setFillColor(colors.HexColor("#eceff1"))
    c.rect(0, h - 110, w, 110, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#263238"))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(45, h - 55, "RIVERSIDE TOOLS & MACHINERY")
    c.setFont("Helvetica", 9)
    c.drawString(45, h - 72, "18 Dockside Road, Cleveland, OH 44113  |  sales@riversidetools.example")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(45, h - 95, "INVOICE RTM-88214")
    c.setFont("Helvetica", 9)
    c.drawRightString(w - 45, h - 95, "Invoice Date: 11 Sep 2026    PO: PO-RS-9912")

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(45, h - 135, "Ship to: Hollow Creek Builders, 77 Quarry Lane, Akron, OH 44301")

    xs = [45, 360, 450, w - 45]
    y = h - 175
    c.setFont("Helvetica-Bold", 10)
    draw_cells(c, y, ["Item", "Qty", "Unit", "Amount"], xs)
    c.line(45, y - 5, w - 45, y - 5)
    c.setFont("Helvetica", 10)
    for li in key["line_items"]:
        y -= 20
        draw_cells(c, y, [li["description"], qty(li["quantity"]),
                          "$" + money(li["unit_price"]), "$" + money(li["amount"])], xs)

    y -= 30
    for label, value, bold in [("Subtotal", key["subtotal"], False),
                               ("Freight & Handling", freight, False),
                               ("Sales Tax (7%)", key["tax"], False),
                               ("Amount Payable (USD)", key["total"], True)]:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(450, y, label)
        c.drawRightString(w - 45, y, "$" + money(value))
        y -= 18
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(45, 60, "Freight is charged at cost and is not taxed. Net 15.")
    c.save()
    save_key("invoice_08", key)


# ---------- invoice_09: credit note with negative amounts and a negative total ----------
def invoice_09():
    key = build_key(
        "Acme Office Supplies Pvt. Ltd.", "CN-2026-0088", "2026-09-18", "PO-88213", "INR",
        [
            ("Ergonomic Office Chair (returned, damaged in transit)", -2, 8500.00),
            ("Whiteboard Markers (Pack of 12) (returned, wrong item)", -5, 240.00),
        ],
        [0.18],
        notes=("This is a credit note, not an invoice: every amount is negative and so is the total "
               "(-21,476.00), because money flows back to the buyer. Quantities are recorded as "
               "negative exactly as printed, so quantity x unit price = amount. A client may prefer "
               "positive quantities with negative amounts, or positive figures plus a document-type "
               "flag. The referenced original invoice (INV-2026-0457) is not the invoice_number here; "
               "the credit note's own number CN-2026-0088 is."),
    )
    doc = SimpleDocTemplate("invoices/invoice_09.pdf", pagesize=A4)
    small = styles["Normal"].clone("small09", fontSize=9, leading=11)
    rows = [["Description", "Qty", "Rate (INR)", "Amount (INR)"]]
    rows += [[li["description"], qty(li["quantity"]), money(li["unit_price"]), money(li["amount"])]
             for li in key["line_items"]]
    n = len(rows)
    rows += [
        ["", "", "Subtotal", money(key["subtotal"])],
        ["", "", "GST @ 18%", money(key["tax"])],
        ["", "", "Total Credit", money(key["total"])],
    ]
    t = Table(rows, colWidths=[260, 45, 90, 95])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b71c1c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, n - 1), 0.4, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 1), (3, -1), colors.HexColor("#b71c1c")),
    ]))
    doc.build([
        Paragraph("Acme Office Supplies Pvt. Ltd.", styles["Title"]),
        Paragraph("12 Park Street, Kolkata 700016 | GSTIN: 19AABCA1234F1Z5", small),
        Spacer(1, 14),
        Paragraph("<b>CREDIT NOTE</b>", styles["Heading2"]),
        Paragraph("Credit Note No: CN-2026-0088<br/>Date: 18 September 2026<br/>"
                  "Against Invoice: INV-2026-0457 dated 15 September 2026<br/>"
                  "PO Number: PO-88213<br/>Issued to: Globex Technologies, Salt Lake Sector V, Kolkata", small),
        Spacer(1, 14), t, Spacer(1, 18),
        Paragraph("This credit note reduces the amount payable against the referenced invoice. "
                  "Negative figures indicate a refund to the buyer.", small),
    ])
    save_key("invoice_09", key)


# ---------- invoice_10: German labels, European date and German number format ----------
def invoice_10():
    key = build_key(
        "Hoffmann Bürotechnik GmbH", "2026-RE-4417", "2026-09-15", "BE-2211", "EUR",
        [
            ("Laserdrucker HL-3280", 3, 289.00),
            ("Tonerkartusche schwarz", 12, 68.50),
            ("Aktenvernichter P-4", 2, 154.00),
        ],
        [0.19],
        notes=("Everything is in German. 'Rechnungsnummer' is the invoice number, 'Bestellnummer' "
               "(order number) is treated as the PO number, 'Zwischensumme' is the subtotal, 'MwSt.' "
               "is the tax and 'Summe' is the total. The date 15.09.2026 is day.month.year -> "
               "2026-09-15. Amounts use German formatting (1.997,00 means one thousand nine hundred "
               "ninety-seven), which must not be read as 1.997. Item descriptions are kept in German "
               "as printed; a client may want them translated."),
    )
    doc = SimpleDocTemplate("invoices/invoice_10.pdf", pagesize=A4)
    small = styles["Normal"].clone("small10", fontSize=9, leading=11)
    header = Table([[
        Paragraph("<b>Hoffmann Bürotechnik GmbH</b><br/>Lindenallee 47<br/>40212 Düsseldorf<br/>"
                  "USt-IdNr.: DE811234567", small),
        Paragraph("<b>Rechnungsnummer:</b> 2026-RE-4417<br/><b>Rechnungsdatum:</b> 15.09.2026<br/>"
                  "<b>Bestellnummer:</b> BE-2211<br/><b>Kundennummer:</b> K-90233", small),
    ]], colWidths=[250, 230])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    rows = [["Pos.", "Bezeichnung", "Menge", "Einzelpreis", "Betrag"]]
    for i, li in enumerate(key["line_items"], start=1):
        rows.append([str(i), li["description"], qty(li["quantity"]),
                     money_de(li["unit_price"]) + " €", money_de(li["amount"]) + " €"])
    n = len(rows)
    rows += [
        ["", "", "", "Zwischensumme", money_de(key["subtotal"]) + " €"],
        ["", "", "", "MwSt. 19%", money_de(key["tax"]) + " €"],
        ["", "", "", "Summe", money_de(key["total"]) + " €"],
    ]
    t = Table(rows, colWidths=[35, 200, 55, 95, 95])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d47a1")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, n - 1), 0.4, colors.grey),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    doc.build([
        Paragraph("RECHNUNG", styles["Title"]), Spacer(1, 10), header, Spacer(1, 18),
        Paragraph("Lieferung an: Steinbach Consulting GmbH, Königsallee 12, 40212 Düsseldorf", small),
        Spacer(1, 12), t, Spacer(1, 18),
        Paragraph("Zahlbar innerhalb von 14 Tagen ohne Abzug. Vielen Dank für Ihren Auftrag.", small),
    ])
    save_key("invoice_10", key)


# ---------- invoice_11: Hindi (Devanagari) mixed with English ----------
HINDI_FONT = "Nirmala"


def register_hindi_font():
    """Nirmala UI ships with Windows and covers Devanagari. Returns False if it isn't available."""
    for path in (r"C:\Windows\Fonts\Nirmala.ttc", r"C:\Windows\Fonts\mangal.ttf"):
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(HINDI_FONT, path, subfontIndex=0))
                return True
            except Exception:
                continue
    return False


def invoice_11():
    if not register_hindi_font():
        print("  ! No Devanagari font found (looked for Nirmala.ttc / mangal.ttf); skipping invoice_11")
        return False

    key = build_key(
        "Verma Pustak Bhandar", "VPB-2026-77", "2026-09-12", "PO-VPB-15", "INR",
        [
            ("रजिस्टर A4 (200 पेज)", 25, 85.00),
            ("बॉल पेन नीला (Box of 20)", 10, 160.00),
            ("फाइल कवर plastic", 40, 45.00),
            ("नोटबुक 100 पेज", 60, 32.00),
        ],
        [0.18],
        notes=("The vendor name is printed twice: 'वर्मा पुस्तक भंडार' in Devanagari and "
               "'Verma Pustak Bhandar' in English. The English form is recorded here; a client may "
               "want the Devanagari form instead. Item descriptions are kept exactly as printed, "
               "mixing both scripts. The date 12-09-2026 is day-month-year (Indian convention) -> "
               "2026-09-12."),
    )
    c = canvas.Canvas("invoices/invoice_11.pdf", pagesize=A4)
    w, h = A4

    c.setFont(HINDI_FONT, 19)
    c.drawString(45, h - 60, "वर्मा पुस्तक भंडार")
    c.setFont(HINDI_FONT, 9)
    c.drawString(45, h - 76, "Verma Pustak Bhandar, Chowk Bazaar, Varanasi 221001 | GSTIN: 09AABCV1234K1Z8")
    c.setFont(HINDI_FONT, 12)
    c.drawString(45, h - 105, "बिल / TAX INVOICE")
    c.setFont(HINDI_FONT, 10)
    for i, line in enumerate([
        "बिल संख्या / Invoice No: VPB-2026-77",
        "दिनांक / Date: 12-09-2026",
        "क्रय आदेश / PO: PO-VPB-15",
        "ग्राहक / Customer: सूर्या पब्लिक स्कूल (Surya Public School)",
    ]):
        c.drawString(45, h - 128 - i * 15, line)

    xs = [45, 330, 420, w - 45]
    y = h - 210
    c.setFont(HINDI_FONT, 10)
    draw_cells(c, y, ["विवरण / Description", "मात्रा", "दर", "राशि"], xs)
    c.line(45, y - 5, w - 45, y - 5)
    for li in key["line_items"]:
        y -= 20
        draw_cells(c, y, [li["description"], qty(li["quantity"]),
                          money(li["unit_price"]), money(li["amount"])], xs)

    y -= 28
    for label, value in [("उप-योग (Subtotal)", key["subtotal"]),
                         ("जीएसटी 18% (GST)", key["tax"]),
                         ("कुल राशि (Total)", key["total"])]:
        c.drawRightString(420, y, label)
        c.drawRightString(w - 45, y, money(value))
        y -= 18
    c.setFont(HINDI_FONT, 9)
    c.drawString(45, 60, "भुगतान 15 दिनों के भीतर करें / Please pay within 15 days.")
    c.save()
    save_key("invoice_11", key)


# ---------- invoice_12: two unrelated invoices in one PDF; key covers the FIRST only ----------
def invoice_12():
    key = build_key(
        "Sunrise Dairy Supplies", "SDS-401", "2026-09-14", "PO-SD-77", "INR",
        [
            ("Toned Milk 500ml (Crate of 24)", 30, 660.00),
            ("Curd 400g (Pack of 12)", 20, 384.00),
            ("Paneer 200g", 25, 96.00),
        ],
        [0.05],
        notes=("Two unrelated invoices were scanned into one PDF: Sunrise Dairy Supplies (SDS-401) on "
               "page 1 and Golden Harvest Grains (GHG-2211, total 19,372.50) on page 2. This answer "
               "key covers ONLY the first invoice. An agent that merges the two, or returns the "
               "second, counts as wrong. In production such a file should be split before extraction; "
               "a client may instead expect a list of two invoices."),
    )
    small = styles["Normal"].clone("small12", fontSize=9, leading=11)
    doc = SimpleDocTemplate("invoices/invoice_12.pdf", pagesize=A4)

    # --- page 1: the invoice the answer key describes ---
    rows = [["Description", "Qty", "Rate (INR)", "Amount (INR)"]]
    rows += [[li["description"], qty(li["quantity"]), money(li["unit_price"]), money(li["amount"])]
             for li in key["line_items"]]
    n = len(rows)
    rows += [
        ["", "", "Subtotal", money(key["subtotal"])],
        ["", "", "GST 5%", money(key["tax"])],
        ["", "", "Total", money(key["total"])],
    ]
    t1 = Table(rows, colWidths=[220, 50, 110, 110])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f9a825")),
        ("GRID", (0, 0), (-1, n - 1), 0.4, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story = [
        Paragraph("Sunrise Dairy Supplies", styles["Title"]),
        Paragraph("Dairy Road, Anand 388001, Gujarat | GSTIN: 24AAJCS7788P1ZR", small),
        Spacer(1, 12),
        Paragraph("<b>TAX INVOICE</b> SDS-401", styles["Heading3"]),
        Paragraph("Date: 14 September 2026 | PO: PO-SD-77 | Buyer: Cafe Aroma, Vadodara", small),
        Spacer(1, 12), t1, Spacer(1, 16),
        Paragraph("Chilled goods. Payment within 7 days.", small),
        PageBreak(),
    ]

    # --- page 2: a completely different invoice, deliberately not in the answer key ---
    other_items = [("Wheat Flour 10kg", 15, 430.00), ("Basmati Rice 25kg", 8, 1500.00)]
    other_rows = [[d, qty(q), money(p), money(q * p)] for d, q, p in other_items]
    other_sum = sum(q * p for _, q, p in other_items)
    other_tax = round(other_sum * 0.05, 2)
    t2 = Table([["Item", "Qty", "Rate", "Amount"]] + other_rows +
               [["", "", "Subtotal", money(other_sum)],
                ["", "", "GST 5%", money(other_tax)],
                ["", "", "Total", money(other_sum + other_tax)]],
               colWidths=[220, 50, 110, 110])
    t2.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story += [
        Paragraph("GOLDEN HARVEST GRAINS", styles["Heading1"]),
        Paragraph("Mandi Gate, Karnal 132001, Haryana | GSTIN: 06AAECG4455J1Z0", small),
        Spacer(1, 12),
        Paragraph("Invoice No: GHG-2211 &nbsp;&nbsp; Date: 02 September 2026 &nbsp;&nbsp; "
                  "PO: PO-GH-4102 &nbsp;&nbsp; Buyer: Sharma Kirana Store", small),
        Spacer(1, 12), t2, Spacer(1, 16),
        Paragraph("Bags counted and accepted at delivery.", small),
    ]
    doc.build(story)
    save_key("invoice_12", key)


# ---------- invoice_13: informal bill, no invoice number, no PO, no tax line ----------
def invoice_13():
    key = build_key(
        "Ravi Electric Works", None, "2026-09-20", None, "INR",
        [
            ("Wiring repair - shop front", 1, 2400.00),
            ("MCB replacement (32A)", 2, 780.00),
            ("Tube light fitting", 3, 450.00),
            ("Labour (2 days)", 1, 1200.00),
        ],
        [],
        subtotal=None,
        tax=None,
        total=6510.00,
        notes=("A small informal bill. No invoice number and no PO number are printed, so both are "
               "null; an agent that invents either is wrong. No subtotal or tax line is printed "
               "either, so subtotal and tax are null and only the printed total (6,510.00) is "
               "recorded. A client may prefer subtotal = total and tax = 0 in this situation. "
               "Currency is INR, shown only as 'Rs.'."),
    )
    c = canvas.Canvas("invoices/invoice_13.pdf", pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 70, "RAVI ELECTRIC WORKS")
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(50, h - 88, "Near Bus Stand, Sitapur Road, Lucknow  -  Mob. 98765 43210")
    c.line(50, h - 96, w - 200, h - 96)

    c.setFont("Helvetica", 11)
    c.drawString(50, h - 125, "Bill")
    c.drawString(50, h - 145, "Date: 20 Sep 2026")
    c.drawString(50, h - 165, "Work done at: Gupta Medical Store, Aliganj")

    y = h - 205
    c.setFont("Helvetica", 11)
    for li in key["line_items"]:
        line = li["description"]
        if li["quantity"] and li["quantity"] != 1:
            line += f"  x {qty(li['quantity'])}"
        c.drawString(60, y, line)
        c.drawRightString(w - 60, y, "Rs. " + money(li["amount"]))
        y -= 22

    y -= 10
    c.line(300, y + 8, w - 60, y + 8)
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(w - 170, y - 8, "Total")
    c.drawRightString(w - 60, y - 8, "Rs. " + money(key["total"]))

    c.setFont("Helvetica-Oblique", 10)
    c.drawString(50, y - 60, "Payment by cash or UPI. Thank you.")
    c.save()
    save_key("invoice_13", key)


# ---------- invoice_14: several similar-looking reference numbers ----------
def invoice_14():
    key = build_key(
        "Meridian Industrial Fasteners", "4471-2026", "2026-09-16", "2026-4471", "USD",
        [
            ("Hex Bolt M10 x 50 (Box of 100)", 12, 46.00),
            ("Flange Nut M10 (Box of 200)", 9, 38.50),
            ("Washer M10 (Box of 500)", 6, 21.00),
        ],
        [0.08],
        notes=("Four similar numbers are printed on purpose. The invoice number is 4471-2026 and the "
               "PO number is 2026-4471 (the digits are the same, the order is not). The Customer ID "
               "(4471-2026-C) and Account Ref (44712026) must be ignored. Swapping the invoice and PO "
               "numbers counts as wrong."),
    )
    doc = SimpleDocTemplate("invoices/invoice_14.pdf", pagesize=LETTER)
    small = styles["Normal"].clone("small14", fontSize=9, leading=11)
    refs = Table([
        ["Invoice No:", "4471-2026", "Customer ID:", "4471-2026-C"],
        ["Invoice Date:", "16 Sep 2026", "Account Ref:", "44712026"],
        ["PO Number:", "2026-4471", "Terms:", "Net 30"],
    ], colWidths=[85, 120, 95, 120])
    refs.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
    ]))

    rows = [["Description", "Qty", "Unit Price", "Amount"]]
    rows += [[li["description"], qty(li["quantity"]), money(li["unit_price"]), money(li["amount"])]
             for li in key["line_items"]]
    n = len(rows)
    rows += [
        ["", "", "Subtotal", money(key["subtotal"])],
        ["", "", "Sales Tax (8%)", money(key["tax"])],
        ["", "", "Total (USD)", money(key["total"])],
    ]
    t = Table(rows, colWidths=[230, 50, 100, 100])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00695c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, n - 1), 0.4, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    doc.build([
        Paragraph("Meridian Industrial Fasteners", styles["Title"]),
        Paragraph("905 Foundry Street, Milwaukee, WI 53204 | orders@meridianfasteners.example", small),
        Spacer(1, 14), refs, Spacer(1, 16),
        Paragraph("Bill To: Kestrel Machine Shop, 44 Rail Yard Ave, Milwaukee, WI 53207", small),
        Spacer(1, 12), t, Spacer(1, 18),
        Paragraph("Please quote the invoice number (not the customer ID) with your payment.", small),
    ])
    save_key("invoice_14", key)


# ---------- invoice_15: ambiguous date 04/05/2026, no clue anywhere on the invoice ----------
def invoice_15():
    key = build_key(
        "Cloudline Hosting", "CLH-20268", "2026-05-04", "CLH-PO-9", "USD",
        [
            ("Cloud VPS (8 vCPU) - monthly", 3, 96.00),
            ("Managed backups - monthly", 3, 18.00),
            ("Bandwidth overage 200 GB", 2, 12.50),
        ],
        [],
        tax=0.00,
        notes=("The only date printed is 04/05/2026, and nothing on the invoice says which number is "
               "the day: the vendor is an online service with no country address, and there is no "
               "second date to compare against. This answer key records 2026-05-04 (4 May), because "
               "day/month/year is the format used in most of the world. If the vendor turns out to be "
               "US-based, 2026-04-05 (5 April) would be correct instead. An agent answering "
               "2026-04-05 is defensible rather than clearly wrong, so treat a mismatch on this "
               "invoice's date as 'undecidable' rather than a real error."),
    )
    c = canvas.Canvas("invoices/invoice_15.pdf", pagesize=A4)
    w, h = A4

    c.setFillColor(colors.HexColor("#00838f"))
    c.rect(0, h - 70, w, 6, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(50, h - 55, "Cloudline Hosting")
    c.setFillColor(colors.grey)
    c.setFont("Helvetica", 9)
    c.drawString(50, h - 90, "billing@cloudline.example  |  cloudline.example")

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    for i, (label, value) in enumerate([("Invoice", "CLH-20268"),
                                        ("Invoice Date", "04/05/2026"),
                                        ("PO Reference", "CLH-PO-9"),
                                        ("Account", "Tallgrass Analytics")]):
        c.drawString(50, h - 125 - i * 16, label)
        c.drawString(170, h - 125 - i * 16, value)

    xs = [50, 330, 420, w - 50]
    y = h - 215
    c.setFont("Helvetica-Bold", 10)
    draw_cells(c, y, ["Service", "Qty", "Unit", "Amount (USD)"], xs)
    c.line(50, y - 5, w - 50, y - 5)
    c.setFont("Helvetica", 10)
    for li in key["line_items"]:
        y -= 20
        draw_cells(c, y, [li["description"], qty(li["quantity"]),
                          money(li["unit_price"]), money(li["amount"])], xs)

    y -= 28
    for label, value, bold in [("Subtotal", key["subtotal"], False),
                               ("Tax", key["tax"], False),
                               ("Total", key["total"], True)]:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(420, y, label)
        c.drawRightString(w - 50, y, money(value))
        y -= 18
    c.setFillColor(colors.grey)
    c.setFont("Helvetica", 9)
    c.drawString(50, 60, "Charged to the card on file. Payment due on receipt.")
    c.save()
    save_key("invoice_15", key)


EASY_SET = (invoice_02, invoice_03, invoice_04, invoice_05)
HARD_SET = (invoice_06, invoice_07, invoice_08, invoice_09, invoice_10,
            invoice_11, invoice_12, invoice_13, invoice_14, invoice_15)

if __name__ == "__main__":
    import sys

    # Default: generate the hard set only, leaving the existing invoice_02..05 files untouched.
    # Pass --all to rebuild every generated invoice from scratch.
    makers = EASY_SET + HARD_SET if "--all" in sys.argv else HARD_SET
    for make in makers:
        name = make.__name__
        if make() is False:
            print(f"Skipped {name}")
        else:
            print(f"Created invoices/{name}.pdf and answer_keys/{name}.json")
