"""FastAPI application bootstrap and middleware configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .core.config import cors_origins


app = FastAPI(
    title="Invoice Agent API",
    version="1.1.0",
    description=(
        "Extracts invoice PDFs or ZIP batches, validates them, and manages the authenticated "
        "invoice workspace. A passing result is not payment authorization or proof of authenticity."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router)
