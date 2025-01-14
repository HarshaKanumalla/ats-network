# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from .routes import auth_router, admin_router, main_router
from .config import get_settings
from .routes import locations, stats
from .routes import dashboard
from .services.initialization import initialize_sample_data  # Add this import

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# System Info
SYSTEM_INFO = {
    "last_updated": "2024-12-19 18:22:00",
    "updated_by": "HarshaKanumalla"
}

# Get settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="ATS Network API",
    description="API for ATS Network application",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None
)

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(main_router)
app.include_router(locations.router, tags=["locations"])
app.include_router(stats.router, tags=["stats"])
app.include_router(dashboard.router, tags=["dashboard"])

@app.get("/")
async def root():
    """Root endpoint returning API information."""
    return {
        "app_name": "ATS Network API",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.environment,
        "documentation": "/docs" if settings.environment != "production" else None
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": SYSTEM_INFO["last_updated"],
        "environment": settings.environment
    }

@app.on_event("startup")
async def startup_event():
    """Initialize services and verify settings on startup."""
    try:
        settings = get_settings()
        logger.info("Verifying application settings:")
        logger.info(f"JWT Algorithm: {settings.jwt_algorithm}")
        logger.info(f"JWT Expiration: {settings.jwt_expiration}")
        logger.info(f"Environment: {settings.environment}")
        
        logger.info("Available routes:")
        for route in app.routes:
            logger.info(f"Route: {route.path}, Methods: {route.methods}")
        
        # Initialize database and sample data
        await initialize_sample_data()
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Startup error: {str(e)}")
        # Don't raise the error to allow the application to start

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    try:
        # Add any cleanup code here
        logger.info("Application shutting down")
    except Exception as e:
        logger.error(f"Shutdown error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment != "production",
        workers=settings.workers_count
    )