"""Environment-backed application settings shared by the API layer."""

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
ZIP_CONTENT_TYPES = {"application/zip", "application/x-zip-compressed"}
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
