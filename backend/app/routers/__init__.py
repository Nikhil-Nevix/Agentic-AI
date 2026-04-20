"""
API routers for FastAPI application.
"""

from app.routers.triage import router as triage_router
from app.routers.auth import router as auth_router
from app.routers.google_chat_webhook import router as google_chat_webhook_router
from app.routers.freshservice_webhook import router as freshservice_webhook_router

__all__ = ['triage_router', 'auth_router', 'google_chat_webhook_router', 'freshservice_webhook_router']
