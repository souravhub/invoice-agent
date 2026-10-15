"""Gmail Connect routes: OAuth, invoice email search, and attachment downloads."""

import logging
import os
from datetime import date
from typing import Annotated, Any
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from ..core.config import frontend_url
from ..core.firebase import authenticated_user
from ..services import gmail


router = APIRouter(tags=["gmail"])
CurrentUser = Annotated[dict[str, Any], Depends(authenticated_user)]
logger = logging.getLogger("invoice_agent.gmail")

CALLBACK_PATH = urlparse(
    os.getenv("GMAIL_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
).path or "/auth/google/callback"


def _raise_for(exc: Exception) -> None:
    if isinstance(exc, gmail.GmailConfigError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
    if isinstance(exc, gmail.GmailNotConnected):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    if isinstance(exc, gmail.GmailServiceError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    if isinstance(exc, RefreshError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Gmail access has expired. Connect Gmail again.") from None
    if isinstance(exc, HttpError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=gmail.gmail_error_message(exc)) from None
    raise exc


def _back_to_app(**params: str) -> RedirectResponse:
    return RedirectResponse(f"{frontend_url()}/gmail-connect?{urlencode(params)}", status_code=303)


@router.get("/api/gmail/status")
def gmail_status(user: CurrentUser):
    return gmail.connection_status(user["uid"])


@router.post("/api/gmail/connect")
def gmail_connect(user: CurrentUser):
    try:
        return {"url": gmail.authorization_url(user["uid"])}
    except Exception as exc:
        _raise_for(exc)


@router.get(CALLBACK_PATH, include_in_schema=False)
def gmail_callback(request: Request):
    """Google redirects here after consent. The encrypted state identifies the user."""
    if request.query_params.get("error"):
        return _back_to_app(gmail="error", message="Google sign-in was cancelled or denied.")
    code = request.query_params.get("code") or ""
    state = request.query_params.get("state") or ""
    if not code or not state:
        return _back_to_app(gmail="error", message="Google sign-in could not be verified.")
    try:
        email = gmail.complete_authorization(code, state)
    except gmail.GmailServiceError as exc:
        return _back_to_app(gmail="error", message=str(exc))
    except Exception:
        logger.exception("Gmail callback failed")
        return _back_to_app(gmail="error", message="Could not finish connecting Gmail. Try again.")
    return _back_to_app(gmail="connected", email=email or "")


@router.post("/api/gmail/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def gmail_disconnect(user: CurrentUser) -> Response:
    try:
        gmail.disconnect(user["uid"])
    except Exception as exc:
        _raise_for(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/gmail/messages")
def gmail_messages(
    user: CurrentUser,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
):
    try:
        return gmail.search_invoice_emails(user["uid"], date_from, date_to)
    except Exception as exc:
        _raise_for(exc)


@router.get("/api/gmail/invoices")
def gmail_saved_invoices(user: CurrentUser, limit: int = Query(100, ge=1, le=100)):
    return gmail.list_saved_invoices(user["uid"], limit)


@router.get("/api/gmail/invoices/{record_id}/file")
def gmail_saved_invoice_file(record_id: str, user: CurrentUser) -> FileResponse:
    try:
        path, filename, media_type = gmail.saved_invoice_file(user["uid"], record_id)
    except Exception as exc:
        _raise_for(exc)
    return FileResponse(path, media_type=media_type, filename=filename, headers={"Cache-Control": "no-store"})


@router.delete("/api/gmail/invoices/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def gmail_delete_saved_invoice(record_id: str, user: CurrentUser) -> Response:
    try:
        gmail.delete_saved_invoice(user["uid"], record_id)
    except Exception as exc:
        _raise_for(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/gmail/messages/{message_id}/attachments/{part_id}")
def gmail_attachment(message_id: str, part_id: str, user: CurrentUser) -> Response:
    try:
        data, filename, media_type = gmail.download_attachment(user["uid"], message_id, part_id)
    except Exception as exc:
        _raise_for(exc)
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )
