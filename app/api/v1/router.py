from fastapi import APIRouter
from . import admin, analytics, auth, centers, monitoring, reports, tests, users, vehicles

api_router = APIRouter()

# Include all API routes
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(centers.router, prefix="/centers", tags=["Centers"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["Monitoring"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(tests.router, prefix="/tests", tags=["Tests"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(vehicles.router, prefix="/vehicles", tags=["Vehicles"])
