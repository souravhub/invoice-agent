"""Top-level API router composition."""

from fastapi import APIRouter

from .gmail import router as gmail_router
from .processing import router as processing_router
from .workspace import router as workspace_router


api_router = APIRouter()
api_router.include_router(processing_router)
api_router.include_router(workspace_router)
api_router.include_router(gmail_router)
