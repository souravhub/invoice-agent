"""Prints the text that load_pdf extracts from sample_invoice.pdf (no API key needed)."""
from pathlib import Path

from ..app.agent.workflow import load_pdf

result = load_pdf({"pdf_path": str(Path(__file__).resolve().parents[2] / "sample_invoice.pdf")})
print(result["raw_text"])
