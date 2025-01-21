# backend/app/services/database.py

from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging
from bson import ObjectId

from ..config import get_settings
from ..models.user import UserInDB, User, UserStatus, Role
from ..core.security import verify_password  # Updated import

# Setup logging
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Initialize database connection
client = AsyncIOMotorClient(settings.mongodb_url)
db = client[settings.database_name]

# Collections
users = db.users
refresh_tokens = db.refresh_tokens
blacklisted_tokens = db.blacklisted_tokens

async def init_db():
    """Initialize database and create indexes."""
    try:
        # Create user indexes
        await users.create_index("email", unique=True)
        await users.create_index("verification_token")
        await users.create_index("reset_token")

        # Create token indexes
        await refresh_tokens.create_index("token", unique=True)
        await refresh_tokens.create_index("user_id")
        await refresh_tokens.create_index("expires_at", expireAfterSeconds=0)

        # Create blacklist indexes
        await blacklisted_tokens.create_index("token", unique=True)
        await blacklisted_tokens.create_index("expires_at", expireAfterSeconds=0)

        # Create document indexes
        await documents.create_index([("user_id", 1)])
        await documents.create_index([("uploaded_at", -1)])

        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise

async def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
    """Authenticate user and update last login."""
    try:
        user = await get_user_by_email(email)
        if not user:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        # Update last login timestamp
        await users.update_one(
            {"_id": user.id},
            {
                "$set": {
                    "last_login": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return user
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return None

async def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Get user by email."""
    try:
        user_dict = await users.find_one({"email": email})
        return UserInDB(**user_dict) if user_dict else None
    except Exception as e:
        logger.error(f"Error getting user by email: {str(e)}")
        return None

async def get_user_by_id(user_id: ObjectId) -> Optional[UserInDB]:
    """Get user by ID."""
    try:
        user_dict = await users.find_one({"_id": user_id})
        return UserInDB(**user_dict) if user_dict else None
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
        return None

async def create_user(user_data: Dict[str, Any]) -> Optional[UserInDB]:
    """Create a new user."""
    try:
        # Add timestamps
        user_data["created_at"] = datetime.utcnow()
        user_data["updated_at"] = datetime.utcnow()
        user_data["status"] = UserStatus.PENDING
        user_data["role"] = Role.USER

        result = await users.insert_one(user_data)
        if result.inserted_id:
            return await get_user_by_id(result.inserted_id)
        return None
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return None

async def update_user(user_id: str, update_data: Dict[str, Any]) -> Optional[UserInDB]:
    """Update user information."""
    try:
        update_data["updated_at"] = datetime.utcnow()
        
        result = await users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        if result.modified_count:
            return await get_user_by_id(ObjectId(user_id))
        return None
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        return None

# Token management functions
async def store_refresh_token(user_id: str, token: str, expires_at: datetime) -> bool:
    """Store refresh token in database."""
    try:
        await refresh_tokens.insert_one({
            "user_id": ObjectId(user_id),
            "token": token,
            "expires_at": expires_at,
            "created_at": datetime.utcnow()
        })
        return True
    except Exception as e:
        logger.error(f"Error storing refresh token: {str(e)}")
        return False

async def validate_refresh_token(token: str) -> Optional[str]:
    """Validate refresh token and return user_id if valid."""
    try:
        token_data = await refresh_tokens.find_one({
            "token": token,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        return str(token_data["user_id"]) if token_data else None
    except Exception as e:
        logger.error(f"Error validating refresh token: {str(e)}")
        return None

async def invalidate_refresh_token(token: str) -> bool:
    """Invalidate a refresh token."""
    try:
        result = await refresh_tokens.delete_one({"token": token})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error invalidating refresh token: {str(e)}")
        return False

async def invalidate_user_refresh_tokens(user_id: str) -> bool:
    """Invalidate all refresh tokens for a user."""
    try:
        result = await refresh_tokens.delete_many({"user_id": ObjectId(user_id)})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error invalidating user refresh tokens: {str(e)}")
        return False

async def cleanup_expired_tokens() -> None:
    """Clean up expired tokens from all token collections."""
    try:
        now = datetime.utcnow()
        
        # Clean up refresh tokens
        await refresh_tokens.delete_many({
            "expires_at": {"$lt": now}
        })
        
        # Clean up blacklisted tokens
        await blacklisted_tokens.delete_many({
            "expires_at": {"$lt": now}
        })
        
        logger.info("Expired tokens cleaned up successfully")
    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {str(e)}")

async def get_user_active_sessions(user_id: str) -> List[Dict[str, Any]]:
    """Get all active sessions for a user."""
    try:
        sessions = await refresh_tokens.find({
            "user_id": ObjectId(user_id),
            "expires_at": {"$gt": datetime.utcnow()}
        }).to_list(None)
        
        return [{
            "token": session["token"],
            "created_at": session["created_at"],
            "expires_at": session["expires_at"]
        } for session in sessions]
    except Exception as e:
        logger.error(f"Error getting user sessions: {str(e)}")
        return []

async def add_to_blacklist(token: str, expires_at: datetime) -> bool:
    """Add a token to the blacklist."""
    try:
        await blacklisted_tokens.insert_one({
            "token": token,
            "expires_at": expires_at,
            "created_at": datetime.utcnow()
        })
        return True
    except Exception as e:
        logger.error(f"Error adding token to blacklist: {str(e)}")
        return False

async def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted."""
    try:
        blacklisted = await blacklisted_tokens.find_one({
            "token": token,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        return bool(blacklisted)
    except Exception as e:
        logger.error(f"Error checking token blacklist: {str(e)}")
        return False

async def get_pending_users() -> List[UserInDB]:
    """Get all users with pending status."""
    try:
        users_list = await users.find({
            "status": UserStatus.PENDING
        }).to_list(None)
        return [UserInDB(**user) for user in users_list]
    except Exception as e:
        logger.error(f"Error getting pending users: {str(e)}")
        return []

async def update_user_status(
    user_id: str,
    status: UserStatus,
    rejection_reason: Optional[str] = None
) -> Optional[UserInDB]:
    """Update user status and optionally add rejection reason."""
    try:
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow()
        }
        
        if rejection_reason and status == UserStatus.REJECTED:
            update_data["rejection_reason"] = rejection_reason

        result = await users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        if result.modified_count:
            return await get_user_by_id(ObjectId(user_id))
        return None
    except Exception as e:
        logger.error(f"Error updating user status: {str(e)}")
        return None

async def verify_user_email(user_id: str) -> Optional[UserInDB]:
    """Update user's email verification status."""
    try:
        result = await users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "is_verified": True,
                    "updated_at": datetime.utcnow(),
                    "verification_token": None
                }
            }
        )
        
        if result.modified_count:
            return await get_user_by_id(ObjectId(user_id))
        return None
    except Exception as e:
        logger.error(f"Error verifying user email: {str(e)}")
        return None

async def store_password_reset_token(
    user_id: str,
    reset_token: str,
    expires_at: datetime
) -> bool:
    """Store password reset token for a user."""
    try:
        result = await users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "reset_token": reset_token,
                    "reset_token_expires": expires_at,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error storing password reset token: {str(e)}")
        return False

async def verify_reset_token(reset_token: str) -> Optional[UserInDB]:
    """Verify password reset token and return user if valid."""
    try:
        user = await users.find_one({
            "reset_token": reset_token,
            "reset_token_expires": {"$gt": datetime.utcnow()}
        })
        return UserInDB(**user) if user else None
    except Exception as e:
        logger.error(f"Error verifying reset token: {str(e)}")
        return None

# Database cleanup and maintenance
async def cleanup_database():
    """Perform regular database cleanup tasks."""
    try:
        await cleanup_expired_tokens()
        # Add any other cleanup tasks here
        logger.info("Database cleanup completed successfully")
    except Exception as e:
        logger.error(f"Database cleanup error: {str(e)}")

async def store_document(user_id: str, document_url: str) -> Optional[str]:
    """Store a document reference in the database."""
    try:
        document = {
            "user_id": ObjectId(user_id),
            "url": document_url,
            "uploaded_at": datetime.utcnow()
        }
        
        result = await documents.insert_one(document)
        
        if result.inserted_id:
            # Update user's documents list
            await users.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$push": {"documents": str(result.inserted_id)},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            return str(result.inserted_id)
        return None
    except Exception as e:
        logger.error(f"Error storing document: {str(e)}")
        return None

async def get_user_documents(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve all documents for a user."""
    try:
        user_docs = await documents.find(
            {"user_id": ObjectId(user_id)}
        ).sort("uploaded_at", -1).to_list(None)
        
        return [
            {
                "id": str(doc["_id"]),
                "url": doc["url"],
                "uploaded_at": doc["uploaded_at"]
            }
            for doc in user_docs
        ]
    except Exception as e:
        logger.error(f"Error retrieving user documents: {str(e)}")
        return []

async def remove_document(user_id: str, document_id: str) -> bool:
    """Remove a document reference from the database."""
    try:
        result = await documents.delete_one({
            "_id": ObjectId(document_id),
            "user_id": ObjectId(user_id)
        })
        
        if result.deleted_count:
            # Remove document reference from user
            await users.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$pull": {"documents": document_id},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Error removing document: {str(e)}")
        return False

# Export all necessary functions
__all__ = [
    'init_db',
    'authenticate_user',
    'get_user_by_email',
    'get_user_by_id',
    'create_user',
    'update_user',
    'store_refresh_token',
    'validate_refresh_token',
    'invalidate_refresh_token',
    'invalidate_user_refresh_tokens',
    'cleanup_expired_tokens',
    'get_user_active_sessions',
    'add_to_blacklist',
    'is_token_blacklisted',
    'get_pending_users',
    'update_user_status',
    'verify_user_email',
    'store_password_reset_token',
    'verify_reset_token',
    'cleanup_database',
    'store_document',           # Added
    'get_user_documents',       # Added
    'remove_document'           # Added
]