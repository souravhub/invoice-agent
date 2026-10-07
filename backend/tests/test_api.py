from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from backend.agent.schema import Invoice, LineItem
from backend.main import app
from backend.schemas import InvoiceCheckResponse
from backend.service import AIProviderError


client = TestClient(app)
SAMPLE_PDF = Path(__file__).resolve().parents[2] / "sample_invoice.pdf"


def mocked_result() -> InvoiceCheckResponse:
    return InvoiceCheckResponse(
        invoice=Invoice(
            vendor_name="Example Vendor",
            invoice_number="INV-001",
            invoice_date="2026-10-07",
            po_number="PO-9",
            currency="USD",
            line_items=[
                LineItem(description="Service", quantity=1, unit_price=100, amount=100)
            ],
            subtotal=100,
            discount=None,
            shipping=None,
            tax=10,
            total=110,
        ),
        status="auto_approved",
        reasons=[],
        attempts=1,
    )


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_check_invoice_returns_documented_result(monkeypatch) -> None:
    monkeypatch.setattr("backend.main.process_invoice", lambda _: mocked_result())

    with SAMPLE_PDF.open("rb") as pdf:
        response = client.post(
            "/api/invoices/check",
            files={"file": ("sample_invoice.pdf", pdf, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["invoice"]["vendor_name"] == "Example Vendor"
    assert body["status"] == "auto_approved"
    assert body["attempts"] == 1


def test_rejects_wrong_content_type() -> None:
    response = client.post(
        "/api/invoices/check",
        files={"file": ("invoice.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "pdf_required"


def test_rejects_spoofed_pdf() -> None:
    response = client.post(
        "/api/invoices/check",
        files={"file": ("invoice.pdf", b"not really a pdf", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_pdf"


def test_enforces_upload_limit(monkeypatch) -> None:
    monkeypatch.setattr("backend.main.MAX_UPLOAD_BYTES", 10)
    response = client.post(
        "/api/invoices/check",
        files={"file": ("invoice.pdf", b"%PDF-1.7" + b"x" * 20, "application/pdf")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_reports_textless_scanned_pdf() -> None:
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    document.showPage()
    document.save()

    response = client.post(
        "/api/invoices/check",
        files={"file": ("scan.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unreadable_pdf"
    assert "OCR" in response.json()["error"]["message"]


def test_reports_missing_provider_configuration(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with SAMPLE_PDF.open("rb") as pdf:
        response = client.post(
            "/api/invoices/check",
            files={"file": ("sample_invoice.pdf", pdf, "application/pdf")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "configuration_error"
    assert "API key" in response.json()["error"]["message"]


def test_temp_directory_is_removed_after_provider_failure(monkeypatch) -> None:
    observed_path: Path | None = None

    def fail(pdf_path: Path):
        nonlocal observed_path
        observed_path = pdf_path
        raise AIProviderError("private provider detail")

    monkeypatch.setattr("backend.main.process_invoice", fail)
    with SAMPLE_PDF.open("rb") as pdf:
        response = client.post(
            "/api/invoices/check",
            files={"file": ("sample_invoice.pdf", pdf, "application/pdf")},
        )

    assert response.status_code == 502
    assert "private provider detail" not in response.text
    assert observed_path is not None
    assert not observed_path.parent.exists()
