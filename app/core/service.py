#backend/app/core/service.py

from typing import Optional
from datetime import datetime
import logging
from .database.manager import DatabaseManager
from .exceptions import ServiceError

logger = logging.getLogger(__name__)

class BaseService:
    """Base service class providing common functionality for all services."""
    
    def __init__(self):
        self.db: Optional[DatabaseManager] = None
        self._initialized = False
        self._init_time = datetime.utcnow()

    async def initialize(self) -> None:
        """Initialize service with database connection and other requirements."""
        if self._initialized:
            return

        try:
            self.db = await DatabaseManager().get_instance()
            self._initialized = True
            logger.info(f"{self.__class__.__name__} initialized successfully")
        except Exception as e:
            logger.error(f"Service initialization error: {str(e)}")
            raise ServiceError(f"Failed to initialize {self.__class__.__name__}")

    async def check_health(self) -> dict:
        """Check service health status."""
        return {
            "service": self.__class__.__name__,
            "initialized": self._initialized,
            "uptime": (datetime.utcnow() - self._init_time).total_seconds(),
            "database_connected": self.db is not None
        }

    async def cleanup(self) -> None:
        """Cleanup service resources."""
        self._initialized = False
        logger.info(f"{self.__class__.__name__} cleaned up successfully")