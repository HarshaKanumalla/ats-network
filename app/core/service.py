# backend/app/core/service.py

from typing import Optional
from datetime import datetime
import logging
from asyncio import Lock
from .database.manager import DatabaseManager
from .exceptions import ServiceError

logger = logging.getLogger(__name__)

class BaseService:
    """Base service class providing common functionality for all services."""
    
    def __init__(self):
        self.db: Optional[DatabaseManager] = None
        self._initialized = False
        self._init_time = None
        self._lock = Lock()  # Ensure thread safety for initialization and cleanup

    async def initialize(self, force: bool = False) -> None:
        """Initialize service with database connection and other requirements.
        
        Args:
            force: If True, reinitialize the service even if already initialized.
        """
        async with self._lock:
            if self._initialized and not force:
                logger.info(f"{self.__class__.__name__} is already initialized")
                return

            try:
                self.db = await DatabaseManager().get_instance()
                self._initialized = True
                self._init_time = datetime.utcnow()
                logger.info(f"{self.__class__.__name__} initialized successfully")
            except Exception as e:
                logger.error(f"Service initialization error: {str(e)}")
                raise ServiceError(f"Failed to initialize {self.__class__.__name__}") from e

    async def check_health(self) -> dict:
        """Check service health status."""
        health_status = {
            "service": self.__class__.__name__,
            "initialized": self._initialized,
            "uptime": (datetime.utcnow() - self._init_time).total_seconds() if self._init_time else 0,
            "database_connected": await self._check_database_health() if self.db else False
        }
        logger.info(f"Health check for {self.__class__.__name__}: {health_status}")
        return health_status

    async def _check_database_health(self) -> bool:
        """Check the health of the database connection."""
        try:
            return await self.db.check_health()
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False

    async def cleanup(self) -> None:
        """Cleanup service resources."""
        async with self._lock:
            try:
                if self.db:
                    await self.db.close()
                    self.db = None
                self._initialized = False
                logger.info(f"{self.__class__.__name__} cleaned up successfully")
            except Exception as e:
                logger.error(f"Error during cleanup of {self.__class__.__name__}: {str(e)}")
                raise ServiceError(f"Failed to clean up {self.__class__.__name__}") from e

    async def __aenter__(self):
        """Support for asynchronous context management."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Support for asynchronous context management."""
        await self.cleanup()