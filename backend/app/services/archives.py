"""Safe synchronous processing for ZIP archives containing invoice PDFs."""

import re
import stat
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile, LargeZipFile, ZipFile, ZipInfo

from ..models.schemas import (
    BatchFileResult,
    BatchSummary,
    ErrorDetail,
    InvoiceBatchResponse,
)
from .invoice import (
    AIProviderError,
    InvalidPDFError,
    UnreadablePDFError,
    process_invoice,
    validate_configuration,
)

MAX_PDFS_PER_ZIP = 10
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
COPY_CHUNK_SIZE = 1024 * 1024


class InvalidZIPError(Exception):
    """Raised when an archive is invalid or violates a batch safety policy."""


def validated_entry_name(info: ZipInfo) -> str:
    """Return a normalized safe relative entry name or reject the archive."""
    normalized = info.filename.replace("\\", "/")
    path = PurePosixPath(normalized)

    if not normalized or path.is_absolute() or ".." in path.parts:
        raise InvalidZIPError("The ZIP contains an unsafe file path.")
    if re.match(r"^[A-Za-z]:", normalized):
        raise InvalidZIPError("The ZIP contains an unsafe file path.")

    unix_mode = info.external_attr >> 16
    if stat.S_ISLNK(unix_mode):
        raise InvalidZIPError("ZIP symbolic links are not supported.")
    if info.flag_bits & 0x1:
        raise InvalidZIPError("Encrypted ZIP entries are not supported.")
    return normalized


def validated_pdf_entries(archive: ZipFile) -> list[tuple[ZipInfo, str]]:
    """Inspect archive metadata before any content is decompressed."""
    entries: list[tuple[ZipInfo, str]] = []
    declared_total = 0

    for info in archive.infolist():
        if info.is_dir():
            continue

        name = validated_entry_name(info)
        suffix = PurePosixPath(name).suffix.lower()
        if suffix == ".zip":
            raise InvalidZIPError("Nested ZIP files are not supported.")
        if suffix != ".pdf":
            raise InvalidZIPError(f"The ZIP contains a non-PDF file: {name}")
        if info.file_size > MAX_PDF_BYTES:
            raise InvalidZIPError(f"A PDF exceeds the {MAX_PDF_BYTES // 1024 // 1024} MB limit: {name}")

        ratio = info.file_size / max(info.compress_size, 1)
        if ratio > MAX_COMPRESSION_RATIO:
            raise InvalidZIPError(f"The ZIP has a suspicious compression ratio: {name}")

        declared_total += info.file_size
        if declared_total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise InvalidZIPError("The ZIP exceeds the total uncompressed size limit.")

        entries.append((info, name))

    if not entries:
        raise InvalidZIPError("The ZIP does not contain any PDF files.")
    if len(entries) > MAX_PDFS_PER_ZIP:
        raise InvalidZIPError(f"A ZIP can contain at most {MAX_PDFS_PER_ZIP} PDFs.")
    return entries


def copy_pdf_entry(
    archive: ZipFile,
    info: ZipInfo,
    destination_directory: Path,
    current_total: int,
) -> tuple[Path, int]:
    """Stream one member to a generated path while enforcing actual byte limits."""
    destination = destination_directory / f"{uuid4().hex}.pdf"
    file_bytes = 0

    try:
        with archive.open(info, "r") as source, destination.open("wb") as output:
            while chunk := source.read(COPY_CHUNK_SIZE):
                file_bytes += len(chunk)
                current_total += len(chunk)
                if file_bytes > MAX_PDF_BYTES:
                    raise InvalidZIPError("A PDF exceeds the per-file uncompressed size limit.")
                if current_total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise InvalidZIPError("The ZIP exceeds the total uncompressed size limit.")
                output.write(chunk)
    except InvalidZIPError:
        raise
    except (BadZipFile, RuntimeError, EOFError, NotImplementedError, OSError) as exc:
        raise InvalidZIPError("The ZIP archive is corrupt or unreadable.") from exc

    return destination, current_total


def safe_file_error(code: str, message: str) -> ErrorDetail:
    return ErrorDetail(code=code, message=message)


def process_zip(zip_path: Path) -> InvoiceBatchResponse:
    """Process accepted PDFs sequentially and retain independent per-file outcomes."""
    file_results: list[BatchFileResult] = []
    total_uncompressed = 0

    try:
        with ZipFile(zip_path, "r") as archive:
            entries = validated_pdf_entries(archive)
            validate_configuration()
            for info, display_name in entries:
                pdf_path, total_uncompressed = copy_pdf_entry(
                    archive,
                    info,
                    zip_path.parent,
                    total_uncompressed,
                )
                try:
                    result = process_invoice(pdf_path)
                    file_results.append(BatchFileResult(filename=display_name, result=result))
                except UnreadablePDFError as exc:
                    file_results.append(
                        BatchFileResult(
                            filename=display_name,
                            error=safe_file_error("unreadable_pdf", str(exc)),
                        )
                    )
                except InvalidPDFError as exc:
                    file_results.append(
                        BatchFileResult(
                            filename=display_name,
                            error=safe_file_error("invalid_pdf", str(exc)),
                        )
                    )
                except AIProviderError:
                    file_results.append(
                        BatchFileResult(
                            filename=display_name,
                            error=safe_file_error(
                                "ai_provider_error",
                                "The AI provider could not process this invoice. Try again later.",
                            ),
                        )
                    )
    except InvalidZIPError:
        raise
    except (BadZipFile, LargeZipFile, RuntimeError, EOFError, NotImplementedError, OSError) as exc:
        raise InvalidZIPError("The uploaded file is not a readable ZIP archive.") from exc

    succeeded = sum(item.result is not None for item in file_results)
    return InvoiceBatchResponse(
        summary=BatchSummary(
            total=len(file_results),
            succeeded=succeeded,
            failed=len(file_results) - succeeded,
        ),
        files=file_results,
    )
