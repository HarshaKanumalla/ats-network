"""Routes module initialization and configuration."""
from fastapi import APIRouter

# Create the main router
main_router = APIRouter()

# Import and include sub-routers
from .auth import router as auth_router
from .admin import router as admin_router
from .users import router as users_router
from .dashboard import router as dashboard_router
from .locations import router as locations_router
from .stats import router as stats_router

# Include all routers with their prefixes
main_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
main_router.include_router(admin_router, prefix="/admin", tags=["Administration"])
main_router.include_router(users_router, prefix="/users", tags=["User Management"])
main_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
main_router.include_router(locations_router, prefix="/locations", tags=["Locations"])
main_router.include_router(stats_router, prefix="/stats", tags=["Statistics"])

# Export the main router
__all__ = ["main_router"]