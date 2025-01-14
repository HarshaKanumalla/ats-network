# backend/app/services/database.py
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging
from fastapi import HTTPException, status
from functools import wraps


from ..config import get_settings
from ..models.user import UserInDB, UserCreate, UserUpdate, User, UserStatus, Role # Added Role import

# Set up logging
logger = logging.getLogger(__name__)

# Configuration
settings = get_settings()
client = AsyncIOMotorClient(settings.mongodb_url)
db = client[settings.database_name]

# System Info
SYSTEM_INFO = {
    "last_updated": "2024-12-19 18:31:19",
    "updated_by": "HarshaKanumalla"
}

async def get_pending_users() -> List[User]:
    """Get all users with pending status."""
    users = await db.users.find({"status": UserStatus.PENDING}).to_list(None)
    return [User(**user) for user in users]

async def update_user_status(user_id: str, status: UserStatus, updated_at: datetime) -> Optional[User]:
    """Update user status and return updated user."""
    result = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "status": status,
                "updated_at": updated_at
            }
        },
        return_document=True
    )
    return User(**result) if result else None
    
# Define the error handling decorator
def handle_db_errors(func):
    """Decorator for consistent database error handling."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Database error in {func.__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database operation failed: {str(e)}"
            )
    return wrapper

@handle_db_errors
async def create_user(user_data: Dict[str, Any]) -> Optional[UserInDB]:
    """Create a new user in the database."""
    try:
        # Create user document with explicit ObjectId conversion
        user_dict = {
            "full_name": user_data.get("full_name"),
            "email": user_data.get("email"),
            "hashed_password": user_data.get("hashed_password"),
            "ats_address": user_data.get("ats_address"),
            "city": user_data.get("city"),
            "district": user_data.get("district"),
            "state": user_data.get("state"),
            "pin_code": user_data.get("pin_code"),
            "status": UserStatus.PENDING,
            "role": Role.USER,
            "is_active": True,
            "is_verified": False,
            "created_at": datetime.utcnow(),
            "documents": []
        }

        # Insert into database
        result = await db.users.insert_one(user_dict)
        
        if result.inserted_id:
            # Retrieve the created document and convert _id to string
            created_user = await db.users.find_one({"_id": result.inserted_id})
            if created_user:
                # Ensure _id is properly converted to string
                created_user["_id"] = str(created_user["_id"])
                return UserInDB(**created_user)
        return None
    except Exception as e:
        logger.error(f"Database error in create_user: {str(e)}")
        raise Exception(f"Database operation failed: {str(e)}")


@handle_db_errors
async def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Get user by email."""
    try:
        user_dict = await db.users.find_one({"email": email})
        if user_dict:
            return UserInDB(**user_dict)
        return None
    except Exception as e:
        logger.error(f"Database error in get_user_by_email: {str(e)}")
        return None

@handle_db_errors
async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
    """Get user by ID."""
    try:
        user_dict = await db.users.find_one({"_id": ObjectId(user_id)})
        if user_dict:
            # Convert ObjectId to string before model creation
            user_dict["_id"] = str(user_dict["_id"])
            return UserInDB(**user_dict)
        return None
    except Exception as e:
        logger.error(f"Database error in get_user_by_id: {str(e)}")
        return None

@handle_db_errors
async def update_user(user_id: str, update_data: Dict[str, Any]) -> Optional[UserInDB]:
    """Update user information."""
    if 'email' in update_data:
        existing_user = await get_user_by_email(update_data['email'])
        if existing_user and str(existing_user.id) != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )

    update_dict = {
        **update_data,
        'updated_at': datetime.utcnow()
    }
    
    result = await db.users.update_one(
        {'_id': ObjectId(user_id)},
        {'$set': update_dict}
    )
    
    if result.modified_count:
        updated_user = await get_user_by_id(user_id)
        logger.info(f"Updated user {user_id}")
        return updated_user
    return None

@handle_db_errors
async def update_user_verification(user_id: str, is_verified: bool) -> bool:
    """Update user verification status."""
    result = await db.users.update_one(
        {'_id': ObjectId(user_id)},
        {
            '$set': {
                'is_verified': is_verified,
                'verification_token': None,
                'updated_at': datetime.utcnow()
            }
        }
    )
    if result.modified_count:
        logger.info(f"Updated verification status for user {user_id} to {is_verified}")
    return result.modified_count > 0

@handle_db_errors
async def update_user_password(user_id: str, hashed_password: str) -> bool:
    """Update a user's password."""
    result = await db.users.update_one(
        {'_id': ObjectId(user_id)},
        {
            '$set': {
                'hashed_password': hashed_password,
                'reset_token': None,
                'reset_token_expires': None,
                'updated_at': datetime.utcnow()
            }
        }
    )
    if result.modified_count:
        logger.info(f"Updated password for user {user_id}")
    return result.modified_count > 0

@handle_db_errors
async def update_user_password_token(user_id: str, reset_token: str) -> bool:
    """Store a password reset token."""
    expires_at = datetime.utcnow() + timedelta(hours=24)
    result = await db.users.update_one(
        {'_id': ObjectId(user_id)},
        {
            '$set': {
                'reset_token': reset_token,
                'reset_token_expires': expires_at,
                'updated_at': datetime.utcnow()
            }
        }
    )
    return result.modified_count > 0

@handle_db_errors
async def get_user_by_reset_token(reset_token: str) -> Optional[UserInDB]:
    """Retrieve user by reset token."""
    user_doc = await db.users.find_one({
        'reset_token': reset_token,
        'reset_token_expires': {'$gt': datetime.utcnow()}
    })
    if user_doc:
        user_doc['id'] = str(user_doc.pop('_id'))
        return UserInDB(**user_doc)
    return None

@handle_db_errors
async def get_user_by_verification_token(token: str) -> Optional[UserInDB]:
    """Retrieve user by verification token."""
    user_doc = await db.users.find_one({'verification_token': token})
    if user_doc:
        user_doc['id'] = str(user_doc.pop('_id'))
        return UserInDB(**user_doc)
    return None

@handle_db_errors
async def store_document(user_id: str, document_url: str) -> bool:
    """Add a document URL to user's documents."""
    result = await db.users.update_one(
        {'_id': ObjectId(user_id)},
        {
            '$push': {'documents': document_url},
            '$set': {'updated_at': datetime.utcnow()}
        }
    )
    if result.modified_count:
        logger.info(f"Added document {document_url} for user {user_id}")
    return result.modified_count > 0

@handle_db_errors
async def get_user_documents(user_id: str) -> List[str]:
    """Retrieve all documents for a user."""
    user = await get_user_by_id(user_id)
    return user.documents if user else []

@handle_db_errors
async def delete_document(user_id: str, document_url: str) -> bool:
    """Remove a document from user's documents."""
    result = await db.users.update_one(
        {'_id': ObjectId(user_id)},
        {
            '$pull': {'documents': document_url},
            '$set': {'updated_at': datetime.utcnow()}
        }
    )
    if result.modified_count:
        logger.info(f"Removed document {document_url} for user {user_id}")
    return result.modified_count > 0

@handle_db_errors
async def update_last_login(user_id: str) -> bool:
    """Update user's last login timestamp."""
    result = await db.users.update_one(
        {'_id': ObjectId(user_id)},
        {'$set': {'last_login': datetime.utcnow()}}
    )
    return result.modified_count > 0

@handle_db_errors
async def get_locations() -> List[Dict]:
    """Get all ATS locations with their stats."""
    try:
        # Get locations from MongoDB
        locations = await db.locations.find().to_list(None)
        
        # Get stats for each location
        response = []
        for location in locations:
            location_stats = await db.stats.find_one({"location_id": location["_id"]})
            
            response.append({
                "name": location["name"],
                "lat": location["lat"],
                "lng": location["lng"],
                "contact": {
                    "name": location["contact_name"],
                    "phone": location["contact_phone"],
                    "email": location["contact_email"]
                },
                "stats": {
                    "totalVehicles": location_stats["total_vehicles"] if location_stats else 0,
                    "atsCenters": location_stats["ats_centers"] if location_stats else 0,
                    "vehiclesUnder8": location_stats["vehicles_under_8"] if location_stats else 0,
                    "vehiclesOver8": location_stats["vehicles_over_8"] if location_stats else 0
                }
            })
        
        return response
    except Exception as e:
        logger.error(f"Database error in get_locations: {str(e)}")
        raise Exception(f"Database operation failed: {str(e)}")

@handle_db_errors
async def get_overall_stats() -> Dict:
    """Get aggregated statistics for all locations."""
    try:
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "totalVehicles": {"$sum": "$total_vehicles"},
                    "atsCenters": {"$sum": "$ats_centers"},
                    "vehiclesUnder8": {"$sum": "$vehicles_under_8"},
                    "vehiclesOver8": {"$sum": "$vehicles_over_8"}
                }
            }
        ]
        
        result = await db.stats.aggregate(pipeline).to_list(None)
        
        if not result:
            return {
                "totalVehicles": 0,
                "atsCenters": 0,
                "vehiclesUnder8": 0,
                "vehiclesOver8": 0
            }
            
        stats = result[0]
        stats.pop("_id", None)
        return stats
    except Exception as e:
        logger.error(f"Database error in get_overall_stats: {str(e)}")
        raise Exception(f"Database operation failed: {str(e)}")

# Add these functions to create initial data
async def create_initial_location(location_data: Dict) -> str:
    """Create a new location."""
    result = await db.locations.insert_one(location_data)
    return str(result.inserted_id)

async def create_initial_stats(stats_data: Dict) -> str:
    """Create initial statistics for a location."""
    result = await db.stats.insert_one(stats_data)
    return str(result.inserted_id)

async def initialize_sample_data():
    """Initialize sample data for locations and stats."""
    try:
        # Check if data already exists
        existing_locations = await db.locations.count_documents({})
        if existing_locations > 0:
            return
            
        # Sample location data
        locations = [
            {
                "name": "Visakhapatnam",
                "lat": 17.6868,
                "lng": 83.2185,
                "contact_name": "Harsha Kanumalla",
                "contact_phone": "+91-9876541230",
                "contact_email": "hkanumalla@utonenergia.com"
            },
            # Add other locations here
        ]
        
        # Create locations and their stats
        for location in locations:
            location_id = await create_initial_location(location)
            await create_initial_stats({
                "location_id": location_id,
                "total_vehicles": 85,
                "ats_centers": 5,
                "vehicles_under_8": 55,
                "vehicles_over_8": 30
            })
            
        logger.info("Sample data initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing sample data: {str(e)}")
        raise

async def create_indexes():
    """Create database indexes if they don't exist."""
    try:
        # Get existing indexes
        existing_indexes = await db.users.list_indexes().to_list(None)
        existing_index_names = [index['name'] for index in existing_indexes]

        # Define required indexes with their specific names
        indexes = [
            {
                'name': 'email_unique',
                'key': [('email', 1)],
                'unique': True,
                'sparse': True
            },
            {
                'name': 'reset_token_index',
                'key': [('reset_token', 1)],
                'sparse': True
            },
            {
                'name': 'verification_token_index',
                'key': [('verification_token', 1)],
                'sparse': True
            }
        ]

        # Create only missing indexes
        for index in indexes:
            if index['name'] not in existing_index_names:
                try:
                    await db.users.create_index(
                        index['key'],
                        unique=index.get('unique', False),
                        sparse=index.get('sparse', False),
                        name=index['name']
                    )
                    logger.info(f"Created index: {index['name']}")
                except Exception as e:
                    logger.warning(f"Error creating index {index['name']}: {str(e)}")
            else:
                logger.info(f"Index {index['name']} already exists")

        logger.info("Database indexes check completed")
    except Exception as e:
        logger.error(f"Error managing database indexes: {str(e)}")
        # Don't raise the exception here, just log it
        # This allows the application to start even if index creation fails

async def init_db():
    """Initialize database connection and verify/create indexes."""
    try:
        # Test database connection
        await client.admin.command('ping')
        logger.info("Database connection established")
        
        # Setup indexes
        await create_indexes()
        
        logger.info(f"Database initialized. System Info: {SYSTEM_INFO}")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise

# Cleanup function for application shutdown
async def close_db_connection():
    """Close database connection."""
    try:
        client.close()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error(f"Error closing database connection: {str(e)}")