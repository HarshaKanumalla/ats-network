# backend/app/main.py

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import Settings, get_settings
from app.core.exceptions import CustomException
from app.api.v1.router import api_router
from app.services.auth.manager import AuthManager
from app.services.database import DatabaseManager
from app.services.websocket import WebSocketManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
settings = get_settings()

async def startup_db_client():
    """Initialize database connection on startup."""
    try:
        app.mongodb_client = AsyncIOMotorClient(settings.mongodb_url)
        app.mongodb = app.mongodb_client[settings.database_name]
        logger.info("Connected to MongoDB")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

async def shutdown_db_client():
    """Close database connection on shutdown."""
    try:
        app.mongodb_client.close()
        logger.info("Closed MongoDB connection")
    except Exception as e:
        logger.error(f"Error closing MongoDB connection: {e}")

async def startup_websocket():
    """Initialize WebSocket manager on startup."""
    try:
        app.websocket_manager = WebSocketManager()
        logger.info("Initialized WebSocket manager")
    except Exception as e:
        logger.error(f"Failed to initialize WebSocket manager: {e}")
        raise

def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="ATS Network API",
        description="Automated Testing Station Network Management System",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json"
    )

    # Add CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handler
    @application.exception_handler(CustomException)
    async def custom_exception_handler(request: Request, exc: CustomException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "message": exc.detail,
                "code": exc.error_code
            }
        )

    # Add startup and shutdown events
    application.add_event_handler("startup", startup_db_client)
    application.add_event_handler("startup", startup_websocket)
    application.add_event_handler("shutdown", shutdown_db_client)

    # Include routers
    application.include_router(
        api_router,
        prefix="/api/v1"
    )

    @application.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow(),
            "version": application.version
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
        reload=settings.debug,
        workers=settings.workers_count
    )
