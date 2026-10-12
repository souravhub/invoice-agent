from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from backend.app.agent.schema import Invoice, LineItem, PurchaseOrder
from backend.app.main import app
from backend.app.models.schemas import (
    BatchFileResult,
    BatchSummary,
    InvoiceBatchResponse,
    InvoiceCheckResponse,
    PurchaseOrderExtractionResponse,
)
from backend.app.services.invoice import AIProviderError, build_configured_checks
from backend.app.services.archives import InvalidZIPError


client = TestClient(app)
SAMPLE_PDF = Path(__file__).resolve().parents[2] / "sample_invoice.pdf"


def mocked_result() -> InvoiceCheckResponse:
    invoice = Invoice(
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
    )
    return InvoiceCheckResponse(
        invoice=invoice,
        status="auto_approved",
        reasons=[],
        attempts=1,
        checks=build_configured_checks(invoice, 1),
    )


def mocked_batch_result() -> InvoiceBatchResponse:
    return InvoiceBatchResponse(
        summary=BatchSummary(total=1, succeeded=1, failed=0),
        files=[BatchFileResult(filename="invoice.pdf", result=mocked_result())],
    )


def zip_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("invoice.pdf", SAMPLE_PDF.read_bytes())
    return buffer.getvalue()


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_workspace_routes_require_a_firebase_id_token() -> None:
    response = client.get("/api/invoices")
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in is required for this request."


def test_cors_preflight_allows_authenticated_workspace_mutations() -> None:
    response = client.options(
        "/api/invoices/example",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]
    assert "Authorization" in response.headers["access-control-allow-headers"]


def test_check_invoice_returns_documented_result(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.api.processing.process_invoice", lambda _: mocked_result())

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
    assert body["checks"][0]["id"] == "required_fields"
    assert body["checks"][0]["status"] == "passed"


def test_extract_purchase_order_returns_documented_result(monkeypatch) -> None:
    purchase_order = PurchaseOrder(
        vendor_name="Example Vendor",
        po_number="PO-9",
        order_date="2026-10-01",
        currency="USD",
        line_items=[LineItem(description="Service", quantity=1, unit_price=100, amount=100)],
        subtotal=100,
        total=100,
    )
    monkeypatch.setattr(
        "backend.app.api.processing.extract_purchase_order",
        lambda _: PurchaseOrderExtractionResponse(purchase_order=purchase_order),
    )
    with SAMPLE_PDF.open("rb") as pdf:
        response = client.post(
            "/api/purchase-orders/extract",
            files={"file": ("po.pdf", pdf, "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json()["purchase_order"]["po_number"] == "PO-9"


def test_two_way_match_endpoint() -> None:
    invoice = mocked_result().invoice.model_dump()
    purchase_order = {
        "vendor_name": "Example Vendor",
        "po_number": "PO-9",
        "order_date": "2026-10-01",
        "currency": "USD",
        "line_items": [{"description": "Service", "quantity": 2, "unit_price": 100, "amount": 200}],
        "subtotal": 200,
        "shipping": None,
        "tax": 20,
        "total": 220,
    }
    response = client.post(
        "/api/invoices/two-way-match",
        json={"invoice": invoice, "purchase_order": purchase_order, "purchase_order_id": "po-doc"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "matched"
    assert response.json()["purchase_order_id"] == "po-doc"


def test_recheck_does_not_invoke_an_ai_provider() -> None:
    invoice = mocked_result().invoice.model_dump()
    response = client.post(
        "/api/invoices/recheck",
        json={"invoice": invoice, "attempts": 1},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "auto_approved"
    assert response.json()["attempts"] == 1


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
    monkeypatch.setattr("backend.app.api.processing.MAX_UPLOAD_BYTES", 10)
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

    monkeypatch.setattr("backend.app.api.processing.process_invoice", fail)
    with SAMPLE_PDF.open("rb") as pdf:
        response = client.post(
            "/api/invoices/check",
            files={"file": ("sample_invoice.pdf", pdf, "application/pdf")},
        )

    assert response.status_code == 502
    assert "private provider detail" not in response.text
    assert observed_path is not None
    assert not observed_path.parent.exists()


def test_check_batch_returns_documented_result(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.api.processing.process_zip", lambda _: mocked_batch_result())
    response = client.post(
        "/api/invoices/check-batch",
        files={"file": ("invoices.zip", zip_bytes(), "application/zip")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {"total": 1, "succeeded": 1, "failed": 0}
    assert body["files"][0]["filename"] == "invoice.pdf"
    assert body["files"][0]["result"]["status"] == "auto_approved"


def test_batch_rejects_wrong_content_type() -> None:
    response = client.post(
        "/api/invoices/check-batch",
        files={"file": ("invoices.txt", b"not a zip", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "zip_required"


def test_batch_rejects_spoofed_zip() -> None:
    response = client.post(
        "/api/invoices/check-batch",
        files={"file": ("invoices.zip", b"not really a zip", "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_zip"


def test_batch_enforces_compressed_upload_limit(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.api.processing.MAX_UPLOAD_BYTES", 10)
    response = client.post(
        "/api/invoices/check-batch",
        files={"file": ("invoices.zip", b"PK\x03\x04" + b"x" * 20, "application/zip")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_batch_temp_directory_is_removed_after_archive_failure(monkeypatch) -> None:
    observed_path: Path | None = None

    def fail(zip_path: Path):
        nonlocal observed_path
        observed_path = zip_path
        raise InvalidZIPError("archive policy failed")

    monkeypatch.setattr("backend.app.api.processing.process_zip", fail)
    response = client.post(
        "/api/invoices/check-batch",
        files={"file": ("invoices.zip", zip_bytes(), "application/zip")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_zip"
    assert observed_path is not None
    assert not observed_path.parent.exists()
