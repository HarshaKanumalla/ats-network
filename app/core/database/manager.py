from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional, Dict, Any, List
import logging
from contextlib import asynccontextmanager
import backoff
from datetime import datetime
from pymongo.errors import (
    ConnectionFailure,
    OperationFailure,
    ServerSelectionTimeoutError
)

from ...core.exceptions import DatabaseError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DatabaseManager:
    """Manages database connections and operations with comprehensive error handling."""
    
    def __init__(self):
        """Initialize database manager with configuration settings."""
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self.connected = False
        
        # Connection pool settings
        self.min_pool_size = settings.mongodb_min_pool_size
        self.max_pool_size = settings.mongodb_max_pool_size
        self.max_idle_time_ms = 60000
        
        # Query timeout settings
        self.default_timeout = 30000  # 30 seconds
        self.long_query_threshold = 10000  # 10 seconds
        
        # Operation retry settings
        self.max_retry_attempts = 3
        self.initial_retry_delay = 1  # seconds
        self.max_retry_delay = 10  # seconds
        
        # Cache settings
        self.query_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
        logger.info("Database manager initialized with enhanced settings")

    @backoff.on_exception(
        backoff.expo,
        (ConnectionFailure, ServerSelectionTimeoutError),
        max_tries=3,
        max_time=30
    )
    async def connect(self) -> None:
        """Establish database connection with retry mechanism.
        
        Raises:
            DatabaseError: If connection fails after retries
        """
        if self.connected:
            return

        try:
            self._client = AsyncIOMotorClient(
                settings.mongodb_url,
                minPoolSize=self.min_pool_size,
                maxPoolSize=self.max_pool_size,
                maxIdleTimeMS=self.max_idle_time_ms,
                connectTimeoutMS=5000,
                serverSelectionTimeoutMS=5000,
                waitQueueTimeoutMS=1000,
                retryWrites=True,
                w='majority'
            )

            # Test connection
            await self._client.admin.command('ping')
            
            self._db = self._client[settings.mongodb_db_name]
            self.connected = True

            # Initialize collections and indexes
            await self._initialize_collections()
            
            logger.info(f"Connected to MongoDB: {settings.mongodb_db_name}")

        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            raise DatabaseError(f"Failed to connect to database: {str(e)}")

    async def _initialize_collections(self) -> None:
        """Initialize collections with proper indexes for optimization.
        
        Raises:
            DatabaseError: If collection initialization fails
        """
        try:
            # Users collection indexes
            await self._db.users.create_index(
                [("email", 1)],
                unique=True,
                background=True
            )
            await self._db.users.create_index(
                [
                    ("role", 1),
                    ("status", 1),
                    ("createdAt", -1)
                ],
                background=True
            )

            # Centers collection indexes
            await self._db.centers.create_index(
                [("location.coordinates", "2dsphere")],
                background=True
            )
            await self._db.centers.create_index(
                [("centerCode", 1)],
                unique=True,
                background=True
            )

            # Test sessions collection indexes
            await self._db.testSessions.create_index(
                [
                    ("vehicleId", 1),
                    ("centerId", 1),
                    ("startTime", -1)
                ],
                background=True
            )

            # Vehicles collection indexes
            await self._db.vehicles.create_index(
                [("registrationNumber", 1)],
                unique=True,
                background=True
            )

            logger.info("Database collections and indexes initialized")

        except Exception as e:
            logger.error(f"Collection initialization error: {str(e)}")
            raise DatabaseError(f"Failed to initialize collections: {str(e)}")

    @asynccontextmanager
    async def transaction(self):
        """Manage database transactions with proper error handling.
        
        Yields:
            Active transaction session
            
        Raises:
            DatabaseError: If transaction operations fail
        """
        if not self.connected:
            await self.connect()

        async with await self._client.start_session() as session:
            try:
                async with session.start_transaction():
                    yield session
                    await session.commit_transaction()
            except Exception as e:
                await session.abort_transaction()
                logger.error(f"Transaction error: {str(e)}")
                raise DatabaseError(f"Transaction failed: {str(e)}")

    async def execute_query(
        self,
        collection: str,
        operation: str,
        query: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        use_cache: bool = False
    ) -> Any:
        """Execute database query with optimization and caching.
        
        Args:
            collection: Target collection name
            operation: Query operation type
            query: Query parameters
            projection: Optional field projection
            options: Optional query options
            use_cache: Whether to use query cache
            
        Returns:
            Query results
            
        Raises:
            DatabaseError: If query execution fails
        """
        try:
            if not self.connected:
                await self.connect()

            collection_obj = self._db[collection]
            cache_key = f"{collection}:{operation}:{hash(str(query))}"

            # Check cache for read operations
            if use_cache and operation == 'find':
                cached_result = self._get_from_cache(cache_key)
                if cached_result:
                    return cached_result

            # Add query timeout
            query_options = {
                'maxTimeMS': self.default_timeout,
                **(options or {})
            }

            # Execute query with monitoring
            start_time = datetime.utcnow()
            
            if operation == 'find_one':
                result = await collection_obj.find_one(
                    query,
                    projection,
                    **query_options
                )
            elif operation == 'find':
                cursor = collection_obj.find(
                    query,
                    projection,
                    **query_options
                )
                result = await cursor.to_list(None)
            elif operation == 'insert_one':
                result = await collection_obj.insert_one(query, **query_options)
                result = result.inserted_id
            elif operation == 'update_one':
                result = await collection_obj.update_one(
                    query,
                    projection,
                    **query_options
                )
                result = result.modified_count
            elif operation == 'delete_one':
                result = await collection_obj.delete_one(query, **query_options)
                result = result.deleted_count
            elif operation == 'aggregate':
                cursor = collection_obj.aggregate(query, **query_options)
                result = await cursor.to_list(None)
            else:
                raise ValueError(f"Unsupported operation: {operation}")

            # Monitor query performance
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            if execution_time > self.long_query_threshold:
                logger.warning(
                    f"Long running query detected: {execution_time}ms\n"
                    f"Collection: {collection}, Operation: {operation}\n"
                    f"Query: {query}"
                )

            # Cache results for read operations
            if use_cache and operation == 'find':
                self._store_in_cache(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Query execution error: {str(e)}")
            raise DatabaseError(f"Query failed: {str(e)}")

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Retrieve data from cache if not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached data if available and fresh
        """
        cached_data = self.query_cache.get(key)
        if cached_data:
            if (datetime.utcnow() - cached_data['timestamp']).seconds < self.cache_ttl:
                return cached_data['data']
            del self.query_cache[key]
        return None

    def _store_in_cache(self, key: str, data: Any) -> None:
        """Store data in cache with timestamp.
        
        Args:
            key: Cache key
            data: Data to cache
        """
        self.query_cache[key] = {
            'data': data,
            'timestamp': datetime.utcnow()
        }

    async def close(self) -> None:
        """Close database connection safely.
        
        Raises:
            DatabaseError: If connection closure fails
        """
        try:
            if self._client:
                self._client.close()
                self.connected = False
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Connection closure error: {str(e)}")
            raise DatabaseError(f"Failed to close database connection: {str(e)}")

    async def cleanup(self) -> None:
        """Perform database cleanup operations.
        
        Raises:
            DatabaseError: If cleanup fails
        """
        try:
            # Clear query cache
            self.query_cache.clear()
            
            # Close connection
            await self.close()
            
        except Exception as e:
            logger.error(f"Database cleanup error: {str(e)}")
            raise DatabaseError(f"Failed to cleanup database resources: {str(e)}")

# Initialize database manager
db_manager = DatabaseManager()