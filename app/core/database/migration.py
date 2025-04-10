# backend/app/core/database/migration_manager.py

from typing import Dict, Any, List
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure, CollectionInvalid

from .schemas import DatabaseSchemas
from ..exceptions import MigrationError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MigrationManager:
    """Manages database migrations and schema updates."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.schemas = DatabaseSchemas()
        self.migrations_collection = "migrations"
        logger.info("Migration manager initialized")

    async def initialize_database(self) -> None:
        pass  # Implement logic here

    async def run_migrations(self) -> None:
        pass  # Implement logic here

    async def _initialize_collection(self, collection_name: str, schema: Dict[str, Any]) -> None:
        """Initialize collection with schema validation."""
        try:
            # Check if collection exists
            collections = await self.db.list_collection_names()

            if collection_name in collections:
                # Update existing collection schema
                await self.db.command({
                    "collMod": collection_name,
                    "validator": schema,
                    "validationLevel": "strict"
                })
                logger.info(f"Updated schema for existing collection: {collection_name}")
            else:
                # Create new collection with schema
                await self.db.create_collection(
                    collection_name,
                    validator=schema,
                    validationLevel="strict"
                )
                logger.info(f"Created new collection: {collection_name}")

        except CollectionInvalid as e:
            logger.error(f"Collection initialization error for {collection_name}: {str(e)}")
            raise MigrationError(f"Collection already exists: {str(e)}")
        except OperationFailure as e:
            logger.error(f"MongoDB operation failed for collection {collection_name}: {str(e)}")
            raise MigrationError(f"Failed to initialize collection {collection_name}: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during collection initialization: {str(e)}")
            raise MigrationError(f"Failed to initialize collection {collection_name}: {str(e)}")

    async def _create_indexes(self) -> None:
        """Create collection indexes."""
        try:
            indexes = self.schemas.get_collection_indexes()

            for collection_name, collection_indexes in indexes.items():
                for index in collection_indexes:
                    await self.db[collection_name].create_index(
                        index["key"],
                        unique=index.get("unique", False),
                        background=True
                    )

            logger.info("Created all required indexes")

        except Exception as e:
            logger.error(f"Index creation error: {str(e)}")
            raise MigrationError(f"Failed to create indexes: {str(e)}")

    async def _get_current_version(self) -> int:
        """Get current database version."""
        try:
            latest_migration = await self.db[self.migrations_collection].find_one(
                sort=[("version", -1)]
            )
            if not latest_migration or "version" not in latest_migration:
                logger.warning("No valid migration version found, defaulting to version 0")
                return 0
            return latest_migration["version"]

        except Exception as e:
            logger.error(f"Version retrieval error: {str(e)}")
            return 0

    async def _get_pending_migrations(self, current_version: int) -> List[Dict[str, Any]]:
        """Get list of pending migrations."""
        migrations = [
            {
                "version": 1,
                "name": "Initialize Core Collections",
                "function": self._migration_001
            },
            {
                "version": 2,
                "name": "Add Equipment Tracking",
                "function": self._migration_002
            },
            {
                "version": 3,
                "name": "Update User Permissions",
                "function": self._migration_003
            }
        ]

        return [m for m in migrations if m["version"] > current_version]

    async def _execute_migration(self, migration: Dict[str, Any]) -> None:
        """Execute single migration with error handling and rollback support."""
        try:
            logger.info(f"Starting migration {migration['version']}: {migration['name']}")

            # Execute migration function
            await migration["function"]()

            # Record successful migration
            await self.db[self.migrations_collection].insert_one({
                "version": migration["version"],
                "name": migration["name"],
                "executed_at": datetime.utcnow(),
                "status": "completed"
            })

            logger.info(f"Completed migration {migration['version']}")

        except Exception as e:
            logger.error(f"Migration {migration['version']} failed: {str(e)}")
            await self._record_failed_migration(migration, str(e))
            raise MigrationError(f"Migration {migration['version']} failed: {str(e)}")

    async def _migration_001(self) -> None:
        """Initial migration for core collections."""
        try:
            # Initialize collections with schemas
            await self.initialize_database()

            # Add initial indexes
            await self._create_indexes()

        except Exception as e:
            logger.error(f"Migration 001 error: {str(e)}")
            raise MigrationError(f"Migration 001 failed: {str(e)}")

    async def _migration_002(self) -> None:
        """Add equipment tracking capabilities."""
        try:
            # Update centers collection schema
            await self.db.command({
                "collMod": "centers",
                "validator": self.schemas.get_centers_schema(),
                "validationLevel": "strict"
            })

            # Add equipment tracking indexes
            await self.db.centers.create_index("testingEquipment.serialNumber")
            await self.db.centers.create_index("testingEquipment.status")

        except Exception as e:
            logger.error(f"Migration 002 error: {str(e)}")
            raise MigrationError(f"Migration 002 failed: {str(e)}")

    async def _migration_003(self) -> None:
        """Update user permissions structure."""
        try:
            # Update users collection schema
            await self.db.command({
                "collMod": "users",
                "validator": self.schemas.get_users_schema(),
                "validationLevel": "strict"
            })

            # Update existing users with new permission structure
            await self.db.users.update_many(
                {"permissions": {"$exists": False}},
                {"$set": {"permissions": []}}
            )

        except Exception as e:
            logger.error(f"Migration 003 error: {str(e)}")
            raise MigrationError(f"Migration 003 failed: {str(e)}")

    async def _record_failed_migration(self, migration: Dict[str, Any], error: str) -> None:
        """Record failed migration attempt."""
        try:
            await self.db[self.migrations_collection].insert_one({
                "version": migration["version"],
                "name": migration["name"],
                "executed_at": datetime.utcnow(),
                "status": "failed",
                "error": error
            })
        except Exception as e:
            logger.error(f"Failed to record migration failure: {str(e)}")