# backend/app/services/cache/cache_service.py

from typing import Dict, Any, Optional, Union
import logging
import json
import pickle
from datetime import datetime, timedelta
import aioredis
import hashlib

from ...core.exceptions import CacheError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class CacheService:
    """Enhanced service for data caching using Redis."""
    
    def __init__(self):
        """Initialize cache service with Redis connection."""
        self.redis = aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        
        # Cache settings
        self.default_ttl = 3600  # 1 hour
        self.key_prefix = "ats:"
        self.serialize_method = "json"  # or "pickle" for complex objects
        
        # Cache namespaces
        self.namespaces = {
            "user": "usr:",
            "center": "ctr:",
            "vehicle": "veh:",
            "test": "tst:",
            "analytics": "anl:"
        }
        
        logger.info("Cache service initialized")

    async def get(
        self,
        key: str,
        namespace: Optional[str] = None
    ) -> Optional[Any]:
        """Retrieve data from cache."""
        try:
            cache_key = self._build_key(key, namespace)
            data = await self.redis.get(cache_key)
            
            if data:
                return self._deserialize(data)
            return None
            
        except Exception as e:
            logger.error(f"Cache retrieval error: {str(e)}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: Optional[str] = None
    ) -> bool:
        """Store data in cache with optional TTL."""
        try:
            cache_key = self._build_key(key, namespace)
            serialized_data = self._serialize(value)
            
            if ttl is None:
                ttl = self.default_ttl
                
            await self.redis.set(
                cache_key,
                serialized_data,
                ex=ttl
            )
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {str(e)}")
            return False

    async def delete(
        self,
        key: str,
        namespace: Optional[str] = None
    ) -> bool:
        """Remove data from cache."""
        try:
            cache_key = self._build_key(key, namespace)
            await self.redis.delete(cache_key)
            return True
            
        except Exception as e:
            logger.error(f"Cache delete error: {str(e)}")
            return False

    async def clear_namespace(
        self,
        namespace: str
    ) -> bool:
        """Clear all keys in a namespace."""
        try:
            pattern = f"{self.key_prefix}{self.namespaces.get(namespace, '')}*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor,
                    match=pattern
                )
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
            return True
            
        except Exception as e:
            logger.error(f"Namespace clearing error: {str(e)}")
            return False

    async def get_many(
        self,
        keys: List[str],
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve multiple items from cache."""
        try:
            cache_keys = [
                self._build_key(key, namespace)
                for key in keys
            ]
            
            values = await self.redis.mget(cache_keys)
            result = {}
            
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = self._deserialize(value)
                    
            return result
            
        except Exception as e:
            logger.error(f"Bulk cache retrieval error: {str(e)}")
            return {}

    async def set_many(
        self,
        data: Dict[str, Any],
        ttl: Optional[int] = None,
        namespace: Optional[str] = None
    ) -> bool:
        """Store multiple items in cache."""
        try:
            pipeline = self.redis.pipeline()
            
            for key, value in data.items():
                cache_key = self._build_key(key, namespace)
                serialized_data = self._serialize(value)
                
                if ttl is None:
                    ttl = self.default_ttl
                    
                pipeline.set(
                    cache_key,
                    serialized_data,
                    ex=ttl
                )
                
            await pipeline.execute()
            return True
            
        except Exception as e:
            logger.error(f"Bulk cache set error: {str(e)}")
            return False

    def _build_key(
        self,
        key: str,
        namespace: Optional[str] = None
    ) -> str:
        """Build cache key with prefix and namespace."""
        if namespace:
            namespace_prefix = self.namespaces.get(namespace, '')
            return f"{self.key_prefix}{namespace_prefix}{key}"
        return f"{self.key_prefix}{key}"

    def _serialize(self, data: Any) -> str:
        """Serialize data for storage."""
        try:
            if self.serialize_method == "json":
                return json.dumps(data)
            elif self.serialize_method == "pickle":
                return pickle.dumps(data)
            raise CacheError(f"Invalid serialization method: {self.serialize_method}")
            
        except Exception as e:
            logger.error(f"Serialization error: {str(e)}")
            raise CacheError("Failed to serialize data")

    def _deserialize(self, data: str) -> Any:
        """Deserialize data from storage."""
        try:
            if self.serialize_method == "json":
                return json.loads(data)
            elif self.serialize_method == "pickle":
                return pickle.loads(data)
            raise CacheError(f"Invalid serialization method: {self.serialize_method}")
            
        except Exception as e:
            logger.error(f"Deserialization error: {str(e)}")
            raise CacheError("Failed to deserialize data")

    async def increment(
        self,
        key: str,
        amount: int = 1,
        namespace: Optional[str] = None
    ) -> int:
        """Increment numeric value in cache."""
        try:
            cache_key = self._build_key(key, namespace)
            return await self.redis.incrby(cache_key, amount)
            
        except Exception as e:
            logger.error(f"Increment error: {str(e)}")
            raise CacheError("Failed to increment value")

    async def decrement(
        self,
        key: str,
        amount: int = 1,
        namespace: Optional[str] = None
    ) -> int:
        """Decrement numeric value in cache."""
        try:
            cache_key = self._build_key(key, namespace)
            return await self.redis.decrby(cache_key, amount)
            
        except Exception as e:
            logger.error(f"Decrement error: {str(e)}")
            raise CacheError("Failed to decrement value")

# Initialize cache service
cache_service = CacheService()