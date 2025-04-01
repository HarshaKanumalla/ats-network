# backend/app/api/v1/monitoring.py

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta
import asyncio
import psutil

from ...core.auth.permissions import RolePermission, require_permission
from ...core.security import get_current_user, verify_websocket_token
from ...services.monitoring.service import monitoring_service
from ...services.notification.service import notification_service
from ...services.health.service import health_service
from ...models.monitoring import (
    SystemHealth,
    PerformanceMetrics,
    AlertConfig,
    MonitoringResponse
)
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

@router.get("/health", response_model=SystemHealth)
async def check_system_health(
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_SYSTEM_HEALTH))
) -> SystemHealth:
    """Check overall system health status."""
    try:
        health_status = await health_service.check_system_health()

        metrics = {
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "network_stats": psutil.net_io_counters()._asdict()
        }

        database_status = await health_service.check_database_health()
        cache_status = await health_service.check_cache_health()
        storage_status = await health_service.check_storage_health()

        logger.info(f"System health check completed successfully at {datetime.utcnow()}")

        return SystemHealth(
            status="success",
            message="Health check completed successfully",
            data={
                "status": "healthy" if all([
                    database_status["healthy"],
                    cache_status["healthy"],
                    storage_status["healthy"]
                ]) else "degraded",
                "timestamp": datetime.utcnow(),
                "metrics": metrics,
                "components": {
                    "database": database_status,
                    "cache": cache_status,
                    "storage": storage_status
                }
            }
        )

    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform health check"
        )

@router.websocket("/ws/metrics")
async def metrics_websocket(
    websocket: WebSocket,
    token: str
):
    """WebSocket endpoint for real-time performance metrics."""
    try:
        # Verify token and permissions
        current_user = await verify_websocket_token(token)
        if not current_user:
            logger.warning("WebSocket connection rejected: Invalid token")
            await websocket.close(code=4001)
            return

        # Accept connection
        await websocket.accept()
        logger.info(f"WebSocket connection established for user {current_user.id}")

        try:
            while True:
                # Collect real-time metrics
                metrics = await monitoring_service.collect_performance_metrics()

                # Send metrics to client
                await websocket.send_json({
                    "type": "metrics",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": metrics
                })

                # Wait before next update
                await asyncio.sleep(settings.metrics_interval)

        except Exception as e:
            logger.error(f"Metrics streaming error: {str(e)}")
            await websocket.send_json({
                "type": "error",
                "message": "Failed to stream metrics"
            })

    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
        await websocket.close(code=4000)

@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics(
    time_range: str = "1h",
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_PERFORMANCE_METRICS))
) -> PerformanceMetrics:
    """Get system performance metrics over time."""
    try:
        metrics = await monitoring_service.get_performance_metrics(time_range)

        logger.info(f"Performance metrics retrieved successfully for time range {time_range}")
        return PerformanceMetrics(
            status="success",
            message="Performance metrics retrieved successfully",
            data=metrics
        )

    except Exception as e:
        logger.error(f"Performance metrics error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance metrics"
        )

@router.post("/alerts/config", response_model=AlertConfig)
async def configure_alerts(
    config: AlertConfig,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_ALERTS))
) -> AlertConfig:
    """Configure system monitoring alerts."""
    try:
        updated_config = await monitoring_service.update_alert_config(
            config=config,
            updated_by=str(current_user.id)
        )

        logger.info(f"Alert configuration updated successfully by user {current_user.id}")
        return AlertConfig(
            status="success",
            message="Alert configuration updated successfully",
            data=updated_config
        )

    except Exception as e:
        logger.error(f"Alert configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update alert configuration"
        )

@router.get("/centers/{center_id}", response_model=MonitoringResponse)
async def monitor_center(
    center_id: str,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MONITOR_CENTERS))
) -> MonitoringResponse:
    """Monitor specific ATS center status and operations."""
    try:
        monitoring_data = await monitoring_service.monitor_center(
            center_id=center_id,
            user_role=current_user.role
        )

        logger.info(f"Monitoring data retrieved for center {center_id}")
        return MonitoringResponse(
            status="success",
            message="Center monitoring data retrieved successfully",
            data=monitoring_data
        )

    except Exception as e:
        logger.error(f"Center monitoring error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to monitor center"
        )

@router.get("/tests/active", response_model=MonitoringResponse)
async def monitor_active_tests(
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MONITOR_TESTS))
) -> MonitoringResponse:
    """Monitor currently active test sessions."""
    try:
        active_tests = await monitoring_service.monitor_active_tests(
            user_role=current_user.role,
            center_id=current_user.center_id
        )

        logger.info(f"Active test monitoring data retrieved successfully for user {current_user.id}")
        return MonitoringResponse(
            status="success",
            message="Active test monitoring data retrieved successfully",
            data=active_tests
        )

    except Exception as e:
        logger.error(f"Active test monitoring error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to monitor active tests"
        )

@router.get("/equipment/{center_id}", response_model=MonitoringResponse)
async def monitor_equipment(
    center_id: str,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MONITOR_EQUIPMENT))
) -> MonitoringResponse:
    """Monitor testing equipment status and calibration."""
    try:
        equipment_status = await monitoring_service.monitor_equipment(
            center_id=center_id,
            user_role=current_user.role
        )

        logger.info(f"Equipment monitoring data retrieved successfully for center {center_id}")
        return MonitoringResponse(
            status="success",
            message="Equipment monitoring data retrieved successfully",
            data=equipment_status
        )

    except Exception as e:
        logger.error(f"Equipment monitoring error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to monitor equipment"
        )

@router.get("/audit-logs", response_model=MonitoringResponse)
async def get_monitoring_audit_logs(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    log_type: Optional[str] = None,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_AUDIT_LOGS))
) -> MonitoringResponse:
    """Get system monitoring audit logs."""
    try:
        logs = await monitoring_service.get_audit_logs(
            start_date=start_date,
            end_date=end_date,
            log_type=log_type,
            user_role=current_user.role
        )

        logger.info(f"Audit logs retrieved successfully for user {current_user.id}")
        return MonitoringResponse(
            status="success",
            message="Audit logs retrieved successfully",
            data=logs
        )

    except Exception as e:
        logger.error(f"Audit log retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs"
        )