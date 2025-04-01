from typing import Dict, Any, Optional, Union, List
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
        try:
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
            
            # Validate serialization method
            if self.serialize_method not in {"json", "pickle"}:
                raise CacheError(f"Invalid serialization method: {self.serialize_method}")
            
            logger.info("Cache service initialized")
        except Exception as e:
            logger.error(f"Cache service initialization error: {str(e)}")
            raise CacheError("Failed to initialize cache service")

    async def _test_connection(self):
        """Test Redis connection during initialization."""
        try:
            await self.redis.ping()
            logger.info("Redis connection successful")
        except Exception as e:
            logger.error(f"Redis connection error: {str(e)}")
            raise CacheError("Failed to connect to Redis during initialization")

    async def get(self, key: str, namespace: Optional[str] = None) -> Optional[Any]:
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

    async def set(self, key: str, value: Any, ttl: Optional[int] = None, namespace: Optional[str] = None) -> bool:
        """Store data in cache with optional TTL."""
        try:
            self._validate_ttl(ttl or self.default_ttl)
            cache_key = self._build_key(key, namespace)
            serialized_data = self._serialize(value)
            
            await self.redis.set(cache_key, serialized_data, ex=ttl or self.default_ttl)
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {str(e)}")
            return False

    async def delete(self, key: str, namespace: Optional[str] = None) -> bool:
        """Remove data from cache."""
        try:
            cache_key = self._build_key(key, namespace)
            await self.redis.delete(cache_key)
            return True
            
        except Exception as e:
            logger.error(f"Cache delete error: {str(e)}")
            return False

    async def clear_namespace(self, namespace: str) -> bool:
        """Clear all keys in a namespace."""
        try:
            self._validate_namespace(namespace)
            pattern = f"{self.key_prefix}{self.namespaces[namespace]}*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor=cursor, match=pattern)
                if keys:
                    await self.redis.delete(*keys)
                if cursor == 0:
                    break
            return True
            
        except Exception as e:
            logger.error(f"Namespace clearing error: {str(e)}")
            return False

    async def get_many(self, keys: List[str], namespace: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve multiple items from cache."""
        try:
            cache_keys = [self._build_key(key, namespace) for key in keys]
            values = await self.redis.mget(cache_keys)
            result = {}
            
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = self._deserialize(value)
                    
            return result
            
        except Exception as e:
            logger.error(f"Bulk cache retrieval error: {str(e)}")
            return {}

    async def set_many(self, data: Dict[str, Any], ttl: Optional[int] = None, namespace: Optional[str] = None) -> bool:
        """Store multiple items in cache."""
        try:
            self._validate_ttl(ttl or self.default_ttl)
            pipeline = self.redis.pipeline()
            
            for key, value in data.items():
                cache_key = self._build_key(key, namespace)
                serialized_data = self._serialize(value)
                pipeline.set(cache_key, serialized_data, ex=ttl or self.default_ttl)
                
            await pipeline.execute()
            return True
            
        except Exception as e:
            logger.error(f"Bulk cache set error: {str(e)}")
            return False

    async def delete_many(self, keys: List[str], namespace: Optional[str] = None) -> bool:
        """Delete multiple keys from cache."""
        try:
            cache_keys = [self._build_key(key, namespace) for key in keys]
            await self.redis.delete(*cache_keys)
            return True
        except Exception as e:
            logger.error(f"Bulk cache delete error: {str(e)}")
            return False

    async def extend_ttl(self, key: str, ttl: int, namespace: Optional[str] = None) -> bool:
        """Extend the TTL of a cache key."""
        try:
            self._validate_ttl(ttl)
            cache_key = self._build_key(key, namespace)
            if await self.redis.exists(cache_key):
                await self.redis.expire(cache_key, ttl)
                return True
            return False
        except Exception as e:
            logger.error(f"Extend TTL error: {str(e)}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Retrieve cache statistics."""
        try:
            stats = await self.redis.info()
            return {
                "used_memory": stats.get("used_memory_human"),
                "total_keys": stats.get("db0", {}).get("keys", 0),
                "uptime": stats.get("uptime_in_seconds")
            }
        except Exception as e:
            logger.error(f"Cache stats retrieval error: {str(e)}")
            return {}

    async def increment(self, key: str, amount: int = 1, namespace: Optional[str] = None) -> int:
        """Increment numeric value in cache."""
        try:
            cache_key = self._build_key(key, namespace)
            return await self.redis.incrby(cache_key, amount)
        except Exception as e:
            logger.error(f"Increment error: {str(e)}")
            raise CacheError("Failed to increment value")

    async def decrement(self, key: str, amount: int = 1, namespace: Optional[str] = None) -> int:
        """Decrement numeric value in cache."""
        try:
            cache_key = self._build_key(key, namespace)
            return await self.redis.decrby(cache_key, amount)
        except Exception as e:
            logger.error(f"Decrement error: {str(e)}")
            raise CacheError("Failed to decrement value")

    def _build_key(self, key: str, namespace: Optional[str] = None) -> str:
        """Build cache key with prefix and namespace."""
        if len(key) > 250:  # Arbitrary limit for long keys
            key = hashlib.sha256(key.encode()).hexdigest()
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

    def _validate_namespace(self, namespace: str) -> None:
        """Validate if the namespace exists."""
        if namespace not in self.namespaces:
            raise CacheError(f"Invalid namespace: {namespace}")

    def _validate_ttl(self, ttl: int) -> None:
        """Validate TTL value."""
        if ttl is not None and ttl <= 0:
            raise CacheError(f"Invalid TTL value: {ttl}. Must be greater than 0.")

# Initialize cache service
cache_service = CacheService()