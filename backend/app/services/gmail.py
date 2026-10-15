"""Read-only Gmail access for finding invoice emails and their attachments.

Each signed-in user connects their own mailbox. Refresh tokens are encrypted
with GMAIL_TOKEN_ENCRYPTION_KEY before they are written to Firestore. Fetched
invoice attachments are saved to a per-user folder under GMAIL_STORAGE_DIR and
their details are recorded in Firestore at users/{uid}/gmailInvoices.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx
from cryptography.fernet import Fernet, InvalidToken
from firebase_admin import firestore
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..core.config import BACKEND_DIR
from ..core.firebase import document_payload, firestore_client, get_owned_document, user_collection


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = [GMAIL_SCOPE]
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
STATE_TTL_SECONDS = 600
HARD_ATTACHMENT_CAP = 25 * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MEDIA_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
MIME_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/x-pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/png": ".png",
}
SIGNATURE_NAME = re.compile(
    r"(signature|logo|icon|spacer|pixel|facebook|twitter|linkedin|instagram|"
    r"banner|footer|email[-_]?sig|image\d{3,})",
    re.IGNORECASE,
)
INVOICE_NAME = re.compile(r"(invoice|receipt|bill|statement|scan)", re.IGNORECASE)
MESSAGE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PART_ID = re.compile(r"^[0-9][0-9.]{0,31}$")
USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

logger = logging.getLogger("invoice_agent.gmail")


class GmailServiceError(Exception):
    """A problem that can be shown to the user in plain language."""


class GmailConfigError(GmailServiceError):
    """The backend is missing Gmail OAuth settings."""


class GmailNotConnected(GmailServiceError):
    """The user has no usable Gmail connection."""


@dataclass
class AttachmentInfo:
    part_id: str
    filename: str
    mime_type: str
    size: int | None


@dataclass
class _Candidate(AttachmentInfo):
    extension: str
    attachment_id: str | None
    inline_data: str | None


# ---------------------------------------------------------------- settings

def _redirect_uri() -> str:
    return os.getenv("GMAIL_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/google/callback").strip()


def _client_config() -> dict[str, Any]:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret or client_id.startswith("replace-"):
        raise GmailConfigError(
            "Gmail is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env.local."
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
            "redirect_uris": [_redirect_uri()],
        }
    }


def _fernet() -> Fernet:
    key = os.getenv("GMAIL_TOKEN_ENCRYPTION_KEY", "").strip()
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise GmailConfigError(
            "GMAIL_TOKEN_ENCRYPTION_KEY is missing or invalid in backend/.env.local."
        ) from None


def max_messages() -> int:
    try:
        return max(1, min(int(os.getenv("GMAIL_MAX_MESSAGES", "25")), 50))
    except ValueError:
        return 25


def max_attachment_bytes() -> int:
    default = 20 * 1024 * 1024
    try:
        value = int(os.getenv("GMAIL_MAX_ATTACHMENT_BYTES", str(default)))
    except ValueError:
        return default
    return default if value < 1024 else min(value, HARD_ATTACHMENT_CAP)


def is_configured() -> bool:
    try:
        _client_config()
        _fernet()
    except GmailConfigError:
        return False
    return True


# ------------------------------------------------------------------- OAuth

def _create_flow(state: str | None = None) -> Flow:
    # oauthlib refuses http callbacks unless this is set; only allow it for local development.
    if _redirect_uri().startswith(("http://localhost", "http://127.0.0.1")):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    # PKCE is off: the verifier generated for the redirect would not survive to the callback request.
    options: dict[str, Any] = {"redirect_uri": _redirect_uri(), "autogenerate_code_verifier": False}
    if state is not None:
        options["state"] = state
    return Flow.from_client_config(_client_config(), SCOPES, **options)


def authorization_url(uid: str) -> str:
    """Return Google's consent URL. The state is an encrypted, expiring token bound to the user."""
    state = _fernet().encrypt(json.dumps({"uid": uid, "nonce": secrets.token_urlsafe(16)}).encode()).decode()
    url, _ = _create_flow(state=state).authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="false",
    )
    return url


def uid_from_state(state: str) -> str:
    try:
        payload = json.loads(_fernet().decrypt(state.encode(), ttl=STATE_TTL_SECONDS))
    except (InvalidToken, ValueError, TypeError):
        raise GmailServiceError("Google sign-in could not be verified. Start again from Gmail Connect.") from None
    uid = payload.get("uid") if isinstance(payload, dict) else None
    if not isinstance(uid, str) or not uid:
        raise GmailServiceError("Google sign-in could not be verified. Start again from Gmail Connect.")
    return uid


def complete_authorization(code: str, state: str) -> str | None:
    """Exchange the one-time code, store the encrypted token, and return the mailbox address."""
    uid = uid_from_state(state)
    flow = _create_flow(state=state)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        logger.error("Gmail token exchange failed (%s)", type(exc).__name__)
        raise GmailServiceError(_friendly_oauth_message(exc)) from None
    credentials = flow.credentials
    if not credentials.refresh_token:
        raise GmailServiceError("Google did not return offline access. Disconnect the app in your Google account and try again.")
    email = None
    try:
        email = _build_service(credentials).users().getProfile(userId="me").execute().get("emailAddress")
    except HttpError:
        logger.error("Gmail connected, but the profile lookup failed")
    _integration(uid).set({
        "email": email,
        "token": _encrypt_credentials(credentials),
        "connectedAt": firestore.SERVER_TIMESTAMP,
    })
    return email


def _friendly_oauth_message(exc: Exception) -> str:
    text = str(exc).lower()
    if "redirect_uri_mismatch" in text:
        return f"The callback URL does not match Google Cloud. Set it to {_redirect_uri()}."
    if "invalid_client" in text:
        return "Google rejected the OAuth client. Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
    if "access_denied" in text:
        return "Access was denied. If the app is in testing, add your Gmail address as a test user."
    return "Could not complete Google sign-in. Try again."


# ---------------------------------------------------------- token storage

def _integration(uid: str):
    return user_collection(uid, "integrations").document("gmail")


def _encrypt_credentials(credentials: Credentials) -> str:
    payload = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }
    return _fernet().encrypt(json.dumps(payload).encode()).decode()


def _decrypt_credentials(encrypted: str) -> Credentials:
    try:
        payload = json.loads(_fernet().decrypt(encrypted.encode()))
    except (InvalidToken, ValueError, TypeError):
        raise GmailNotConnected("The saved Gmail connection could not be read. Connect Gmail again.") from None
    client = _client_config()["web"]
    expiry = payload.get("expiry")
    return Credentials(
        token=payload.get("token"),
        refresh_token=payload.get("refresh_token"),
        token_uri=TOKEN_URI,
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=SCOPES,
        expiry=datetime.fromisoformat(expiry) if expiry else None,
    )


def _load_credentials(uid: str) -> Credentials:
    snapshot = _integration(uid).get()
    data = snapshot.to_dict() if snapshot.exists else None
    if not data or not data.get("token"):
        raise GmailNotConnected("Gmail is not connected.")
    credentials = _decrypt_credentials(data["token"])
    if not credentials.valid:
        try:
            credentials.refresh(Request())
        except RefreshError:
            raise GmailNotConnected("Gmail access has expired. Connect Gmail again.") from None
        _integration(uid).update({"token": _encrypt_credentials(credentials)})
    return credentials


def _build_service(credentials: Credentials):
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def connection_status(uid: str) -> dict[str, Any]:
    if not is_configured():
        return {"configured": False, "connected": False, "email": None}
    snapshot = _integration(uid).get()
    data = snapshot.to_dict() if snapshot.exists else None
    connected = bool(data and data.get("token"))
    return {"configured": True, "connected": connected, "email": data.get("email") if connected else None}


def disconnect(uid: str) -> None:
    """Revoke the token with Google (best effort) and delete it from Firestore."""
    reference = _integration(uid)
    snapshot = reference.get()
    data = snapshot.to_dict() if snapshot.exists else None
    if data and data.get("token"):
        try:
            credentials = _decrypt_credentials(data["token"])
            httpx.post(REVOKE_URI, data={"token": credentials.refresh_token}, timeout=10)
        except (GmailServiceError, httpx.HTTPError):
            logger.warning("Could not revoke the Gmail token with Google")
    reference.delete()


def gmail_error_message(exc: HttpError) -> str:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in (401, 403):
        return "Gmail access was denied or has expired. Connect Gmail again."
    if status == 429:
        return "Gmail rate limit reached. Wait a minute and try again."
    return "Gmail could not complete that request. Try again in a moment."


# ------------------------------------------------------------------ search

def build_search_query(date_from: date | None, date_to: date | None) -> str:
    """Gmail search for likely invoice mail. before: is exclusive, so the end date moves forward a day."""
    parts = [
        '(invoice OR receipt OR billing OR "tax invoice" OR "payment receipt" OR "amount due")',
        "has:attachment",
        "-in:spam",
        "-in:trash",
    ]
    if date_from:
        parts.append("after:" + date_from.strftime("%Y/%m/%d"))
    if date_to:
        parts.append("before:" + (date_to + timedelta(days=1)).strftime("%Y/%m/%d"))
    return " ".join(parts)


def search_invoice_emails(uid: str, date_from: date | None, date_to: date | None) -> dict[str, Any]:
    if date_from and date_to and date_from > date_to:
        raise GmailServiceError("The start date must be on or before the end date.")
    service = _build_service(_load_credentials(uid))
    query = build_search_query(date_from, date_to)
    listing = service.users().messages().list(
        userId="me", q=query, maxResults=max_messages(), includeSpamTrash=False,
    ).execute()
    message_ids = list(dict.fromkeys(item["id"] for item in listing.get("messages") or [] if item.get("id")))

    messages: dict[str, dict] = {}
    auth_failure: list[HttpError] = []

    def collect(request_id: str, response: dict, exception: Exception | None) -> None:
        if isinstance(exception, HttpError) and getattr(exception.resp, "status", None) in (401, 403):
            auth_failure.append(exception)
        elif exception is None and response:
            messages[request_id] = response

    if message_ids:
        batch = service.new_batch_http_request(callback=collect)
        for message_id in message_ids:
            batch.add(service.users().messages().get(userId="me", id=message_id, format="full"), request_id=message_id)
        batch.execute()
    if auth_failure:
        raise auth_failure[0]

    parsed = {
        message_id: _collect_attachments(messages[message_id].get("payload") or {})
        for message_id in message_ids if message_id in messages
    }
    references = {
        (message_id, candidate.part_id): _saved_reference(uid, message_id, candidate.part_id)
        for message_id, (candidates, _, _) in parsed.items()
        for candidate in candidates
    }
    already_saved = {
        snapshot.id for snapshot in firestore_client().get_all(list(references.values())) if snapshot.exists
    } if references else set()

    results = []
    saved_new = failed = 0
    for message_id in message_ids:
        message = messages.get(message_id)
        if message is None:
            results.append({
                "id": message_id, "sender": "Unknown sender", "subject": "(could not load this email)",
                "received": None, "attachments": [], "note": "This message could not be read.",
            })
            continue
        candidates, signature_skips, unsupported_skips = parsed[message_id]
        notes = []
        if signature_skips:
            notes.append(f"Ignored {signature_skips} likely signature image{'s' if signature_skips != 1 else ''}.")
        if unsupported_skips:
            notes.append(f"Ignored {unsupported_skips} unsupported file{'s' if unsupported_skips != 1 else ''}.")
        if not candidates and not notes:
            notes.append("No PDF or image attachments found.")
        headers = _headers(message.get("payload") or {})
        sender = _clip(_decode_header(headers.get("from")), 200) or "Unknown sender"
        subject = _clip(_decode_header(headers.get("subject")), 300) or "(no subject)"
        received = _received_iso(message)

        attachments = []
        for candidate in candidates:
            reference = references[(message_id, candidate.part_id)]
            saved_id: str | None = reference.id if reference.id in already_saved else None
            saved_status: str | None = "existing" if saved_id else None
            if saved_id is None:
                try:
                    data = _attachment_bytes(service, message_id, candidate)
                    _store_attachment(uid, reference, message_id, candidate, data, sender, subject, received)
                    saved_id = reference.id
                    saved_status = "new"
                    saved_new += 1
                except GmailServiceError as exc:
                    failed += 1
                    notes.append(f"{candidate.filename}: {exc}")
                except HttpError as exc:
                    if getattr(exc.resp, "status", None) in (401, 403):
                        raise
                    failed += 1
                    notes.append(f"{candidate.filename}: could not be downloaded.")
            attachments.append({**asdict(AttachmentInfo(candidate.part_id, candidate.filename, candidate.mime_type, candidate.size)), "saved_id": saved_id, "saved_status": saved_status})

        results.append({
            "id": message_id,
            "sender": sender,
            "subject": subject,
            "received": received,
            "attachments": attachments,
            "note": " ".join(notes),
        })
    return {
        "query": query,
        "messages": results,
        "saved_new": saved_new,
        "already_saved": len(already_saved),
        "failed": failed,
    }


# ----------------------------------------------- saved invoices (folder + Firestore)

def storage_root() -> Path:
    configured = os.getenv("GMAIL_STORAGE_DIR", "").strip()
    return Path(configured).resolve() if configured else (BACKEND_DIR / "storage" / "gmail-invoices").resolve()


def _user_folder(uid: str) -> Path:
    if not USER_ID.fullmatch(uid):
        raise GmailServiceError("Invalid user.")
    return storage_root() / uid


def _saved_reference(uid: str, message_id: str, part_id: str):
    record_id = hashlib.sha256(f"{message_id}:{part_id}".encode()).hexdigest()[:32]
    return user_collection(uid, "gmailInvoices").document(record_id)


def _store_attachment(uid, reference, message_id, candidate, data, sender, subject, received) -> None:
    """Write the file to the user's folder, then record its details in Firestore."""
    folder = _user_folder(uid)
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{reference.id}{candidate.extension}"
    path = folder / stored_name
    partial = path.with_name(stored_name + ".part")
    try:
        partial.write_bytes(data)
        os.replace(partial, path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise GmailServiceError("could not be saved to the invoice folder.") from None
    reference.set({
        "source": "gmail",
        "messageId": message_id,
        "partId": candidate.part_id,
        "sender": sender,
        "subject": subject,
        "receivedAt": received,
        "fileName": _safe_filename(candidate.filename, candidate.extension),
        "storedFileName": stored_name,
        "mimeType": MEDIA_TYPES[candidate.extension],
        "sizeBytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "createdAt": firestore.SERVER_TIMESTAMP,
    })


def list_saved_invoices(uid: str, limit: int = 100) -> list[dict[str, Any]]:
    query = (
        user_collection(uid, "gmailInvoices")
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [document_payload(snapshot) for snapshot in query.stream()]


def saved_invoice_file(uid: str, record_id: str) -> tuple[Path, str, str]:
    """Return (path, download name, media type) for a saved invoice owned by the user."""
    _, snapshot = get_owned_document(uid, "gmailInvoices", record_id)
    data = snapshot.to_dict() or {}
    folder = _user_folder(uid)
    path = (folder / str(data.get("storedFileName") or "")).resolve()
    if path.parent != folder or not path.is_file():
        raise GmailServiceError("The saved file is missing from the invoice folder.")
    return path, str(data.get("fileName") or path.name), str(data.get("mimeType") or "application/octet-stream")


def delete_saved_invoice(uid: str, record_id: str) -> None:
    reference, snapshot = get_owned_document(uid, "gmailInvoices", record_id)
    folder = _user_folder(uid)
    path = (folder / str((snapshot.to_dict() or {}).get("storedFileName") or "")).resolve()
    if path.parent == folder and path.is_file():
        path.unlink()
    reference.delete()


def download_attachment(uid: str, message_id: str, part_id: str) -> tuple[bytes, str, str]:
    """Return (bytes, safe filename, media type) for one supported attachment, straight from Gmail."""
    if not MESSAGE_ID.fullmatch(message_id) or not PART_ID.fullmatch(part_id):
        raise GmailServiceError("Invalid attachment reference.")
    service = _build_service(_load_credentials(uid))
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    candidates, _, _ = _collect_attachments(message.get("payload") or {})
    candidate = next((item for item in candidates if item.part_id == part_id), None)
    if candidate is None:
        raise GmailServiceError("That attachment was not found.")
    data = _attachment_bytes(service, message_id, candidate)
    return data, _safe_filename(candidate.filename, candidate.extension), MEDIA_TYPES[candidate.extension]


def _attachment_bytes(service, message_id: str, candidate: _Candidate) -> bytes:
    if candidate.size is not None and candidate.size > max_attachment_bytes():
        raise GmailServiceError("The attachment is larger than the allowed limit.")
    if candidate.attachment_id:
        encoded = service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=candidate.attachment_id,
        ).execute().get("data") or ""
    else:
        encoded = candidate.inline_data or ""
    try:
        data = base64.urlsafe_b64decode((encoded + "=" * (-len(encoded) % 4)).encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise GmailServiceError("Could not decode the attachment.") from None
    if not data:
        raise GmailServiceError("The attachment was empty.")
    if len(data) > max_attachment_bytes():
        raise GmailServiceError("The attachment is larger than the allowed limit.")
    if not _matches_declared_type(data, candidate.extension):
        raise GmailServiceError("The attachment did not look like a valid PDF or image.")
    return data


# ------------------------------------------------------------ MIME parsing

def _headers(payload: dict) -> dict[str, str]:
    found: dict[str, str] = {}
    for item in payload.get("headers") or []:
        name = str(item.get("name") or "").lower()
        if name and name not in found:
            found[name] = str(item.get("value") or "")
    return found


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return value.strip()


def _clip(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def _received_iso(message: dict) -> str | None:
    try:
        return datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=timezone.utc).isoformat()
    except (KeyError, TypeError, ValueError, OSError, OverflowError):
        return None


def _iter_parts(part: dict):
    if not isinstance(part, dict):
        return
    yield part
    for child in part.get("parts") or []:
        yield from _iter_parts(child)


def _base_mime(mime: str | None) -> str:
    return (mime or "").split(";", 1)[0].strip().lower()


def _filename_from_header(value: str) -> str:
    if not value:
        return ""
    starred = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", value, re.IGNORECASE)
    if starred:
        return unquote(starred.group(1).strip().strip('"'))
    quoted = re.search(r'(?:filename|name)\s*=\s*"([^"]+)"', value, re.IGNORECASE)
    if quoted:
        return quoted.group(1)
    plain = re.search(r"(?:filename|name)\s*=\s*([^;]+)", value, re.IGNORECASE)
    return plain.group(1).strip().strip('"') if plain else ""


def _part_filename(part: dict) -> str:
    filename = _decode_header(str(part.get("filename") or ""))
    if filename:
        return filename
    headers = _headers(part)
    return _decode_header(
        _filename_from_header(headers.get("content-disposition", ""))
        or _filename_from_header(headers.get("content-type", ""))
    )


def _choose_extension(filename: str, mime: str) -> str | None:
    extension = Path(filename).suffix.lower()
    return extension if extension in ALLOWED_EXTENSIONS else MIME_EXTENSIONS.get(_base_mime(mime))


def _is_signature_image(filename: str, mime: str, disposition: str, size: int | None) -> bool:
    """Skip tiny inline images and common signature filenames. PDFs are always kept."""
    if _choose_extension(filename, mime) == ".pdf":
        return False
    if INVOICE_NAME.search(filename or ""):
        return False
    if filename and SIGNATURE_NAME.search(filename):
        return True
    if size is not None and size < 2048:
        return True
    return disposition == "inline" and (size is None or size < 30_000)


def _collect_attachments(payload: dict) -> tuple[list[_Candidate], int, int]:
    candidates: list[_Candidate] = []
    signature_skips = unsupported_skips = 0
    for part in _iter_parts(payload):
        mime = _base_mime(str(part.get("mimeType") or ""))
        if mime.startswith("multipart/"):
            continue
        filename = _part_filename(part) or "attachment"
        body = part.get("body") or {}
        if not (part.get("filename") or body.get("attachmentId") or mime in MIME_EXTENSIONS):
            continue
        extension = _choose_extension(filename, mime)
        if extension is None:
            unsupported_skips += 1
            continue
        size = body.get("size")
        size = int(size) if isinstance(size, (int, str)) and str(size).isdigit() else None
        disposition = _headers(part).get("content-disposition", "").split(";", 1)[0].strip().lower()
        if _is_signature_image(filename, mime, disposition, size):
            signature_skips += 1
            continue
        attachment_id = body.get("attachmentId")
        candidates.append(_Candidate(
            part_id=str(part.get("partId") or ""),
            filename=_clip(filename.replace("/", " ").replace("\\", " "), 120),
            mime_type=mime,
            size=size,
            extension=extension,
            attachment_id=str(attachment_id) if attachment_id else None,
            inline_data=None if attachment_id else body.get("data"),
        ))
    return [item for item in candidates if item.part_id], signature_skips, unsupported_skips


def _matches_declared_type(data: bytes, extension: str) -> bool:
    if extension == ".pdf":
        return data.startswith(b"%PDF")
    if extension in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    return False


def _safe_filename(original: str, extension: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", Path(original).stem).strip(" .")[:100] or "invoice"
    return f"{stem}{extension}"
