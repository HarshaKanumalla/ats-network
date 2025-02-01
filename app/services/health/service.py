# backend/app/services/health/service.py

"""
Service for monitoring system health, performance metrics, and service availability.
Provides system diagnostics and health checks for all components.
"""

from typing import Dict, Any, List
from datetime import datetime
import logging
import psutil
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from ...core.exceptions import HealthCheckError
from ...database import get_database
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class HealthMonitoringService:
    """Service for monitoring system health and performance."""
    
    def __init__(self):
        """Initialize health monitoring service."""
        self.db = None
        self.services = {
            "database": self._check_database_health,
            "s3": self._check_s3_health,
            "email": self._check_email_health,
            "websocket": self._check_websocket_health
        }
        logger.info("Health monitoring service initialized")

    async def check_system_health(self) -> Dict[str, Any]:
        """Perform comprehensive system health check."""
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow(),
                "components": {},
                "system_metrics": await self._get_system_metrics()
            }
            
            # Check all services
            for service, check_func in self.services.items():
                try:
                    status = await check_func()
                    health_status["components"][service] = status
                    
                    if status["status"] == "unhealthy":
                        health_status["status"] = "degraded"
                except Exception as e:
                    health_status["components"][service] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
                    health_status["status"] = "degraded"
            
            # Store health check result
            await self._store_health_check(health_status)
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            raise HealthCheckError("Failed to check system health")

    async def _get_system_metrics(self) -> Dict[str, Any]:
        """Get system performance metrics."""
        return {
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "active_connections": len(await self._get_active_connections()),
            "process_metrics": {
                "threads": psutil.Process().num_threads(),
                "memory": psutil.Process().memory_info().rss / 1024 / 1024
            }
        }

    async def _check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and performance."""
        try:
            db = await get_database()
            
            start_time = datetime.utcnow()
            await db.command('ping')
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return {
                "status": "healthy",
                "response_time_ms": response_time
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def _check_s3_health(self) -> Dict[str, Any]:
        """Check S3 service availability."""
        # Implementation for S3 health check
        pass

    async def _check_email_health(self) -> Dict[str, Any]:
        """Check email service status."""
        # Implementation for email service health check
        pass

    async def _check_websocket_health(self) -> Dict[str, Any]:
        """Check WebSocket service status."""
        # Implementation for WebSocket health check
        pass

    async def _store_health_check(
        self,
        health_status: Dict[str, Any]
    ) -> None:
        """Store health check results for monitoring."""
        try:
            db = await get_database()
            
            await db.healthChecks.insert_one({
                **health_status,
                "createdAt": datetime.utcnow()
            })
            
        except Exception as e:
            logger.error(f"Health check storage error: {str(e)}")

# Initialize health monitoring service
health_monitoring_service = HealthMonitoringService()