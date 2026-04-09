"""
API routers for FastAPI application.
"""

from app.routers.triage import router as triage_router
from app.routers.auth import router as auth_router

__all__ = ['triage_router', 'auth_router']
