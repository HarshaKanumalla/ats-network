# backend/app/main.py

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from datetime import datetime

from app.core.config import get_settings
from app.core.exceptions import CustomException, HTTPException
from app.api.v1.router import api_router
from app.core.middleware.error_handler import error_handler
from app.services.database import DatabaseManager
from app.services.websocket import WebSocketManager
from app.services.cache import CacheService

# Configure logging with rotation
log_handler = RotatingFileHandler("app.log", maxBytes=10 * 1024 * 1024, backupCount=5)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), log_handler],
)
logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize services
db_manager = DatabaseManager()
websocket_manager = WebSocketManager()
cache_service = CacheService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    try:
        # Startup
        logger.info("Starting up application services...")
        await db_manager.connect()
        await websocket_manager.initialize()
        await cache_service.initialize()
        logger.info("Application startup complete")

        yield

    except Exception as e:
        logger.error(f"Application lifecycle error: {str(e)}")
        raise

    finally:
        # Shutdown
        logger.info("Shutting down application services...")
        try:
            await websocket_manager.shutdown()
            await db_manager.disconnect()
            await cache_service.cleanup()
            logger.info("Application shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")

def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title=settings.APP_NAME,
        description="Automated Testing Station Network Management System",
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Add CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add error handling middleware
    application.middleware("http")(error_handler)

    # Custom exception handlers
    @application.exception_handler(CustomException)
    async def custom_exception_handler(request: Request, exc: CustomException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "message": exc.detail,
                "code": exc.error_code,
                "timestamp": datetime.utcnow().isoformat(),
                "path": request.url.path,
            },
        )

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "message": str(exc.detail),
                "timestamp": datetime.utcnow().isoformat(),
                "path": request.url.path,
            },
        )

    @application.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        response_content = {
            "status": "error",
            "message": "Internal server error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.url.path,
        }
        if settings.DEBUG:
            response_content["detail"] = str(exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_content,
        )

    # Include routers
    application.include_router(
        api_router,
        prefix=settings.API_V1_PREFIX,
    )

    @application.get("/health")
    async def health_check():
        """Enhanced health check endpoint."""
        try:
            return {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "version": application.version,
                "environment": settings.ENVIRONMENT,
                "services": {
                    "database": await db_manager.check_health(),
                    "cache": await cache_service.check_health(),
                    "websocket": websocket_manager.is_healthy(),
                },
            }
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            }

    return application

# Create application instance
app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        workers=settings.WORKERS_COUNT,
    )