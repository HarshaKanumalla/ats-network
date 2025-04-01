"""
Service for comprehensive audit logging, activity tracking, and compliance monitoring.
Tracks all system changes and user actions for accountability and compliance.
"""

from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
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
    
    VALID_ACTIONS = {"create", "modify", "delete", "view", "approve", "reject"}
    VALID_ENTITIES = {"user", "center", "vehicle", "test", "document"}
    
    def __init__(self):
        """Initialize audit service."""
        self.db = None
        logger.info("Audit service initialized")

    def _validate_audit_entry(
        self,
        action: str,
        entity_type: str,
        changes: Optional[Dict[str, Any]] = None
    ) -> None:
        """Validate audit entry data."""
        if action not in self.VALID_ACTIONS:
            raise AuditError(f"Invalid action. Must be one of: {self.VALID_ACTIONS}")
            
        if entity_type not in self.VALID_ENTITIES:
            raise AuditError(f"Invalid entity type. Must be one of: {self.VALID_ENTITIES}")
            
        if changes and not isinstance(changes, dict):
            raise AuditError("Changes must be a dictionary")

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
            self._validate_audit_entry(action, entity_type, changes)
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
            changes = {
                "before": old_data,
                "after": new_data,
                "modified_fields": self._get_modified_fields(old_data, new_data)
            }
            
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
                        "user": {"$arrayElemAt": ["$user", 0]}
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

    async def check_compliance_status(
        self,
        entity_type: str,
        entity_id: str
    ) -> Dict[str, Any]:
        """Check compliance status for an entity."""
        try:
            db = await get_database()
            
            logs = await db.auditLogs.find({
                "entityType": entity_type,
                "entityId": ObjectId(entity_id),
                "timestamp": {
                    "$gte": datetime.utcnow() - timedelta(days=90)
                }
            }).to_list(None)
            
            required_actions = settings.COMPLIANCE_REQUIREMENTS.get(entity_type, [])
            completed_actions = {log["action"] for log in logs}
            
            missing_actions = set(required_actions) - completed_actions
            
            return {
                "is_compliant": len(missing_actions) == 0,
                "missing_actions": list(missing_actions),
                "last_audit": logs[0]["timestamp"] if logs else None,
                "audit_count": len(logs)
            }
            
        except Exception as e:
            logger.error(f"Compliance check error: {str(e)}")
            raise AuditError("Failed to check compliance status")

    async def generate_audit_summary(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Generate summary of audit activities."""
        try:
            db = await get_database()
            
            pipeline = [
                {
                    "$match": {
                        "timestamp": {
                            "$gte": start_date,
                            "$lte": end_date
                        }
                    }
                },
                {
                    "$group": {
                        "_id": {
                            "action": "$action",
                            "entityType": "$entityType"
                        },
                        "count": {"$sum": 1},
                        "users": {"$addToSet": "$userId"}
                    }
                }
            ]
            
            results = await db.auditLogs.aggregate(pipeline).to_list(None)
            
            return {
                "period": {
                    "start": start_date,
                    "end": end_date
                },
                "total_actions": sum(r["count"] for r in results),
                "action_summary": [
                    {
                        "action": r["_id"]["action"],
                        "entity_type": r["_id"]["entityType"],
                        "count": r["count"],
                        "unique_users": len(r["users"])
                    }
                    for r in results
                ]
            }
            
        except Exception as e:
            logger.error(f"Audit summary generation error: {str(e)}")
            raise AuditError("Failed to generate audit summary")

    async def manage_audit_retention(
        self,
        retention_days: int = 365
    ) -> Dict[str, Any]:
        """Manage audit log retention."""
        try:
            db = await get_database()
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            pipeline = [
                {
                    "$match": {
                        "timestamp": {"$lt": cutoff_date}
                    }
                },
                {
                    "$out": "auditLogsArchive"
                }
            ]
            await db.auditLogs.aggregate(pipeline).to_list(None)
            
            result = await db.auditLogs.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            return {
                "archived_count": result.deleted_count,
                "retention_date": cutoff_date,
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Audit retention management error: {str(e)}")
            raise AuditError("Failed to manage audit retention")

    async def analyze_activity_patterns(
        self,
        timeframe_hours: int = 24
    ) -> Dict[str, Any]:
        """Analyze activity patterns for anomaly detection."""
        try:
            db = await get_database()
            start_time = datetime.utcnow() - timedelta(hours=timeframe_hours)
            
            pipeline = [
                {
                    "$match": {
                        "timestamp": {"$gte": start_time}
                    }
                },
                {
                    "$group": {
                        "_id": {
                            "user": "$userId",
                            "hour": {"$hour": "$timestamp"}
                        },
                        "action_count": {"$sum": 1},
                        "actions": {"$addToSet": "$action"}
                    }
                }
            ]
            
            results = await db.auditLogs.aggregate(pipeline).to_list(None)
            
            patterns = []
            for r in results:
                if r["action_count"] > settings.ACTIVITY_THRESHOLD:
                    patterns.append({
                        "user_id": r["_id"]["user"],
                        "hour": r["_id"]["hour"],
                        "action_count": r["action_count"],
                        "unique_actions": len(r["actions"]),
                        "severity": "high" if r["action_count"] > settings.ACTIVITY_THRESHOLD * 2 else "medium"
                    })
            
            return {
                "timeframe_hours": timeframe_hours,
                "total_patterns": len(patterns),
                "suspicious_patterns": patterns
            }
            
        except Exception as e:
            logger.error(f"Activity pattern analysis error: {str(e)}")
            raise AuditError("Failed to analyze activity patterns")

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