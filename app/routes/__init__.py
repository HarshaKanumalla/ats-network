# backend/app/routes/__init__.py
from fastapi import APIRouter
from .auth import router as auth_router
from .users import router as users_router
from .admin import router as admin_router


# Create a main router to combine all routes
main_router = APIRouter()

# Include the sub-routers
main_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
main_router.include_router(users_router, prefix="/users", tags=["Users"])
main_router.include_router(admin_router, prefix="/admin", tags=["Admin"])


__all__ = ['auth_router', 'admin_router', 'users_router', 'main_router']

