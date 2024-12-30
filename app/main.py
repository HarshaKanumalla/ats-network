# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from .routes import auth_router, admin_router, main_router
from .config import get_settings

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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(main_router)


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

@app.on_event("startup")
async def startup_event():
    """Initialize services and verify settings on startup."""
    settings = get_settings()
    logger.info("Verifying application settings:")
    logger.info(f"JWT Algorithm: {settings.jwt_algorithm}")
    logger.info(f"JWT Expiration: {settings.jwt_expiration}")
    logger.info(f"Environment: {settings.environment}")
    logger.info("Available routes:")
    for route in app.routes:
        logger.info(f"Route: {route.path}, Methods: {route.methods}")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": SYSTEM_INFO["last_updated"],
        "environment": settings.environment
    }

# Handle startup events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    # Add any startup initialization here
    pass

# Handle shutdown events
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    # Add any cleanup code here
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment != "production",
        workers=settings.workers_count
    )