# backend/app/__init__.py
from .routes import auth_router, admin_router

__all__ = [
    'auth_router',
    'admin_router'
]