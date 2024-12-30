# backend/app/__init__.py
from .routes import auth_router, admin_router
from .models import *
from .services import *

__all__ = [
    'auth_router',
    'admin_router'
]