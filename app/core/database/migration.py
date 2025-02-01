from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
import json
import asyncio

from ...core.exceptions import MigrationError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DatabaseMigration:
    """Manages database schema migrations and version control."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize migration system with database connection.
        
        Args:
            db: Database instance for migration operations
        """
        self.db = db
        self.migrations_collection = "migrations"
        
        # Migration settings
        self.batch_size = 1000
        self.timeout = 3600  # 1 hour maximum for migrations
        self.backup_enabled = True
        
        # Version tracking
        self.current_version = None
        self.target_version = None
        
        logger.info("Migration system initialized")

    async def initialize(self) -> None:
        """Initialize migration system and verify setup.
        
        Raises:
            MigrationError: If initialization fails
        """
        try:
            # Create migrations collection if needed
            collections = await self.db.list_collection_names()
            if self.migrations_collection not in collections:
                await self.db.create_collection(self.migrations_collection)
                
                # Create required indexes
                await self.db[self.migrations_collection].create_index(
                    "version",
                    unique=True
                )
                await self.db[self.migrations_collection].create_index(
                    [
                        ("status", 1),
                        ("executedAt", -1)
                    ]
                )
            
            # Get current version
            self.current_version = await self.get_current_version()
            logger.info(f"Current database version: {self.current_version}")
            
        except Exception as e:
            logger.error(f"Migration initialization error: {str(e)}")
            raise MigrationError("Failed to initialize migration system")

    async def get_current_version(self) -> int:
        """Get current database schema version.
        
        Returns:
            Current version number
            
        Raises:
            MigrationError: If version retrieval fails
        """
        try:
            latest_migration = await self.db[self.migrations_collection].find_one(
                sort=[("version", -1)]
            )
            return latest_migration["version"] if latest_migration else 0
        except Exception as e:
            logger.error(f"Version retrieval error: {str(e)}")
            return 0

    async def run_migrations(
        self,
        target_version: Optional[int] = None,
        backup: bool = True
    ) -> None:
        """Execute pending database migrations.
        
        Args:
            target_version: Optional specific version to migrate to
            backup: Whether to create backup before migration
            
        Raises:
            MigrationError: If migration fails
        """
        try:
            self.target_version = target_version
            current_version = await self.get_current_version()
            
            # Get pending migrations
            pending_migrations = await self._get_pending_migrations(
                current_version,
                target_version
            )
            
            if not pending_migrations:
                logger.info("No pending migrations found")
                return
                
            # Create backup if enabled
            if backup and self.backup_enabled:
                await self._create_backup()
            
            # Execute migrations in sequence
            for migration in pending_migrations:
                await self._execute_migration(migration)
            
            logger.info("All migrations completed successfully")
            
        except Exception as e:
            logger.error(f"Migration execution error: {str(e)}")
            raise MigrationError("Failed to execute migrations")

    async def rollback(self, version: int) -> None:
        """Rollback database to specific version.
        
        Args:
            version: Target version to rollback to
            
        Raises:
            MigrationError: If rollback fails
        """
        try:
            current_version = await self.get_current_version()
            if version >= current_version:
                raise MigrationError("Rollback version must be lower than current version")
            
            # Create backup before rollback
            if self.backup_enabled:
                await self._create_backup()
            
            # Get migrations to roll back
            migrations = await self.db[self.migrations_collection].find(
                {"version": {"$gt": version}},
                sort=[("version", -1)]
            ).to_list(None)
            
            # Execute rollbacks in reverse order
            for migration in migrations:
                await self._execute_rollback(migration)
            
            logger.info(f"Successfully rolled back to version {version}")
            
        except Exception as e:
            logger.error(f"Rollback error: {str(e)}")
            raise MigrationError("Failed to rollback database")

    async def _get_pending_migrations(
        self,
        current_version: int,
        target_version: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get list of pending migrations to execute.
        
        Args:
            current_version: Current database version
            target_version: Optional target version
            
        Returns:
            List of pending migrations
        """
        migrations = [
            {
                "version": 1,
                "name": "Initialize User Schema",
                "up": self._migration_001_up,
                "down": self._migration_001_down
            },
            {
                "version": 2,
                "name": "Add Center Equipment Tracking",
                "up": self._migration_002_up,
                "down": self._migration_002_down
            },
            {
                "version": 3,
                "name": "Add Test Session Results Schema",
                "up": self._migration_003_up,
                "down": self._migration_003_down
            },
            {
                "version": 4,
                "name": "Add Vehicle History Tracking",
                "up": self._migration_004_up,
                "down": self._migration_004_down
            }
        ]
        
        # Filter pending migrations
        pending = [
            m for m in migrations
            if m["version"] > current_version and
            (target_version is None or m["version"] <= target_version)
        ]
        
        return sorted(pending, key=lambda x: x["version"])

    async def _execute_migration(self, migration: Dict[str, Any]) -> None:
        """Execute single migration with error handling.
        
        Args:
            migration: Migration to execute
            
        Raises:
            MigrationError: If migration fails
        """
        try:
            logger.info(f"Starting migration {migration['version']}: {migration['name']}")
            start_time = datetime.utcnow()
            
            # Record migration start
            await self._record_migration_start(migration)
            
            # Execute migration
            await migration["up"](self.db)
            
            # Record successful completion
            duration = (datetime.utcnow() - start_time).total_seconds()
            await self._record_migration_complete(migration, duration)
            
            logger.info(f"Completed migration {migration['version']}")
            
        except Exception as e:
            logger.error(f"Migration {migration['version']} failed: {str(e)}")
            
            # Attempt rollback
            try:
                await migration["down"](self.db)
                await self._record_migration_failed(migration, str(e))
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {str(rollback_error)}")
                
            raise MigrationError(f"Migration {migration['version']} failed")

    async def _create_backup(self) -> None:
        """Create database backup before migration.
        
        Raises:
            MigrationError: If backup fails
        """
        try:
            # Implement backup logic here
            # This could involve creating a dump of the database
            # or copying collections to backup collections
            pass
        except Exception as e:
            logger.error(f"Backup creation error: {str(e)}")
            raise MigrationError("Failed to create backup")

    async def _record_migration_start(self, migration: Dict[str, Any]) -> None:
        """Record start of migration execution.
        
        Args:
            migration: Migration being executed
        """
        await self.db[self.migrations_collection].insert_one({
            "version": migration["version"],
            "name": migration["name"],
            "status": "in_progress",
            "startedAt": datetime.utcnow()
        })

    async def _record_migration_complete(
        self,
        migration: Dict[str, Any],
        duration: float
    ) -> None:
        """Record successful migration completion.
        
        Args:
            migration: Completed migration
            duration: Execution duration in seconds
        """
        await self.db[self.migrations_collection].update_one(
            {"version": migration["version"]},
            {
                "$set": {
                    "status": "completed",
                    "completedAt": datetime.utcnow(),
                    "duration": duration
                }
            }
        )

    async def _record_migration_failed(
        self,
        migration: Dict[str, Any],
        error: str
    ) -> None:
        """Record failed migration.
        
        Args:
            migration: Failed migration
            error: Error message
        """
        await self.db[self.migrations_collection].update_one(
            {"version": migration["version"]},
            {
                "$set": {
                    "status": "failed",
                    "error": error,
                    "failedAt": datetime.utcnow()
                }
            }
        )

    # Migration Implementations
    async def _migration_001_up(self, db: AsyncIOMotorDatabase) -> None:
        """Initialize user schema migration."""
        await db.users.update_many(
            {"role": {"$exists": False}},
            {
                "$set": {
                    "role": "ats_testing",
                    "permissions": [],
                    "status": "pending",
                    "isActive": True,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }
            }
        )

    async def _migration_001_down(self, db: AsyncIOMotorDatabase) -> None:
        """Rollback user schema migration."""
        await db.users.update_many(
            {},
            {
                "$unset": {
                    "role": "",
                    "permissions": "",
                    "status": "",
                    "isActive": "",
                    "createdAt": "",
                    "updatedAt": ""
                }
            }
        )

    async def _migration_002_up(self, db: AsyncIOMotorDatabase) -> None:
        """Add center equipment tracking migration."""
        await db.centers.update_many(
            {"testingEquipment": {"$exists": False}},
            {
                "$set": {
                    "testingEquipment": [],
                    "equipmentStatus": {
                        "lastUpdate": datetime.utcnow(),
                        "items": {}
                    }
                }
            }
        )

    async def _migration_002_down(self, db: AsyncIOMotorDatabase) -> None:
        """Rollback center equipment tracking migration."""
        await db.centers.update_many(
            {},
            {
                "$unset": {
                    "testingEquipment": "",
                    "equipmentStatus": ""
                }
            }
        )

    async def _migration_003_up(self, db: AsyncIOMotorDatabase) -> None:
        """Add test session results schema migration."""
        await db.testSessions.update_many(
            {"testResults": {"$exists": False}},
            {
                "$set": {
                    "testResults": {
                        "visualInspection": None,
                        "speedTest": None,
                        "brakeTest": None,
                        "noiseTest": None,
                        "headlightTest": None,
                        "axleTest": None
                    },
                    "resultsSummary": {
                        "status": "pending",
                        "completionPercentage": 0,
                        "lastUpdated": datetime.utcnow()
                    }
                }
            }
        )

    async def _migration_003_down(self, db: AsyncIOMotorDatabase) -> None:
        """Rollback test session results schema migration."""
        await db.testSessions.update_many(
            {},
            {
                "$unset": {
                    "testResults": "",
                    "resultsSummary": ""
                }
            }
        )

    async def _migration_004_up(self, db: AsyncIOMotorDatabase) -> None:
        """Add vehicle history tracking migration."""
        await db.vehicles.update_many(
            {"history": {"$exists": False}},
            {
                "$set": {
                    "history": [],
                    "lastTest": None,
                    "nextTestDue": None,
                    "status": "active",
                    "updatedAt": datetime.utcnow()
                }
            }
        )

    async def _migration_004_down(self, db: AsyncIOMotorDatabase) -> None:
        """Rollback vehicle history tracking migration."""
        await db.vehicles.update_many(
            {},
            {
                "$unset": {
                    "history": "",
                    "lastTest": "",
                    "nextTestDue": "",
                    "status": "",
                    "updatedAt": ""
                }
            }
        )

# Initialize migration system
async def get_migration_manager(db: AsyncIOMotorDatabase) -> DatabaseMigration:
    """Get initialized migration manager instance.
    
    Args:
        db: Database instance
        
    Returns:
        Initialized migration manager
    """
    migration_manager = DatabaseMigration(db)
    await migration_manager.initialize()
    return migration_manager