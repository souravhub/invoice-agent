"""Authenticated Firestore access used exclusively by the FastAPI layer."""

from __future__ import annotations

import os
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import firebase_admin
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials, firestore
from google.auth.exceptions import DefaultCredentialsError


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def firebase_app() -> firebase_admin.App:
    """Initialize Firebase Admin lazily so non-database API routes still start cleanly."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        credential_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        options = {"projectId": project_id} if project_id else None
        if credential_path:
            return firebase_admin.initialize_app(credentials.Certificate(credential_path), options)
        return firebase_admin.initialize_app(options=options)


def firestore_client():
    return firestore.client(app=firebase_app())


def authenticated_user(
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if authorization is None or authorization.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in is required for this request.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        app = firebase_app()
        return auth.verify_id_token(authorization.credentials, app=app)
    except (DefaultCredentialsError, FileNotFoundError, auth.CertificateFetchError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Firebase Admin is not configured. Set FIREBASE_SERVICE_ACCOUNT_PATH "
                "or GOOGLE_APPLICATION_CREDENTIALS on the backend."
            ),
        ) from None
    except (ValueError, auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The sign-in session is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def user_collection(uid: str, name: str):
    return firestore_client().collection("users").document(uid).collection(name)


def json_safe(value: Any) -> Any:
    """Convert Firestore-specific values into JSON response values."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def document_payload(snapshot) -> dict[str, Any]:
    return {"id": snapshot.id, **json_safe(snapshot.to_dict() or {})}


def get_owned_document(uid: str, collection_name: str, document_id: str):
    reference = user_collection(uid, collection_name).document(document_id)
    snapshot = reference.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="The requested record could not be found.")
    return reference, snapshot
