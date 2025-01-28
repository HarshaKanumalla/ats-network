"""Database service for managing data persistence and retrieval operations.

This service provides a centralized interface for all database operations,
implementing efficient data access patterns, connection pooling, and proper
error handling for robust data management.
"""

from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
import logging
from bson import ObjectId

from ..config import get_settings
from ..models.user import UserInDB, User, UserStatus, Role
from ..core.security import SecurityManager

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize database connection with connection pooling
client = AsyncIOMotorClient(
    settings.mongodb_url,
    maxPoolSize=50,
    minPoolSize=10,
    maxIdleTimeMS=30000
)

db = client[settings.database_name]

# Collection references
users = db.users
refresh_tokens = db.refresh_tokens
blacklisted_tokens = db.blacklisted_tokens
documents = db.documents

async def initialize_database():
    """Initialize database connections and create necessary indexes."""
    try:
        logger.info("Initializing database connections and indexes")
        
        # Get existing indexes
        existing_indexes = await users.list_indexes().to_list(None)
        existing_index_names = [index["name"] for index in existing_indexes]
        
        # Create user collection indexes if they don't exist
        if "email_unique" not in existing_index_names:
            await users.create_index("email", unique=True, name="email_unique")
        
        if "verification_token_1" not in existing_index_names:
            await users.create_index("verification_token", name="verification_token_1")
        
        if "reset_token_1" not in existing_index_names:
            await users.create_index("reset_token", name="reset_token_1")
        
        if "created_at_-1" not in existing_index_names:
            await users.create_index([("created_at", -1)], name="created_at_-1")
        
        # Create token collection indexes
        await refresh_tokens.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
            name="expires_at_ttl"
        )
        await refresh_tokens.create_index("user_id", name="user_id_1")
        await refresh_tokens.create_index("token", unique=True, name="token_unique")
        
        # Create blacklist indexes
        await blacklisted_tokens.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
            name="blacklist_expires_at_ttl"
        )
        
        # Create document indexes
        await documents.create_index([("user_id", 1)], name="user_id_1")
        await documents.create_index([("uploaded_at", -1)], name="uploaded_at_-1")
        
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error("Database initialization failed", exc_info=True)
        raise

async def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Retrieve a user by their email address.

    This function performs a case-insensitive search for a user by email,
    implementing proper error handling and logging for debugging purposes.

    Args:
        email: The email address to search for

    Returns:
        UserInDB object if found, None otherwise
    """
    try:
        user_dict = await users.find_one(
            {"email": {"$regex": f"^{email}$", "$options": "i"}}
        )
        return UserInDB(**user_dict) if user_dict else None
    except Exception as e:
        logger.error(f"Error retrieving user by email: {email}", exc_info=True)
        return None

async def get_user_by_id(user_id: ObjectId) -> Optional[UserInDB]:
    """Retrieve a user by their unique identifier.

    This function fetches a user record by ID, implementing proper error
    handling and type conversion for MongoDB ObjectIds.

    Args:
        user_id: The unique identifier of the user

    Returns:
        UserInDB object if found, None otherwise
    """
    try:
        user_dict = await users.find_one({"_id": user_id})
        return UserInDB(**user_dict) if user_dict else None
    except Exception as e:
        logger.error(f"Error retrieving user by ID: {user_id}", exc_info=True)
        return None

async def create_user(user_data: Dict[str, Any]) -> Optional[UserInDB]:
    """Create a new user in the database.

    This function handles new user creation, including proper data validation,
    timestamp management, and default value assignment.

    Args:
        user_data: Dictionary containing user information

    Returns:
        UserInDB object of the created user if successful, None otherwise
    """
    try:
        current_time = datetime.utcnow()
        user_data.update({
            "created_at": current_time,
            "updated_at": current_time,
            "status": UserStatus.PENDING,
            "role": Role.USER,
            "is_active": True,
            "is_verified": False
        })
        
        result = await users.insert_one(user_data)
        if result.inserted_id:
            return await get_user_by_id(result.inserted_id)
        return None
        
    except Exception as e:
        logger.error("Error creating new user", exc_info=True)
        return None

async def update_user(
    user_id: str,
    update_data: Dict[str, Any]
) -> Optional[UserInDB]:
    """Update user information in the database.

    This function handles user data updates, implementing proper validation
    and maintaining update timestamps.

    Args:
        user_id: The unique identifier of the user to update
        update_data: Dictionary containing fields to update

    Returns:
        Updated UserInDB object if successful, None otherwise
    """
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
        logger.error(f"Error updating user: {user_id}", exc_info=True)
        return None

async def store_refresh_token(
    user_id: str,
    token: str,
    expires_at: datetime
) -> bool:
    """Store a refresh token in the database.

    This function manages refresh token storage, implementing proper expiration
    handling and token cleanup.

    Args:
        user_id: The ID of the user associated with the token
        token: The refresh token to store
        expires_at: Token expiration timestamp

    Returns:
        Boolean indicating success of the operation
    """
    try:
        await refresh_tokens.insert_one({
            "user_id": ObjectId(user_id),
            "token": token,
            "expires_at": expires_at,
            "created_at": datetime.utcnow()
        })
        return True
    except Exception as e:
        logger.error("Error storing refresh token", exc_info=True)
        return False

async def validate_refresh_token(refresh_token: str) -> Optional[str]:
    """Validate a refresh token and return the associated user ID.

    Args:
        refresh_token: The refresh token to validate

    Returns:
        The user ID if token is valid, None otherwise
    """
    try:
        token_data = await refresh_tokens.find_one({
            "token": refresh_token,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        if token_data:
            return str(token_data["user_id"])
        return None
        
    except Exception as e:
        logger.error(f"Error validating refresh token: {str(e)}")
        return None

async def update_user_status(user_id: str, status: UserStatus) -> Optional[User]:
    """Update a user's status in the database.
    
    Args:
        user_id: The unique identifier of the user
        status: The new status to set for the user
        
    Returns:
        Updated User object if successful, None otherwise
    """
    try:
        logger.info(f"Updating status to {status} for user: {user_id}")
        
        result = await users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count:
            updated_user = await get_user_by_id(ObjectId(user_id))
            logger.info(f"Successfully updated status for user: {user_id}")
            return updated_user
            
        logger.warning(f"No user found to update status: {user_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error updating user status: {str(e)}", exc_info=True)
        return None

async def get_pending_users() -> List[User]:
    """Retrieve all users with pending registration status.
    
    Returns:
        List of User objects with pending status
    """
    try:
        logger.info("Retrieving pending user registrations")
        
        cursor = users.find({"status": UserStatus.PENDING})
        pending_users = []
        
        async for user_doc in cursor:
            pending_users.append(User(**user_doc))
        
        logger.info(f"Found {len(pending_users)} pending users")
        return pending_users
        
    except Exception as e:
        logger.error("Error retrieving pending users", exc_info=True)
        return []

async def get_user_statistics() -> Dict[str, int]:
    """Get statistics about user registrations and statuses.
    
    Returns:
        Dictionary containing user statistics
    """
    try:
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_users": {"$sum": 1},
                    "pending_users": {
                        "$sum": {"$cond": [{"$eq": ["$status", UserStatus.PENDING]}, 1, 0]}
                    },
                    "approved_users": {
                        "$sum": {"$cond": [{"$eq": ["$status", UserStatus.APPROVED]}, 1, 0]}
                    },
                    "rejected_users": {
                        "$sum": {"$cond": [{"$eq": ["$status", UserStatus.REJECTED]}, 1, 0]}
                    }
                }
            }
        ]
        
        result = await users.aggregate(pipeline).to_list(length=1)
        
        if result:
            stats = result[0]
            del stats["_id"]
            return stats
        
        return {
            "total_users": 0,
            "pending_users": 0,
            "approved_users": 0,
            "rejected_users": 0
        }
        
    except Exception as e:
        logger.error(f"Error retrieving user statistics: {str(e)}", exc_info=True)
        return {
            "total_users": 0,
            "pending_users": 0,
            "approved_users": 0,
            "rejected_users": 0
        }

async def get_user_documents(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve all documents associated with a user.

    This function fetches all document records associated with the specified user,
    including metadata and access information.

    Args:
        user_id: The unique identifier of the user

    Returns:
        A list of document records with metadata
    """
    try:
        logger.info(f"Retrieving documents for user: {user_id}")
        
        cursor = documents.find({"user_id": ObjectId(user_id)})
        user_docs = []
        
        async for doc in cursor:
            user_docs.append({
                "id": str(doc["_id"]),
                "filename": doc["filename"],
                "upload_date": doc["uploaded_at"].isoformat(),
                "file_type": doc.get("file_type", "unknown"),
                "file_size": doc.get("file_size", 0),
                "status": doc.get("status", "active")
            })
        
        logger.info(f"Found {len(user_docs)} documents for user {user_id}")
        return user_docs
        
    except Exception as e:
        logger.error(f"Error retrieving user documents: {str(e)}", exc_info=True)
        return []


async def store_document(
    user_id: str,
    file_url: str,
    file_metadata: Dict[str, Any] = None
) -> Optional[str]:
    """Store document metadata in the database.

    This function creates a new document record in the database, associating
    it with the specified user and storing relevant metadata.

    Args:
        user_id: The unique identifier of the user
        file_url: The URL where the document is stored
        file_metadata: Optional dictionary containing additional metadata

    Returns:
        The document ID if successful, None otherwise
    """
    try:
        logger.info(f"Storing document metadata for user: {user_id}")
        
        document_data = {
            "user_id": ObjectId(user_id),
            "file_url": file_url,
            "uploaded_at": datetime.utcnow(),
            "status": "active",
            "filename": file_url.split("/")[-1]
        }

        if file_metadata:
            document_data.update(file_metadata)
        
        result = await documents.insert_one(document_data)
        
        if result.inserted_id:
            logger.info(f"Document metadata stored successfully: {result.inserted_id}")
            
            # Update user's documents list
            await users.update_one(
                {"_id": ObjectId(user_id)},
                {"$push": {"documents": str(result.inserted_id)}}
            )
            
            return str(result.inserted_id)
            
        logger.warning("Failed to store document metadata")
        return None
        
    except Exception as e:
        logger.error(f"Error storing document metadata: {str(e)}", exc_info=True)
        return None

async def get_document_by_id(document_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a specific document by its ID.

    This function fetches detailed information about a specific document,
    including its metadata and access information.

    Args:
        document_id: The unique identifier of the document

    Returns:
        Document information dictionary if found, None otherwise
    """
    try:
        logger.info(f"Retrieving document: {document_id}")
        
        doc = await documents.find_one({"_id": ObjectId(document_id)})
        
        if doc:
            return {
                "id": str(doc["_id"]),
                "user_id": str(doc["user_id"]),
                "filename": doc["filename"],
                "file_url": doc["file_url"],
                "upload_date": doc["uploaded_at"].isoformat(),
                "status": doc.get("status", "active"),
                "file_type": doc.get("file_type", "unknown"),
                "file_size": doc.get("file_size", 0),
                "metadata": {
                    key: value for key, value in doc.items()
                    if key not in ["_id", "user_id", "filename", "file_url", "uploaded_at", "status", "file_type", "file_size"]
                }
            }
            
        logger.warning(f"Document not found: {document_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error retrieving document: {str(e)}", exc_info=True)
        return None

async def update_document_status(document_id: str, status: str) -> bool:
    """Update the status of a document.

    This function modifies the status of a document record, useful for
    managing document lifecycle states.

    Args:
        document_id: The unique identifier of the document
        status: The new status to set

    Returns:
        Boolean indicating success of the operation
    """
    try:
        logger.info(f"Updating status to {status} for document: {document_id}")
        
        result = await documents.update_one(
            {"_id": ObjectId(document_id)},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        success = result.modified_count > 0
        if success:
            logger.info(f"Document status updated successfully: {document_id}")
        else:
            logger.warning(f"Document not found for status update: {document_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error updating document status: {str(e)}", exc_info=True)
        return False

async def delete_document(document_id: str, user_id: str) -> bool:
    """Delete a document and remove it from the user's document list.

    This function handles the complete removal of a document record,
    including updating the user's document list.

    Args:
        document_id: The unique identifier of the document to delete
        user_id: The ID of the user who owns the document

    Returns:
        Boolean indicating success of the deletion
    """
    try:
        logger.info(f"Deleting document {document_id} for user {user_id}")
        
        # First remove document from user's documents list
        await users.update_one(
            {"_id": ObjectId(user_id)},
            {"$pull": {"documents": document_id}}
        )
        
        # Then delete the document record
        result = await documents.delete_one({
            "_id": ObjectId(document_id),
            "user_id": ObjectId(user_id)
        })
        
        if result.deleted_count:
            logger.info(f"Document {document_id} successfully deleted")
            return True
            
        logger.warning(f"Document {document_id} not found or not deleted")
        return False
        
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}", exc_info=True)
        return False

async def update_document_metadata(
    document_id: str,
    metadata: Dict[str, Any]
) -> bool:
    """Update the metadata of a document.

    This function allows updating various metadata fields of a document
    while maintaining the document's core attributes.

    Args:
        document_id: The unique identifier of the document
        metadata: Dictionary containing metadata fields to update

    Returns:
        Boolean indicating success of the update
    """
    try:
        logger.info(f"Updating metadata for document: {document_id}")
        
        # Ensure we're not updating protected fields
        protected_fields = ["_id", "user_id", "file_url", "uploaded_at"]
        update_data = {
            key: value for key, value in metadata.items()
            if key not in protected_fields
        }
        
        if not update_data:
            logger.warning("No valid metadata fields to update")
            return False
        
        update_data["updated_at"] = datetime.utcnow()
        
        result = await documents.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": update_data}
        )
        
        success = result.modified_count > 0
        if success:
            logger.info(f"Document metadata updated successfully: {document_id}")
        else:
            logger.warning(f"Document not found for metadata update: {document_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error updating document metadata: {str(e)}", exc_info=True)
        return False

async def get_location_statistics() -> List[Dict[str, Any]]:
    """Retrieve statistics for all ATS locations.

    This function aggregates operational data for each location, including
    vehicle counts, testing volumes, and performance metrics. It provides
    comprehensive statistical information for monitoring network performance.

    Returns:
        A list of dictionaries containing location statistics
    """
    try:
        logger.info("Retrieving location statistics")
        
        pipeline = [
            {
                "$lookup": {
                    "from": "vehicles",
                    "localField": "_id",
                    "foreignField": "location_id",
                    "as": "vehicles"
                }
            },
            {
                "$project": {
                    "name": 1,
                    "lat": 1,
                    "lng": 1,
                    "contact_name": 1,
                    "contact_phone": 1,
                    "contact_email": 1,
                    "total_vehicles": {"$size": "$vehicles"},
                    "vehicles_under_8": {
                        "$size": {
                            "$filter": {
                                "input": "$vehicles",
                                "as": "vehicle",
                                "cond": {"$lt": ["$$vehicle.age", 8]}
                            }
                        }
                    },
                    "vehicles_over_8": {
                        "$size": {
                            "$filter": {
                                "input": "$vehicles",
                                "as": "vehicle",
                                "cond": {"$gte": ["$$vehicle.age", 8]}
                            }
                        }
                    }
                }
            }
        ]

        locations = await db.locations.aggregate(pipeline).to_list(None)
        logger.info(f"Retrieved statistics for {len(locations)} locations")
        return locations

    except Exception as e:
        logger.error("Error retrieving location statistics", exc_info=True)
        return []

async def get_overall_statistics() -> Dict[str, Any]:
    """Retrieve network-wide statistics.

    This function calculates aggregate statistics across all locations,
    providing a comprehensive overview of the entire ATS network's
    performance and operational metrics.

    Returns:
        Dictionary containing network-wide statistics
    """
    try:
        logger.info("Calculating overall network statistics")

        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_vehicles": {"$sum": "$total_vehicles"},
                    "active_centers": {"$sum": {"$cond": [{"$eq": ["$is_active", True]}, 1, 0]}},
                    "recent_tests": {
                        "$sum": {
                            "$size": {
                                "$filter": {
                                    "input": "$tests",
                                    "as": "test",
                                    "cond": {
                                        "$gte": ["$$test.test_date", 
                                                {"$dateSubtract": {
                                                    "startDate": "$$NOW",
                                                    "unit": "day",
                                                    "amount": 7
                                                }}]
                                    }
                                }
                            }
                        }
                    },
                    "pending_approvals": {"$sum": "$pending_count"}
                }
            }
        ]

        result = await db.locations.aggregate(pipeline).to_list(1)
        
        stats = result[0] if result else {
            "total_vehicles": 0,
            "active_centers": 0,
            "recent_tests": 0,
            "pending_approvals": 0
        }
        
        stats["last_updated"] = datetime.utcnow().isoformat()
        
        logger.info("Overall statistics calculated successfully")
        return stats

    except Exception as e:
        logger.error("Error calculating overall statistics", exc_info=True)
        return {
            "total_vehicles": 0,
            "active_centers": 0,
            "recent_tests": 0,
            "pending_approvals": 0,
            "last_updated": datetime.utcnow().isoformat()
        }

async def update_location_stats(location_id: str) -> Dict[str, Any]:
    """Update statistics for a specific location.

    This function recalculates and updates the statistical metrics for a given
    location, ensuring that dashboard data reflects current operational status.

    Args:
        location_id: The unique identifier of the location

    Returns:
        Updated statistics dictionary for the location
    """
    try:
        logger.info(f"Updating statistics for location: {location_id}")

        pipeline = [
            {"$match": {"_id": ObjectId(location_id)}},
            {
                "$lookup": {
                    "from": "vehicles",
                    "localField": "_id",
                    "foreignField": "location_id",
                    "as": "vehicles"
                }
            },
            {
                "$project": {
                    "total_vehicles": {"$size": "$vehicles"},
                    "vehicles_under_8": {
                        "$size": {
                            "$filter": {
                                "input": "$vehicles",
                                "as": "vehicle",
                                "cond": {"$lt": ["$$vehicle.age", 8]}
                            }
                        }
                    },
                    "vehicles_over_8": {
                        "$size": {
                            "$filter": {
                                "input": "$vehicles",
                                "as": "vehicle",
                                "cond": {"$gte": ["$$vehicle.age", 8]}
                            }
                        }
                    }
                }
            }
        ]

        result = await db.locations.aggregate(pipeline).to_list(1)
        
        if not result:
            logger.warning(f"Location not found: {location_id}")
            return {
                "total_vehicles": 0,
                "vehicles_under_8": 0,
                "vehicles_over_8": 0
            }

        stats = result[0]
        logger.info(f"Statistics updated for location: {location_id}")
        return stats

    except Exception as e:
        logger.error(f"Error updating location statistics: {str(e)}", exc_info=True)
        return {
            "total_vehicles": 0,
            "vehicles_under_8": 0,
            "vehicles_over_8": 0
        }

async def get_location_data(location_id: Optional[str] = None) -> Union[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Retrieve location data from the database.

    This function fetches location information, either for a specific location
    or all locations if no ID is provided. It includes basic location details
    and associated contact information.

    Args:
        location_id: Optional unique identifier of a specific location

    Returns:
        If location_id is provided: Dictionary containing location details if found, None otherwise
        If location_id is not provided: List of dictionaries containing all locations' details
    """
    try:
        if location_id:
            logger.info(f"Retrieving data for location: {location_id}")
            location = await db.locations.find_one({"_id": ObjectId(location_id)})
            if location:
                return location
            logger.warning(f"Location not found: {location_id}")
            return None

        logger.info("Retrieving data for all locations")
        cursor = db.locations.find({})
        locations = await cursor.to_list(None)
        logger.info(f"Retrieved {len(locations)} locations")
        return locations

    except Exception as e:
        logger.error(f"Error retrieving location data: {str(e)}", exc_info=True)
        return [] if location_id is None else None