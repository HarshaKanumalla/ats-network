# backend/app/services/audit/service.py

"""
Service for comprehensive audit logging, activity tracking, and compliance monitoring.
Tracks all system changes and user actions for accountability and compliance.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from bson import ObjectId

from ...core.exceptions import AuditError
from ...models.audit import AuditLog
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class AuditService:
    """Service for managing system-wide audit logging and tracking."""
    
    def __init__(self):
        """Initialize audit service."""
        self.db = None
        logger.info("Audit service initialized")

    async def log_activity(
        self,
        user_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Log system activity with detailed tracking."""
        try:
            db = await get_database()
            
            audit_entry = {
                "userId": ObjectId(user_id),
                "action": action,
                "entityType": entity_type,
                "entityId": ObjectId(entity_id),
                "changes": changes or {},
                "metadata": metadata or {},
                "timestamp": datetime.utcnow(),
                "ipAddress": metadata.get("ipAddress") if metadata else None,
                "userAgent": metadata.get("userAgent") if metadata else None
            }
            
            result = await db.auditLogs.insert_one(audit_entry)
            audit_entry["_id"] = result.inserted_id
            
            logger.info(f"Logged activity: {action} on {entity_type} by user {user_id}")
            return audit_entry
            
        except Exception as e:
            logger.error(f"Activity logging error: {str(e)}")
            raise AuditError("Failed to log activity")

    async def track_changes(
        self,
        user_id: str,
        entity_type: str,
        entity_id: str,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Track detailed changes between old and new data states."""
        try:
            # Calculate changes
            changes = {
                "before": old_data,
                "after": new_data,
                "modified_fields": self._get_modified_fields(old_data, new_data)
            }
            
            # Log change activity
            audit_entry = await self.log_activity(
                user_id=user_id,
                action="modify",
                entity_type=entity_type,
                entity_id=entity_id,
                changes=changes
            )
            
            logger.info(f"Tracked changes for {entity_type} {entity_id}")
            return audit_entry
            
        except Exception as e:
            logger.error(f"Change tracking error: {str(e)}")
            raise AuditError("Failed to track changes")

    async def get_audit_trail(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve filtered audit trail based on criteria."""
        try:
            db = await get_database()
            
            # Build query
            query = {}
            if entity_type:
                query["entityType"] = entity_type
            if entity_id:
                query["entityId"] = ObjectId(entity_id)
            if user_id:
                query["userId"] = ObjectId(user_id)
            if action:
                query["action"] = action
            if start_date and end_date:
                query["timestamp"] = {
                    "$gte": start_date,
                    "$lte": end_date
                }
            
            # Get audit logs with user details
            pipeline = [
                {"$match": query},
                {
                    "$lookup": {
                        "from": "users",
                        "localField": "userId",
                        "foreignField": "_id",
                        "as": "user"
                    }
                },
                {
                    "$project": {
                        "action": 1,
                        "entityType": 1,
                        "entityId": 1,
                        "changes": 1,
                        "timestamp": 1,
                        "metadata": 1,
                        "user": {
                            "$arrayElemAt": ["$user", 0]
                        }
                    }
                },
                {"$sort": {"timestamp": -1}}
            ]
            
            audit_trail = await db.auditLogs.aggregate(pipeline).to_list(None)
            
            logger.info("Retrieved audit trail")
            return audit_trail
            
        except Exception as e:
            logger.error(f"Audit trail retrieval error: {str(e)}")
            raise AuditError("Failed to retrieve audit trail")

    def _get_modified_fields(
        self,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate modified fields between old and new data states."""
        modified_fields = {}
        
        for key in set(old_data.keys()) | set(new_data.keys()):
            if key in old_data and key in new_data:
                if old_data[key] != new_data[key]:
                    modified_fields[key] = {
                        "old": old_data[key],
                        "new": new_data[key]
                    }
            elif key in old_data:
                modified_fields[key] = {
                    "old": old_data[key],
                    "new": None
                }
            else:
                modified_fields[key] = {
                    "old": None,
                    "new": new_data[key]
                }
        
        return modified_fields

# Initialize audit service
audit_service = AuditService()