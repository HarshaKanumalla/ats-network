# backend/app/main.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys
from logging.handlers import RotatingFileHandler
from motor.motor_asyncio import AsyncIOMotorClient
import redis
from .routes.auth import router as auth_router
from .routes.admin import router as admin_router
from .middleware.logging import RequestLoggingMiddleware
from .config import get_settings

# Configure logging
def setup_logging():
    """Configure application-wide logging."""
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = RotatingFileHandler(
        'app.log',
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Set levels for third-party loggers
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('fastapi').setLevel(logging.DEBUG)

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

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

# Global request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    logger.info(f"Request headers: {dict(request.headers)}")
    
    try:
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}", exc_info=True)
        raise

# CORS configuration
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Add custom logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Initialize Redis client
redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=settings.redis_password,
    decode_responses=True
)

# Include routers
app.include_router(auth_router)
app.include_router(admin_router, prefix="/admin", tags=["admin"])

@app.on_event("startup")
async def startup_event():
    """Initialize services and verify connections on startup."""
    try:
        logger.info("Verifying application settings:")
        logger.info(f"JWT Algorithm: {settings.token_algorithm}")
        logger.info(f"JWT Expiration: {settings.access_token_expire_minutes}")
        logger.info(f"Environment: {settings.environment}")

        # Test database connection
        logger.info("Testing database connection...")
        client = AsyncIOMotorClient(settings.mongodb_url)
        await client.admin.command('ping')
        logger.info("Database connection successful")

        # Test Redis connection
        logger.info("Testing Redis connection...")
        redis_client.ping()
        logger.info("Redis connection successful")

        logger.info("Application startup complete")
    except Exception as e:
        logger.error(f"Startup error: {str(e)}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    try:
        logger.info("Shutting down application...")
        redis_client.close()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Shutdown error: {str(e)}", exc_info=True)

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
        "environment": settings.environment
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment != "production",
        workers=settings.workers_count
    )