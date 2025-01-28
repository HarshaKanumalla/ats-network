"""Application entry point and configuration."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys
from contextlib import asynccontextmanager

# Import main_router specifically from routes package
from app.routes import main_router
from app.services.initialization import initialization_service
from app.middleware import AuthMiddleware, RequestLogger
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle events."""
    try:
        logger.info("Initializing application components")
        await initialization_service.initialize_application()
        logger.info("Application initialization completed successfully")
        yield
    except Exception as e:
        logger.error("Application initialization failed", exc_info=True)
        raise
    finally:
        logger.info("Performing application shutdown procedures")

def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="ATS Network API",
        description="Advanced Transportation System Network Management API",
        version="1.0.0",
        lifespan=lifespan
    )

    # Configure CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # Your frontend URL
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    # Add custom middleware
    application.add_middleware(AuthMiddleware)
    application.add_middleware(RequestLogger)

    # Include the API router with prefix
    application.include_router(main_router, prefix="/api/v1")

    return application

# Create the application instance
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