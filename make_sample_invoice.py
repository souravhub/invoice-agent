"""Generates sample_invoice.pdf so you have something to test with."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

styles = getSampleStyleSheet()
doc = SimpleDocTemplate("sample_invoice.pdf", pagesize=A4)
story = [
    Paragraph("Acme Office Supplies Pvt. Ltd.", styles["Title"]),
    Paragraph("12 Park Street, Kolkata 700016 | GSTIN: 19AABCA1234F1Z5", styles["Normal"]),
    Spacer(1, 16),
    Paragraph("<b>TAX INVOICE</b>", styles["Heading2"]),
    Paragraph("Invoice No: INV-2026-0457", styles["Normal"]),
    Paragraph("Invoice Date: 15 September 2026", styles["Normal"]),
    Paragraph("PO Number: PO-88213", styles["Normal"]),
    Paragraph("Bill To: Globex Technologies, Salt Lake Sector V, Kolkata", styles["Normal"]),
    Spacer(1, 16),
]
rows = [
    ["Description", "Qty", "Unit Price (INR)", "Amount (INR)"],
    ["A4 Printer Paper (500 sheets)", "20", "350.00", "7,000.00"],
    ["Ballpoint Pens - Box of 50", "5", "420.00", "2,100.00"],
    ["Ergonomic Office Chair", "2", "8,500.00", "17,000.00"],
    ["Whiteboard Markers (Pack of 12)", "10", "240.00", "2,400.00"],
    ["", "", "Subtotal", "28,500.00"],
    ["", "", "GST @ 18%", "5,130.00"],
    ["", "", "Total Due", "33,630.00"],
]
t = Table(rows, colWidths=[220, 50, 110, 100])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("GRID", (0, 0), (-1, 4), 0.5, colors.grey),
    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("FONTNAME", (2, 7), (3, 7), "Helvetica-Bold"),
]))
story += [t, Spacer(1, 20), Paragraph("Payment due within 30 days. Thank you for your business.", styles["Normal"])]
doc.build(story)
print("Created sample_invoice.pdf")
