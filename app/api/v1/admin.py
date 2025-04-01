# backend/app/api/v1/admin.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from ...core.auth.permissions import RolePermission, require_permission
from ...core.security import get_current_user
from ...services.admin.service import admin_service
from ...services.audit.service import audit_service
from ...services.notification.service import notification_service
from ...models.admin import SystemStats, AuditLog, SystemConfig
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

class MaintenanceRequest(BaseModel):
    start_time: datetime
    duration: int = Field(..., gt=0, description="Duration must be greater than 0")
    description: str = Field(..., max_length=255, description="Description must be under 255 characters")

class NotificationRequest(BaseModel):
    message: str = Field(..., max_length=500, description="Message must be under 500 characters")
    user_roles: Optional[List[str]] = None
    priority: str = Field(default="normal", regex="^(normal|high|low)$")

@router.get("/dashboard", response_model=Dict[str, Any])
async def get_admin_dashboard(
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_ADMIN_DASHBOARD))
) -> Dict[str, Any]:
    """Get comprehensive administrative dashboard data."""
    try:
        stats = await admin_service.get_system_statistics()
        recent_activity = await admin_service.get_recent_activity()
        system_health = await admin_service.get_system_health()

        return {
            "statistics": stats,
            "recent_activity": recent_activity,
            "system_health": system_health,
            "last_updated": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"Dashboard data retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard data"
        )

@router.get("/audit-logs", response_model=List[AuditLog])
async def get_audit_logs(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: Optional[str] = None,
    action_type: Optional[str] = None,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_AUDIT_LOGS))
) -> List[AuditLog]:
    """Retrieve system audit logs with filtering options."""
    try:
        logs = await audit_service.get_audit_logs(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            action_type=action_type
        )
        return logs
    except Exception as e:
        logger.error(f"Audit log retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs"
        )

@router.get("/system/statistics", response_model=SystemStats)
async def get_system_statistics(
    period: Optional[str] = "24h",
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_SYSTEM_STATS))
) -> SystemStats:
    """Get detailed system statistics and metrics."""
    try:
        stats = await admin_service.get_detailed_statistics(period)
        return SystemStats(
            status="success",
            message="Statistics retrieved successfully",
            data=stats
        )
    except Exception as e:
        logger.error(f"Statistics retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system statistics"
        )

@router.post("/system/maintenance", response_model=Dict[str, Any])
async def schedule_maintenance(
    request: MaintenanceRequest,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_SYSTEM))
) -> Dict[str, Any]:
    """Schedule system maintenance window."""
    try:
        maintenance = await admin_service.schedule_maintenance(
            start_time=request.start_time,
            duration=request.duration,
            description=request.description,
            scheduled_by=str(current_user.id)
        )
        await notification_service.notify_system_maintenance(
            start_time=request.start_time,
            duration=request.duration,
            description=request.description
        )
        return {
            "status": "success",
            "message": "Maintenance scheduled successfully",
            "data": maintenance
        }
    except Exception as e:
        logger.error(f"Maintenance scheduling error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule maintenance"
        )

@router.get("/system/config", response_model=SystemConfig)
async def get_system_configuration(
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_SYSTEM))
) -> SystemConfig:
    """Get current system configuration settings."""
    try:
        config = await admin_service.get_system_config()
        return SystemConfig(
            status="success",
            message="Configuration retrieved successfully",
            data=config
        )
    except Exception as e:
        logger.error(f"Configuration retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system configuration"
        )

@router.put("/system/config", response_model=SystemConfig)
async def update_system_configuration(
    updates: Dict[str, Any],
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_SYSTEM))
) -> SystemConfig:
    """Update system configuration settings."""
    try:
        if not admin_service.validate_config_updates(updates):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid configuration updates"
            )
        updated_config = await admin_service.update_system_config(
            updates=updates,
            updated_by=str(current_user.id)
        )
        await audit_service.log_config_change(
            user_id=str(current_user.id),
            changes=updates
        )
        return SystemConfig(
            status="success",
            message="Configuration updated successfully",
            data=updated_config
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Configuration update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update system configuration"
        )

@router.post("/system/backup", response_model=Dict[str, Any])
async def initiate_system_backup(
    backup_type: str = "full",
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_SYSTEM))
) -> Dict[str, Any]:
    """Initiate system backup operation."""
    try:
        backup = await admin_service.initiate_backup(
            backup_type=backup_type,
            initiated_by=str(current_user.id)
        )
        return {
            "status": "success",
            "message": "Backup initiated successfully",
            "data": backup
        }
    except Exception as e:
        logger.error(f"Backup initiation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate system backup"
        )

@router.get("/system/tasks", response_model=List[Dict[str, Any]])
async def get_system_tasks(
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_SYSTEM_TASKS))
) -> List[Dict[str, Any]]:
    """Get system background tasks status."""
    try:
        tasks = await admin_service.get_system_tasks(
            task_type=task_type,
            status=status
        )
        return tasks
    except Exception as e:
        logger.error(f"Task retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system tasks"
        )

@router.post("/notifications/broadcast", response_model=Dict[str, Any])
async def broadcast_system_notification(
    request: NotificationRequest,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_SYSTEM))
) -> Dict[str, Any]:
    """Broadcast system-wide notification."""
    try:
        broadcast = await notification_service.broadcast_notification(
            message=request.message,
            user_roles=request.user_roles,
            priority=request.priority,
            sent_by=str(current_user.id)
        )
        return {
            "status": "success",
            "message": "Notification broadcast successfully",
            "data": broadcast
        }
    except Exception as e:
        logger.error(f"Notification broadcast error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to broadcast notification"
        )