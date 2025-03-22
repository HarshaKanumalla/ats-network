# backend/app/core/database/manager.py

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import backoff
from pymongo.errors import (
    ConnectionFailure, 
    OperationFailure,
    ServerSelectionTimeoutError
)

from .migration_manager import MigrationManager
from ..exceptions import DatabaseError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DatabaseManager:
    """Manages database connections and operations with migration support."""
    
    def __init__(self):
        """Initialize database manager with configuration settings."""
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self.migration_manager: Optional[MigrationManager] = None
        self.connected = False
        
        # Connection pool settings
        self.connection_settings = {
            'min_pool_size': settings.MONGODB_MIN_POOL_SIZE,
            'max_pool_size': settings.MONGODB_MAX_POOL_SIZE,
            'max_idle_time_ms': 60000,
            'connect_timeout_ms': 5000,
            'server_selection_timeout_ms': 5000,
            'wait_queue_timeout_ms': 1000,
            'retry_writes': True,
            'w': 'majority'
        }
        
        logger.info("Database manager initialized")

    @backoff.on_exception(
        backoff.expo,
        (ConnectionFailure, ServerSelectionTimeoutError),
        max_tries=3,
        max_time=30
    )
    async def connect(self) -> None:
        """Establish database connection with retry mechanism."""
        if self.connected:
            return

        try:
            # Initialize MongoDB client
            self._client = AsyncIOMotorClient(
                settings.MONGODB_URL,
                **self.connection_settings
            )

            # Test connection
            await self._client.admin.command('ping')
            
            # Initialize database
            self._db = self._client[settings.MONGODB_DB_NAME]
            
            # Initialize migration manager
            self.migration_manager = MigrationManager(self._db)
            
            # Run initial setup and migrations
            await self._initialize_database()
            
            self.connected = True
            logger.info(f"Connected to MongoDB: {settings.MONGODB_DB_NAME}")

        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            raise DatabaseError(f"Failed to connect to database: {str(e)}")

    async def _initialize_database(self) -> None:
        """Initialize database with schema validation and run migrations."""
        try:
            # Initialize database with schema validation
            await self.migration_manager.initialize_database()
            
            # Run pending migrations
            await self.migration_manager.run_migrations()
            
            logger.info("Database initialization completed")

        except Exception as e:
            logger.error(f"Database initialization error: {str(e)}")
            raise DatabaseError(f"Failed to initialize database: {str(e)}")

    async def get_database(self) -> AsyncIOMotorDatabase:
        """Get database instance with connection check."""
        if not self.connected:
            await self.connect()
        return self._db

    async def execute_query(
        self,
        collection: str,
        operation: str,
        query: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None,
        session: Optional[Any] = None
    ) -> Any:
        """Execute database query with error handling."""
        try:
            if not self.connected:
                await self.connect()

            db = await self.get_database()
            collection_obj = db[collection]

            # Execute query with optional session
            if operation == 'find_one':
                result = await collection_obj.find_one(
                    query,
                    projection,
                    session=session,
                    **(options or {})
                )
            elif operation == 'find':
                cursor = collection_obj.find(
                    query,
                    projection,
                    session=session,
                    **(options or {})
                )
                result = await cursor.to_list(None)
            elif operation == 'insert_one':
                result = await collection_obj.insert_one(
                    query,
                    session=session,
                    **(options or {})
                )
            elif operation == 'update_one':
                result = await collection_obj.update_one(
                    query,
                    projection,
                    session=session,
                    **(options or {})
                )
            elif operation == 'delete_one':
                result = await collection_obj.delete_one(
                    query,
                    session=session,
                    **(options or {})
                )
            else:
                raise DatabaseError(f"Unsupported operation: {operation}")

            return result

        except Exception as e:
            logger.error(f"Query execution error: {str(e)}")
            raise DatabaseError(f"Failed to execute query: {str(e)}")

    async def create_collection(
        self,
        name: str,
        schema: Dict[str, Any]
    ) -> None:
        """Create new collection with schema validation."""
        try:
            if not self.connected:
                await self.connect()

            await self._db.create_collection(
                name,
                validator=schema,
                validationLevel="strict"
            )
            logger.info(f"Created collection: {name}")

        except Exception as e:
            logger.error(f"Collection creation error: {str(e)}")
            raise DatabaseError(f"Failed to create collection: {str(e)}")

    async def update_collection_schema(
        self,
        name: str,
        schema: Dict[str, Any]
    ) -> None:
        """Update existing collection schema."""
        try:
            if not self.connected:
                await self.connect()

            await self._db.command({
                "collMod": name,
                "validator": schema,
                "validationLevel": "strict"
            })
            logger.info(f"Updated schema for collection: {name}")

        except Exception as e:
            logger.error(f"Schema update error: {str(e)}")
            raise DatabaseError(f"Failed to update schema: {str(e)}")

    async def check_health(self) -> Dict[str, Any]:
        """Check database health status."""
        try:
            if not self.connected:
                await self.connect()

            # Check connection
            await self._client.admin.command('ping')
            
            # Get database stats
            stats = await self._db.command('dbStats')
            
            return {
                'status': 'healthy',
                'connection': True,
                'collections': await self._db.list_collection_names(),
                'statistics': {
                    'collections': stats['collections'],
                    'objects': stats['objects'],
                    'dataSize': stats['dataSize'],
                    'storageSize': stats['storageSize']
                }
            }

        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            return {
                'status': 'unhealthy',
                'connection': False,
                'error': str(e)
            }

    async def close(self) -> None:
        """Close database connection safely."""
        try:
            if self._client:
                self._client.close()
                self.connected = False
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Connection closure error: {str(e)}")
            raise DatabaseError(f"Failed to close database connection: {str(e)}")

# Initialize database manager
db_manager = DatabaseManager()