"""Prints the text that load_pdf extracts from sample_invoice.pdf (no API key needed)."""
from workflow import load_pdf

result = load_pdf({"pdf_path": "sample_invoice.pdf"})
print(result["raw_text"])
