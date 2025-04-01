# backend/app/core/redis.py

import aioredis
from typing import Optional, Dict, Any
from .config import settings
import logging

logger = logging.getLogger(__name__)

class RedisManager:
    """Redis connection manager."""
    
    _instance: Optional[aioredis.Redis] = None
    
    @classmethod
    async def get_instance(cls) -> aioredis.Redis:
        """Get Redis instance with connection pooling."""
        if cls._instance is None:
            try:
                redis_settings = settings.get_redis_settings()
                cls._validate_redis_settings(redis_settings)
                cls._instance = await aioredis.from_url(
                    f"redis://{redis_settings['host']}:{redis_settings['port']}",
                    password=redis_settings['password'],
                    db=redis_settings['db'],
                    ssl=redis_settings['ssl'],
                    max_connections=redis_settings['max_connections'],
                    timeout=redis_settings['connection_timeout'],
                    retry_on_timeout=redis_settings['retry_on_timeout']
                )
                logger.info("Redis connection initialized")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                raise
        return cls._instance
    
    @classmethod
    async def close(cls) -> None:
        """Close Redis connection."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None
            logger.info("Redis connection closed")
    
    @classmethod
    async def check_health(cls) -> bool:
        """Check Redis connection health."""
        try:
            instance = await cls.get_instance()
            await instance.ping()
            logger.info("Redis health check passed")
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {str(e)}")
            return False

    @staticmethod
    def _validate_redis_settings(redis_settings: Dict[str, Any]) -> None:
        """Validate Redis settings."""
        required_keys = ["host", "port", "db", "max_connections", "connection_timeout"]
        for key in required_keys:
            if key not in redis_settings:
                raise ValueError(f"Missing required Redis setting: {key}")

    async def __aenter__(self):
        return await self.get_instance()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

redis_manager = RedisManager()