from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo
import stat

import pytest

from backend.app.models.schemas import InvoiceCheckResponse
from backend.app.services.invoice import UnreadablePDFError
from backend.app.services.archives import InvalidZIPError, process_zip


SAMPLE_PDF = Path(__file__).resolve().parents[2] / "sample_invoice.pdf"


def mocked_result() -> InvoiceCheckResponse:
    from backend.tests.test_api import mocked_result as api_mocked_result

    return api_mocked_result()


def write_zip(path: Path, entries: list[tuple[str, bytes]], compression=ZIP_STORED) -> None:
    with ZipFile(path, "w", compression=compression) as archive:
        for name, content in entries:
            archive.writestr(name, content)


def test_processes_pdfs_sequentially_and_keeps_per_file_errors(tmp_path, monkeypatch) -> None:
    zip_path = tmp_path / "invoices.zip"
    pdf_bytes = SAMPLE_PDF.read_bytes()
    write_zip(zip_path, [("one.pdf", pdf_bytes), ("folder/two.pdf", pdf_bytes)])

    monkeypatch.setattr("backend.app.services.archives.validate_configuration", lambda: None)
    calls: list[Path] = []

    def process(pdf_path: Path):
        calls.append(pdf_path)
        assert pdf_path.parent == tmp_path
        assert pdf_path.suffix == ".pdf"
        assert pdf_path.name not in {"one.pdf", "two.pdf"}
        if len(calls) == 2:
            raise UnreadablePDFError("No readable text was found. OCR is required.")
        return mocked_result()

    monkeypatch.setattr("backend.app.services.archives.process_invoice", process)
    response = process_zip(zip_path)

    assert len(calls) == 2
    assert response.summary.model_dump() == {"total": 2, "succeeded": 1, "failed": 1}
    assert response.files[0].filename == "one.pdf"
    assert response.files[0].result is not None
    assert response.files[1].filename == "folder/two.pdf"
    assert response.files[1].error.code == "unreadable_pdf"


@pytest.mark.parametrize("unsafe_name", ["../escape.pdf", "/absolute.pdf", "C:\\escape.pdf"])
def test_rejects_unsafe_paths(tmp_path, monkeypatch, unsafe_name) -> None:
    zip_path = tmp_path / "unsafe.zip"
    write_zip(zip_path, [(unsafe_name, SAMPLE_PDF.read_bytes())])
    monkeypatch.setattr("backend.app.services.archives.validate_configuration", lambda: None)

    with pytest.raises(InvalidZIPError, match="unsafe file path"):
        process_zip(zip_path)


def test_rejects_non_pdf_and_nested_zip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.archives.validate_configuration", lambda: None)

    non_pdf = tmp_path / "non-pdf.zip"
    write_zip(non_pdf, [("notes.txt", b"not an invoice")])
    with pytest.raises(InvalidZIPError, match="non-PDF"):
        process_zip(non_pdf)

    nested = tmp_path / "nested.zip"
    write_zip(nested, [("inside.zip", b"PK\x05\x06")])
    with pytest.raises(InvalidZIPError, match="Nested ZIP"):
        process_zip(nested)


def test_rejects_symbolic_links(tmp_path, monkeypatch) -> None:
    zip_path = tmp_path / "link.zip"
    info = ZipInfo("linked.pdf")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(zip_path, "w") as archive:
        archive.writestr(info, b"target.pdf")
    monkeypatch.setattr("backend.app.services.archives.validate_configuration", lambda: None)

    with pytest.raises(InvalidZIPError, match="symbolic links"):
        process_zip(zip_path)


def test_rejects_suspicious_compression_ratio(tmp_path, monkeypatch) -> None:
    zip_path = tmp_path / "bomb.zip"
    write_zip(zip_path, [("invoice.pdf", b"A" * 100_000)], compression=ZIP_DEFLATED)
    monkeypatch.setattr("backend.app.services.archives.validate_configuration", lambda: None)

    with pytest.raises(InvalidZIPError, match="compression ratio"):
        process_zip(zip_path)


def test_enforces_pdf_count(tmp_path, monkeypatch) -> None:
    zip_path = tmp_path / "many.zip"
    write_zip(zip_path, [("one.pdf", b"%PDF-1.7"), ("two.pdf", b"%PDF-1.7")])
    monkeypatch.setattr("backend.app.services.archives.validate_configuration", lambda: None)
    monkeypatch.setattr("backend.app.services.archives.MAX_PDFS_PER_ZIP", 1)

    with pytest.raises(InvalidZIPError, match="at most 1"):
        process_zip(zip_path)
