# backend/app/middleware/__init__.py

from .auth import AuthMiddleware

__all__ = ['AuthMiddleware']