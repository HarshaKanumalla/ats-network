"""Initialization service for application startup and configuration management.

This service handles all aspects of application initialization including database
connection management, index configuration, and initial data seeding.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from datetime import datetime
import logging
from typing import Dict, Any, List

from ..config import get_settings
from ..models.user import UserStatus, Role
from ..core.security import SecurityManager

logger = logging.getLogger(__name__)
settings = get_settings()


class InitializationService:
    def __init__(self):
        """Initialize the service with configuration settings."""
        self.initialization_timestamp = datetime.utcnow()
        self.client = None
        self.db = None
        logger.info("Initialization service created")

    async def initialize_application(self) -> None:
        """Execute the complete application initialization sequence."""
        try:
            logger.info("Beginning application initialization sequence")
            await self._setup_database_connection()
            await self._verify_database_connection()
            await self._initialize_database_structure()
            await self._configure_indexes()
            await self._verify_required_collections()
            await self._seed_initial_data()
            logger.info("Application initialization completed successfully")
        except Exception as e:
            logger.error("Application initialization failed", exc_info=True)
            await self.handle_initialization_failure(e)
            raise

    async def _setup_database_connection(self) -> None:
        """Set up the database connection with proper configuration."""
        try:
            self.client = AsyncIOMotorClient(
                settings.mongodb_url,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=30000,
                serverSelectionTimeoutMS=5000
            )
            self.db = self.client[settings.database_name]
            logger.info("Database connection established")
        except Exception as e:
            logger.error("Failed to set up database connection", exc_info=True)
            raise RuntimeError("Database connection setup failed") from e

    async def _verify_database_connection(self) -> None:
        """Verify database connectivity and configuration."""
        try:
            await self.client.admin.command('ping')
            logger.info("Database connection verified successfully")
        except Exception as e:
            logger.error("Database connection verification failed", exc_info=True)
            raise RuntimeError("Unable to establish database connection") from e

    async def _initialize_database_structure(self) -> None:
        """Initialize the database structure and required collections."""
        try:
            collections = await self.db.list_collection_names()
            required_collections = [
                'users', 'locations', 'documents', 'tokens',
                'refresh_tokens', 'blacklisted_tokens'
            ]
            
            for collection in required_collections:
                if collection not in collections:
                    await self.db.create_collection(collection)
                    logger.info(f"Created collection: {collection}")
            
            logger.info("Database structure initialized successfully")
        except Exception as e:
            logger.error("Database structure initialization failed", exc_info=True)
            raise

    async def _configure_indexes(self) -> None:
        """Configure database indexes for optimal performance."""
        try:
            await self._setup_users_indexes()
            await self._setup_tokens_indexes()
            await self._setup_documents_indexes()
            await self._setup_blacklist_indexes()
            logger.info("Database indexes configured successfully")
        except Exception as e:
            logger.error(f"Index configuration failed: {str(e)}")
            raise

    async def _setup_users_indexes(self) -> None:
        """Set up indexes for the users collection."""
        try:
            # Unique email index
            await self.db.users.create_index(
                [("email", 1)],
                unique=True,
                background=True,
                name="email_unique"
            )

            # Created at index
            await self.db.users.create_index(
                [("created_at", -1)],
                background=True,
                name="created_at_-1"
            )

            # Verification token index
            await self.db.users.create_index(
                [("verification_token", 1)],
                sparse=True,
                background=True,
                name="verification_token_1"
            )

            # Reset token index
            await self.db.users.create_index(
                [("reset_token", 1)],
                sparse=True,
                background=True,
                name="reset_token_1"
            )
        except Exception as e:
            if "already exists" not in str(e):
                raise

    async def _setup_tokens_indexes(self) -> None:
        """Set up indexes for the refresh_tokens collection."""
        try:
            # Expiration index
            await self.db.refresh_tokens.create_index(
                [("expires_at", 1)],
                expireAfterSeconds=0,
                background=True,
                name="expires_at_ttl"
            )

            # User ID index
            await self.db.refresh_tokens.create_index(
                [("user_id", 1)],
                background=True,
                name="user_id_1"
            )

            # Unique token index
            await self.db.refresh_tokens.create_index(
                [("token", 1)],
                unique=True,
                background=True,
                name="token_unique"
            )
        except Exception as e:
            if "already exists" not in str(e):
                raise

    async def _setup_documents_indexes(self) -> None:
        """Set up indexes for the documents collection."""
        try:
            # User ID index
            await self.db.documents.create_index(
                [("user_id", 1)],
                background=True,
                name="user_id_1"
            )

            # Upload date index
            await self.db.documents.create_index(
                [("uploaded_at", -1)],
                background=True,
                name="uploaded_at_-1"
            )
        except Exception as e:
            if "already exists" not in str(e):
                raise

    async def _setup_blacklist_indexes(self) -> None:
        """Set up indexes for the blacklisted_tokens collection."""
        try:
            await self.db.blacklisted_tokens.create_index(
                [("expires_at", 1)],
                expireAfterSeconds=0,
                background=True,
                name="blacklist_expires_ttl"
            )
        except Exception as e:
            if "already exists" not in str(e):
                raise

    async def _verify_required_collections(self) -> None:
        """Verify the existence and structure of required collections."""
        try:
            collections = await self.db.list_collection_names()
            required_collections = [
                'users', 'locations', 'documents', 'tokens',
                'refresh_tokens', 'blacklisted_tokens'
            ]
            
            missing_collections = set(required_collections) - set(collections)
            if missing_collections:
                raise RuntimeError(f"Missing required collections: {missing_collections}")
            
            logger.info("Required collections verified successfully")
        except Exception as e:
            logger.error("Collection verification failed", exc_info=True)
            raise

    async def _seed_initial_data(self) -> None:
        """Seed the database with initial required data."""
        try:
            await self._create_default_admin()
            logger.info("Initial data seeding completed successfully")
        except Exception as e:
            logger.error("Initial data seeding failed", exc_info=True)
            raise

    async def _create_default_admin(self) -> None:
        """Create the default administrative user if it doesn't exist."""
        try:
            admin_exists = await self.db.users.find_one({"email": settings.admin_email})
            
            if not admin_exists:
                password_hash = SecurityManager.get_password_hash(settings.admin_password)
                
                admin_user = {
                    "email": settings.admin_email,
                    "role": Role.ADMIN,
                    "status": UserStatus.APPROVED,
                    "is_active": True,
                    "hashed_password": password_hash,
                    "is_verified": True,
                    "created_at": self.initialization_timestamp,
                    "updated_at": self.initialization_timestamp,
                    "full_name": "Admin User",
                    "ats_address": "Admin Office",
                    "city": "Admin City",
                    "district": "Admin District",
                    "state": "Admin State",
                    "pin_code": "000000",
                    "documents": []
                }
                
                await self.db.users.insert_one(admin_user)
                logger.info("Default administrative user created successfully")
        except Exception as e:
            logger.error("Failed to create default admin user", exc_info=True)
            raise

    async def handle_initialization_failure(self, error: Exception) -> None:
        """Handle initialization failures and perform cleanup."""
        logger.warning("Performing initialization failure cleanup")
        try:
            if self.client:
                self.client.close()
            logger.info("Database connections closed during failure cleanup")
        except Exception as cleanup_error:
            logger.error("Cleanup after initialization failure encountered errors", exc_info=True)


# Initialize the service
initialization_service = InitializationService()