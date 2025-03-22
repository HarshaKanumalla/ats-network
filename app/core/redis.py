#backend/app/core/redis.py

import aioredis
from typing import Optional
from .config import settings

class RedisManager:
    """Redis connection manager."""
    
    _instance: Optional[aioredis.Redis] = None
    
    @classmethod
    async def get_instance(cls) -> aioredis.Redis:
        """Get Redis instance with connection pooling."""
        if cls._instance is None:
            redis_settings = settings.get_redis_settings()
            cls._instance = await aioredis.from_url(
                f"redis://{redis_settings['host']}:{redis_settings['port']}",
                password=redis_settings['password'],
                db=redis_settings['db'],
                ssl=redis_settings['ssl'],
                max_connections=redis_settings['max_connections'],
                timeout=redis_settings['connection_timeout'],
                retry_on_timeout=redis_settings['retry_on_timeout']
            )
        return cls._instance
    
    @classmethod
    async def close(cls) -> None:
        """Close Redis connection."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None

redis_manager = RedisManager()